"""
AmneziaWG integration module.
Handles WireGuard key generation, peer management, and config generation.

LEGACY SOURCE: krot-prod-main/backend/amneziawg.py
PROTOCOL: AmneziaWG parameters MUST remain unchanged for compatibility.
"""
# <!-- GRACE: module="M-003" contract="amneziawg-integration" -->
# <!-- GRACE: legacy-source="krot-prod-main/backend/amneziawg.py" -->

import asyncio
import ipaddress
import re
from pathlib import Path
from typing import Optional, Tuple

import httpx
from loguru import logger

from app.core.config import settings
from app.core.security import decrypt_data, encrypt_data


class AmneziaWGManager:
    """
    Manager for AmneziaWG VPN operations.
    
    IMPORTANT: Obfuscation parameters (Jc, Jmin, Jmax, S1, S2, H1-H4)
    must match between server and client for successful connection.
    """
    
    def __init__(
        self,
        config_dir: str = "/etc/amnezia/amneziawg",
        interface: str = "awg0",
    ):
        self.config_dir = Path(config_dir)
        self.interface = interface
        self.server_config = self.config_dir / f"{self.interface}.conf"
        
        # Obfuscation parameters from settings (MUST match legacy)
        self.obfuscation = settings.awg_obfuscation_params
        
        logger.info(f"[VPN] AmneziaWGManager initialized with interface {interface}")
        logger.debug(f"[VPN] Obfuscation params: {self.obfuscation}")

    async def generate_keypair(self) -> Tuple[str, str]:
        """
        Generate a new WireGuard keypair.
        
        Returns:
            Tuple of (private_key, public_key)
        """
        try:
            # Generate private key
            private_proc = await asyncio.create_subprocess_exec(
                "awg", "genkey",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            private_stdout, private_stderr = await private_proc.communicate()
            if private_proc.returncode != 0:
                raise RuntimeError(private_stderr.decode().strip() or "awg genkey failed")

            private_key = private_stdout.decode().strip()
            
            # Derive public key
            public_proc = await asyncio.create_subprocess_exec(
                "awg", "pubkey",
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            public_stdout, public_stderr = await public_proc.communicate(private_key.encode())
            if public_proc.returncode != 0:
                raise RuntimeError(public_stderr.decode().strip() or "awg pubkey failed")

            public_key = public_stdout.decode().strip()
            
            logger.debug(f"[VPN] Generated keypair: public={public_key[:20]}...")
            return private_key, public_key
            
        except Exception as e:
            logger.error(f"[VPN] Error generating keypair: {e}")
            raise

    def get_server_public_key(self) -> Optional[str]:
        """
        Get server's public key from config directory.
        
        Returns:
            Server public key or None if not found.
        """
        try:
            key_file = self.config_dir / "vpn_pub"
            if key_file.exists():
                return key_file.read_text().strip()
        except Exception as e:
            logger.error(f"[VPN] Error reading server public key: {e}")
        return None

    async def get_server_endpoint(self) -> Optional[str]:
        """
        Get server's external IP address.
        
        Returns:
            External IP or None if detection fails.
        """
        endpoints = [
            "https://api.ipify.org",
            "https://ifconfig.me",
            "https://api4.my-ip.io/ip",
        ]
        
        async with httpx.AsyncClient(timeout=5.0) as client:
            for ep in endpoints:
                try:
                    response = await client.get(ep)
                    if response.status_code == 200:
                        return response.text.strip()
                except Exception:
                    continue
        
        logger.warning("[VPN] Could not detect external IP")
        return None

    def get_next_client_ip(self, used_ips: set[str]) -> str:
        """
        Get the next available IP address in the VPN subnet.
        
        Args:
            used_ips: Set of already used IP addresses
            
        Returns:
            Next available IP address
        """
        # Parse subnet from settings
        network = ipaddress.ip_network(settings.vpn_subnet, strict=False)
        
        # Start from .2 (skip network address and gateway)
        for ip in list(network.hosts())[1:]:
            if str(ip) not in used_ips:
                return str(ip)
        
        raise ValueError("No available IP addresses in VPN subnet")

    def create_client_config(
        self,
        private_key: str,
        address: str,
        server_public_key: str,
        endpoint: str,
    ) -> str:
        """
        Create a client configuration file content.
        
        Args:
            private_key: Client's private key
            address: Client's VPN IP address
            server_public_key: Server's public key
            endpoint: Server's endpoint (IP:port)
            
        Returns:
            Configuration file content as string
        """
        config = f"""[Interface]
PrivateKey = {private_key}
Address = {address}/32
DNS = {settings.vpn_dns}
MTU = {settings.vpn_mtu}
Jc = {self.obfuscation['jc']}
Jmin = {self.obfuscation['jmin']}
Jmax = {self.obfuscation['jmax']}
S1 = {self.obfuscation['s1']}
S2 = {self.obfuscation['s2']}
H1 = {self.obfuscation['h1']}
H2 = {self.obfuscation['h2']}
H3 = {self.obfuscation['h3']}
H4 = {self.obfuscation['h4']}

[Peer]
PublicKey = {server_public_key}
Endpoint = {endpoint}:{settings.vpn_port}
AllowedIPs = 0.0.0.0/0
PersistentKeepalive = 25
"""
        return config

    async def add_peer(self, public_key: str, address: str) -> bool:
        """
        Add a peer to the VPN server.
        
        Args:
            public_key: Client's public key
            address: Client's VPN IP address
            
        Returns:
            True if successful, False otherwise
        """
        try:
            # Add peer config to file
            peer_config = f"""

[Peer]
PublicKey = {public_key}
AllowedIPs = {address}/32
"""
            
            # Append to server config
            if self.server_config.exists():
                with open(self.server_config, "a") as f:
                    f.write(peer_config)
            else:
                raise FileNotFoundError(f"Server config not found: {self.server_config}")
            
            # Apply peer to running interface
            try:
                proc = await asyncio.create_subprocess_exec(
                    "awg", "set", self.interface,
                    "peer", public_key,
                    "allowed-ips", f"{address}/32",
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
                await asyncio.wait_for(proc.wait(), timeout=5)
                
                if proc.returncode != 0:
                    stderr = await proc.stderr.read() if proc.stderr else b""
                    logger.warning(
                        "[VPN] Failed to add peer dynamically, relying on host-managed sync: "
                        f"{stderr.decode().strip() or proc.returncode}"
                    )
                    
            except asyncio.TimeoutError:
                logger.warning("[VPN] Timeout adding peer dynamically, relying on host-managed sync")
            
            logger.info(f"[VPN] Added peer: {public_key[:20]}... -> {address}")
            return True
            
        except Exception as e:
            logger.error(f"[VPN] Error adding peer: {e}")
            return False

    async def remove_peer(self, public_key: str) -> bool:
        """
        Remove a peer from the VPN server.
        
        Args:
            public_key: Client's public key
            
        Returns:
            True if successful, False otherwise
        """
        try:
            # Remove from running interface
            proc = await asyncio.create_subprocess_exec(
                "awg", "set", self.interface,
                "peer", public_key, "remove",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            await proc.wait()
            
            # Remove from config file
            if self.server_config.exists():
                content = self.server_config.read_text()
                # Remove peer section
                pattern = rf'\n\[Peer\]\nPublicKey\s*=\s*{re.escape(public_key)}\nAllowedIPs\s*=\s*[^\n]+\n'
                new_content = re.sub(pattern, '', content)
                self.server_config.write_text(new_content)

            if proc.returncode != 0:
                stderr = await proc.stderr.read() if proc.stderr else b""
                logger.warning(
                    "[VPN] Failed to remove peer dynamically, relying on host-managed sync: "
                    f"{stderr.decode().strip() or proc.returncode}"
                )
            
            logger.info(f"[VPN] Removed peer: {public_key[:20]}...")
            return True
            
        except Exception as e:
            logger.error(f"[VPN] Error removing peer: {e}")
            return False

    async def get_peer_stats(self) -> dict:
        """
        Get statistics for all peers.
        
        Returns:
            Dict mapping public_key to stats dict
        """
        stats = {}
        
        try:
            proc = await asyncio.create_subprocess_exec(
                "awg", "show", self.interface, "dump",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, _ = await proc.communicate()
            
            if proc.returncode != 0:
                return stats
            
            # Parse dump output
            # Format: private-key public-key listen-port fwmark
            # For each peer: public-key preshared-key endpoint allowed-ips latest-handshake transfer-rx transfer-tx
            lines = stdout.decode().strip().split('\n')
            
            if len(lines) < 2:
                return stats
            
            # Skip first line (interface info)
            for line in lines[1:]:
                parts = line.split('\t')
                if len(parts) >= 8:
                    peer_key = parts[0]
                    handshake = int(parts[4]) if parts[4].isdigit() else 0
                    rx_bytes = int(parts[5]) if parts[5].isdigit() else 0
                    tx_bytes = int(parts[6]) if parts[6].isdigit() else 0
                    
                    from datetime import datetime, timezone
                    stats[peer_key] = {
                        "last_handshake": (
                            datetime.fromtimestamp(handshake, tz=timezone.utc)
                            if handshake > 0 else None
                        ),
                        "upload": tx_bytes,  # tx = sent by client = upload
                        "download": rx_bytes,  # rx = received by client = download
                    }
                    
        except Exception as e:
            logger.error(f"[VPN] Error getting peer stats: {e}")
        
        return stats

    async def is_service_running(self) -> bool:
        """Check if the VPN service is running."""
        try:
            proc = await asyncio.create_subprocess_exec(
                "systemctl", "is-active", f"awg-quick@{self.interface}",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, _ = await proc.communicate()
            return stdout.decode().strip() == "active"
        except Exception:
            return False

    async def restart_service(self) -> bool:
        """Restart the VPN service."""
        try:
            proc = await asyncio.create_subprocess_exec(
                "systemctl", "restart", f"awg-quick@{self.interface}",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            await proc.wait()
            logger.info(f"[VPN] Service restarted: {self.interface}")
            return proc.returncode == 0
        except Exception as e:
            logger.error(f"[VPN] Error restarting service: {e}")
            return False

    def update_obfuscation(self, params: dict) -> bool:
        """
        Update obfuscation parameters in server config.
        
        WARNING: This will require all clients to update their configs!
        
        Args:
            params: Dict with obfuscation parameters
            
        Returns:
            True if successful, False otherwise
        """
        if not self.server_config.exists():
            return False
        
        try:
            content = self.server_config.read_text()
            
            for key, val in params.items():
                # Capitalize key name (Jc, Jmin, Jmax, S1, S2, H1-H4)
                k = key.capitalize() if key.lower() not in ("jmin", "jmax") else key.capitalize()
                if key.lower() == "jmin":
                    k = "Jmin"
                elif key.lower() == "jmax":
                    k = "Jmax"
                
                content = re.sub(rf'{k}\s*=\s*\d+', f'{k} = {val}', content, flags=re.IGNORECASE)
                self.obfuscation[key] = int(val)
            
            self.server_config.write_text(content)
            logger.warning(f"[VPN] Obfuscation params updated: {params}")
            return True
            
        except Exception as e:
            logger.error(f"[VPN] Error updating obfuscation: {e}")
            return False


# Global instance
wg_manager = AmneziaWGManager()

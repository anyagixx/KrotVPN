"""
Routing manager for split-tunneling and custom routes.

LEGACY SOURCE: krot-prod-main/backend/routing.py
Handles iptables, ipset, and routing rules.

GRACE-lite module contract:
- Owns host-level split-tunneling behavior and route health inspection.
- This code assumes Linux host tools exist and may mutate live routing state.
- In production, some routing concerns are explicitly host-managed outside the FastAPI process.
- Changes here should be reviewed like infrastructure changes, not normal application logic.
"""
# <!-- GRACE: module="M-007" contract="routing-manager" -->
# <!-- GRACE: legacy-source="krot-prod-main/backend/routing.py" -->

import asyncio
import ipaddress
import socket
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from loguru import logger

from app.routing.domain_rules import RuleValidationError, normalize_domain_rule_input
from app.routing.models import CidrRouteRule, DomainMatchType, DomainRouteRule, RouteTarget
from app.routing.policy import DecisionReason, RouteDecision, RoutePolicyResolver


class RoutingManager:
    """
    Manager for split-tunneling and routing rules.
    
    Handles:
    - Russian IP set for direct routing
    - Custom routes (direct or VPN)
    - iptables rules
    - Routing tables
    """
    
    IPSET_RU = "ru_ips"
    IPSET_CUSTOM_DIRECT = "custom_direct"
    IPSET_CUSTOM_VPN = "custom_vpn"
    ROUTING_TABLE = 100
    FWMARK = 255
    
    def __init__(self):
        self.update_script = Path("/usr/local/bin/update_ru_ips.sh")
        self.scheduler = AsyncIOScheduler()
        self._initialized = False
    
    async def initialize(self) -> None:
        """Initialize routing manager and start scheduler."""
        if self._initialized:
            return
        
        # Schedule RU IPset update every 24 hours
        self.scheduler.add_job(
            self.update_ru_ipset,
            'interval',
            hours=24,
            id='update_ru_ipset',
        )
        self.scheduler.start()
        
        # Initial update
        await self.update_ru_ipset()
        
        self._initialized = True
        logger.info("[ROUTING] RoutingManager initialized")
    
    async def update_ru_ipset(self) -> bool:
        """
        Update Russian IP set from ipverse.
        
        Returns:
            True if successful, False otherwise
        """
        try:
            if self.update_script.exists():
                proc = await asyncio.create_subprocess_exec(
                    "bash", str(self.update_script),
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
                await proc.wait()
                
                if proc.returncode == 0:
                    logger.info("[ROUTING] RU IPset updated successfully")
                    return True
                else:
                    logger.error("[ROUTING] Failed to update RU IPset")
                    return False
            else:
                logger.warning("[ROUTING] Update script not found, creating...")
                await self._create_update_script()
                return await self.update_ru_ipset()
                
        except Exception as e:
            logger.error(f"[ROUTING] Error updating RU IPset: {e}")
            return False
    
    async def _create_update_script(self) -> None:
        """Create the RU IPset update script."""
        script_content = '''#!/bin/bash
# Update Russian IP set for split-tunneling

ipset create ru_ips hash:net 2>/dev/null || true
ipset flush ru_ips

# Add private networks
ipset add ru_ips 10.0.0.0/8 2>/dev/null || true
ipset add ru_ips 192.168.0.0/16 2>/dev/null || true
ipset add ru_ips 172.16.0.0/12 2>/dev/null || true

# Download and add Russian IPs
curl -sL https://raw.githubusercontent.com/ipverse/rir-ip/master/country/ru/ipv4-aggregated.txt | \\
    grep -v '^#' | grep -E '^[0-9]' | \\
    while read line; do
        ipset add ru_ips $line 2>/dev/null || true
    done

echo "RU IPset updated: $(ipset list ru_ips | grep 'Number of entries' | cut -d: -f2) entries"
'''
        
        # Create directory if needed
        self.update_script.parent.mkdir(parents=True, exist_ok=True)
        self.update_script.write_text(script_content)
        self.update_script.chmod(0o755)
        
        logger.info("[ROUTING] Created update script")
    
    async def get_ipset_stats(self) -> dict[str, Any]:
        """Get statistics for IP sets."""
        stats = {}
        
        for ipset_name in [self.IPSET_RU, self.IPSET_CUSTOM_DIRECT, self.IPSET_CUSTOM_VPN]:
            try:
                proc = await asyncio.create_subprocess_exec(
                    "ipset", "list", ipset_name,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
                stdout, _ = await proc.communicate()
                
                if proc.returncode == 0:
                    lines = stdout.decode().split('\n')
                    for line in lines:
                        if line.startswith("Number of entries:"):
                            count = int(line.split(':')[1].strip())
                            stats[ipset_name] = {"entries": count, "status": "active"}
                            break
                else:
                    stats[ipset_name] = {"entries": 0, "status": "inactive"}
                    
            except Exception as e:
                logger.error(f"[ROUTING] Error getting ipset stats: {e}")
                stats[ipset_name] = {"entries": 0, "status": "error"}
        
        return stats
    
    async def check_tunnel_status(self, tunnel_interface: str = "awg0") -> dict[str, str]:
        """
        Check VPN tunnel status.
        
        Args:
            tunnel_interface: Tunnel interface name
            
        Returns:
            Dict with interface and status
        """
        config_path = Path(f"/etc/amnezia/amneziawg/{tunnel_interface}.conf")

        def _config_is_host_managed() -> bool:
            try:
                return config_path.exists()
            except PermissionError:
                return True

        try:
            # Check if interface exists and is up
            proc = await asyncio.create_subprocess_exec(
                "ip", "link", "show", tunnel_interface,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, _ = await proc.communicate()
            
            if proc.returncode != 0:
                if _config_is_host_managed():
                    return {"interface": tunnel_interface, "status": "host_managed"}
                return {"interface": tunnel_interface, "status": "down"}
            
            if "UP" not in stdout.decode():
                return {"interface": tunnel_interface, "status": "down"}
            
            # Try to ping through tunnel
            proc = await asyncio.create_subprocess_exec(
                "ping", "-c", "1", "-W", "2", "-I", tunnel_interface, "8.8.8.8",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            await proc.wait()
            
            if proc.returncode == 0:
                return {"interface": tunnel_interface, "status": "up"}
            else:
                return {"interface": tunnel_interface, "status": "no_connectivity"}
                
        except FileNotFoundError:
            if _config_is_host_managed():
                return {"interface": tunnel_interface, "status": "host_managed"}
            return {"interface": tunnel_interface, "status": "down"}
        except Exception as e:
            logger.error(f"[ROUTING] Error checking tunnel status: {e}")
            if _config_is_host_managed():
                return {"interface": tunnel_interface, "status": "host_managed"}
            return {"interface": tunnel_interface, "status": "error"}

    async def is_ip_in_ru_ipset(self, ip: str) -> bool:
        """Check whether an IP belongs to the current RU ipset baseline."""
        try:
            normalized_ip = str(ipaddress.ip_address(ip))
        except ValueError:
            return False

        try:
            proc = await asyncio.create_subprocess_exec(
                "ipset", "test", self.IPSET_RU, normalized_ip,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            await proc.communicate()
            return proc.returncode == 0
        except FileNotFoundError:
            logger.warning("[ROUTING] ipset is not available; RU baseline check skipped")
            return False
        except Exception as e:
            logger.warning(f"[ROUTING] RU baseline ipset lookup failed for {ip}: {e}")
            return False

    async def resolve_effective_target(
        self,
        address: str,
        *,
        domain_rules: list[DomainRouteRule] | None = None,
        cidr_rules: list[CidrRouteRule] | None = None,
        custom_routes: list[dict[str, Any]] | None = None,
    ) -> RouteDecision:
        """Resolve the effective route target while preserving the legacy RU baseline."""
        stripped = address.strip()
        if not stripped:
            return RouteDecision(
                route_target=RouteTarget.DE,
                reason=DecisionReason.DEFAULT,
                trace_marker="ROUTE_DECISION_FALLBACK",
            )

        resolved_ip: str | None = None
        domain: str | None = None
        if self._is_ip_or_cidr(stripped):
            if "/" not in stripped:
                resolved_ip = stripped
        else:
            domain = stripped
            resolved_ip = await self._resolve_domain_to_ipv4(stripped)

        legacy_domain_rules, legacy_cidr_rules = self._build_legacy_policy_rules(custom_routes or [])
        resolver = RoutePolicyResolver(default_target=RouteTarget.DE)
        decision = resolver.resolve(
            domain=domain,
            resolved_ip=resolved_ip,
            domain_rules=[*(domain_rules or []), *legacy_domain_rules],
            cidr_rules=[*(cidr_rules or []), *legacy_cidr_rules],
        )
        if decision.reason is not DecisionReason.DEFAULT:
            return decision

        if resolved_ip is not None and await self.is_ip_in_ru_ipset(resolved_ip):
            return RouteDecision(
                route_target=RouteTarget.RU,
                reason=DecisionReason.RU_BASELINE,
                trace_marker="ROUTE_DECISION_RU_BASELINE",
                matched_domain=domain,
                normalized_domain=decision.normalized_domain,
                resolved_ip=resolved_ip,
            )

        return decision

    async def _resolve_domain_to_ipv4(self, domain: str) -> str | None:
        """Resolve a domain to one IPv4 address for policy compatibility checks."""
        try:
            results = await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: socket.getaddrinfo(domain, None, socket.AF_INET),
            )
        except Exception:
            return None

        for result in results:
            ip = result[4][0]
            if ip:
                return ip
        return None

    def _build_legacy_policy_rules(
        self,
        routes: list[dict[str, Any]],
    ) -> tuple[list[DomainRouteRule], list[CidrRouteRule]]:
        """Translate legacy custom routes into policy-rule equivalents."""
        domain_rules: list[DomainRouteRule] = []
        cidr_rules: list[CidrRouteRule] = []

        for index, route in enumerate(routes, start=1):
            address = str(route.get("address", "")).strip()
            if not address:
                continue

            route_target = self._legacy_route_target(str(route.get("route_type", "vpn")))
            priority = int(route.get("priority", 500))
            if self._is_ip_or_cidr(address):
                normalized_cidr = self._normalize_legacy_cidr(address)
                if normalized_cidr is None:
                    continue
                cidr_rules.append(
                    CidrRouteRule(
                        id=-index,
                        cidr=address,
                        normalized_cidr=normalized_cidr,
                        route_target=route_target,
                        priority=priority,
                    )
                )
                continue

            try:
                normalized = normalize_domain_rule_input(address)
            except RuleValidationError:
                continue

            domain_rules.append(
                DomainRouteRule(
                    id=-index,
                    domain=normalized.raw_domain,
                    normalized_domain=normalized.normalized_domain,
                    match_type=normalized.match_type,
                    route_target=route_target,
                    priority=priority,
                )
            )

        return domain_rules, cidr_rules

    def _legacy_route_target(self, route_type: str) -> RouteTarget:
        """Map legacy direct/vpn routes to policy route targets."""
        return RouteTarget.DIRECT if route_type == "direct" else RouteTarget.DE

    def _is_ip_or_cidr(self, value: str) -> bool:
        """Return True when a string is parseable as an IP or CIDR."""
        try:
            if "/" in value:
                ipaddress.ip_network(value, strict=False)
            else:
                ipaddress.ip_address(value)
            return True
        except ValueError:
            return False

    def _normalize_legacy_cidr(self, value: str) -> str | None:
        """Normalize a legacy IP or CIDR route for policy matching."""
        try:
            if "/" in value:
                return str(ipaddress.ip_network(value, strict=False))
            return f"{ipaddress.ip_address(value)}/32"
        except ValueError:
            return None
    
    async def setup_split_tunnel(
        self,
        client_interface: str = "awg-client",
        tunnel_interface: str = "awg0",
        bypass_ru: bool = True,
    ) -> bool:
        """
        Setup split-tunneling rules.
        
        Args:
            client_interface: Interface for VPN clients
            tunnel_interface: Interface for exit tunnel
            bypass_ru: Whether to bypass VPN for Russian IPs
            
        Returns:
            True if successful
        """
        try:
            # Create ipsets if not exist
            for ipset_name in [self.IPSET_RU, self.IPSET_CUSTOM_DIRECT, self.IPSET_CUSTOM_VPN]:
                proc = await asyncio.create_subprocess_exec(
                    "ipset", "create", ipset_name, "hash:net",
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
                await proc.wait()
            
            # Add private networks to RU ipset
            for network in ["10.0.0.0/8", "192.168.0.0/16", "172.16.0.0/12"]:
                proc = await asyncio.create_subprocess_exec(
                    "ipset", "add", self.IPSET_RU, network,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
                await proc.wait()
            
            # Setup routing table
            proc = await asyncio.create_subprocess_exec(
                "ip", "rule", "add", "fwmark", str(self.FWMARK),
                "lookup", str(self.ROUTING_TABLE),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            await proc.wait()
            
            proc = await asyncio.create_subprocess_exec(
                "ip", "route", "add", "default", "dev", tunnel_interface,
                "table", str(self.ROUTING_TABLE),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            await proc.wait()
            
            # Setup NAT
            proc = await asyncio.create_subprocess_exec(
                "iptables", "-t", "nat", "-A", "POSTROUTING",
                "-o", tunnel_interface, "-j", "MASQUERADE",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            await proc.wait()
            
            # Create custom mangle chain
            proc = await asyncio.create_subprocess_exec(
                "iptables", "-t", "mangle", "-N", "AMNEZIA_PREROUTING",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            await proc.wait()
            
            # Link chain to PREROUTING
            proc = await asyncio.create_subprocess_exec(
                "iptables", "-t", "mangle", "-C", "PREROUTING",
                "-i", client_interface, "-j", "AMNEZIA_PREROUTING",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            result = await proc.wait()
            
            if result != 0:
                proc = await asyncio.create_subprocess_exec(
                    "iptables", "-t", "mangle", "-A", "PREROUTING",
                    "-i", client_interface, "-j", "AMNEZIA_PREROUTING",
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
                await proc.wait()
            
            # Flush and rebuild rules
            proc = await asyncio.create_subprocess_exec(
                "iptables", "-t", "mangle", "-F", "AMNEZIA_PREROUTING",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            await proc.wait()
            
            # Custom VPN routes (mark for VPN)
            proc = await asyncio.create_subprocess_exec(
                "iptables", "-t", "mangle", "-A", "AMNEZIA_PREROUTING",
                "-m", "set", "--match-set", self.IPSET_CUSTOM_VPN, "dst",
                "-j", "MARK", "--set-mark", str(self.FWMARK),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            await proc.wait()
            
            proc = await asyncio.create_subprocess_exec(
                "iptables", "-t", "mangle", "-A", "AMNEZIA_PREROUTING",
                "-m", "set", "--match-set", self.IPSET_CUSTOM_VPN, "dst",
                "-j", "RETURN",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            await proc.wait()
            
            # Custom direct routes (bypass VPN)
            proc = await asyncio.create_subprocess_exec(
                "iptables", "-t", "mangle", "-A", "AMNEZIA_PREROUTING",
                "-m", "set", "--match-set", self.IPSET_CUSTOM_DIRECT, "dst",
                "-j", "RETURN",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            await proc.wait()
            
            # RU bypass
            if bypass_ru:
                proc = await asyncio.create_subprocess_exec(
                    "iptables", "-t", "mangle", "-A", "AMNEZIA_PREROUTING",
                    "-m", "set", "--match-set", self.IPSET_RU, "dst",
                    "-j", "RETURN",
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
                await proc.wait()
            
            # Default: mark for VPN
            proc = await asyncio.create_subprocess_exec(
                "iptables", "-t", "mangle", "-A", "AMNEZIA_PREROUTING",
                "-j", "MARK", "--set-mark", str(self.FWMARK),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            await proc.wait()
            
            logger.info("[ROUTING] Split-tunneling configured successfully")
            return True
            
        except Exception as e:
            logger.error(f"[ROUTING] Error setting up split-tunnel: {e}")
            return False
    
    async def sync_custom_routes(self, routes: list[dict[str, Any]]) -> None:
        """
        Sync custom routes from database to ipset.
        
        Args:
            routes: List of route dicts with 'address' and 'route_type'
        """
        # Flush custom ipsets
        for ipset_name in [self.IPSET_CUSTOM_DIRECT, self.IPSET_CUSTOM_VPN]:
            proc = await asyncio.create_subprocess_exec(
                "ipset", "flush", ipset_name,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            await proc.wait()
        
        # Add routes
        for route in routes:
            address = route.get("address", "").strip()
            route_type = route.get("route_type", "vpn")
            
            if not address:
                continue
            
            ipset_name = (
                self.IPSET_CUSTOM_DIRECT if route_type == "direct"
                else self.IPSET_CUSTOM_VPN
            )
            
            # Check if address is IP or domain
            is_ip = not any(c.isalpha() for c in address)
            
            ips_to_add = []
            if is_ip:
                ips_to_add.append(address)
            else:
                # Resolve domain
                try:
                    results = await asyncio.get_event_loop().run_in_executor(
                        None,
                        lambda: socket.getaddrinfo(address, None, socket.AF_INET)
                    )
                    ips_to_add = list(set(r[4][0] for r in results))
                except Exception as e:
                    logger.warning(f"[ROUTING] Could not resolve {address}: {e}")
                    continue
            
            for ip in ips_to_add:
                proc = await asyncio.create_subprocess_exec(
                    "ipset", "add", ipset_name, ip,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
                await proc.wait()
        
        logger.info(f"[ROUTING] Synced {len(routes)} custom routes")


# Global instance
routing_manager = RoutingManager()

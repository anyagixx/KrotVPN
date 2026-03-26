"""
VPN service for business logic.

GRACE-lite module contract:
- Owns VPN client provisioning, topology selection and config generation.
- New topology model is `VPNNode` + `VPNRoute`; `VPNServer` remains a legacy compatibility mirror.
- Invariant: one `VPNClient` per user, with topology fields preferred over legacy `server_id`.
- This module is host-coupled through AmneziaWG tools and should be treated as infrastructure-sensitive code.

CHANGE_SUMMARY
- 2026-03-26: Added internal-client provisioning helper and stable provisioning/config-render trace markers for manual CLI parity.
- 2026-03-27: Added device-scoped client lookup helpers so revoke or block policy can target peer state through the existing VPN service.
- 2026-03-27: Relaxed user-level lookup and added optional device-bound provisioning during the multi-device migration window.
"""
# <!-- GRACE: module="M-003" contract="vpn-service" -->

from datetime import datetime
from typing import Any

from loguru import logger
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.security import decrypt_data, encrypt_data
from app.routing.manager import routing_manager
from app.vpn.amneziawg import wg_manager
from app.vpn.models import (
    VPNClient,
    VPNConfig,
    VPNNode,
    VPNRoute,
    VPNServer,
    VPNStats,
)


class VPNService:
    """Service for VPN operations."""

    def __init__(self, session: AsyncSession):
        self.session = session
        self.wg = wg_manager

    async def get_server(self, server_id: int | None) -> VPNServer | None:
        """Get VPN server by ID."""
        if server_id is None:
            return None
        return await self.session.get(VPNServer, server_id)

    async def get_node(self, node_id: int | None) -> VPNNode | None:
        """Get VPN node by ID."""
        if node_id is None:
            return None
        return await self.session.get(VPNNode, node_id)

    async def get_route(self, route_id: int | None) -> VPNRoute | None:
        """Get VPN route by ID."""
        if route_id is None:
            return None
        return await self.session.get(VPNRoute, route_id)

    async def get_server_by_public_key(self, public_key: str) -> VPNServer | None:
        """Get legacy VPN server by public key."""
        result = await self.session.execute(
            select(VPNServer).where(VPNServer.public_key == public_key)
        )
        return result.scalar_one_or_none()

    async def get_active_server(self) -> VPNServer | None:
        """Get an active server for new clients."""
        result = await self.session.execute(
            select(VPNServer)
            .where(
                VPNServer.is_active == True,
                VPNServer.is_online == True,
                VPNServer.is_entry_node == True,
                VPNServer.current_clients < VPNServer.max_clients,
            )
            .order_by(VPNServer.current_clients.asc())
        )
        return result.scalar_one_or_none()

    async def get_active_entry_node(self) -> VPNNode | None:
        """Get an active entry node for route-less fallback."""
        result = await self.session.execute(
            select(VPNNode)
            .where(
                VPNNode.is_active == True,
                VPNNode.is_online == True,
                VPNNode.is_entry_node == True,
                VPNNode.current_clients < VPNNode.max_clients,
            )
            .order_by(VPNNode.current_clients.asc(), VPNNode.created_at.asc())
        )
        return result.scalar_one_or_none()

    async def get_default_route(self) -> VPNRoute | None:
        """Get the default active route for new clients."""
        result = await self.session.execute(
            select(VPNRoute)
            .where(
                VPNRoute.is_active == True,
                VPNRoute.is_default == True,
            )
            .order_by(VPNRoute.priority.asc(), VPNRoute.created_at.asc())
        )
        return result.scalar_one_or_none()

    async def get_active_route(self) -> VPNRoute | None:
        """Get the next active route when there is no explicit default."""
        route = await self.get_default_route()
        if route is not None:
            return route

        result = await self.session.execute(
            select(VPNRoute)
            .where(VPNRoute.is_active == True)
            .order_by(VPNRoute.priority.asc(), VPNRoute.created_at.asc())
        )
        return result.scalar_one_or_none()

    async def get_server_for_route(self, route: VPNRoute | None) -> VPNServer | None:
        """Resolve the legacy entry server used to provision a route."""
        if route is None:
            return None

        entry_node = await self.get_node(route.entry_node_id)
        return await self.get_legacy_server_for_node(entry_node, create=False)

    async def create_client(
        self,
        user_id: int,
        device_id: int | None = None,
        server_id: int | None = None,
    ) -> VPNClient:
        """
        Create a new VPN client for a user.
        
        Args:
            user_id: User ID
            device_id: Optional logical device ID for device-bound provisioning
            server_id: Optional specific server ID
            
        Returns:
            Created VPNClient
        """
        existing_client = (
            await self.get_device_client(device_id, active_only=False)
            if device_id is not None
            else await self.get_user_client(user_id, active_only=False)
        )
        route: VPNRoute | None = None
        entry_node: VPNNode | None = None
        exit_node: VPNNode | None = None

        # Get server
        if server_id:
            server = await self.get_server(server_id)
            if server is not None:
                route, entry_node, exit_node = await self._resolve_topology_for_server(server)
        elif existing_client is not None:
            route, entry_node, exit_node, server = await self._select_topology_for_existing_client(existing_client)
        else:
            route, entry_node, exit_node, server = await self._select_topology_for_new_client()

        if entry_node is None and server is not None:
            _, entry_node, exit_node = await self._resolve_topology_for_server(server)

        if entry_node is not None:
            server = await self.get_legacy_server_for_node(entry_node)

        if not server or entry_node is None:
            raise ValueError("No available VPN servers")

        if existing_client is not None:
            if existing_client.is_active:
                current_entry_node = await self.get_node(existing_client.entry_node_id)
                current_server = await self.get_server(existing_client.server_id)
                current_public_key = (
                    current_entry_node.public_key if current_entry_node is not None
                    else current_server.public_key if current_server is not None
                    else None
                )
                if server_id and current_public_key != entry_node.public_key:
                    raise ValueError("User already has an active VPN client on another server")
                await self._sync_client_topology(
                    existing_client,
                    route=route,
                    entry_node=entry_node,
                    exit_node=exit_node,
                )
                await self.session.flush()
                return existing_client

            current_entry_node = await self.get_node(existing_client.entry_node_id)
            current_server = await self.get_server(existing_client.server_id)
            current_public_key = (
                current_entry_node.public_key if current_entry_node is not None
                else current_server.public_key if current_server is not None
                else None
            )

            if current_public_key == entry_node.public_key:
                await self.activate_client(existing_client)
                await self._sync_client_topology(
                    existing_client,
                    route=route,
                    entry_node=entry_node,
                    exit_node=exit_node,
                )
                await self.session.refresh(existing_client)
                return existing_client

            reprovisioned = await self._reprovision_client(
                existing_client,
                server,
                route=route,
                entry_node=entry_node,
                exit_node=exit_node,
            )
            await self.session.refresh(reprovisioned)
            return reprovisioned

        client = await self._provision_new_client(
            user_id=user_id,
            device_id=device_id,
            server=server,
            route=route,
            entry_node=entry_node,
            exit_node=exit_node,
        )
        await self.session.refresh(client)
        return client

    async def get_client(self, client_id: int) -> VPNClient | None:
        """Get VPN client by ID."""
        return await self.session.get(VPNClient, client_id)

    async def get_user_client(self, user_id: int, active_only: bool = True) -> VPNClient | None:
        """Get one VPN client for a user for backward-compatible callers."""
        query = select(VPNClient).where(VPNClient.user_id == user_id)
        if active_only:
            query = query.where(VPNClient.is_active == True)

        result = await self.session.execute(query.order_by(VPNClient.created_at.asc(), VPNClient.id.asc()))
        return result.scalars().first()

    async def get_device_client(self, device_id: int, active_only: bool = True) -> VPNClient | None:
        """Get the VPN client currently bound to one logical device."""
        query = select(VPNClient).where(VPNClient.device_id == device_id)
        if active_only:
            query = query.where(VPNClient.is_active == True)
        result = await self.session.execute(query.order_by(VPNClient.created_at.asc(), VPNClient.id.asc()))
        return result.scalars().first()

    async def list_device_clients(
        self,
        device_id: int,
        *,
        active_only: bool = False,
    ) -> list[VPNClient]:
        """List VPN clients linked to one device."""
        query = select(VPNClient).where(VPNClient.device_id == device_id)
        if active_only:
            query = query.where(VPNClient.is_active == True)
        result = await self.session.execute(query.order_by(VPNClient.created_at.asc()))
        return list(result.scalars().all())

    async def deactivate_device_clients(self, device_id: int) -> int:
        """Deactivate every active VPN client bound to one device."""
        clients = await self.list_device_clients(device_id, active_only=True)
        for client in clients:
            await self.deactivate_client(client)
        return len(clients)

    async def provision_internal_client(
        self,
        user_id: int,
        *,
        reprovision: bool = False,
    ) -> VPNClient:
        """Create, reuse, or explicitly reprovision a client for the internal CLI path."""
        if not reprovision:
            return await self.create_client(user_id)

        existing = await self.get_user_client(user_id, active_only=False)
        if existing is None:
            return await self.create_client(user_id)

        route, entry_node, exit_node, server = await self._select_topology_for_existing_client(existing)
        if entry_node is None and server is not None:
            _, entry_node, exit_node = await self._resolve_topology_for_server(server)
        if entry_node is not None:
            server = await self.get_legacy_server_for_node(entry_node)
        if not server or entry_node is None:
            raise ValueError("No available VPN servers")

        if existing.is_active:
            await self.deactivate_client(existing)

        reprovisioned = await self._reprovision_client(
            existing,
            server,
            route=route,
            entry_node=entry_node,
            exit_node=exit_node,
        )
        await self.session.refresh(reprovisioned)
        return reprovisioned

    async def get_client_config(self, client: VPNClient) -> VPNConfig:
        """
        Generate VPN configuration for client.
        
        Args:
            client: VPNClient instance
            
        Returns:
            VPNConfig with configuration content
        """
        route = await self.get_route(client.route_id)
        entry_node = await self.get_node(client.entry_node_id)
        exit_node = await self.get_node(client.exit_node_id)
        server = await self.get_server(client.server_id)

        if entry_node is None and server is not None:
            _, entry_node, exit_node = await self._resolve_topology_for_server(server)
        if entry_node is None:
            raise ValueError("Entry node not found")

        # Decrypt private key
        private_key = decrypt_data(client.private_key_enc)
        
        # Get server endpoint from entry topology first.
        endpoint = entry_node.endpoint or (server.endpoint if server else None) or await self.wg.get_server_endpoint()
        if not endpoint:
            raise ValueError("Cannot determine server endpoint")
        
        # Generate config
        config_content = self.wg.create_client_config(
            private_key=private_key,
            address=client.address,
            server_public_key=entry_node.public_key if entry_node.public_key else (server.public_key if server else ""),
            endpoint=endpoint,
        )
        logger.info(
            "[VPN][config][VPN_CONFIG_RENDERED] "
            f"user_id={client.user_id} client_id={client.id} route_id={client.route_id} "
            f"entry_node_id={client.entry_node_id} resolved_endpoint={endpoint}"
        )
        
        return VPNConfig(
            config=config_content,
            server_name=entry_node.name,
            server_location=entry_node.location,
            route_name=route.name if route else None,
            entry_server_name=entry_node.name,
            entry_server_location=entry_node.location,
            exit_server_name=exit_node.name if exit_node else None,
            exit_server_location=exit_node.location if exit_node else None,
            address=client.address,
            public_key=client.public_key,
            created_at=client.created_at,
        )

    async def deactivate_client(self, client: VPNClient) -> None:
        """Deactivate a VPN client."""
        client.is_active = False
        await self.wg.remove_peer(client.public_key)
        
        # Update legacy and route-aware client counts.
        server = await self.get_server(client.server_id)
        if server and server.current_clients > 0:
            server.current_clients -= 1
        await self._apply_topology_client_delta(client, -1)
        
        await self.session.flush()

    async def activate_client(self, client: VPNClient) -> None:
        """Activate a VPN client."""
        client.is_active = True
        await self.wg.add_peer(client.public_key, client.address)
        
        # Update legacy and route-aware client counts.
        server = await self.get_server(client.server_id)
        if server and server.current_clients < server.max_clients:
            server.current_clients += 1
        await self._apply_topology_client_delta(client, 1)
        
        await self.session.flush()

    async def update_client_stats(self, client: VPNClient) -> None:
        """Update client traffic statistics."""
        stats = await self.wg.get_peer_stats()
        
        if client.public_key in stats:
            peer_stats = stats[client.public_key]
            client.total_upload_bytes = peer_stats["upload"]
            client.total_download_bytes = peer_stats["download"]
            client.last_handshake_at = peer_stats["last_handshake"]
            client.updated_at = datetime.utcnow()
            await self.session.flush()

    async def get_client_stats(self, client: VPNClient) -> VPNStats:
        """Get VPN client statistics."""
        await self.update_client_stats(client)
        
        entry_node = await self.get_node(client.entry_node_id)
        server = await self.get_server(client.server_id)
        if entry_node is None and server is not None:
            _, entry_node, _ = await self._resolve_topology_for_server(server)
        
        # Check if connected (handshake within last 3 minutes)
        is_connected = False
        if client.last_handshake_at:
            delta = datetime.utcnow() - client.last_handshake_at
            is_connected = delta.total_seconds() < 180
        
        return VPNStats(
            total_upload_bytes=client.total_upload_bytes,
            total_download_bytes=client.total_download_bytes,
            last_handshake_at=client.last_handshake_at,
            is_connected=is_connected,
            server_name=entry_node.name if entry_node else (server.name if server else "Unknown"),
            server_location=entry_node.location if entry_node else (server.location if server else "Unknown"),
        )

    async def list_nodes(self) -> list[VPNNode]:
        """List all VPN nodes."""
        result = await self.session.execute(
            select(VPNNode).order_by(VPNNode.created_at)
        )
        return list(result.scalars().all())

    async def list_routes(self) -> list[VPNRoute]:
        """List all VPN routes."""
        result = await self.session.execute(
            select(VPNRoute).order_by(VPNRoute.priority.asc(), VPNRoute.created_at.asc())
        )
        return list(result.scalars().all())

    async def get_node_statuses(self) -> list[dict[str, Any]]:
        """Get status of all VPN nodes."""
        nodes = await self.list_nodes()
        statuses: list[dict[str, Any]] = []

        for node in nodes:
            load = (node.current_clients / node.max_clients * 100) if node.max_clients > 0 else 0
            statuses.append(
                {
                    "id": node.id,
                    "name": node.name,
                    "role": node.role,
                    "country_code": node.country_code,
                    "location": node.location,
                    "endpoint": node.endpoint,
                    "port": node.port,
                    "public_key": node.public_key,
                    "is_active": node.is_active,
                    "is_online": node.is_online,
                    "is_entry_node": node.is_entry_node,
                    "is_exit_node": node.is_exit_node,
                    "current_clients": node.current_clients,
                    "max_clients": node.max_clients,
                    "load_percent": round(load, 1),
                }
            )

        return statuses

    async def get_route_statuses(self) -> list[dict[str, Any]]:
        """Get status of all VPN routes with resolved node names."""
        routes = await self.list_routes()
        statuses: list[dict[str, Any]] = []
        tunnel_health = await routing_manager.check_tunnel_status()

        for route in routes:
            entry_node = await self.get_node(route.entry_node_id)
            exit_node = await self.get_node(route.exit_node_id)
            load = (route.current_clients / route.max_clients * 100) if route.max_clients > 0 else 0
            tunnel_status = tunnel_health.get("status", "unknown") if exit_node is not None else "not_configured"
            statuses.append(
                {
                    "id": route.id,
                    "name": route.name,
                    "entry_node_id": route.entry_node_id,
                    "entry_node_name": entry_node.name if entry_node else "Unknown",
                    "entry_node_location": entry_node.location if entry_node else "Unknown",
                    "exit_node_id": route.exit_node_id,
                    "exit_node_name": exit_node.name if exit_node else None,
                    "exit_node_location": exit_node.location if exit_node else None,
                    "is_active": route.is_active,
                    "is_default": route.is_default,
                    "tunnel_interface": tunnel_health.get("interface") if exit_node is not None else None,
                    "tunnel_status": tunnel_status,
                    "priority": route.priority,
                    "current_clients": route.current_clients,
                    "max_clients": route.max_clients,
                    "load_percent": round(load, 1),
                }
            )

        return statuses

    async def create_node(
        self,
        *,
        name: str,
        role: str,
        country_code: str,
        location: str,
        endpoint: str,
        port: int = 51821,
        public_key: str,
        private_key: str | None = None,
        is_active: bool = True,
        is_online: bool = True,
        max_clients: int = 100,
    ) -> VPNNode:
        """Create a route-aware node and sync legacy entry-server record when needed."""
        normalized_role, is_entry_node, is_exit_node = self._normalize_node_role(role)
        existing = await self.session.execute(
            select(VPNNode).where(VPNNode.public_key == public_key)
        )
        if existing.scalar_one_or_none() is not None:
            raise ValueError("Node with this public key already exists")

        private_key_enc = encrypt_data(private_key) if private_key else None
        node = VPNNode(
            name=name,
            role=normalized_role,
            country_code=country_code.upper(),
            location=location,
            endpoint=endpoint,
            port=port,
            public_key=public_key,
            private_key_enc=private_key_enc,
            is_active=is_active,
            is_online=is_online,
            is_entry_node=is_entry_node,
            is_exit_node=is_exit_node,
            max_clients=max_clients,
        )
        self.session.add(node)
        await self.session.flush()

        await self._sync_legacy_server_for_node(node)
        await self.session.refresh(node)
        return node

    async def update_node(self, node: VPNNode, **changes: Any) -> VPNNode:
        """Update a route-aware node and keep the legacy entry layer in sync."""
        normalized_role = changes.get("role", node.role)
        normalized_role, is_entry_node, is_exit_node = self._normalize_node_role(normalized_role)

        public_key = changes.get("public_key", node.public_key)
        if public_key != node.public_key:
            existing = await self.session.execute(
                select(VPNNode).where(VPNNode.public_key == public_key, VPNNode.id != node.id)
            )
            if existing.scalar_one_or_none() is not None:
                raise ValueError("Node with this public key already exists")

        if "name" in changes:
            node.name = changes["name"]
        if "country_code" in changes:
            node.country_code = changes["country_code"].upper()
        if "location" in changes:
            node.location = changes["location"]
        if "endpoint" in changes:
            node.endpoint = changes["endpoint"]
        if "port" in changes:
            node.port = changes["port"]
        if "public_key" in changes:
            node.public_key = changes["public_key"]
        if "private_key" in changes:
            node.private_key_enc = encrypt_data(changes["private_key"]) if changes["private_key"] else None
        if "is_active" in changes:
            node.is_active = changes["is_active"]
        if "is_online" in changes:
            node.is_online = changes["is_online"]
        if "max_clients" in changes:
            node.max_clients = changes["max_clients"]

        node.role = normalized_role
        node.is_entry_node = is_entry_node
        node.is_exit_node = is_exit_node
        node.updated_at = datetime.utcnow()

        await self.session.flush()
        await self._sync_legacy_server_for_node(node)
        await self.session.refresh(node)
        return node

    async def delete_node(self, node: VPNNode) -> None:
        """Delete a node if it is not referenced by routes, clients, or active legacy entry state."""
        if await self._count_node_clients(node.id) > 0:
            raise ValueError("Cannot delete node with assigned clients")

        route_refs = await self.session.execute(
            select(func.count(VPNRoute.id)).where(
                (VPNRoute.entry_node_id == node.id) | (VPNRoute.exit_node_id == node.id)
            )
        )
        if int(route_refs.scalar() or 0) > 0:
            raise ValueError("Cannot delete node used by existing routes")

        legacy_server = await self.get_server_by_public_key(node.public_key)
        if legacy_server is not None:
            if legacy_server.current_clients > 0:
                raise ValueError("Cannot delete node while its legacy server has active clients")
            await self.session.delete(legacy_server)

        await self.session.delete(node)
        await self.session.flush()

    async def create_route(
        self,
        *,
        name: str,
        entry_node_id: int,
        exit_node_id: int | None = None,
        is_active: bool = True,
        is_default: bool = False,
        priority: int = 100,
        max_clients: int | None = None,
    ) -> VPNRoute:
        """Create a route between entry and optional exit nodes."""
        existing = await self.session.execute(
            select(VPNRoute).where(VPNRoute.name == name)
        )
        if existing.scalar_one_or_none() is not None:
            raise ValueError("Route with this name already exists")

        entry_node = await self.get_node(entry_node_id)
        if entry_node is None:
            raise ValueError("Entry node not found")
        if not entry_node.is_entry_node:
            raise ValueError("Selected entry node cannot accept client connections")

        exit_node = await self.get_node(exit_node_id)
        if exit_node_id is not None and exit_node is None:
            raise ValueError("Exit node not found")
        if exit_node is not None and not exit_node.is_exit_node:
            raise ValueError("Selected exit node is not marked as an exit node")

        route = VPNRoute(
            name=name,
            entry_node_id=entry_node_id,
            exit_node_id=exit_node_id,
            is_active=is_active,
            is_default=is_default,
            priority=priority,
            max_clients=max_clients or self._route_capacity(entry_node, exit_node),
            current_clients=0,
        )
        self.session.add(route)
        await self.session.flush()

        if is_default:
            await self._set_default_route(route)

        await self.session.refresh(route)
        return route

    async def update_route(self, route: VPNRoute, **changes: Any) -> VPNRoute:
        """Update route topology and enforce single default route semantics."""
        entry_node_id = changes.get("entry_node_id", route.entry_node_id)
        exit_node_id = changes.get("exit_node_id", route.exit_node_id)

        entry_node = await self.get_node(entry_node_id)
        if entry_node is None:
            raise ValueError("Entry node not found")
        if not entry_node.is_entry_node:
            raise ValueError("Selected entry node cannot accept client connections")

        exit_node = await self.get_node(exit_node_id)
        if exit_node_id is not None and exit_node is None:
            raise ValueError("Exit node not found")
        if exit_node is not None and not exit_node.is_exit_node:
            raise ValueError("Selected exit node is not marked as an exit node")

        if "name" in changes and changes["name"] != route.name:
            existing = await self.session.execute(
                select(VPNRoute).where(VPNRoute.name == changes["name"], VPNRoute.id != route.id)
            )
            if existing.scalar_one_or_none() is not None:
                raise ValueError("Route with this name already exists")
            route.name = changes["name"]

        route.entry_node_id = entry_node_id
        route.exit_node_id = exit_node_id
        if "is_active" in changes:
            route.is_active = changes["is_active"]
        if "priority" in changes:
            route.priority = changes["priority"]
        if "max_clients" in changes:
            route.max_clients = changes["max_clients"]
        elif "entry_node_id" in changes or "exit_node_id" in changes:
            route.max_clients = self._route_capacity(entry_node, exit_node)

        route.updated_at = datetime.utcnow()
        await self.session.flush()

        if changes.get("is_default") is True:
            await self._set_default_route(route)
        elif changes.get("is_default") is False:
            route.is_default = False
            await self.session.flush()

        await self.session.refresh(route)
        return route

    async def delete_route(self, route: VPNRoute) -> None:
        """Delete a route if no clients are assigned."""
        result = await self.session.execute(
            select(func.count(VPNClient.id)).where(VPNClient.route_id == route.id)
        )
        if int(result.scalar() or 0) > 0:
            raise ValueError("Cannot delete route with assigned clients")

        await self.session.delete(route)
        await self.session.flush()

    async def _count_node_clients(self, node_id: int | None) -> int:
        """Count client records assigned to a node."""
        if node_id is None:
            return 0

        result = await self.session.execute(
            select(func.count(VPNClient.id)).where(
                (VPNClient.entry_node_id == node_id) | (VPNClient.exit_node_id == node_id)
            )
        )
        return int(result.scalar() or 0)

    async def _set_default_route(self, route: VPNRoute) -> None:
        """Mark one route as default and clear the flag from the rest."""
        result = await self.session.execute(
            select(VPNRoute).where(VPNRoute.id != route.id, VPNRoute.is_default == True)
        )
        for other in result.scalars().all():
            other.is_default = False

        route.is_default = True
        await self.session.flush()

    async def _sync_legacy_server_for_node(self, node: VPNNode) -> None:
        """Mirror entry-capable nodes into the legacy vpn_servers table."""
        legacy_server = await self.get_server_by_public_key(node.public_key)
        if not node.is_entry_node:
            if legacy_server is not None and legacy_server.current_clients == 0:
                await self.session.delete(legacy_server)
                await self.session.flush()
            return

        if legacy_server is None:
            legacy_server = VPNServer(
                name=node.name,
                location=node.location,
                endpoint=node.endpoint,
                port=node.port,
                public_key=node.public_key,
                private_key_enc=node.private_key_enc,
                is_active=node.is_active,
                is_online=node.is_online,
                is_entry_node=True,
                is_exit_node=node.is_exit_node,
                max_clients=node.max_clients,
                current_clients=node.current_clients,
            )
            self.session.add(legacy_server)
            await self.session.flush()
            return

        legacy_server.name = node.name
        legacy_server.location = node.location
        legacy_server.endpoint = node.endpoint
        legacy_server.port = node.port
        legacy_server.public_key = node.public_key
        legacy_server.private_key_enc = node.private_key_enc
        legacy_server.is_active = node.is_active
        legacy_server.is_online = node.is_online
        legacy_server.is_entry_node = True
        legacy_server.is_exit_node = node.is_exit_node
        legacy_server.max_clients = node.max_clients
        legacy_server.updated_at = datetime.utcnow()
        await self.session.flush()

    async def list_legacy_servers(self) -> list[VPNServer]:
        """Compatibility helper for direct legacy server access."""
        result = await self.session.execute(
            select(VPNServer).order_by(VPNServer.created_at)
        )
        return list(result.scalars().all())

    async def set_legacy_server_online(self, server_id: int, is_online: bool) -> None:
        """Compatibility helper to update mirrored server online status."""
        server = await self.get_server(server_id)
        if server is not None:
            server.is_online = is_online
            server.last_ping_at = datetime.utcnow()
            await self.session.flush()

    def _normalize_node_role(self, role: str) -> tuple[str, bool, bool]:
        """Translate role string into normalized role and boolean flags."""
        normalized = (role or "entry").strip().lower()
        if normalized == "combined":
            return normalized, True, True
        if normalized == "exit":
            return normalized, False, True
        return "entry", True, False

    def _route_capacity(self, entry_node: VPNNode, exit_node: VPNNode | None) -> int:
        """Calculate effective route capacity from participating nodes."""
        if exit_node is None:
            return entry_node.max_clients
        return min(entry_node.max_clients, exit_node.max_clients)

    async def _select_server_for_existing_client(self, client: VPNClient) -> VPNServer | None:
        """Reuse the existing server when it is still suitable, otherwise pick a new active one."""
        current_server = await self.get_server(client.server_id)
        if (
            current_server
            and current_server.is_active
            and current_server.is_online
            and current_server.is_entry_node
            and (
                client.is_active
                or current_server.current_clients < current_server.max_clients
            )
        ):
            return current_server

        return await self.get_active_server()

    async def _select_topology_for_existing_client(
        self,
        client: VPNClient,
    ) -> tuple[VPNRoute | None, VPNNode | None, VPNNode | None, VPNServer | None]:
        """Prefer the client's assigned route, then fall back to route/default/legacy server logic."""
        route = await self.get_route(client.route_id)
        entry_node = await self.get_node(client.entry_node_id)
        exit_node = await self.get_node(client.exit_node_id)

        if route is not None:
            if entry_node is None:
                entry_node = await self.get_node(route.entry_node_id)
            if exit_node is None:
                exit_node = await self.get_node(route.exit_node_id)
            server = await self.get_server_for_route(route)
            if entry_node is not None:
                return route, entry_node, exit_node, server

        server = await self._select_server_for_existing_client(client)
        if server is None:
            return None, None, None, None

        fallback_route, fallback_entry, fallback_exit = await self._resolve_topology_for_server(server)
        return fallback_route, fallback_entry, fallback_exit, server

    async def _select_topology_for_new_client(
        self,
    ) -> tuple[VPNRoute | None, VPNNode | None, VPNNode | None, VPNServer | None]:
        """Pick route-aware topology first, then fall back to the legacy entry server pool."""
        route = await self.get_active_route()
        if route is not None:
            entry_node = await self.get_node(route.entry_node_id)
            exit_node = await self.get_node(route.exit_node_id)
            server = await self.get_server_for_route(route)
            if entry_node is not None:
                return route, entry_node, exit_node, server

        entry_node = await self.get_active_entry_node()
        if entry_node is None:
            return None, None, None, None

        server = await self.get_legacy_server_for_node(entry_node)
        route, entry_node, exit_node = await self._resolve_topology_for_server(server)
        return route, entry_node, exit_node, server

    async def _resolve_topology_for_server(
        self,
        server: VPNServer,
    ) -> tuple[VPNRoute | None, VPNNode | None, VPNNode | None]:
        """Derive route-aware metadata from a legacy server record."""
        result = await self.session.execute(
            select(VPNNode).where(VPNNode.public_key == server.public_key)
        )
        entry_node = result.scalar_one_or_none()
        if entry_node is None:
            return None, None, None

        result = await self.session.execute(
            select(VPNRoute)
            .where(VPNRoute.entry_node_id == entry_node.id)
            .order_by(VPNRoute.is_default.desc(), VPNRoute.priority.asc(), VPNRoute.created_at.asc())
        )
        route = result.scalars().first()
        exit_node = await self.get_node(route.exit_node_id) if route is not None else None
        return route, entry_node, exit_node

    async def _sync_client_topology(
        self,
        client: VPNClient,
        *,
        route: VPNRoute | None,
        entry_node: VPNNode | None,
        exit_node: VPNNode | None,
    ) -> None:
        """Persist route-aware metadata on the client without breaking legacy fields."""
        client.route_id = route.id if route is not None else None
        client.entry_node_id = entry_node.id if entry_node is not None else None
        client.exit_node_id = exit_node.id if exit_node is not None else None

    async def _get_used_ips(
        self,
        *,
        entry_node_id: int | None,
        server_id: int,
        exclude_client_id: int | None = None,
    ) -> set[str]:
        """Collect already allocated client IPs for a server."""
        if entry_node_id is not None:
            query = select(VPNClient.address).where(
                (VPNClient.entry_node_id == entry_node_id)
                | ((VPNClient.entry_node_id == None) & (VPNClient.server_id == server_id))
            )
        else:
            query = select(VPNClient.address).where(VPNClient.server_id == server_id)
        if exclude_client_id is not None:
            query = query.where(VPNClient.id != exclude_client_id)

        result = await self.session.execute(query)
        return {row[0] for row in result.fetchall()}

    async def _provision_new_client(
        self,
        user_id: int,
        device_id: int | None,
        server: VPNServer,
        *,
        route: VPNRoute | None = None,
        entry_node: VPNNode | None = None,
        exit_node: VPNNode | None = None,
    ) -> VPNClient:
        """Provision a fresh VPN client record."""
        if entry_node is None:
            raise ValueError("Entry node is required for provisioning")
        server = await self.get_legacy_server_for_node(entry_node)
        private_key, public_key = await self.wg.generate_keypair()
        used_ips = await self._get_used_ips(entry_node_id=entry_node.id, server_id=server.id)
        address = self.wg.get_next_client_ip(used_ips)
        private_key_enc = encrypt_data(private_key)

        client = VPNClient(
            user_id=user_id,
            device_id=device_id,
            server_id=server.id,
            route_id=route.id if route is not None else None,
            entry_node_id=entry_node.id if entry_node is not None else None,
            exit_node_id=exit_node.id if exit_node is not None else None,
            public_key=public_key,
            private_key_enc=private_key_enc,
            address=address,
            is_active=True,
        )
        self.session.add(client)

        await self.wg.add_peer(public_key, address)
        logger.info(
            "[VPN][peer][VPN_PEER_APPLIED] "
            f"user_id={user_id} client_id={client.id} address={address} "
            f"route_id={client.route_id} entry_node_id={client.entry_node_id} reprovision=false"
        )
        server.current_clients += 1
        await self._apply_topology_client_delta(client, 1)
        await self.session.flush()
        return client

    async def _reprovision_client(
        self,
        client: VPNClient,
        server: VPNServer,
        *,
        route: VPNRoute | None = None,
        entry_node: VPNNode | None = None,
        exit_node: VPNNode | None = None,
    ) -> VPNClient:
        """Reassign an inactive client record to a new server with fresh keys."""
        if entry_node is None:
            raise ValueError("Entry node is required for reprovisioning")
        previous_entry_node_id = client.entry_node_id
        previous_exit_node_id = client.exit_node_id
        previous_route_id = client.route_id
        server = await self.get_legacy_server_for_node(entry_node)
        private_key, public_key = await self.wg.generate_keypair()
        used_ips = await self._get_used_ips(
            entry_node_id=entry_node.id,
            server_id=server.id,
            exclude_client_id=int(client.id) if client.id is not None else None,
        )
        address = self.wg.get_next_client_ip(used_ips)

        client.server_id = server.id
        client.route_id = route.id if route is not None else None
        client.entry_node_id = entry_node.id if entry_node is not None else None
        client.exit_node_id = exit_node.id if exit_node is not None else None
        client.public_key = public_key
        client.private_key_enc = encrypt_data(private_key)
        client.address = address
        client.is_active = True
        client.total_upload_bytes = 0
        client.total_download_bytes = 0
        client.last_handshake_at = None
        client.updated_at = datetime.utcnow()

        await self.wg.add_peer(public_key, address)
        logger.info(
            "[VPN][peer][VPN_PEER_APPLIED] "
            f"user_id={client.user_id} client_id={client.id} address={address} "
            f"route_id={client.route_id} entry_node_id={client.entry_node_id} reprovision=true"
        )
        server.current_clients += 1
        await self._apply_topology_client_delta_by_ids(previous_route_id, previous_entry_node_id, previous_exit_node_id, -1)
        await self._apply_topology_client_delta(client, 1)
        await self.session.flush()
        return client

    async def _apply_topology_client_delta(self, client: VPNClient, delta: int) -> None:
        """Adjust node and route counters for a client assignment."""
        await self._apply_topology_client_delta_by_ids(
            client.route_id,
            client.entry_node_id,
            client.exit_node_id,
            delta,
        )

    async def _apply_topology_client_delta_by_ids(
        self,
        route_id: int | None,
        entry_node_id: int | None,
        exit_node_id: int | None,
        delta: int,
    ) -> None:
        """Adjust topology counters with floor-at-zero semantics."""
        route = await self.get_route(route_id)
        if route is not None:
            route.current_clients = max(0, route.current_clients + delta)

        entry_node = await self.get_node(entry_node_id)
        if entry_node is not None:
            entry_node.current_clients = max(0, entry_node.current_clients + delta)

        exit_node = await self.get_node(exit_node_id)
        if exit_node is not None:
            exit_node.current_clients = max(0, exit_node.current_clients + delta)

    async def get_legacy_server_for_node(
        self,
        node: VPNNode | None,
        *,
        create: bool = True,
    ) -> VPNServer | None:
        """Resolve or materialize the legacy server mirror for an entry-capable node."""
        if node is None:
            return None

        legacy_server = await self.get_server_by_public_key(node.public_key)
        if legacy_server is not None or not create:
            return legacy_server

        await self._sync_legacy_server_for_node(node)
        return await self.get_server_by_public_key(node.public_key)

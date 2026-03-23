"""
Bootstrap VPN server, node, and route records from environment configuration.
"""

from loguru import logger
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.vpn.models import VPNNode, VPNRoute, VPNServer


def _entry_server_config() -> dict[str, str | int | None]:
    """Resolve entry-node config with fallback to legacy VPN_SERVER_* settings."""
    return {
        "public_key": settings.vpn_entry_server_public_key or settings.vpn_server_public_key,
        "endpoint": settings.vpn_entry_server_endpoint or settings.vpn_server_endpoint,
        "name": settings.vpn_entry_server_name or settings.vpn_server_name,
        "location": settings.vpn_entry_server_location or settings.vpn_server_location,
        "country_code": settings.vpn_entry_server_country_code,
        "max_clients": settings.vpn_entry_server_max_clients or settings.vpn_server_max_clients,
    }


def _exit_server_config() -> dict[str, str | int | None]:
    """Resolve exit-node config from dedicated environment values."""
    return {
        "public_key": settings.vpn_exit_server_public_key,
        "endpoint": settings.vpn_exit_server_endpoint,
        "name": settings.vpn_exit_server_name,
        "location": settings.vpn_exit_server_location,
        "country_code": settings.vpn_exit_server_country_code,
        "max_clients": settings.vpn_exit_server_max_clients,
    }


async def ensure_default_vpn_server(session: AsyncSession) -> VPNServer | None:
    """Ensure the deprecated vpn_servers mirror exists for rollback compatibility."""
    entry = _entry_server_config()
    public_key = entry["public_key"]
    endpoint = entry["endpoint"]

    if not public_key or not endpoint:
        logger.info("[VPN] Default VPN server bootstrap skipped: env is incomplete")
        return None

    result = await session.execute(
        select(VPNServer).where(VPNServer.public_key == public_key)
    )
    server = result.scalar_one_or_none()

    if server:
        server.name = str(entry["name"])
        server.location = str(entry["location"])
        server.endpoint = str(endpoint)
        server.port = settings.vpn_port
        server.max_clients = int(entry["max_clients"])
        server.is_active = True
        server.is_online = True
        server.is_entry_node = True
        server.is_exit_node = False
        await session.flush()
        await session.refresh(server)
        logger.info(f"[VPN] Default VPN server synced: {server.name} ({server.endpoint})")
        return server

    server = VPNServer(
        name=str(entry["name"]),
        location=str(entry["location"]),
        endpoint=str(endpoint),
        port=settings.vpn_port,
        public_key=str(public_key),
        is_active=True,
        is_online=True,
        is_entry_node=True,
        is_exit_node=False,
        max_clients=int(entry["max_clients"]),
    )

    session.add(server)
    await session.flush()
    await session.refresh(server)
    logger.info(f"[VPN] Default VPN server created: {server.name} ({server.endpoint})")
    return server


async def ensure_default_vpn_topology(
    session: AsyncSession,
    legacy_server: VPNServer | None = None,
) -> VPNRoute | None:
    """Ensure the route-aware topology exists when entry/exit envs are available."""
    entry = _entry_server_config()
    exit_cfg = _exit_server_config()

    entry_node = await _upsert_node(
        session=session,
        public_key=(legacy_server.public_key if legacy_server else entry["public_key"]),
        endpoint=(legacy_server.endpoint if legacy_server else entry["endpoint"]),
        name=(legacy_server.name if legacy_server else entry["name"]),
        location=(legacy_server.location if legacy_server else entry["location"]),
        country_code=entry["country_code"],
        max_clients=(legacy_server.max_clients if legacy_server else entry["max_clients"]),
        is_entry_node=True,
        is_exit_node=False,
    )
    if entry_node is None:
        logger.info("[VPN] Route bootstrap skipped: entry node is incomplete")
        return None

    if not exit_cfg["public_key"] or not exit_cfg["endpoint"]:
        logger.info("[VPN] Route bootstrap skipped: exit node env is incomplete")
        return None

    exit_node = await _upsert_node(
        session=session,
        public_key=exit_cfg["public_key"],
        endpoint=exit_cfg["endpoint"],
        name=exit_cfg["name"],
        location=exit_cfg["location"],
        country_code=exit_cfg["country_code"],
        max_clients=exit_cfg["max_clients"],
        is_entry_node=False,
        is_exit_node=True,
    )
    if exit_node is None:
        return None

    result = await session.execute(
        select(VPNRoute).where(VPNRoute.name == settings.vpn_default_route_name)
    )
    route = result.scalar_one_or_none()

    if route:
        route.entry_node_id = int(entry_node.id)
        route.exit_node_id = int(exit_node.id)
        route.is_active = True
        route.is_default = True
        route.priority = 100
        route.max_clients = min(entry_node.max_clients, exit_node.max_clients)
        await session.flush()
        await session.refresh(route)
        logger.info(
            f"[VPN] Default route synced: {route.name} ({entry_node.name} -> {exit_node.name})"
        )
        return route

    route = VPNRoute(
        name=settings.vpn_default_route_name,
        entry_node_id=int(entry_node.id),
        exit_node_id=int(exit_node.id),
        is_active=True,
        is_default=True,
        priority=100,
        max_clients=min(entry_node.max_clients, exit_node.max_clients),
        current_clients=0,
    )
    session.add(route)
    await session.flush()
    await session.refresh(route)
    logger.info(
        f"[VPN] Default route created: {route.name} ({entry_node.name} -> {exit_node.name})"
    )
    return route


async def _upsert_node(
    session: AsyncSession,
    public_key: str | None,
    endpoint: str | None,
    name: str | int | None,
    location: str | int | None,
    country_code: str | int | None,
    max_clients: str | int | None,
    is_entry_node: bool,
    is_exit_node: bool,
) -> VPNNode | None:
    """Create or update a route-aware VPN node."""
    if not public_key or not endpoint:
        return None

    result = await session.execute(
        select(VPNNode).where(VPNNode.public_key == public_key)
    )
    node = result.scalar_one_or_none()
    role = _node_role(is_entry_node=is_entry_node, is_exit_node=is_exit_node)

    if node:
        node.name = str(name)
        node.location = str(location)
        node.country_code = str(country_code).upper()
        node.endpoint = str(endpoint)
        node.port = settings.vpn_port
        node.is_active = True
        node.is_online = True
        node.is_entry_node = is_entry_node
        node.is_exit_node = is_exit_node
        node.role = role
        node.max_clients = int(max_clients)
        await session.flush()
        await session.refresh(node)
        return node

    node = VPNNode(
        name=str(name),
        role=role,
        country_code=str(country_code).upper(),
        location=str(location),
        endpoint=str(endpoint),
        port=settings.vpn_port,
        public_key=str(public_key),
        is_active=True,
        is_online=True,
        is_entry_node=is_entry_node,
        is_exit_node=is_exit_node,
        max_clients=int(max_clients),
    )
    session.add(node)
    await session.flush()
    await session.refresh(node)
    return node


def _node_role(*, is_entry_node: bool, is_exit_node: bool) -> str:
    """Convert booleans to a stable node role string."""
    if is_entry_node and is_exit_node:
        return "combined"
    if is_exit_node:
        return "exit"
    return "entry"

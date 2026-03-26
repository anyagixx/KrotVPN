"""
VPN API router.

GRACE-lite module contract:
- User-facing source of truth for config delivery, QR delivery and client stats.
- Admin-facing compatibility endpoints still exist for legacy `/admin/servers` clients.
- Prefer node/route endpoints for new work; treat legacy server endpoints as compatibility shims.
"""
# <!-- GRACE: module="M-003" api-group="VPN API" -->

import io
from typing import Annotated

import qrcode
from fastapi import APIRouter, HTTPException, Query, status
from fastapi.responses import StreamingResponse

from app.core import CurrentAdmin, CurrentUser, DBSession
from app.billing.service import BillingService
from app.devices.models import DeviceStatus
from app.devices.service import DeviceAccessPolicyService, DeviceLimitExceededError
from app.vpn.models import VPNClient
from app.vpn.schemas import (
    NodeCreate,
    NodeListResponse,
    NodeStatusResponse,
    NodeUpdate,
    RouteCreate,
    RouteListResponse,
    RouteStatusResponse,
    RouteUpdate,
    ServerCreate,
    ServerListResponse,
    ServerStatusResponse,
    ServerUpdate,
    VPNConfigResponse,
    VPNStatsResponse,
)
from app.vpn.service import VPNService

router = APIRouter(prefix="/api/vpn", tags=["vpn"])
# Deprecated compatibility surface. New code should use /api/admin/nodes and /api/admin/routes.
admin_router = APIRouter(prefix="/api/admin/servers", tags=["admin"])
admin_nodes_router = APIRouter(prefix="/api/admin/nodes", tags=["admin"])
admin_routes_router = APIRouter(prefix="/api/admin/routes", tags=["admin"])


def format_bytes(bytes_count: int) -> str:
    """Format bytes to human readable string."""
    if bytes_count == 0:
        return "0 B"
    
    units = ["B", "KB", "MB", "GB", "TB"]
    k = 1024
    i = 0
    
    while bytes_count >= k and i < len(units) - 1:
        bytes_count /= k
        i += 1
    
    return f"{bytes_count:.1f} {units[i]}"


def legacy_server_status_from_node(node_status: dict) -> ServerStatusResponse:
    """Project a route-aware entry node into the legacy server response shape."""
    return ServerStatusResponse(
        id=node_status["id"],
        name=node_status["name"],
        location=node_status["location"],
        is_online=node_status["is_online"],
        current_clients=node_status["current_clients"],
        max_clients=node_status["max_clients"],
        load_percent=node_status["load_percent"],
    )


async def get_or_provision_user_client(
    user_id: int,
    session: DBSession,
) -> VPNClient | None:
    """Return existing VPN client or provision one for users with active access."""
    # This helper intentionally couples billing access and provisioning:
    # user-facing config endpoints should opportunistically self-heal missing VPN clients.
    service = VPNService(session)
    billing_service = BillingService(session)
    subscription = await billing_service.get_user_subscription(user_id)
    if not subscription:
        return None

    policy = DeviceAccessPolicyService(session)
    devices = await policy.list_user_devices(user_id)
    active_device = next((device for device in devices if device.status is DeviceStatus.ACTIVE), None)

    if active_device is not None:
        client = await service.get_device_client(int(active_device.id))
        if client is not None:
            return client
        try:
            return await service.provision_device_client(
                user_id,
                int(active_device.id),
                reprovision=False,
            )
        except ValueError:
            return None

    legacy_client = await service.get_user_client(user_id)
    if legacy_client is not None and legacy_client.device_id is None:
        return legacy_client

    try:
        primary_device = await policy.ensure_primary_device(
            user_id,
            name="Primary device",
            platform="web-default",
        )
        return await service.provision_device_client(
            user_id,
            int(primary_device.id),
            reprovision=False,
        )
    except (ValueError, DeviceLimitExceededError):
        return None


# ==================== User Endpoints ====================

@router.get("/config", response_model=VPNConfigResponse)
async def get_vpn_config(
    current_user: CurrentUser,
    session: DBSession,
):
    """Get VPN configuration for current user."""
    service = VPNService(session)
    
    client = await get_or_provision_user_client(current_user.id, session)
    if client is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="VPN client not found. Please activate your subscription first.",
        )
    
    if not client.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="VPN access is disabled",
        )
    
    config = await service.get_client_config(client)
    
    return VPNConfigResponse(
        config=config.config,
        server_name=config.server_name,
        server_location=config.server_location,
        route_name=config.route_name,
        entry_server_name=config.entry_server_name,
        entry_server_location=config.entry_server_location,
        exit_server_name=config.exit_server_name,
        exit_server_location=config.exit_server_location,
        address=config.address,
        created_at=config.created_at,
    )


@router.get("/config/download")
async def download_vpn_config(
    current_user: CurrentUser,
    session: DBSession,
):
    """Download VPN configuration as .conf file."""
    service = VPNService(session)
    
    client = await get_or_provision_user_client(current_user.id, session)
    if client is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="VPN client not found",
        )
    
    config = await service.get_client_config(client)
    
    return StreamingResponse(
        iter([config.config]),
        media_type="text/plain",
        headers={
            "Content-Disposition": f"attachment; filename=krotvpn-{current_user.id}.conf"
        },
    )


@router.get("/config/qr")
async def get_vpn_config_qr(
    current_user: CurrentUser,
    session: DBSession,
):
    """Get VPN configuration as QR code image."""
    service = VPNService(session)
    
    client = await get_or_provision_user_client(current_user.id, session)
    if client is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="VPN client not found",
        )
    
    config = await service.get_client_config(client)
    
    # Generate QR code
    qr = qrcode.QRCode(version=1, box_size=10, border=5)
    qr.add_data(config.config)
    qr.make(fit=True)
    
    img = qr.make_image(fill_color="black", back_color="white")
    
    # Return as PNG
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    
    return StreamingResponse(buf, media_type="image/png")


@router.get("/stats", response_model=VPNStatsResponse)
async def get_vpn_stats(
    current_user: CurrentUser,
    session: DBSession,
):
    """Get VPN usage statistics for current user."""
    service = VPNService(session)
    
    client = await get_or_provision_user_client(current_user.id, session)
    if client is None:
        return VPNStatsResponse(
            total_upload_bytes=0,
            total_download_bytes=0,
            total_upload_formatted="0 B",
            total_download_formatted="0 B",
            last_handshake_at=None,
            is_connected=False,
            server_name="None",
            server_location="None",
        )
    
    stats = await service.get_client_stats(client)
    
    return VPNStatsResponse(
        total_upload_bytes=stats.total_upload_bytes,
        total_download_bytes=stats.total_download_bytes,
        total_upload_formatted=format_bytes(stats.total_upload_bytes),
        total_download_formatted=format_bytes(stats.total_download_bytes),
        last_handshake_at=stats.last_handshake_at,
        is_connected=stats.is_connected,
        server_name=stats.server_name,
        server_location=stats.server_location,
    )


@router.get("/servers", response_model=ServerListResponse)
async def list_servers(
    current_user: CurrentUser,
    session: DBSession,
):
    """Deprecated compatibility endpoint. Prefer /api/vpn/nodes and /api/vpn/routes."""
    service = VPNService(session)
    statuses = await service.get_node_statuses()
    
    return ServerListResponse(
        servers=[
            legacy_server_status_from_node(status_data)
            for status_data in statuses
            if status_data["is_entry_node"]
        ]
    )


@router.get("/nodes", response_model=NodeListResponse)
async def list_nodes(
    current_user: CurrentUser,
    session: DBSession,
):
    """List public VPN nodes for authenticated users."""
    service = VPNService(session)
    statuses = await service.get_node_statuses()

    return NodeListResponse(
        nodes=[
            NodeStatusResponse(**status_data)
            for status_data in statuses
            if status_data["is_active"]
        ]
    )


@router.get("/routes", response_model=RouteListResponse)
async def list_routes(
    current_user: CurrentUser,
    session: DBSession,
):
    """List public VPN routes for authenticated users."""
    service = VPNService(session)
    statuses = await service.get_route_statuses()

    return RouteListResponse(
        routes=[
            RouteStatusResponse(**status_data)
            for status_data in statuses
            if status_data["is_active"] and status_data["exit_node_id"] is not None
        ]
    )


# ==================== Admin Endpoints ====================

@admin_router.get("", response_model=ServerListResponse)
async def admin_list_servers(
    admin: CurrentAdmin,
    session: DBSession,
):
    """Deprecated compatibility endpoint. Prefer /api/admin/nodes and /api/admin/routes."""
    service = VPNService(session)
    statuses = await service.get_node_statuses()
    
    return ServerListResponse(
        servers=[
            legacy_server_status_from_node(status_data)
            for status_data in statuses
            if status_data["is_entry_node"]
        ]
    )


@admin_router.post("", status_code=status.HTTP_201_CREATED)
async def create_server(
    data: ServerCreate,
    admin: CurrentAdmin,
    session: DBSession,
):
    """Deprecated compatibility endpoint. Creates a route-aware node under the hood."""
    service = VPNService(session)

    role = "combined" if data.is_entry_node and data.is_exit_node else "exit" if data.is_exit_node else "entry"
    try:
        node = await service.create_node(
            name=data.name,
            role=role,
            country_code="ZZ",
            location=data.location,
            endpoint=data.endpoint,
            port=data.port,
            public_key=data.public_key,
            private_key=data.private_key,
            is_active=True,
            is_online=True,
            max_clients=data.max_clients,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc

    return {"id": node.id, "status": "created", "compat": True}


@admin_router.get("/{server_id}", response_model=ServerStatusResponse)
async def get_server(
    server_id: int,
    admin: CurrentAdmin,
    session: DBSession,
):
    """Deprecated compatibility endpoint backed by the entry-node layer."""
    service = VPNService(session)
    node = await service.get_node(server_id)

    if node is None or not node.is_entry_node:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Server not found",
        )

    load = (node.current_clients / node.max_clients * 100) if node.max_clients > 0 else 0
    return ServerStatusResponse(
        id=node.id,
        name=node.name,
        location=node.location,
        is_online=node.is_online,
        current_clients=node.current_clients,
        max_clients=node.max_clients,
        load_percent=round(load, 1),
    )


@admin_router.put("/{server_id}")
async def update_server(
    server_id: int,
    data: ServerUpdate,
    admin: CurrentAdmin,
    session: DBSession,
):
    """Deprecated compatibility endpoint backed by node updates."""
    service = VPNService(session)
    node = await service.get_node(server_id)

    if node is None or not node.is_entry_node:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Server not found",
        )

    update_data = data.model_dump(exclude_unset=True)
    node_payload = {
        "name": update_data.get("name"),
        "location": update_data.get("location"),
        "endpoint": update_data.get("endpoint"),
        "is_active": update_data.get("is_active"),
        "max_clients": update_data.get("max_clients"),
    }
    node_payload = {key: value for key, value in node_payload.items() if value is not None}

    try:
        await service.update_node(node, **node_payload)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc

    return {"status": "updated", "compat": True}


@admin_router.delete("/{server_id}")
async def delete_server(
    server_id: int,
    admin: CurrentAdmin,
    session: DBSession,
):
    """Deprecated compatibility endpoint backed by node deletion."""
    service = VPNService(session)
    node = await service.get_node(server_id)

    if node is None or not node.is_entry_node:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Server not found",
        )

    try:
        await service.delete_node(node)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc

    return {"status": "deleted", "compat": True}


@admin_nodes_router.get("", response_model=NodeListResponse)
async def admin_list_nodes(
    admin: CurrentAdmin,
    session: DBSession,
):
    """List all VPN nodes (admin)."""
    service = VPNService(session)
    statuses = await service.get_node_statuses()

    return NodeListResponse(
        nodes=[
            NodeStatusResponse(**status_data)
            for status_data in statuses
        ]
    )


@admin_nodes_router.post("", status_code=status.HTTP_201_CREATED)
async def create_node(
    data: NodeCreate,
    admin: CurrentAdmin,
    session: DBSession,
):
    """Create a route-aware VPN node."""
    service = VPNService(session)

    try:
        node = await service.create_node(**data.model_dump())
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc

    return {"id": node.id, "status": "created"}


@admin_nodes_router.get("/{node_id}", response_model=NodeStatusResponse)
async def get_node(
    node_id: int,
    admin: CurrentAdmin,
    session: DBSession,
):
    """Get node details."""
    service = VPNService(session)
    node = await service.get_node(node_id)

    if node is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Node not found",
        )

    load = (node.current_clients / node.max_clients * 100) if node.max_clients > 0 else 0
    return NodeStatusResponse(
        id=node.id,
        name=node.name,
        role=node.role,
        country_code=node.country_code,
        location=node.location,
        endpoint=node.endpoint,
        port=node.port,
        public_key=node.public_key,
        is_active=node.is_active,
        is_online=node.is_online,
        is_entry_node=node.is_entry_node,
        is_exit_node=node.is_exit_node,
        current_clients=node.current_clients,
        max_clients=node.max_clients,
        load_percent=round(load, 1),
    )


@admin_nodes_router.put("/{node_id}")
async def update_node(
    node_id: int,
    data: NodeUpdate,
    admin: CurrentAdmin,
    session: DBSession,
):
    """Update a route-aware VPN node."""
    service = VPNService(session)
    node = await service.get_node(node_id)

    if node is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Node not found",
        )

    try:
        await service.update_node(node, **data.model_dump(exclude_unset=True))
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc

    return {"status": "updated"}


@admin_nodes_router.delete("/{node_id}")
async def delete_node(
    node_id: int,
    admin: CurrentAdmin,
    session: DBSession,
):
    """Delete a route-aware VPN node."""
    service = VPNService(session)
    node = await service.get_node(node_id)

    if node is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Node not found",
        )

    try:
        await service.delete_node(node)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc

    return {"status": "deleted"}


@admin_routes_router.get("", response_model=RouteListResponse)
async def admin_list_routes(
    admin: CurrentAdmin,
    session: DBSession,
):
    """List all VPN routes (admin)."""
    service = VPNService(session)
    statuses = await service.get_route_statuses()

    return RouteListResponse(
        routes=[
            RouteStatusResponse(**status_data)
            for status_data in statuses
        ]
    )


@admin_routes_router.post("", status_code=status.HTTP_201_CREATED)
async def create_route(
    data: RouteCreate,
    admin: CurrentAdmin,
    session: DBSession,
):
    """Create a VPN route."""
    service = VPNService(session)

    try:
        route = await service.create_route(**data.model_dump())
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc

    return {"id": route.id, "status": "created"}


@admin_routes_router.get("/{route_id}", response_model=RouteStatusResponse)
async def get_route(
    route_id: int,
    admin: CurrentAdmin,
    session: DBSession,
):
    """Get route details."""
    service = VPNService(session)
    route = await service.get_route(route_id)

    if route is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Route not found",
        )

    statuses = await service.get_route_statuses()
    status_data = next((item for item in statuses if item["id"] == route_id), None)
    if status_data is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Route not found",
        )
    return RouteStatusResponse(**status_data)


@admin_routes_router.put("/{route_id}")
async def update_route(
    route_id: int,
    data: RouteUpdate,
    admin: CurrentAdmin,
    session: DBSession,
):
    """Update a VPN route."""
    service = VPNService(session)
    route = await service.get_route(route_id)

    if route is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Route not found",
        )

    try:
        await service.update_route(route, **data.model_dump(exclude_unset=True))
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc

    return {"status": "updated"}


@admin_routes_router.delete("/{route_id}")
async def delete_route(
    route_id: int,
    admin: CurrentAdmin,
    session: DBSession,
):
    """Delete a VPN route."""
    service = VPNService(session)
    route = await service.get_route(route_id)

    if route is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Route not found",
        )

    try:
        await service.delete_route(route)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc

    return {"status": "deleted"}

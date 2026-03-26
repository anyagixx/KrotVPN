"""
User device management API.

MODULE_CONTRACT
- PURPOSE: Expose authenticated user APIs for listing devices, provisioning device-bound configs, revoking devices and rotating one device config.
- SCOPE: Current-user device registry operations only; admin enforcement stays outside this router.
- DEPENDS: M-001 auth/session dependencies, M-003 vpn provisioning and config rendering, M-021 device-access-policy, M-022 device-provisioning-api.
- LINKS: V-M-022.

MODULE_MAP
- list_devices: Returns the current user's tracked devices and slot counters.
- create_device: Creates one device, provisions one device-bound VPN peer and returns the rendered config.
- revoke_device: Revokes one device owned by the current user.
- rotate_device_config: Rotates one device config through device-bound reprovisioning and returns a fresh config.

CHANGE_SUMMARY
- 2026-03-27: Added first user-facing device management API for list/create/revoke/rotate flows.
"""
# <!-- GRACE: module="M-022" api-group="User Device API" -->

from fastapi import APIRouter, HTTPException, status

from app.core import CurrentUser, DBSession
from app.devices.models import UserDevice
from app.devices.schemas import (
    DeviceConfigBundleResponse,
    DeviceCreateRequest,
    DeviceListResponse,
    DeviceResponse,
)
from app.devices.service import DeviceAccessPolicyService, DeviceLimitExceededError
from app.vpn.service import VPNService

router = APIRouter(prefix="/api/devices", tags=["devices"])


def _serialize_device(device: UserDevice) -> DeviceResponse:
    """Convert one device row into the public API shape."""
    return DeviceResponse(
        id=int(device.id),
        device_key=device.device_key,
        name=device.name,
        platform=device.platform,
        status=device.status.value,
        config_version=device.config_version,
        created_at=device.created_at,
        updated_at=device.updated_at,
        revoked_at=device.revoked_at,
        blocked_at=device.blocked_at,
        last_seen_at=device.last_seen_at,
        last_handshake_at=device.last_handshake_at,
        last_endpoint=device.last_endpoint,
        block_reason=device.block_reason,
    )


async def _get_user_device_or_404(
    policy: DeviceAccessPolicyService,
    *,
    user_id: int,
    device_id: int,
) -> UserDevice:
    """Load one device and enforce current-user ownership."""
    device = await policy.get_user_device(user_id, device_id)
    if device is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Device not found",
        )
    return device


@router.get("", response_model=DeviceListResponse)
async def list_devices(
    current_user: CurrentUser,
    session: DBSession,
):
    """Return the current user's devices and slot counters."""
    policy = DeviceAccessPolicyService(session)
    devices = await policy.list_user_devices(int(current_user.id))
    consumed_slots = await policy.get_consumed_device_count(int(current_user.id))
    device_limit = await policy.get_effective_device_limit(int(current_user.id))
    return DeviceListResponse(
        devices=[_serialize_device(device) for device in devices],
        consumed_slots=consumed_slots,
        device_limit=device_limit,
    )


@router.post("", response_model=DeviceConfigBundleResponse, status_code=status.HTTP_201_CREATED)
async def create_device(
    payload: DeviceCreateRequest,
    current_user: CurrentUser,
    session: DBSession,
):
    """Create one new logical device and provision its device-bound config."""
    policy = DeviceAccessPolicyService(session)
    vpn = VPNService(session)
    try:
        device = await policy.create_device_record(
            int(current_user.id),
            name=payload.name,
            platform=payload.platform,
        )
    except DeviceLimitExceededError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc

    client = await vpn.create_client(int(current_user.id), device_id=int(device.id))
    config = await vpn.get_client_config(client)
    return DeviceConfigBundleResponse(
        device=_serialize_device(device),
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


@router.delete("/{device_id}", response_model=DeviceResponse)
async def revoke_device(
    device_id: int,
    current_user: CurrentUser,
    session: DBSession,
):
    """Revoke one device and free its slot."""
    policy = DeviceAccessPolicyService(session)
    device = await _get_user_device_or_404(policy, user_id=int(current_user.id), device_id=device_id)
    updated = await policy.revoke_device(device)
    return _serialize_device(updated)


@router.post("/{device_id}/rotate", response_model=DeviceConfigBundleResponse)
async def rotate_device_config(
    device_id: int,
    current_user: CurrentUser,
    session: DBSession,
):
    """Rotate one device config and return the fresh rendered config bundle."""
    policy = DeviceAccessPolicyService(session)
    vpn = VPNService(session)
    device = await _get_user_device_or_404(policy, user_id=int(current_user.id), device_id=device_id)
    if device.status.value != "active":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Only active devices can rotate config",
        )

    updated = await policy.rotate_device_config(device)
    client = await vpn.provision_device_client(
        int(current_user.id),
        int(updated.id),
        reprovision=True,
    )
    config = await vpn.get_client_config(client)
    return DeviceConfigBundleResponse(
        device=_serialize_device(updated),
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

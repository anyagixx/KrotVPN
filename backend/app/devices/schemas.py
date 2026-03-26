"""
Device API schemas.

MODULE_CONTRACT
- PURPOSE: Define request/response shapes for user-facing device management and config delivery.
- SCOPE: Device list, device create, revoke, rotate, and bundled config response payloads.
- DEPENDS: M-003 vpn config response shape, M-020 device-registry, M-022 device-provisioning-api.
- LINKS: V-M-022.

MODULE_MAP
- DeviceResponse: Public shape for one logical user device.
- DeviceConfigBundleResponse: Device metadata plus rendered VPN config.
- DeviceListResponse: Device list plus effective limit counters.
- DeviceCreateRequest: Request payload for creating a new logical device.

CHANGE_SUMMARY
- 2026-03-27: Added user-facing device management schemas for device-bound provisioning and config lifecycle operations.
"""
# <!-- GRACE: module="M-022" contract="device-api-schemas" -->

from datetime import datetime

from pydantic import Field
from sqlmodel import SQLModel


class DeviceResponse(SQLModel):
    """Public representation of one logical user device."""

    id: int
    device_key: str
    name: str
    platform: str | None = None
    status: str
    config_version: int
    created_at: datetime
    updated_at: datetime
    revoked_at: datetime | None = None
    blocked_at: datetime | None = None
    last_seen_at: datetime | None = None
    last_handshake_at: datetime | None = None
    last_endpoint: str | None = None
    block_reason: str | None = None


class DeviceConfigBundleResponse(SQLModel):
    """Device metadata bundled with a rendered VPN config."""

    device: DeviceResponse
    config: str
    server_name: str
    server_location: str
    route_name: str | None = None
    entry_server_name: str | None = None
    entry_server_location: str | None = None
    exit_server_name: str | None = None
    exit_server_location: str | None = None
    address: str
    created_at: datetime


class DeviceListResponse(SQLModel):
    """List of user devices with the current slot usage."""

    devices: list[DeviceResponse]
    consumed_slots: int
    device_limit: int


class DeviceCreateRequest(SQLModel):
    """Request payload for creating a new device."""

    name: str = Field(..., min_length=1, max_length=100)
    platform: str | None = Field(default=None, max_length=50)

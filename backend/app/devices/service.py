"""
Device access policy service.

MODULE_CONTRACT
- PURPOSE: Enforce device-slot policy from subscriptions, and coordinate revoke, rotate and block actions for device-bound access.
- SCOPE: Effective device-limit resolution, active-slot accounting, device creation guards, lifecycle transitions and audit-event writes.
- DEPENDS: M-001 DB session lifecycle, M-003 VPN service peer control, M-004 billing plan and subscription state, M-020 device-registry, M-021 device-access-policy, M-025 device-audit-log.
- LINKS: M-020 device-registry, M-021 device-access-policy, M-025 device-audit-log, V-M-021.

MODULE_MAP
- DeviceLimitExceededError: Raised when provisioning would exceed the effective device limit.
- DeviceAccessPolicyService: Coordinates per-user device slots and device lifecycle transitions.
- get_user_device: Resolves one owned device for authenticated API flows.
- get_effective_device_limit: Resolves the current device limit from active billing state.
- assert_can_create_device: Rejects provisioning before peer creation if the user has no available device slot.
- create_device_record: Persists a new active device and records an audit event.
- revoke_device: Revokes one device, deactivates its active peers and frees the slot.
- rotate_device_config: Increments config version for one logical device and records a rotation event without creating a new device identity.
- block_device: Blocks one device, deactivates active peers and records the enforcement action.
- unblock_device: Removes the blocked state without silently reactivating the old peer.

CHANGE_SUMMARY
- 2026-03-27: Added first-pass device access policy for per-plan limits and device lifecycle enforcement.
"""
# <!-- GRACE: module="M-021" contract="device-access-policy" -->

from __future__ import annotations

from datetime import datetime

from loguru import logger
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.billing.service import BillingService
from app.devices.models import (
    DeviceEventSeverity,
    DeviceSecurityEvent,
    DeviceSecurityEventType,
    DeviceStatus,
    UserDevice,
)
from app.vpn.service import VPNService


class DeviceLimitExceededError(ValueError):
    """Raised when a user has exhausted their effective device slots."""


class DeviceAccessPolicyService:
    """Policy service for device-bound access limits and lifecycle transitions."""

    def __init__(self, session: AsyncSession):
        self.session = session
        self.billing = BillingService(session)
        self.vpn = VPNService(session)

    async def list_user_devices(self, user_id: int) -> list[UserDevice]:
        """Return all devices for one user ordered by creation time."""
        result = await self.session.execute(
            select(UserDevice)
            .where(UserDevice.user_id == user_id)
            .order_by(UserDevice.created_at.asc(), UserDevice.id.asc())
        )
        return list(result.scalars().all())

    async def get_user_device(self, user_id: int, device_id: int) -> UserDevice | None:
        """Return one device only if it belongs to the requested user."""
        result = await self.session.execute(
            select(UserDevice).where(
                UserDevice.id == device_id,
                UserDevice.user_id == user_id,
            )
        )
        return result.scalar_one_or_none()

    async def get_consumed_device_count(self, user_id: int) -> int:
        """Return the number of slots currently consumed by active or blocked devices."""
        result = await self.session.execute(
            select(UserDevice)
            .where(
                UserDevice.user_id == user_id,
                UserDevice.status.in_([DeviceStatus.ACTIVE, DeviceStatus.BLOCKED]),
            )
        )
        return len(list(result.scalars().all()))

    async def get_effective_device_limit(self, user_id: int) -> int:
        """Resolve the effective device limit from active billing state."""
        return await self.billing.get_effective_device_limit(user_id)

    async def assert_can_create_device(self, user_id: int) -> None:
        """Reject device creation before any peer provisioning if the limit is exhausted."""
        consumed = await self.get_consumed_device_count(user_id)
        limit = await self.get_effective_device_limit(user_id)
        logger.info(
            "[VPN][device][VPN_DEVICE_CREATE_REQUESTED] "
            f"user_id={user_id} consumed_slots={consumed} device_limit={limit}"
        )
        if limit <= 0 or consumed >= limit:
            logger.warning(
                "[VPN][device][VPN_DEVICE_LIMIT_REJECTED] "
                f"user_id={user_id} consumed_slots={consumed} device_limit={limit}"
            )
            raise DeviceLimitExceededError("Device limit exceeded")

    async def create_device_record(
        self,
        user_id: int,
        *,
        name: str,
        platform: str | None = None,
    ) -> UserDevice:
        """Create a new active device after enforcing slot policy."""
        await self.assert_can_create_device(user_id)
        device = UserDevice(
            user_id=user_id,
            name=name.strip() or "New device",
            platform=platform,
            status=DeviceStatus.ACTIVE,
        )
        self.session.add(device)
        await self.session.flush()
        await self._record_event(
            user_id=user_id,
            device_id=int(device.id),
            event_type=DeviceSecurityEventType.DEVICE_CREATED,
            severity=DeviceEventSeverity.INFO,
            details_json='{"source":"device_access_policy"}',
        )
        logger.info(
            "[VPN][device][VPN_DEVICE_CREATED] "
            f"user_id={user_id} device_id={device.id} device_key={device.device_key} status={device.status.value}"
        )
        await self.session.refresh(device)
        return device

    async def revoke_device(self, device: UserDevice, *, reason: str = "user_request") -> UserDevice:
        """Revoke one device and deactivate any active peer bound to it."""
        if device.status is not DeviceStatus.REVOKED:
            await self.vpn.deactivate_device_clients(int(device.id))
            now = datetime.utcnow()
            device.status = DeviceStatus.REVOKED
            device.revoked_at = now
            device.updated_at = now
            device.block_reason = reason
            await self._record_event(
                user_id=int(device.user_id),
                device_id=int(device.id),
                event_type=DeviceSecurityEventType.DEVICE_REVOKED,
                severity=DeviceEventSeverity.INFO,
                details_json=f'{{"reason":"{reason}"}}',
            )
            logger.info(
                "[VPN][device][VPN_DEVICE_REVOKED] "
                f"user_id={device.user_id} device_id={device.id} reason={reason}"
            )
            await self.session.flush()
        return device

    async def rotate_device_config(self, device: UserDevice, *, reason: str = "user_rotate") -> UserDevice:
        """Mark a device config rotation without changing the logical device identity."""
        device.config_version += 1
        device.updated_at = datetime.utcnow()
        await self._record_event(
            user_id=int(device.user_id),
            device_id=int(device.id),
            event_type=DeviceSecurityEventType.CONFIG_ROTATED,
            severity=DeviceEventSeverity.INFO,
            details_json=f'{{"reason":"{reason}","config_version":{device.config_version}}}',
        )
        logger.info(
            "[VPN][device][VPN_DEVICE_CONFIG_ROTATED] "
            f"user_id={device.user_id} device_id={device.id} config_version={device.config_version} reason={reason}"
        )
        await self.session.flush()
        return device

    async def block_device(self, device: UserDevice, *, reason: str = "admin_block") -> UserDevice:
        """Block one device and deactivate any active peers while preserving slot consumption."""
        if device.status is not DeviceStatus.BLOCKED:
            await self.vpn.deactivate_device_clients(int(device.id))
            now = datetime.utcnow()
            device.status = DeviceStatus.BLOCKED
            device.blocked_at = now
            device.updated_at = now
            device.block_reason = reason
            await self._record_event(
                user_id=int(device.user_id),
                device_id=int(device.id),
                event_type=DeviceSecurityEventType.DEVICE_BLOCKED,
                severity=DeviceEventSeverity.WARNING,
                details_json=f'{{"reason":"{reason}"}}',
            )
            logger.warning(
                "[VPN][device][VPN_DEVICE_BLOCKED] "
                f"user_id={device.user_id} device_id={device.id} reason={reason}"
            )
            await self.session.flush()
        return device

    async def unblock_device(self, device: UserDevice, *, reason: str = "admin_unblock") -> UserDevice:
        """Remove the blocked state without automatically restoring the old peer."""
        if device.status is DeviceStatus.BLOCKED:
            device.status = DeviceStatus.ACTIVE
            device.updated_at = datetime.utcnow()
            device.blocked_at = None
            device.block_reason = None
            await self._record_event(
                user_id=int(device.user_id),
                device_id=int(device.id),
                event_type=DeviceSecurityEventType.DEVICE_UNBLOCKED,
                severity=DeviceEventSeverity.INFO,
                details_json=f'{{"reason":"{reason}"}}',
            )
            logger.info(
                "[VPN][device][VPN_DEVICE_UNBLOCKED] "
                f"user_id={device.user_id} device_id={device.id} reason={reason}"
            )
            await self.session.flush()
        return device

    async def _record_event(
        self,
        *,
        user_id: int,
        device_id: int,
        event_type: DeviceSecurityEventType,
        severity: DeviceEventSeverity,
        details_json: str | None,
    ) -> DeviceSecurityEvent:
        """Write one durable audit event for a device policy transition."""
        event = DeviceSecurityEvent(
            user_id=user_id,
            device_id=device_id,
            event_type=event_type,
            severity=severity,
            details_json=details_json,
        )
        self.session.add(event)
        await self.session.flush()
        logger.info(
            "[VPN][device][VPN_DEVICE_AUDIT_RECORDED] "
            f"user_id={user_id} device_id={device_id} event_type={event_type.value} severity={severity.value}"
        )
        return event

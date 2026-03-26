"""
MODULE_CONTRACT
- PURPOSE: Verify per-plan device limits and device lifecycle transitions for the first-pass device access policy.
- SCOPE: Limit rejection, revoke freeing a slot, rotate preserving logical identity and block preserving slot consumption.
- DEPENDS: M-001 async DB setup, M-003 VPN client records, M-004 billing plans and subscriptions, M-020 device-registry, M-021 device-access-policy.
- LINKS: V-M-021.

MODULE_MAP
- session: In-memory async DB session fixture for device access policy tests.
- test_create_device_record_rejects_when_limit_is_reached: Verifies deterministic device-limit rejection before provisioning.
- test_revoke_device_frees_slot: Verifies revoke deactivates the slot and allows another device.
- test_rotate_and_block_preserve_logical_device_identity: Verifies rotate keeps the same device while block consumes the slot.

CHANGE_SUMMARY
- 2026-03-27: Added device access policy tests for plan limits and lifecycle transitions.
"""

from datetime import datetime, timedelta

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool
from sqlmodel import SQLModel

from app.billing.models import Plan, Subscription, SubscriptionStatus
from app.core.database import import_all_models
from app.devices.models import DeviceStatus, UserDevice
from app.devices.service import DeviceAccessPolicyService, DeviceLimitExceededError
from app.users.models import User
from app.vpn.models import VPNClient


@pytest.fixture
async def session() -> AsyncSession:
    import_all_models()
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        future=True,
        poolclass=StaticPool,
    )

    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)

    session_maker = async_sessionmaker(
        engine,
        class_=AsyncSession,
        expire_on_commit=False,
        autoflush=False,
        autocommit=False,
    )

    async with session_maker() as session:
        yield session

    await engine.dispose()


async def _seed_user_with_plan(session: AsyncSession, *, device_limit: int = 1) -> User:
    user = User(email=f"user-{device_limit}@example.com", password_hash="hash")
    session.add(user)
    await session.flush()

    plan = Plan(
        name=f"Plan {device_limit}",
        price=100,
        duration_days=30,
        device_limit=device_limit,
    )
    session.add(plan)
    await session.flush()

    subscription = Subscription(
        user_id=int(user.id),
        plan_id=int(plan.id),
        status=SubscriptionStatus.ACTIVE,
        is_active=True,
        started_at=datetime.utcnow(),
        expires_at=datetime.utcnow() + timedelta(days=30),
    )
    session.add(subscription)
    await session.flush()
    return user


@pytest.mark.asyncio
async def test_create_device_record_rejects_when_limit_is_reached(session: AsyncSession):
    user = await _seed_user_with_plan(session, device_limit=1)
    service = DeviceAccessPolicyService(session)

    await service.create_device_record(int(user.id), name="iPhone", platform="ios")

    with pytest.raises(DeviceLimitExceededError):
        await service.create_device_record(int(user.id), name="MacBook", platform="macos")


@pytest.mark.asyncio
async def test_revoke_device_frees_slot(session: AsyncSession, monkeypatch: pytest.MonkeyPatch):
    user = await _seed_user_with_plan(session, device_limit=1)
    service = DeviceAccessPolicyService(session)
    device = await service.create_device_record(int(user.id), name="iPhone", platform="ios")

    client = VPNClient(
        user_id=int(user.id),
        device_id=int(device.id),
        public_key="pubkey-revoke",
        private_key_enc="enc-revoke",
        address="10.10.0.2",
        is_active=True,
    )
    session.add(client)
    await session.flush()

    async def fake_remove_peer(public_key: str) -> bool:
        assert public_key == "pubkey-revoke"
        return True

    monkeypatch.setattr(service.vpn.wg, "remove_peer", fake_remove_peer)
    await service.revoke_device(device, reason="user_request")

    assert device.status is DeviceStatus.REVOKED
    assert device.revoked_at is not None
    assert client.is_active is False

    replacement = await service.create_device_record(int(user.id), name="MacBook", platform="macos")
    assert replacement.id != device.id


@pytest.mark.asyncio
async def test_rotate_and_block_preserve_logical_device_identity(session: AsyncSession):
    user = await _seed_user_with_plan(session, device_limit=1)
    service = DeviceAccessPolicyService(session)
    device = await service.create_device_record(int(user.id), name="iPad", platform="ios")

    device_id_before = int(device.id)
    config_version_before = device.config_version

    await service.rotate_device_config(device, reason="user_rotate")
    assert int(device.id) == device_id_before
    assert device.config_version == config_version_before + 1
    assert device.status is DeviceStatus.ACTIVE

    await service.block_device(device, reason="fraud_review")
    assert device.status is DeviceStatus.BLOCKED

    with pytest.raises(DeviceLimitExceededError):
        await service.create_device_record(int(user.id), name="Windows", platform="windows")

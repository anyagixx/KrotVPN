"""
MODULE_CONTRACT
- PURPOSE: Verify authenticated user device API behavior for list/create/revoke/rotate flows.
- SCOPE: Response-shape assertions, current-user dependency overrides, and device-bound config delivery through router-level stubs.
- DEPENDS: M-001 dependency overrides, M-003 vpn config rendering surface, M-021 device-access-policy, M-022 device-provisioning-api.
- LINKS: V-M-022.

MODULE_MAP
- _build_app: Constructs a FastAPI test client with current-user and DB dependency overrides.
- test_list_devices_returns_owned_devices_and_slot_counters: Verifies list payload includes devices and effective slot counters.
- test_create_device_returns_device_bound_config_bundle: Verifies create flow provisions a device and returns rendered config.
- test_create_device_returns_conflict_when_limit_is_exhausted: Verifies device limit failures map to HTTP 409.
- test_revoke_device_returns_updated_device_state: Verifies revoke flow only returns the caller-owned device.
- test_rotate_device_returns_fresh_config_bundle: Verifies rotate flow returns updated config_version and rendered config.

CHANGE_SUMMARY
- 2026-03-27: Added router-level device API tests for list/create/revoke/rotate flows.
"""

from datetime import datetime
from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core import get_current_user
from app.core.database import get_session
from app.devices.models import DeviceStatus, UserDevice
from app.devices.service import DeviceLimitExceededError
from app.devices import router as devices_router_module


class DummySession:
    pass


def _build_app() -> TestClient:
    app = FastAPI()
    app.include_router(devices_router_module.router)

    async def override_session():
        yield DummySession()

    async def current_user_override():
        class User:
            id = 1
            is_active = True

        return User()

    app.dependency_overrides[get_session] = override_session
    app.dependency_overrides[get_current_user] = current_user_override
    return TestClient(app)


def _device(*, device_id: int, name: str, status: DeviceStatus = DeviceStatus.ACTIVE, config_version: int = 1) -> UserDevice:
    now = datetime.utcnow()
    return UserDevice(
        id=device_id,
        user_id=1,
        device_key=f"device-{device_id}",
        name=name,
        platform="ios",
        status=status,
        config_version=config_version,
        created_at=now,
        updated_at=now,
    )


class StubPolicyService:
    def __init__(self, session):
        self.session = session

    async def list_user_devices(self, user_id: int):
        assert user_id == 1
        return [_device(device_id=10, name="iPhone")]

    async def get_consumed_device_count(self, user_id: int):
        assert user_id == 1
        return 1

    async def get_effective_device_limit(self, user_id: int):
        assert user_id == 1
        return 3

    async def create_device_record(self, user_id: int, *, name: str, platform: str | None = None):
        assert user_id == 1
        return UserDevice(
            id=11,
            user_id=1,
            device_key="device-11",
            name=name,
            platform=platform,
            status=DeviceStatus.ACTIVE,
            config_version=1,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
        )

    async def get_user_device(self, user_id: int, device_id: int):
        assert user_id == 1
        if device_id == 10:
            return _device(device_id=10, name="iPhone")
        return None

    async def revoke_device(self, device: UserDevice, *, reason: str = "user_request"):
        device.status = DeviceStatus.REVOKED
        return device

    async def rotate_device_config(self, device: UserDevice, *, reason: str = "user_rotate"):
        device.config_version += 1
        return device


class LimitExceededPolicyService(StubPolicyService):
    async def create_device_record(self, user_id: int, *, name: str, platform: str | None = None):
        raise DeviceLimitExceededError("Device limit exceeded")


class StubVPNService:
    def __init__(self, session):
        self.session = session

    async def create_client(self, user_id: int, device_id: int | None = None):
        assert user_id == 1
        assert device_id is not None
        return SimpleNamespace(
            id=91,
            user_id=1,
            route_id=None,
            entry_node_id=10,
            created_at=datetime.utcnow(),
            address="10.10.0.9",
            public_key="pub-91",
        )

    async def provision_device_client(self, user_id: int, device_id: int, *, reprovision: bool = False):
        assert user_id == 1
        assert device_id == 10
        assert reprovision is True
        return SimpleNamespace(
            id=92,
            user_id=1,
            route_id=None,
            entry_node_id=10,
            created_at=datetime.utcnow(),
            address="10.10.0.10",
            public_key="pub-92",
        )

    async def get_client_config(self, client):
        return SimpleNamespace(
            config="[Interface]\nAddress = 10.10.0.9/32",
            server_name="RU Entry",
            server_location="Russia",
            route_name="default-ru",
            entry_server_name="RU Entry",
            entry_server_location="Russia",
            exit_server_name=None,
            exit_server_location=None,
            address=client.address,
            created_at=datetime.utcnow(),
        )


def test_list_devices_returns_owned_devices_and_slot_counters(monkeypatch):
    monkeypatch.setattr(devices_router_module, "DeviceAccessPolicyService", StubPolicyService)
    client = _build_app()

    response = client.get("/api/devices")

    assert response.status_code == 200
    body = response.json()
    assert body["consumed_slots"] == 1
    assert body["device_limit"] == 3
    assert len(body["devices"]) == 1
    assert body["devices"][0]["name"] == "iPhone"


def test_create_device_returns_device_bound_config_bundle(monkeypatch):
    monkeypatch.setattr(devices_router_module, "DeviceAccessPolicyService", StubPolicyService)
    monkeypatch.setattr(devices_router_module, "VPNService", StubVPNService)
    client = _build_app()

    response = client.post("/api/devices", json={"name": "MacBook", "platform": "macos"})

    assert response.status_code == 201
    body = response.json()
    assert body["device"]["name"] == "MacBook"
    assert body["device"]["platform"] == "macos"
    assert body["server_name"] == "RU Entry"
    assert body["address"] == "10.10.0.9"


def test_create_device_returns_conflict_when_limit_is_exhausted(monkeypatch):
    monkeypatch.setattr(devices_router_module, "DeviceAccessPolicyService", LimitExceededPolicyService)
    monkeypatch.setattr(devices_router_module, "VPNService", StubVPNService)
    client = _build_app()

    response = client.post("/api/devices", json={"name": "MacBook"})

    assert response.status_code == 409
    assert response.json()["detail"] == "Device limit exceeded"


def test_revoke_device_returns_updated_device_state(monkeypatch):
    monkeypatch.setattr(devices_router_module, "DeviceAccessPolicyService", StubPolicyService)
    client = _build_app()

    response = client.delete("/api/devices/10")

    assert response.status_code == 200
    assert response.json()["status"] == "revoked"


def test_rotate_device_returns_fresh_config_bundle(monkeypatch):
    monkeypatch.setattr(devices_router_module, "DeviceAccessPolicyService", StubPolicyService)
    monkeypatch.setattr(devices_router_module, "VPNService", StubVPNService)
    client = _build_app()

    response = client.post("/api/devices/10/rotate")

    assert response.status_code == 200
    body = response.json()
    assert body["device"]["id"] == 10
    assert body["device"]["config_version"] == 2
    assert body["address"] == "10.10.0.10"

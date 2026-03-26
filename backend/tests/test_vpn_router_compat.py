import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core import get_current_user
from app.core.database import get_session
from app.devices.models import DeviceStatus, UserDevice
from app.vpn import router as vpn_router_module


class DummySession:
    pass


class StubVPNService:
    def __init__(self, session):
        self.session = session

    async def get_node_statuses(self):
        return [
            {
                "id": 10,
                "name": "RU Entry Node",
                "role": "entry",
                "country_code": "RU",
                "location": "Russia",
                "endpoint": "1.1.1.1",
                "port": 51821,
                "public_key": "entry-pub",
                "is_active": True,
                "is_online": True,
                "is_entry_node": True,
                "is_exit_node": False,
                "current_clients": 4,
                "max_clients": 50,
                "load_percent": 8.0,
            },
            {
                "id": 11,
                "name": "DE Exit Node",
                "role": "exit",
                "country_code": "DE",
                "location": "Germany",
                "endpoint": "2.2.2.2",
                "port": 51821,
                "public_key": "exit-pub",
                "is_active": True,
                "is_online": True,
                "is_entry_node": False,
                "is_exit_node": True,
                "current_clients": 4,
                "max_clients": 50,
                "load_percent": 8.0,
            },
        ]


def _build_app() -> TestClient:
    app = FastAPI()
    app.include_router(vpn_router_module.router)

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


def test_public_servers_endpoint_is_compat_wrapper(monkeypatch):
    monkeypatch.setattr(vpn_router_module, "VPNService", StubVPNService)
    client = _build_app()

    response = client.get("/api/vpn/servers")

    assert response.status_code == 200
    body = response.json()
    assert len(body["servers"]) == 1
    assert body["servers"][0]["name"] == "RU Entry Node"
    assert body["servers"][0]["location"] == "Russia"


def test_public_nodes_endpoint_returns_route_aware_nodes(monkeypatch):
    monkeypatch.setattr(vpn_router_module, "VPNService", StubVPNService)
    client = _build_app()

    response = client.get("/api/vpn/nodes")

    assert response.status_code == 200
    body = response.json()
    assert len(body["nodes"]) == 2
    assert {item["role"] for item in body["nodes"]} == {"entry", "exit"}


@pytest.mark.asyncio
async def test_get_or_provision_user_client_prefers_active_primary_device(monkeypatch):
    device = UserDevice(
        id=21,
        user_id=1,
        device_key="device-21",
        name="Primary device",
        platform="web-default",
        status=DeviceStatus.ACTIVE,
    )

    class StubVPNService:
        def __init__(self, session):
            self.session = session

        async def get_device_client(self, device_id, active_only=True):
            assert device_id == 21
            assert active_only is True
            return None

        async def provision_device_client(self, user_id, device_id, *, reprovision=False):
            assert user_id == 1
            assert device_id == 21
            assert reprovision is False
            return {"client_id": 99, "device_id": 21}

        async def get_user_client(self, user_id):
            raise AssertionError("legacy user client fallback should not be used when active device exists")

    class StubBillingService:
        def __init__(self, session):
            self.session = session

        async def get_user_subscription(self, user_id):
            assert user_id == 1
            return object()

    class StubDevicePolicyService:
        def __init__(self, session):
            self.session = session

        async def list_user_devices(self, user_id):
            assert user_id == 1
            return [device]

    monkeypatch.setattr(vpn_router_module, "VPNService", StubVPNService)
    monkeypatch.setattr(vpn_router_module, "BillingService", StubBillingService)
    monkeypatch.setattr(vpn_router_module, "DeviceAccessPolicyService", StubDevicePolicyService)

    result = await vpn_router_module.get_or_provision_user_client(1, DummySession())

    assert result == {"client_id": 99, "device_id": 21}

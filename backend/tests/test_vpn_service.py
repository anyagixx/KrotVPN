from datetime import datetime

import pytest

from app.vpn import service as vpn_service_module
from app.vpn.models import VPNClient, VPNNode, VPNRoute, VPNServer
from app.vpn.service import VPNService


class DummySession:
    async def refresh(self, obj):
        return obj

    async def flush(self):
        return None


@pytest.mark.asyncio
async def test_create_client_returns_existing_active_client_for_same_entry_node(monkeypatch):
    service = VPNService(DummySession())
    existing = VPNClient(
        id=1,
        user_id=10,
        server_id=5,
        route_id=20,
        entry_node_id=10,
        exit_node_id=11,
        public_key="client-pub",
        private_key_enc="enc",
        address="10.10.0.2",
        is_active=True,
    )
    route = VPNRoute(id=20, name="RU -> DE", entry_node_id=10, exit_node_id=11)
    entry_node = VPNNode(
        id=10,
        name="RU Entry Node",
        role="entry",
        country_code="RU",
        location="Russia",
        endpoint="1.1.1.1",
        public_key="entry-pub",
        is_entry_node=True,
        is_exit_node=False,
    )
    exit_node = VPNNode(
        id=11,
        name="DE Exit Node",
        role="exit",
        country_code="DE",
        location="Germany",
        endpoint="2.2.2.2",
        public_key="exit-pub",
        is_entry_node=False,
        is_exit_node=True,
    )
    legacy_server = VPNServer(
        id=5,
        name="RU legacy",
        location="Russia",
        endpoint="1.1.1.1",
        public_key="entry-pub",
    )
    sync_calls: list[tuple[int | None, int | None, int | None]] = []

    async def fake_get_user_client(user_id, active_only=True):
        assert active_only is False
        return existing

    async def fake_get_route(route_id):
        return route if route_id == 20 else None

    async def fake_get_node(node_id):
        if node_id == 10:
            return entry_node
        if node_id == 11:
            return exit_node
        return None

    async def fake_get_server(server_id):
        return legacy_server if server_id == 5 else None

    async def fake_get_server_for_route(selected_route):
        assert selected_route is route
        return None

    async def fake_get_legacy_server_for_node(node, create=True):
        assert node is entry_node
        return legacy_server

    async def fake_sync(client, *, route, entry_node, exit_node):
        sync_calls.append((route.id if route else None, entry_node.id if entry_node else None, exit_node.id if exit_node else None))

    monkeypatch.setattr(service, "get_user_client", fake_get_user_client)
    monkeypatch.setattr(service, "get_route", fake_get_route)
    monkeypatch.setattr(service, "get_node", fake_get_node)
    monkeypatch.setattr(service, "get_server", fake_get_server)
    monkeypatch.setattr(service, "get_server_for_route", fake_get_server_for_route)
    monkeypatch.setattr(service, "get_legacy_server_for_node", fake_get_legacy_server_for_node)
    monkeypatch.setattr(service, "_sync_client_topology", fake_sync)

    result = await service.create_client(user_id=10)

    assert result is existing
    assert sync_calls == [(20, 10, 11)]


@pytest.mark.asyncio
async def test_create_client_provisions_new_client_from_active_route(monkeypatch):
    service = VPNService(DummySession())
    route = VPNRoute(id=20, name="RU -> DE", entry_node_id=10, exit_node_id=11)
    entry_node = VPNNode(
        id=10,
        name="RU Entry Node",
        role="entry",
        country_code="RU",
        location="Russia",
        endpoint="1.1.1.1",
        public_key="entry-pub",
        is_entry_node=True,
        is_exit_node=False,
    )
    exit_node = VPNNode(
        id=11,
        name="DE Exit Node",
        role="exit",
        country_code="DE",
        location="Germany",
        endpoint="2.2.2.2",
        public_key="exit-pub",
        is_entry_node=False,
        is_exit_node=True,
    )
    legacy_server = VPNServer(
        id=5,
        name="RU legacy",
        location="Russia",
        endpoint="1.1.1.1",
        public_key="entry-pub",
    )

    async def fake_get_user_client(user_id, active_only=True):
        return None

    async def fake_get_active_route():
        return route

    async def fake_get_node(node_id):
        if node_id == 10:
            return entry_node
        if node_id == 11:
            return exit_node
        return None

    async def fake_get_server_for_route(selected_route):
        assert selected_route is route
        return None

    async def fake_get_legacy_server_for_node(node, create=True):
        assert node is entry_node
        return legacy_server

    async def fake_provision(*, user_id, device_id=None, server, route, entry_node, exit_node):
        assert user_id == 10
        assert device_id is None
        assert server is legacy_server
        assert route is not None and route.id == 20
        assert entry_node is not None and entry_node.id == 10
        assert exit_node is not None and exit_node.id == 11
        return VPNClient(
            id=100,
            user_id=user_id,
            server_id=server.id,
            route_id=route.id,
            entry_node_id=entry_node.id,
            exit_node_id=exit_node.id,
            public_key="client-pub",
            private_key_enc="enc",
            address="10.10.0.9",
            is_active=True,
        )

    monkeypatch.setattr(service, "get_user_client", fake_get_user_client)
    monkeypatch.setattr(service, "get_active_route", fake_get_active_route)
    monkeypatch.setattr(service, "get_node", fake_get_node)
    monkeypatch.setattr(service, "get_server_for_route", fake_get_server_for_route)
    monkeypatch.setattr(service, "get_legacy_server_for_node", fake_get_legacy_server_for_node)
    monkeypatch.setattr(service, "_provision_new_client", fake_provision)

    result = await service.create_client(user_id=10)

    assert result.user_id == 10
    assert result.route_id == 20
    assert result.entry_node_id == 10
    assert result.exit_node_id == 11


@pytest.mark.asyncio
async def test_get_client_config_prefers_route_topology_over_legacy_server(monkeypatch):
    service = VPNService(DummySession())
    client = VPNClient(
        id=1,
        user_id=10,
        server_id=5,
        route_id=20,
        entry_node_id=10,
        exit_node_id=11,
        public_key="client-pub",
        private_key_enc="encrypted-private",
        address="10.10.0.2",
        is_active=True,
        created_at=datetime(2026, 3, 23),
    )
    route = VPNRoute(id=20, name="RU -> DE", entry_node_id=10, exit_node_id=11)
    entry_node = VPNNode(
        id=10,
        name="RU Entry Node",
        role="entry",
        country_code="RU",
        location="Russia",
        endpoint="1.1.1.1",
        public_key="entry-pub",
        is_entry_node=True,
        is_exit_node=False,
    )
    exit_node = VPNNode(
        id=11,
        name="DE Exit Node",
        role="exit",
        country_code="DE",
        location="Germany",
        endpoint="2.2.2.2",
        public_key="exit-pub",
        is_entry_node=False,
        is_exit_node=True,
    )
    legacy_server = VPNServer(
        id=5,
        name="Old server name",
        location="Legacy location",
        endpoint="9.9.9.9",
        public_key="legacy-pub",
    )
    config_calls: list[tuple[str, str, str, str]] = []

    async def fake_get_route(route_id):
        return route if route_id == 20 else None

    async def fake_get_node(node_id):
        if node_id == 10:
            return entry_node
        if node_id == 11:
            return exit_node
        return None

    async def fake_get_server(server_id):
        return legacy_server if server_id == 5 else None

    monkeypatch.setattr(service, "get_route", fake_get_route)
    monkeypatch.setattr(service, "get_node", fake_get_node)
    monkeypatch.setattr(service, "get_server", fake_get_server)
    monkeypatch.setattr(vpn_service_module, "decrypt_data", lambda value: "decrypted-private")

    def fake_create_client_config(*, private_key, address, server_public_key, endpoint):
        config_calls.append((private_key, address, server_public_key, endpoint))
        return "[Interface]\n[Peer]"

    monkeypatch.setattr(service.wg, "create_client_config", fake_create_client_config)

    config = await service.get_client_config(client)

    assert config.server_name == "RU Entry Node"
    assert config.server_location == "Russia"
    assert config.route_name == "RU -> DE"
    assert config.entry_server_name == "RU Entry Node"
    assert config.exit_server_name == "DE Exit Node"


@pytest.mark.asyncio
async def test_provision_device_client_reprovisions_existing_device_peer(monkeypatch):
    service = VPNService(DummySession())
    existing = VPNClient(
        id=5,
        user_id=10,
        device_id=77,
        server_id=5,
        route_id=20,
        entry_node_id=10,
        exit_node_id=11,
        public_key="client-pub",
        private_key_enc="enc",
        address="10.10.0.2",
        is_active=True,
    )
    route = VPNRoute(id=20, name="RU -> DE", entry_node_id=10, exit_node_id=11)
    entry_node = VPNNode(
        id=10,
        name="RU Entry Node",
        role="entry",
        country_code="RU",
        location="Russia",
        endpoint="1.1.1.1",
        public_key="entry-pub",
        is_entry_node=True,
        is_exit_node=False,
    )
    exit_node = VPNNode(
        id=11,
        name="DE Exit Node",
        role="exit",
        country_code="DE",
        location="Germany",
        endpoint="2.2.2.2",
        public_key="exit-pub",
        is_entry_node=False,
        is_exit_node=True,
    )
    legacy_server = VPNServer(
        id=5,
        name="RU legacy",
        location="Russia",
        endpoint="1.1.1.1",
        public_key="entry-pub",
    )
    deactivated: list[int] = []
    reprovisioned: list[int] = []

    async def fake_get_device_client(device_id, active_only=True):
        assert device_id == 77
        assert active_only is False
        return existing

    async def fake_select(existing_client):
        assert existing_client is existing
        return route, entry_node, exit_node, legacy_server

    async def fake_get_legacy_server_for_node(node, create=True):
        assert node is entry_node
        return legacy_server

    async def fake_deactivate(client):
        deactivated.append(int(client.id))
        client.is_active = False

    async def fake_reprovision(client, server, *, route, entry_node, exit_node):
        reprovisioned.append(int(client.id))
        client.is_active = True
        client.address = "10.10.0.9"
        return client

    monkeypatch.setattr(service, "get_device_client", fake_get_device_client)
    monkeypatch.setattr(service, "_select_topology_for_existing_client", fake_select)
    monkeypatch.setattr(service, "get_legacy_server_for_node", fake_get_legacy_server_for_node)
    monkeypatch.setattr(service, "deactivate_client", fake_deactivate)
    monkeypatch.setattr(service, "_reprovision_client", fake_reprovision)

    result = await service.provision_device_client(10, 77, reprovision=True)

    assert result is existing
    assert deactivated == [5]
    assert reprovisioned == [5]
    assert result.address == "10.10.0.9"


@pytest.mark.asyncio
async def test_get_route_statuses_includes_tunnel_health(monkeypatch):
    service = VPNService(DummySession())
    route = VPNRoute(
        id=20,
        name="RU -> DE",
        entry_node_id=10,
        exit_node_id=11,
        is_active=True,
        is_default=True,
        priority=100,
        current_clients=3,
        max_clients=10,
    )
    entry_node = VPNNode(
        id=10,
        name="RU Entry Node",
        role="entry",
        country_code="RU",
        location="Russia",
        endpoint="1.1.1.1",
        public_key="entry-pub",
        is_entry_node=True,
        is_exit_node=False,
    )
    exit_node = VPNNode(
        id=11,
        name="DE Exit Node",
        role="exit",
        country_code="DE",
        location="Germany",
        endpoint="2.2.2.2",
        public_key="exit-pub",
        is_entry_node=False,
        is_exit_node=True,
    )

    async def fake_list_routes():
        return [route]

    async def fake_get_node(node_id):
        if node_id == 10:
            return entry_node
        if node_id == 11:
            return exit_node
        return None

    async def fake_check_tunnel_status():
        return {"interface": "awg0", "status": "up"}

    monkeypatch.setattr(service, "list_routes", fake_list_routes)
    monkeypatch.setattr(service, "get_node", fake_get_node)
    monkeypatch.setattr(vpn_service_module.routing_manager, "check_tunnel_status", fake_check_tunnel_status)

    statuses = await service.get_route_statuses()

    assert len(statuses) == 1
    assert statuses[0]["name"] == "RU -> DE"
    assert statuses[0]["tunnel_interface"] == "awg0"
    assert statuses[0]["tunnel_status"] == "up"
    assert statuses[0]["entry_node_name"] == "RU Entry Node"
    assert statuses[0]["exit_node_name"] == "DE Exit Node"


@pytest.mark.asyncio
async def test_provision_internal_client_reuses_normal_create_path(monkeypatch):
    service = VPNService(DummySession())
    client = VPNClient(
        id=5,
        user_id=10,
        server_id=3,
        public_key="pub",
        private_key_enc="enc",
        address="10.10.0.10",
        is_active=True,
    )

    async def fake_create_client(user_id):
        assert user_id == 10
        return client

    monkeypatch.setattr(service, "create_client", fake_create_client)

    result = await service.provision_internal_client(10, reprovision=False)

    assert result is client


@pytest.mark.asyncio
async def test_provision_internal_client_reprovisions_existing_client(monkeypatch):
    session = DummySession()
    service = VPNService(session)
    existing = VPNClient(
        id=9,
        user_id=15,
        server_id=5,
        route_id=20,
        entry_node_id=10,
        exit_node_id=11,
        public_key="old-pub",
        private_key_enc="enc",
        address="10.10.0.20",
        is_active=True,
    )
    route = VPNRoute(id=20, name="RU -> DE", entry_node_id=10, exit_node_id=11)
    entry_node = VPNNode(
        id=10,
        name="RU Entry Node",
        role="entry",
        country_code="RU",
        location="Russia",
        endpoint="1.1.1.1",
        public_key="entry-pub",
        is_entry_node=True,
        is_exit_node=False,
    )
    exit_node = VPNNode(
        id=11,
        name="DE Exit Node",
        role="exit",
        country_code="DE",
        location="Germany",
        endpoint="2.2.2.2",
        public_key="exit-pub",
        is_entry_node=False,
        is_exit_node=True,
    )
    legacy_server = VPNServer(
        id=5,
        name="RU legacy",
        location="Russia",
        endpoint="1.1.1.1",
        public_key="entry-pub",
    )
    deactivated = []
    reprovisioned = VPNClient(
        id=9,
        user_id=15,
        server_id=5,
        route_id=20,
        entry_node_id=10,
        exit_node_id=11,
        public_key="new-pub",
        private_key_enc="enc2",
        address="10.10.0.21",
        is_active=True,
    )

    async def fake_get_user_client(user_id, active_only=True):
        assert user_id == 15
        assert active_only is False
        return existing

    async def fake_select_existing(client):
        assert client is existing
        return route, entry_node, exit_node, legacy_server

    async def fake_get_legacy_server_for_node(node, create=True):
        assert node is entry_node
        return legacy_server

    async def fake_deactivate_client(client):
        deactivated.append(client.id)
        client.is_active = False

    async def fake_reprovision(client, server, *, route, entry_node, exit_node):
        assert client is existing
        assert server is legacy_server
        assert route is not None and route.id == 20
        assert entry_node is not None and entry_node.id == 10
        assert exit_node is not None and exit_node.id == 11
        return reprovisioned

    monkeypatch.setattr(service, "get_user_client", fake_get_user_client)
    monkeypatch.setattr(service, "_select_topology_for_existing_client", fake_select_existing)
    monkeypatch.setattr(service, "get_legacy_server_for_node", fake_get_legacy_server_for_node)
    monkeypatch.setattr(service, "deactivate_client", fake_deactivate_client)
    monkeypatch.setattr(service, "_reprovision_client", fake_reprovision)

    result = await service.provision_internal_client(15, reprovision=True)

    assert deactivated == [9]
    assert result is reprovisioned

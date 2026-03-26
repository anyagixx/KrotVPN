"""
MODULE_CONTRACT
- PURPOSE: Verify admin-facing routing policy API behavior for CRUD-like creation, decision explanation, and DNS-binding visibility.
- SCOPE: Response-shape assertions, admin dependency overrides, and deterministic decision evidence for route-policy endpoints.
- DEPENDS: M-001 dependency overrides, M-014 domain-rule-store responses, M-016 route-decision-api.
- LINKS: V-M-006, V-M-016.

MODULE_MAP
- _build_client: Constructs a FastAPI test client with admin and DB dependency overrides.
- test_create_domain_route_rule_returns_created_rule: Verifies policy mutation response shape for created domain rules.
- test_explain_route_decision_returns_reason_and_trace: Verifies decision explanation payload includes reason and trace marker.
- test_list_policy_dns_bindings_exposes_active_bindings: Verifies active DNS bindings are exposed through the admin-facing policy API.

CHANGE_SUMMARY
- 2026-03-24: Added route decision API tests for policy creation, explainability, and DNS binding visibility.
"""

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core import get_current_admin
from app.core.database import get_session
from app.routing.models import RouteTarget
from app.routing import router as routing_router_module


class DummySession:
    pass


def _build_client() -> TestClient:
    app = FastAPI()
    app.include_router(routing_router_module.router)

    async def override_session():
        yield DummySession()

    async def current_admin_override():
        class Admin:
            id = 1
            is_active = True
        return Admin()

    app.dependency_overrides[get_session] = override_session
    app.dependency_overrides[get_current_admin] = current_admin_override
    return TestClient(app)


def test_create_domain_route_rule_returns_created_rule(monkeypatch):
    class StubStore:
        def __init__(self, session):
            self.session = session

        async def create_domain_rule(self, payload):
            from app.routing.models import DomainMatchType, DomainRouteRule

            return DomainRouteRule(
                id=7,
                domain="*.example.com",
                normalized_domain="example.com",
                match_type=DomainMatchType.WILDCARD,
                route_target=payload.route_target,
                priority=payload.priority,
                description=payload.description,
            )

    async def noop_refresh(rule):
        return []

    monkeypatch.setattr(routing_router_module, "DomainRuleStore", StubStore)
    monkeypatch.setattr(routing_router_module.policy_dns_observer, "refresh_domain_bindings", noop_refresh)
    client = _build_client()

    response = client.post(
        "/api/routing/policy/domains",
        json={
            "domain": "*.example.com",
            "route_target": "de",
            "priority": 10,
            "description": "cdn",
        },
    )

    body = response.json()
    assert response.status_code == 201
    assert body["normalized_domain"] == "example.com"
    assert body["route_target"] == "de"


def test_explain_route_decision_returns_reason_and_trace(monkeypatch):
    class StubStore:
        def __init__(self, session):
            self.session = session

        async def list_active_domain_rules(self):
            return []

        async def list_active_cidr_rules(self):
            return []

    async def fake_get_all_routes(session):
        return [{"address": "stream.example.com", "route_type": "vpn"}]

    class Decision:
        route_target = RouteTarget.DE
        reason = type("DecisionReasonValue", (), {"value": "domain_exact"})()
        trace_marker = "ROUTE_DECISION_DOMAIN_EXACT"
        rule_id = 5
        normalized_domain = "stream.example.com"
        resolved_ip = "203.0.113.7"

    async def fake_resolve(address, **kwargs):
        assert address == "stream.example.com"
        return Decision()

    monkeypatch.setattr(routing_router_module, "DomainRuleStore", StubStore)
    monkeypatch.setattr(routing_router_module, "_get_all_routes", fake_get_all_routes)
    monkeypatch.setattr(routing_router_module.routing_manager, "resolve_effective_target", fake_resolve)
    monkeypatch.setattr(routing_router_module.policy_dns_observer, "get_active_bindings", lambda: [])

    client = _build_client()
    response = client.post(
        "/api/routing/policy/explain",
        json={"address": "stream.example.com"},
    )

    body = response.json()
    assert response.status_code == 200
    assert body["route_target"] == "de"
    assert body["decision_reason"] == "domain_exact"
    assert body["trace_marker"] == "ROUTE_DECISION_DOMAIN_EXACT"


def test_list_policy_dns_bindings_exposes_active_bindings(monkeypatch):
    from app.routing.policy import DnsBoundRoute

    monkeypatch.setattr(
        routing_router_module.policy_dns_observer,
        "get_active_bindings",
        lambda: [
            DnsBoundRoute(
                normalized_domain="example.com",
                resolved_ip="1.1.1.1",
                route_target=RouteTarget.DE,
                rule_id=9,
            )
        ],
    )
    client = _build_client()

    response = client.get("/api/routing/policy/dns-bindings")

    assert response.status_code == 200
    assert response.json() == [
        {
            "normalized_domain": "example.com",
            "resolved_ip": "1.1.1.1",
            "route_target": "de",
            "rule_id": 9,
        }
    ]

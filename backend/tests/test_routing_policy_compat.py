from app.routing.manager import RoutingManager
from app.routing.models import RouteTarget
from app.routing.policy import DecisionReason


class StubRoutingManager(RoutingManager):
    def __init__(self):
        super().__init__()
        self._resolved = {}
        self._ru_members = set()

    async def _resolve_domain_to_ipv4(self, domain: str) -> str | None:
        return self._resolved.get(domain)

    async def is_ip_in_ru_ipset(self, ip: str) -> bool:
        return ip in self._ru_members


def test_legacy_direct_domain_route_becomes_policy_domain_override():
    manager = StubRoutingManager()

    decision = manager._build_legacy_policy_rules(
        [{"address": "portal.example.com", "route_type": "direct"}]
    )[0][0]

    assert decision.normalized_domain == "portal.example.com"
    assert decision.route_target is RouteTarget.DIRECT


def test_legacy_vpn_cidr_route_becomes_policy_cidr_override():
    manager = StubRoutingManager()

    decision = manager._build_legacy_policy_rules(
        [{"address": "8.8.8.0/24", "route_type": "vpn"}]
    )[1][0]

    assert decision.normalized_cidr == "8.8.8.0/24"
    assert decision.route_target is RouteTarget.DE


async def test_resolve_effective_target_preserves_ru_baseline_for_unmatched_ip():
    manager = StubRoutingManager()
    manager._ru_members.add("77.88.8.8")

    decision = await manager.resolve_effective_target("77.88.8.8")

    assert decision.route_target is RouteTarget.RU
    assert decision.reason is DecisionReason.RU_BASELINE


async def test_resolve_effective_target_uses_legacy_custom_route_before_baseline():
    manager = StubRoutingManager()
    manager._resolved["stream.example.com"] = "77.88.8.8"
    manager._ru_members.add("77.88.8.8")

    decision = await manager.resolve_effective_target(
        "stream.example.com",
        custom_routes=[{"address": "stream.example.com", "route_type": "vpn"}],
    )

    assert decision.route_target is RouteTarget.DE
    assert decision.reason is DecisionReason.DOMAIN_EXACT

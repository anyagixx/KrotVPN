from datetime import UTC, datetime, timedelta

from app.routing.dns_resolver import DNSObserver
from app.routing.models import DomainMatchType, DomainRouteRule, RouteTarget
from app.routing.policy import DnsBoundRoute


class FrozenClock:
    def __init__(self, start: datetime):
        self.current = start

    def now(self) -> datetime:
        return self.current

    def advance(self, seconds: int) -> None:
        self.current += timedelta(seconds=seconds)


async def test_refresh_domain_bindings_creates_active_dns_bound_routes():
    async def resolver(domain: str) -> list[str]:
        assert domain == "example.com"
        return ["1.1.1.1", "1.1.1.2"]

    clock = FrozenClock(datetime(2026, 3, 24, tzinfo=UTC))
    observer = DNSObserver(resolver, now_func=clock.now, default_ttl_seconds=60)
    rule = DomainRouteRule(
        id=5,
        domain="*.example.com",
        normalized_domain="example.com",
        match_type=DomainMatchType.WILDCARD,
        route_target=RouteTarget.DE,
        priority=10,
    )

    refreshed = await observer.refresh_domain_bindings(rule)

    assert [binding.resolved_ip for binding in refreshed] == ["1.1.1.1", "1.1.1.2"]
    active = observer.get_active_bindings()
    assert active == [
        DnsBoundRoute(normalized_domain="example.com", resolved_ip="1.1.1.1", route_target=RouteTarget.DE, rule_id=5),
        DnsBoundRoute(normalized_domain="example.com", resolved_ip="1.1.1.2", route_target=RouteTarget.DE, rule_id=5),
    ]


async def test_expire_stale_bindings_removes_expired_records():
    async def resolver(domain: str) -> list[str]:
        return ["2.2.2.2"]

    clock = FrozenClock(datetime(2026, 3, 24, tzinfo=UTC))
    observer = DNSObserver(resolver, now_func=clock.now, default_ttl_seconds=30)
    rule = DomainRouteRule(
        id=6,
        domain="api.example.com",
        normalized_domain="api.example.com",
        match_type=DomainMatchType.EXACT,
        route_target=RouteTarget.RU,
        priority=10,
    )

    await observer.refresh_domain_bindings(rule)
    clock.advance(31)
    expired = observer.expire_stale_bindings()

    assert [binding.resolved_ip for binding in expired] == ["2.2.2.2"]
    assert observer.get_active_bindings() == []


async def test_refresh_domain_bindings_replaces_previous_ip_set():
    calls = {
        "count": 0,
    }

    async def resolver(domain: str) -> list[str]:
        calls["count"] += 1
        if calls["count"] == 1:
            return ["3.3.3.3"]
        return ["4.4.4.4"]

    clock = FrozenClock(datetime(2026, 3, 24, tzinfo=UTC))
    observer = DNSObserver(resolver, now_func=clock.now, default_ttl_seconds=60)
    rule = DomainRouteRule(
        id=7,
        domain="video.example.com",
        normalized_domain="video.example.com",
        match_type=DomainMatchType.EXACT,
        route_target=RouteTarget.DE,
        priority=10,
    )

    await observer.refresh_domain_bindings(rule)
    await observer.refresh_domain_bindings(rule)

    active = observer.get_active_bindings()
    assert active == [
        DnsBoundRoute(
            normalized_domain="video.example.com",
            resolved_ip="4.4.4.4",
            route_target=RouteTarget.DE,
            rule_id=7,
        )
    ]

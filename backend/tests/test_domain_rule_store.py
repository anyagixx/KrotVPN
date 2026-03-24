import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool
from sqlmodel import SQLModel

from app.routing.domain_rules import (
    DomainRuleStore,
    RuleValidationError,
    normalize_cidr_rule_input,
    normalize_domain_rule_input,
)
from app.routing.models import (
    CidrRouteRuleCreate,
    DomainMatchType,
    DomainRouteRuleCreate,
    RouteTarget,
)


@pytest.fixture
async def session() -> AsyncSession:
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


def test_normalize_domain_rule_input_classifies_exact_and_wildcard():
    exact = normalize_domain_rule_input(" Example.COM. ")
    wildcard = normalize_domain_rule_input("*.Sub.Example.com")

    assert exact.normalized_domain == "example.com"
    assert exact.match_type is DomainMatchType.EXACT
    assert wildcard.normalized_domain == "sub.example.com"
    assert wildcard.match_type is DomainMatchType.WILDCARD


@pytest.mark.parametrize(
    "value",
    [
        "",
        "localhost",
        "*bad.example.com",
        "*.*.example.com",
        "exa_mple.com",
        "-edge.example.com",
        "example..com",
    ],
)
def test_normalize_domain_rule_input_rejects_invalid_values(value: str):
    with pytest.raises(RuleValidationError):
        normalize_domain_rule_input(value)


def test_normalize_cidr_rule_input_normalizes_single_ip_and_cidr():
    assert normalize_cidr_rule_input("1.2.3.4") == "1.2.3.4/32"
    assert normalize_cidr_rule_input("10.0.0.9/24") == "10.0.0.0/24"


@pytest.mark.asyncio
async def test_create_domain_rule_normalizes_and_rejects_duplicates(session: AsyncSession):
    store = DomainRuleStore(session)

    created = await store.create_domain_rule(
        DomainRouteRuleCreate(
            domain="*.Example.com.",
            route_target=RouteTarget.DE,
            priority=20,
            description="cdn egress",
        )
    )

    assert created.domain == "*.example.com"
    assert created.normalized_domain == "example.com"
    assert created.match_type is DomainMatchType.WILDCARD

    with pytest.raises(RuleValidationError):
        await store.create_domain_rule(
            DomainRouteRuleCreate(
                domain="*.example.com",
                route_target=RouteTarget.RU,
            )
        )


@pytest.mark.asyncio
async def test_create_cidr_rule_normalizes_and_rejects_duplicates(session: AsyncSession):
    store = DomainRuleStore(session)

    created = await store.create_cidr_rule(
        CidrRouteRuleCreate(
            cidr="10.10.10.50/24",
            route_target=RouteTarget.RU,
            priority=30,
        )
    )

    assert created.normalized_cidr == "10.10.10.0/24"

    with pytest.raises(RuleValidationError):
        await store.create_cidr_rule(
            CidrRouteRuleCreate(
                cidr="10.10.10.0/24",
                route_target=RouteTarget.DE,
            )
        )


@pytest.mark.asyncio
async def test_list_active_rules_orders_by_priority(session: AsyncSession):
    store = DomainRuleStore(session)

    await store.create_domain_rule(
        DomainRouteRuleCreate(domain="zeta.example.com", route_target=RouteTarget.DE, priority=50)
    )
    await store.create_domain_rule(
        DomainRouteRuleCreate(domain="alpha.example.com", route_target=RouteTarget.RU, priority=10)
    )

    rules = await store.list_active_domain_rules()

    assert [rule.normalized_domain for rule in rules] == [
        "alpha.example.com",
        "zeta.example.com",
    ]

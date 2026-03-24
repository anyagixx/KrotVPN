"""
Routing models for split-tunneling and policy-driven routing.

MODULE_CONTRACT
- PURPOSE: Define persisted routing rules, API schemas, and policy-facing enums for host-level routing decisions.
- SCOPE: Custom routes, exact-domain rules, wildcard-domain rules, explicit CIDR rules, and routing status response shapes.
- DEPENDS: sqlmodel, sqlalchemy metadata constraints.
- LINKS: M-007 routing, M-014 domain-rule-store, V-M-014.

MODULE_MAP
- RouteType: Legacy custom-route destination enum.
- RouteTarget: Policy route target enum for RU, DE, DIRECT, or DEFAULT decisions.
- DomainMatchType: Policy rule classifier for exact and wildcard domain rules.
- CustomRoute: Existing custom route persistence model.
- DomainRouteRule: Persisted exact or wildcard domain rule.
- CidrRouteRule: Persisted explicit IP/CIDR rule.
- RoutingStatus: Routing runtime status response.
- CustomRouteCreate: Request schema for custom route creation.
- CustomRouteResponse: Response schema for custom route reads.
- DomainRouteRuleCreate: Request schema for domain rule creation.
- DomainRouteRuleUpdate: Partial-update schema for domain rules.
- DomainRouteRuleResponse: Response schema for domain rules.
- CidrRouteRuleCreate: Request schema for CIDR rule creation.
- CidrRouteRuleUpdate: Partial-update schema for CIDR rules.
- CidrRouteRuleResponse: Response schema for CIDR rules.

CHANGE_SUMMARY
- 2026-03-24: Added domain and CIDR routing rule entities plus policy schemas for domain-aware routing migration.
"""
# <!-- GRACE: module="M-007 M-014" entity="CustomRoute,DomainRouteRule,CidrRouteRule" -->

from __future__ import annotations

from datetime import datetime
from enum import Enum

from sqlalchemy import UniqueConstraint
from sqlmodel import Field, SQLModel


class RouteType(str, Enum):
    """Route type for legacy custom routing."""

    DIRECT = "direct"
    VPN = "vpn"


class RouteTarget(str, Enum):
    """Policy route target for routing decisions."""

    RU = "ru"
    DE = "de"
    DIRECT = "direct"
    DEFAULT = "default"


class DomainMatchType(str, Enum):
    """Supported domain policy rule classes."""

    EXACT = "exact"
    WILDCARD = "wildcard"


class CustomRoute(SQLModel, table=True):
    """Custom routing rule."""

    __tablename__ = "custom_routes"

    id: int | None = Field(default=None, primary_key=True)
    address: str = Field(max_length=255, index=True)
    route_type: RouteType = Field(default=RouteType.VPN)
    description: str | None = Field(default=None, max_length=500)
    is_active: bool = Field(default=True)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class DomainRouteRule(SQLModel, table=True):
    """Persisted exact or wildcard domain routing rule."""

    __tablename__ = "domain_route_rules"
    __table_args__ = (
        UniqueConstraint(
            "normalized_domain",
            "match_type",
            name="uq_domain_route_rules_normalized_domain_match_type",
        ),
    )

    id: int | None = Field(default=None, primary_key=True)
    domain: str = Field(max_length=255, index=True)
    normalized_domain: str = Field(max_length=253, index=True)
    match_type: DomainMatchType = Field(default=DomainMatchType.EXACT)
    route_target: RouteTarget = Field(default=RouteTarget.DEFAULT)
    priority: int = Field(default=100, index=True)
    description: str | None = Field(default=None, max_length=500)
    is_active: bool = Field(default=True, index=True)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class CidrRouteRule(SQLModel, table=True):
    """Persisted explicit IP or CIDR routing rule."""

    __tablename__ = "cidr_route_rules"
    __table_args__ = (
        UniqueConstraint(
            "normalized_cidr",
            name="uq_cidr_route_rules_normalized_cidr",
        ),
    )

    id: int | None = Field(default=None, primary_key=True)
    cidr: str = Field(max_length=64, index=True)
    normalized_cidr: str = Field(max_length=64, index=True)
    route_target: RouteTarget = Field(default=RouteTarget.DEFAULT)
    priority: int = Field(default=100, index=True)
    description: str | None = Field(default=None, max_length=500)
    is_active: bool = Field(default=True, index=True)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class RoutingStatus(SQLModel):
    """Routing system status."""

    ru_ipset_entries: int
    ru_ipset_status: str
    tunnel_status: str
    custom_routes_count: int
    last_ru_update: datetime | None


class CustomRouteCreate(SQLModel):
    """Schema for creating a custom route."""

    address: str = Field(..., min_length=1, max_length=255)
    route_type: RouteType
    description: str | None = None


class CustomRouteResponse(SQLModel):
    """Custom route response."""

    id: int
    address: str
    route_type: RouteType
    description: str | None
    is_active: bool
    created_at: datetime

    model_config = {"from_attributes": True}


class DomainRouteRuleCreate(SQLModel):
    """Schema for creating an exact or wildcard domain rule."""

    domain: str = Field(..., min_length=1, max_length=255)
    route_target: RouteTarget
    priority: int = Field(default=100, ge=0, le=10000)
    description: str | None = Field(default=None, max_length=500)


class DomainRouteRuleUpdate(SQLModel):
    """Partial update schema for domain rules."""

    route_target: RouteTarget | None = None
    priority: int | None = Field(default=None, ge=0, le=10000)
    description: str | None = Field(default=None, max_length=500)
    is_active: bool | None = None


class DomainRouteRuleResponse(SQLModel):
    """Response schema for a domain route rule."""

    id: int
    domain: str
    normalized_domain: str
    match_type: DomainMatchType
    route_target: RouteTarget
    priority: int
    description: str | None
    is_active: bool
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class CidrRouteRuleCreate(SQLModel):
    """Schema for creating an explicit CIDR or single-IP rule."""

    cidr: str = Field(..., min_length=1, max_length=64)
    route_target: RouteTarget
    priority: int = Field(default=100, ge=0, le=10000)
    description: str | None = Field(default=None, max_length=500)


class CidrRouteRuleUpdate(SQLModel):
    """Partial update schema for CIDR rules."""

    route_target: RouteTarget | None = None
    priority: int | None = Field(default=None, ge=0, le=10000)
    description: str | None = Field(default=None, max_length=500)
    is_active: bool | None = None


class CidrRouteRuleResponse(SQLModel):
    """Response schema for an explicit CIDR rule."""

    id: int
    cidr: str
    normalized_cidr: str
    route_target: RouteTarget
    priority: int
    description: str | None
    is_active: bool
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}

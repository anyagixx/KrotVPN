"""Routing module exports."""
from app.routing.models import (
    CidrRouteRule,
    CidrRouteRuleCreate,
    CidrRouteRuleResponse,
    CidrRouteRuleUpdate,
    CustomRoute,
    CustomRouteCreate,
    CustomRouteResponse,
    DomainMatchType,
    DomainRouteRule,
    DomainRouteRuleCreate,
    DomainRouteRuleResponse,
    DomainRouteRuleUpdate,
    RouteType,
    RouteTarget,
    RoutingStatus,
)
from app.routing.domain_rules import (
    DomainRuleStore,
    RuleValidationError,
    normalize_cidr_rule_input,
    normalize_domain_rule_input,
)
from app.routing.manager import RoutingManager, routing_manager
from app.routing.router import router as routing_router

__all__ = [
    # Models
    "CidrRouteRule",
    "CidrRouteRuleCreate",
    "CidrRouteRuleResponse",
    "CidrRouteRuleUpdate",
    "CustomRoute",
    "CustomRouteCreate",
    "CustomRouteResponse",
    "DomainMatchType",
    "DomainRouteRule",
    "DomainRouteRuleCreate",
    "DomainRouteRuleResponse",
    "DomainRouteRuleUpdate",
    "RouteType",
    "RouteTarget",
    "RoutingStatus",
    # Store
    "DomainRuleStore",
    "RuleValidationError",
    "normalize_cidr_rule_input",
    "normalize_domain_rule_input",
    # Manager
    "RoutingManager",
    "routing_manager",
    # Router
    "routing_router",
]

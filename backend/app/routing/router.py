"""
Routing API router.

MODULE_CONTRACT
- PURPOSE: Expose admin-facing routing status, custom route management, policy CRUD, and route-decision inspection APIs.
- SCOPE: Routing status reads, RU update trigger, legacy custom-route CRUD, domain/CIDR policy CRUD, DNS binding visibility, and decision explain endpoints.
- DEPENDS: M-001 auth and DB session injection, M-007 routing runtime, M-013 route-policy-resolver, M-014 domain-rule-store, M-015 dns-observer, M-016 route-decision-api.
- LINKS: M-007 routing, M-016 route-decision-api, V-M-007, V-M-016.

MODULE_MAP
- get_routing_status: Returns current routing status and last RU update timestamp.
- update_ru_ips: Triggers RU ipset refresh through the routing manager.
- list_custom_routes/create_custom_route/delete_custom_route: Maintain legacy custom-route state and sync it into runtime ipsets.
- list_domain_route_rules/create_domain_route_rule/update_domain_route_rule/delete_domain_route_rule: Manage domain-based policy rules.
- list_cidr_route_rules/create_cidr_route_rule/update_cidr_route_rule/delete_cidr_route_rule: Manage CIDR-based policy rules.
- explain_route_decision: Returns effective route target, reason, and trace marker for an input address.
- list_policy_dns_bindings: Returns active DNS-derived bindings used by policy decisions.

CHANGE_SUMMARY
- 2026-03-24: Expanded routing API to include policy CRUD, DNS binding visibility, and decision explainability for route-policy migration work.
"""
# <!-- GRACE: module="M-016" api-group="Routing API" -->

import asyncio
import socket
from datetime import datetime, timezone
from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select

from app.core import CurrentAdmin, CurrentUser, DBSession
from app.routing.domain_rules import DomainRuleStore, RuleValidationError
from app.routing.dns_resolver import DNSObserver
from app.routing.manager import routing_manager
from app.routing.models import (
    ActiveDNSBindingResponse,
    CidrRouteRule,
    CidrRouteRuleCreate,
    CidrRouteRuleResponse,
    CidrRouteRuleUpdate,
    CustomRoute,
    CustomRouteCreate,
    CustomRouteResponse,
    DomainRouteRule,
    DomainRouteRuleCreate,
    DomainRouteRuleResponse,
    DomainRouteRuleUpdate,
    RouteDecisionExplainRequest,
    RouteDecisionExplainResponse,
    RouteType,
    RoutingStatus,
)

router = APIRouter(prefix="/api/routing", tags=["routing"])

# Track last RU update time globally
_last_ru_update: datetime | None = None


async def _resolve_ipv4_addresses(domain: str) -> list[str]:
    """Resolve a domain to IPv4 addresses for DNS policy bindings."""
    try:
        results = await asyncio.get_event_loop().run_in_executor(
            None,
            lambda: socket.getaddrinfo(domain, None, socket.AF_INET),
        )
    except Exception:
        return []

    seen: dict[str, None] = {}
    for result in results:
        ip = result[4][0]
        if ip:
            seen[ip] = None
    return list(seen.keys())


policy_dns_observer = DNSObserver(_resolve_ipv4_addresses)


@router.get("/status", response_model=RoutingStatus)
async def get_routing_status(
    admin: CurrentAdmin,
    session: DBSession,
):
    """Get routing system status."""
    global _last_ru_update
    
    ipset_stats = await routing_manager.get_ipset_stats()
    tunnel_status = await routing_manager.check_tunnel_status()
    
    # Count custom routes
    result = await session.execute(select(CustomRoute).where(CustomRoute.is_active == True))
    custom_routes = result.scalars().all()
    
    return RoutingStatus(
        ru_ipset_entries=ipset_stats.get(routing_manager.IPSET_RU, {}).get("entries", 0),
        ru_ipset_status=ipset_stats.get(routing_manager.IPSET_RU, {}).get("status", "unknown"),
        tunnel_status=tunnel_status.get("status", "unknown"),
        custom_routes_count=len(custom_routes),
        last_ru_update=_last_ru_update,
    )


@router.post("/update-ru")
async def update_ru_ips(
    admin: CurrentAdmin,
):
    """Update Russian IP set."""
    global _last_ru_update
    
    success = await routing_manager.update_ru_ipset()
    
    if success:
        _last_ru_update = datetime.now(timezone.utc)
        return {"status": "updated", "updated_at": _last_ru_update.isoformat()}
    
    raise HTTPException(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        detail="Failed to update RU IPset",
    )


@router.get("/custom", response_model=list[CustomRouteResponse])
async def list_custom_routes(
    admin: CurrentAdmin,
    session: DBSession,
):
    """List all custom routes."""
    result = await session.execute(
        select(CustomRoute).order_by(CustomRoute.created_at.desc())
    )
    routes = result.scalars().all()
    
    return [
        CustomRouteResponse(
            id=r.id,
            address=r.address,
            route_type=r.route_type,
            description=r.description,
            is_active=r.is_active,
            created_at=r.created_at,
        )
        for r in routes
    ]


@router.post("/custom", response_model=CustomRouteResponse, status_code=status.HTTP_201_CREATED)
async def create_custom_route(
    data: CustomRouteCreate,
    admin: CurrentAdmin,
    session: DBSession,
):
    """Create a custom route."""
    # Check for duplicates
    result = await session.execute(
        select(CustomRoute).where(CustomRoute.address == data.address)
    )
    if result.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Route already exists",
        )
    
    route = CustomRoute(
        address=data.address.strip(),
        route_type=data.route_type,
        description=data.description,
    )
    
    session.add(route)
    await session.flush()
    await session.refresh(route)
    
    # Sync with ipset
    routes = await _get_all_routes(session)
    await routing_manager.sync_custom_routes(routes)
    
    return CustomRouteResponse(
        id=route.id,
        address=route.address,
        route_type=route.route_type,
        description=route.description,
        is_active=route.is_active,
        created_at=route.created_at,
    )


@router.delete("/custom/{route_id}")
async def delete_custom_route(
    route_id: int,
    admin: CurrentAdmin,
    session: DBSession,
):
    """Delete a custom route."""
    route = await session.get(CustomRoute, route_id)
    
    if not route:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Route not found",
        )
    
    await session.delete(route)
    await session.flush()
    
    # Sync with ipset
    routes = await _get_all_routes(session)
    await routing_manager.sync_custom_routes(routes)
    
    return {"status": "deleted"}


async def _get_all_routes(session) -> list[dict]:
    """Get all active routes as dicts."""
    result = await session.execute(
        select(CustomRoute).where(CustomRoute.is_active == True)
    )
    routes = result.scalars().all()
    return [
        {"address": r.address, "route_type": r.route_type.value}
        for r in routes
    ]


@router.get("/policy/domains", response_model=list[DomainRouteRuleResponse])
async def list_domain_route_rules(
    admin: CurrentAdmin,
    session: DBSession,
):
    """List stored domain policy rules."""
    del admin
    store = DomainRuleStore(session)
    return await store.list_domain_rules()


@router.post("/policy/domains", response_model=DomainRouteRuleResponse, status_code=status.HTTP_201_CREATED)
async def create_domain_route_rule(
    data: DomainRouteRuleCreate,
    admin: CurrentAdmin,
    session: DBSession,
):
    """Create a domain routing rule and refresh DNS bindings for active domains."""
    del admin
    store = DomainRuleStore(session)
    try:
        rule = await store.create_domain_rule(data)
    except RuleValidationError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    if rule.is_active:
        await policy_dns_observer.refresh_domain_bindings(rule)
    return rule


@router.put("/policy/domains/{rule_id}", response_model=DomainRouteRuleResponse)
async def update_domain_route_rule(
    rule_id: int,
    data: DomainRouteRuleUpdate,
    admin: CurrentAdmin,
    session: DBSession,
):
    """Update a domain routing rule and refresh or clear DNS bindings."""
    del admin
    store = DomainRuleStore(session)
    rule = await session.get(DomainRouteRule, rule_id)
    if rule is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Domain rule not found")

    rule = await store.update_domain_rule(rule, data)
    if rule.is_active:
        await policy_dns_observer.refresh_domain_bindings(rule)
    else:
        policy_dns_observer.clear_domain_bindings(rule.normalized_domain)
    return rule


@router.delete("/policy/domains/{rule_id}")
async def delete_domain_route_rule(
    rule_id: int,
    admin: CurrentAdmin,
    session: DBSession,
):
    """Delete a domain routing rule and clear DNS bindings."""
    del admin
    store = DomainRuleStore(session)
    rule = await session.get(DomainRouteRule, rule_id)
    if rule is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Domain rule not found")

    policy_dns_observer.clear_domain_bindings(rule.normalized_domain)
    await store.delete_domain_rule(rule)
    return {"status": "deleted"}


@router.get("/policy/cidrs", response_model=list[CidrRouteRuleResponse])
async def list_cidr_route_rules(
    admin: CurrentAdmin,
    session: DBSession,
):
    """List stored CIDR policy rules."""
    del admin
    store = DomainRuleStore(session)
    return await store.list_cidr_rules()


@router.post("/policy/cidrs", response_model=CidrRouteRuleResponse, status_code=status.HTTP_201_CREATED)
async def create_cidr_route_rule(
    data: CidrRouteRuleCreate,
    admin: CurrentAdmin,
    session: DBSession,
):
    """Create an explicit CIDR routing rule."""
    del admin
    store = DomainRuleStore(session)
    try:
        return await store.create_cidr_rule(data)
    except RuleValidationError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.put("/policy/cidrs/{rule_id}", response_model=CidrRouteRuleResponse)
async def update_cidr_route_rule(
    rule_id: int,
    data: CidrRouteRuleUpdate,
    admin: CurrentAdmin,
    session: DBSession,
):
    """Update an explicit CIDR routing rule."""
    del admin
    store = DomainRuleStore(session)
    rule = await session.get(CidrRouteRule, rule_id)
    if rule is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="CIDR rule not found")

    return await store.update_cidr_rule(rule, data)


@router.delete("/policy/cidrs/{rule_id}")
async def delete_cidr_route_rule(
    rule_id: int,
    admin: CurrentAdmin,
    session: DBSession,
):
    """Delete an explicit CIDR routing rule."""
    del admin
    store = DomainRuleStore(session)
    rule = await session.get(CidrRouteRule, rule_id)
    if rule is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="CIDR rule not found")

    await store.delete_cidr_rule(rule)
    return {"status": "deleted"}


@router.get("/policy/dns-bindings", response_model=list[ActiveDNSBindingResponse])
async def list_policy_dns_bindings(
    admin: CurrentAdmin,
):
    """List active DNS-derived bindings used by the route policy layer."""
    del admin
    return [
        ActiveDNSBindingResponse(
            normalized_domain=binding.normalized_domain,
            resolved_ip=binding.resolved_ip,
            route_target=binding.route_target,
            rule_id=binding.rule_id,
        )
        for binding in policy_dns_observer.get_active_bindings()
    ]


@router.post("/policy/explain", response_model=RouteDecisionExplainResponse)
async def explain_route_decision(
    data: RouteDecisionExplainRequest,
    admin: CurrentAdmin,
    session: DBSession,
):
    """Explain the effective route decision for a domain or IP input."""
    del admin
    store = DomainRuleStore(session)
    domain_rules = await store.list_active_domain_rules()
    cidr_rules = await store.list_active_cidr_rules()
    custom_routes = await _get_all_routes(session)

    decision = await routing_manager.resolve_effective_target(
        data.address,
        domain_rules=domain_rules,
        cidr_rules=cidr_rules,
        dns_bound_routes=policy_dns_observer.get_active_bindings(),
        custom_routes=custom_routes,
    )
    return RouteDecisionExplainResponse(
        address=data.address,
        route_target=decision.route_target,
        decision_reason=decision.reason.value,
        trace_marker=decision.trace_marker,
        rule_id=decision.rule_id,
        normalized_domain=decision.normalized_domain,
        resolved_ip=decision.resolved_ip,
    )

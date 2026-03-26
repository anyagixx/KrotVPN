"""
Admin API router for analytics and management.

MODULE_CONTRACT
- PURPOSE: Expose privileged admin analytics and system endpoints over current backend state.
- SCOPE: Dashboard statistics, revenue analytics, user analytics, system health, and privileged operational visibility.
- DEPENDS: M-001 auth and DB session injection, M-002 user models, M-003 vpn topology models, M-004 billing models, M-005 referral models, M-006 admin-api graph surface, M-016 route-policy observability dependencies.
- LINKS: M-006 admin-api, M-016 route-decision-api, V-M-006.

MODULE_MAP
- get_admin_stats: Aggregates dashboard metrics across users, subscriptions, revenue, VPN, and routing visibility.
- get_revenue_analytics: Returns grouped payment revenue analytics over a bounded date range.
- get_users_analytics: Returns grouped user registration analytics over a bounded date range.
- get_system_health: Returns coarse host health metrics for privileged operators.

CHANGE_SUMMARY
- 2026-03-24: Added route-aware admin statistics so dashboard reporting can surface node, route, rule, and DNS-binding state during routing migration.
"""
# <!-- GRACE: module="M-006" api-group="Admin API" -->

from datetime import datetime, timedelta

from fastapi import APIRouter, Query
from sqlalchemy import func, select
from sqlmodel import col

from app.core import CurrentAdmin, CurrentSuperuser, DBSession
from app.billing.models import Payment, PaymentStatus, Plan, Subscription
from app.referrals.models import Referral, ReferralCode
from app.routing.models import CidrRouteRule, DomainRouteRule
from app.routing.router import policy_dns_observer
from app.users.models import User, UserRole
from app.vpn.models import VPNClient, VPNNode, VPNRoute, VPNServer

router = APIRouter(prefix="/api/admin", tags=["admin"])


# ==================== Dashboard Stats ====================

@router.get("/stats")
async def get_admin_stats(
    admin: CurrentAdmin,
    session: DBSession,
):
    """Get admin dashboard statistics."""
    # Keep in mind that `online_servers` still counts legacy `VPNServer` rows,
    # so this endpoint is not yet a perfect reflection of the newer node/route topology.
    now = datetime.utcnow()
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    
    # Users count
    total_users = (await session.execute(select(func.count(User.id)))).scalar() or 0
    new_users_month = (await session.execute(
        select(func.count(User.id)).where(User.created_at >= month_start)
    )).scalar() or 0
    
    # Active subscriptions
    active_subs = (await session.execute(
        select(func.count(Subscription.id)).where(
            Subscription.is_active == True,
            Subscription.expires_at > now,
        )
    )).scalar() or 0
    
    # Trial subscriptions
    trial_subs = (await session.execute(
        select(func.count(Subscription.id)).where(
            Subscription.is_trial == True,
            Subscription.is_active == True,
            Subscription.expires_at > now,
        )
    )).scalar() or 0
    
    # Revenue this month
    revenue_month = (await session.execute(
        select(func.sum(Payment.amount)).where(
            Payment.status == PaymentStatus.SUCCEEDED,
            Payment.paid_at >= month_start,
        )
    )).scalar() or 0
    
    # Total revenue
    total_revenue = (await session.execute(
        select(func.sum(Payment.amount)).where(
            Payment.status == PaymentStatus.SUCCEEDED,
        )
    )).scalar() or 0
    
    # VPN clients
    active_vpn_clients = (await session.execute(
        select(func.count(VPNClient.id)).where(VPNClient.is_active == True)
    )).scalar() or 0
    
    # Servers
    online_servers = (await session.execute(
        select(func.count(VPNServer.id)).where(VPNServer.is_online == True)
    )).scalar() or 0

    # Route-aware topology summary
    active_nodes = (await session.execute(
        select(func.count(VPNNode.id)).where(VPNNode.is_active == True)
    )).scalar() or 0
    online_nodes = (await session.execute(
        select(func.count(VPNNode.id)).where(
            VPNNode.is_active == True,
            VPNNode.is_online == True,
        )
    )).scalar() or 0
    active_routes = (await session.execute(
        select(func.count(VPNRoute.id)).where(VPNRoute.is_active == True)
    )).scalar() or 0
    default_routes = (await session.execute(
        select(func.count(VPNRoute.id)).where(
            VPNRoute.is_active == True,
            VPNRoute.is_default == True,
        )
    )).scalar() or 0
    active_domain_rules = (await session.execute(
        select(func.count(DomainRouteRule.id)).where(DomainRouteRule.is_active == True)
    )).scalar() or 0
    active_cidr_rules = (await session.execute(
        select(func.count(CidrRouteRule.id)).where(CidrRouteRule.is_active == True)
    )).scalar() or 0
    active_dns_bindings = len(policy_dns_observer.get_active_bindings())

    return {
        "users": {
            "total": total_users,
            "new_this_month": new_users_month,
        },
        "subscriptions": {
            "active": active_subs,
            "trial": trial_subs,
        },
        "revenue": {
            "this_month": revenue_month,
            "total": total_revenue,
        },
        "vpn": {
            "active_clients": active_vpn_clients,
            "online_servers": online_servers,
            "online_servers_source": "legacy_vpn_server",
            "topology_note": "Legacy VPNServer mirror count; use routing summary for policy-driven topology.",
        },
        "routing": {
            "online_nodes": online_nodes,
            "active_nodes": active_nodes,
            "active_routes": active_routes,
            "default_routes": default_routes,
            "domain_rules_active": active_domain_rules,
            "cidr_rules_active": active_cidr_rules,
            "dns_bindings_active": active_dns_bindings,
            "policy_mode": "domain_first_with_ru_fallback",
        },
    }


@router.get("/analytics/revenue")
async def get_revenue_analytics(
    admin: CurrentAdmin,
    session: DBSession,
    days: int = Query(default=30, ge=1, le=365),
):
    """Get revenue analytics for the last N days."""
    now = datetime.utcnow()
    start_date = now - timedelta(days=days)
    
    # Daily revenue
    result = await session.execute(
        select(
            func.date(Payment.paid_at).label("date"),
            func.sum(Payment.amount).label("revenue"),
            func.count(Payment.id).label("payments"),
        )
        .where(
            Payment.status == PaymentStatus.SUCCEEDED,
            Payment.paid_at >= start_date,
        )
        .group_by(func.date(Payment.paid_at))
        .order_by(func.date(Payment.paid_at))
    )
    
    daily_data = [
        {
            "date": str(row.date),
            "revenue": float(row.revenue or 0),
            "payments": row.payments,
        }
        for row in result.all()
    ]
    
    return {
        "period_days": days,
        "daily": daily_data,
    }


@router.get("/analytics/users")
async def get_users_analytics(
    admin: CurrentAdmin,
    session: DBSession,
    days: int = Query(default=30, ge=1, le=365),
):
    """Get user registration analytics."""
    now = datetime.utcnow()
    start_date = now - timedelta(days=days)
    
    # Daily registrations
    result = await session.execute(
        select(
            func.date(User.created_at).label("date"),
            func.count(User.id).label("count"),
        )
        .where(User.created_at >= start_date)
        .group_by(func.date(User.created_at))
        .order_by(func.date(User.created_at))
    )
    
    daily_data = [
        {
            "date": str(row.date),
            "count": row.count,
        }
        for row in result.all()
    ]
    
    return {
        "period_days": days,
        "daily": daily_data,
    }


# ==================== System ====================

@router.get("/system/health")
async def get_system_health(
    admin: CurrentAdmin,
    session: DBSession,
):
    """Get system health status."""
    import psutil
    
    cpu_percent = psutil.cpu_percent(interval=0.5)
    mem = psutil.virtual_memory()
    disk = psutil.disk_usage('/')
    
    return {
        "cpu_percent": cpu_percent,
        "memory": {
            "total": mem.total,
            "used": mem.used,
            "percent": mem.percent,
        },
        "disk": {
            "total": disk.total,
            "used": disk.used,
            "percent": disk.percent,
        },
    }

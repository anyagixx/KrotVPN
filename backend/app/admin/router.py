"""
Admin API router for analytics and management.
"""
# <!-- GRACE: module="M-006" api-group="Admin API" -->

from datetime import datetime, timedelta

from fastapi import APIRouter, Query
from sqlalchemy import func, select
from sqlmodel import col

from app.core import CurrentAdmin, CurrentSuperuser, DBSession
from app.billing.models import Payment, PaymentStatus, Plan, Subscription
from app.referrals.models import Referral, ReferralCode
from app.users.models import User, UserRole
from app.vpn.models import VPNClient, VPNServer

router = APIRouter(prefix="/api/admin", tags=["admin"])


# ==================== Dashboard Stats ====================

@router.get("/stats")
async def get_admin_stats(
    admin: CurrentAdmin,
    session: DBSession,
):
    """Get admin dashboard statistics."""
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

"""
Billing API router.
"""
# <!-- GRACE: module="M-004" api-group="Billing API" -->

import json
from datetime import datetime

from fastapi import APIRouter, HTTPException, Request, status
from loguru import logger

from app.core import CurrentAdmin, CurrentUser, DBSession
from app.billing.models import (
    Payment,
    PaymentProvider,
    PaymentStatus,
    Plan,
    PlanResponse,
    PaymentResponse,
    Subscription,
    SubscriptionResponse,
    SubscriptionStatus,
)
from app.billing.schemas import (
    AdminSubscriptionUpdate,
    PaymentCreateRequest,
    PaymentHistoryResponse,
    PlanCreate,
    PlanUpdate,
    SubscribeRequest,
    SubscriptionStatusResponse,
)
from app.billing.service import BillingService

router = APIRouter(prefix="/api/billing", tags=["billing"])
admin_router = APIRouter(prefix="/api/admin/billing", tags=["admin"])


# ==================== Public Plan Endpoints ====================

@router.get("/plans", response_model=list[PlanResponse])
async def list_plans(
    session: DBSession,
):
    """List all active subscription plans."""
    service = BillingService(session)
    plans = await service.get_plans(active_only=True)
    
    return [
        PlanResponse(
            id=p.id,
            name=p.name,
            description=p.description,
            price=p.price,
            currency=p.currency,
            duration_days=p.duration_days,
            features=json.loads(p.features) if p.features else [],
            is_popular=p.is_popular,
        )
        for p in plans
    ]


# ==================== User Subscription Endpoints ====================

@router.get("/subscription", response_model=SubscriptionStatusResponse)
async def get_subscription_status(
    current_user: CurrentUser,
    session: DBSession,
):
    """Get current user's subscription status."""
    service = BillingService(session)
    subscription = await service.get_user_subscription(current_user.id)
    
    if not subscription:
        return SubscriptionStatusResponse(
            has_subscription=False,
            is_active=False,
            is_trial=False,
            plan_name=None,
            days_left=0,
            expires_at=None,
            is_recurring=False,
        )
    
    now = datetime.utcnow()
    days_left = max(0, (subscription.expires_at - now).days)
    
    # Get plan name
    plan_name = None
    if subscription.plan_id:
        plan = await service.get_plan(subscription.plan_id)
        plan_name = plan.name if plan else None
    
    return SubscriptionStatusResponse(
        has_subscription=True,
        is_active=subscription.is_active and subscription.expires_at > now,
        is_trial=subscription.is_trial,
        plan_name=plan_name or ("Trial" if subscription.is_trial else None),
        days_left=days_left,
        expires_at=subscription.expires_at,
        is_recurring=subscription.is_recurring,
    )


@router.get("/subscription/detail", response_model=SubscriptionResponse | None)
async def get_subscription_detail(
    current_user: CurrentUser,
    session: DBSession,
):
    """Get current user's subscription details."""
    service = BillingService(session)
    subscription = await service.get_user_subscription(current_user.id)
    
    if not subscription:
        return None
    
    now = datetime.utcnow()
    days_left = max(0, (subscription.expires_at - now).days)
    
    # Get plan name
    plan_name = None
    if subscription.plan_id:
        plan = await service.get_plan(subscription.plan_id)
        plan_name = plan.name if plan else None
    
    return SubscriptionResponse(
        id=subscription.id,
        plan_id=subscription.plan_id or 0,
        plan_name=plan_name or "Trial",
        status=subscription.status,
        is_active=subscription.is_active,
        started_at=subscription.started_at,
        expires_at=subscription.expires_at,
        days_left=days_left,
        is_trial=subscription.is_trial,
        is_recurring=subscription.is_recurring,
    )


# ==================== Payment Endpoints ====================

@router.post("/subscribe", response_model=PaymentResponse)
async def create_subscription_payment(
    data: SubscribeRequest,
    current_user: CurrentUser,
    session: DBSession,
    request: Request,
):
    """Create a payment for subscription."""
    service = BillingService(session)
    
    # Get plan
    plan = await service.get_plan(data.plan_id)
    if not plan or not plan.is_active:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Plan not found or inactive",
        )
    
    # Create payment
    return_url = str(request.url.replace(path="/subscription", query=""))
    payment = await service.create_payment(
        user_id=current_user.id,
        plan=plan,
        provider=data.provider,
        return_url=return_url,
    )
    
    return PaymentResponse(
        id=payment.id,
        amount=payment.amount,
        currency=payment.currency,
        provider=payment.provider,
        status=payment.status,
        payment_url=payment.payment_url,
        created_at=payment.created_at,
        paid_at=payment.paid_at,
    )


@router.get("/payments", response_model=PaymentHistoryResponse)
async def get_payment_history(
    current_user: CurrentUser,
    session: DBSession,
    limit: int = 20,
):
    """Get user's payment history."""
    service = BillingService(session)
    payments = await service.get_user_payments(current_user.id, limit)
    
    return PaymentHistoryResponse(
        items=[
            PaymentResponse(
                id=p.id,
                amount=p.amount,
                currency=p.currency,
                provider=p.provider,
                status=p.status,
                payment_url=p.payment_url,
                created_at=p.created_at,
                paid_at=p.paid_at,
            )
            for p in payments
        ],
        total=len(payments),
    )


# ==================== Webhooks ====================

@router.post("/webhooks/yookassa")
async def yookassa_webhook(
    request: Request,
    session: DBSession,
):
    """Handle YooKassa webhook notifications."""
    body = await request.body()
    data = await request.json()
    
    logger.info(f"[BILLING] YooKassa webhook: {data.get('event')}")
    
    service = BillingService(session)
    
    # Verify signature (optional but recommended)
    # signature = request.headers.get("X-Content-Signature", "")
    # if not yookassa_client.verify_webhook_signature(body, signature):
    #     raise HTTPException(status_code=400, detail="Invalid signature")
    
    payment = await service.process_payment_webhook(
        PaymentProvider.YOOKASSA,
        data,
    )
    
    if payment:
        return {"status": "ok", "payment_id": payment.id}
    
    return {"status": "ignored"}


# ==================== Admin Endpoints ====================

@admin_router.get("/plans", response_model=list[PlanResponse])
async def admin_list_plans(
    admin: CurrentAdmin,
    session: DBSession,
):
    """List all plans (admin)."""
    service = BillingService(session)
    plans = await service.get_plans(active_only=False)
    
    return [
        PlanResponse(
            id=p.id,
            name=p.name,
            description=p.description,
            price=p.price,
            currency=p.currency,
            duration_days=p.duration_days,
            features=json.loads(p.features) if p.features else [],
            is_popular=p.is_popular,
        )
        for p in plans
    ]


@admin_router.post("/plans", status_code=status.HTTP_201_CREATED)
async def admin_create_plan(
    data: PlanCreate,
    admin: CurrentAdmin,
    session: DBSession,
):
    """Create a new plan (admin)."""
    service = BillingService(session)
    plan = await service.create_plan(data.model_dump())
    
    return {"id": plan.id, "status": "created"}


@admin_router.put("/plans/{plan_id}")
async def admin_update_plan(
    plan_id: int,
    data: PlanUpdate,
    admin: CurrentAdmin,
    session: DBSession,
):
    """Update a plan (admin)."""
    service = BillingService(session)
    plan = await service.get_plan(plan_id)
    
    if not plan:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Plan not found",
        )
    
    update_data = data.model_dump(exclude_unset=True)
    
    if "features" in update_data and isinstance(update_data["features"], list):
        update_data["features"] = json.dumps(update_data["features"])
    
    for field, value in update_data.items():
        setattr(plan, field, value)
    
    await session.flush()
    
    return {"status": "updated"}


@admin_router.delete("/plans/{plan_id}")
async def admin_delete_plan(
    plan_id: int,
    admin: CurrentAdmin,
    session: DBSession,
):
    """Delete a plan (admin)."""
    service = BillingService(session)
    plan = await service.get_plan(plan_id)
    
    if not plan:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Plan not found",
        )
    
    # Soft delete - just deactivate
    plan.is_active = False
    await session.flush()
    
    return {"status": "deleted"}


@admin_router.get("/stats")
async def admin_get_billing_stats(
    admin: CurrentAdmin,
    session: DBSession,
):
    """Get billing statistics (admin)."""
    service = BillingService(session)
    stats = await service.get_subscription_stats()
    return stats


@admin_router.put("/subscriptions/{subscription_id}")
async def admin_update_subscription(
    subscription_id: int,
    data: AdminSubscriptionUpdate,
    admin: CurrentAdmin,
    session: DBSession,
):
    """Update a subscription (admin)."""
    subscription = await session.get(Subscription, subscription_id)
    
    if not subscription:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Subscription not found",
        )
    
    update_data = data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(subscription, field, value)
    
    await session.flush()
    
    return {"status": "updated"}


@admin_router.post("/subscriptions/{subscription_id}/extend")
async def admin_extend_subscription(
    subscription_id: int,
    days: int,
    admin: CurrentAdmin,
    session: DBSession,
):
    """Extend a subscription by given days (admin)."""
    service = BillingService(session)
    subscription = await session.get(Subscription, subscription_id)
    
    if not subscription:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Subscription not found",
        )
    
    await service.extend_subscription(subscription, days)
    
    return {"status": "extended", "days": days}

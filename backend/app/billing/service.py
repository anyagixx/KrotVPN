"""
Billing service for subscription and payment management.

GRACE-lite module contract:
- Owns plans, subscriptions, payment records and webhook side effects.
- `payment succeeded` is the critical business event: it may extend subscriptions,
  provision VPN access and trigger referral bonuses.
- Webhook handling must remain idempotent.
- Billing changes are security-sensitive and money-sensitive even when code diffs look small.

CHANGE_SUMMARY
- 2026-03-26: Added complimentary internal-access helpers so manual non-billable clients can stay inside the subscription model.
- 2026-03-27: Added effective device-limit helpers so device-bound provisioning can enforce per-plan limits before peer creation.
"""
# <!-- GRACE: module="M-004" contract="billing-service" -->

import json
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.billing.models import (
    Payment,
    PaymentProvider,
    PaymentStatus,
    Plan,
    Subscription,
    SubscriptionStatus,
)
from app.billing.yookassa import yookassa_client
from loguru import logger


class BillingService:
    """Service for billing operations."""
    
    def __init__(self, session: AsyncSession):
        self.session = session
        self.yookassa = yookassa_client
    
    # ==================== Plans ====================
    
    async def get_plans(self, active_only: bool = True) -> list[Plan]:
        """Get all subscription plans."""
        query = select(Plan)
        
        if active_only:
            query = query.where(Plan.is_active == True)
        
        query = query.order_by(Plan.sort_order, Plan.price)
        
        result = await self.session.execute(query)
        return list(result.scalars().all())
    
    async def get_plan(self, plan_id: int) -> Plan | None:
        """Get plan by ID."""
        return await self.session.get(Plan, plan_id)
    
    async def create_plan(self, data: dict) -> Plan:
        """Create a new plan."""
        plan = Plan(
            name=data["name"],
            description=data.get("description"),
            price=data["price"],
            currency=data.get("currency", "RUB"),
            duration_days=data["duration_days"],
            device_limit=data.get("device_limit", 1),
            features=json.dumps(data.get("features", [])),
            is_popular=data.get("is_popular", False),
            sort_order=data.get("sort_order", 0),
        )
        
        self.session.add(plan)
        await self.session.flush()
        await self.session.refresh(plan)
        
        logger.info(f"[BILLING] Plan created: {plan.name}")
        return plan
    
    # ==================== Subscriptions ====================
    
    async def get_user_subscription(self, user_id: int) -> Subscription | None:
        """Get user's active subscription."""
        now = datetime.utcnow()
        
        result = await self.session.execute(
            select(Subscription)
            .where(
                Subscription.user_id == user_id,
                Subscription.is_active == True,
                Subscription.expires_at > now,
            )
            .order_by(Subscription.expires_at.desc())
        )
        return result.scalar_one_or_none()

    async def get_effective_device_limit(self, user_id: int) -> int:
        """Resolve the device limit for one user from the active subscription context."""
        subscription = await self.get_user_subscription(user_id)
        if subscription is None:
            return 0

        if subscription.is_complimentary:
            return 9999

        if subscription.plan_id is None:
            return 1

        plan = await self.get_plan(subscription.plan_id)
        if plan is None:
            return 1
        return max(1, int(plan.device_limit))
    
    async def get_user_subscription_history(
        self, user_id: int, limit: int = 10
    ) -> list[Subscription]:
        """Get user's subscription history."""
        result = await self.session.execute(
            select(Subscription)
            .where(Subscription.user_id == user_id)
            .order_by(Subscription.created_at.desc())
            .limit(limit)
        )
        return list(result.scalars().all())

    async def get_active_complimentary_access(
        self,
        user_id: int,
        access_label: str | None = None,
    ) -> Subscription | None:
        """Return the current complimentary access record for one user."""
        now = datetime.utcnow()
        query = (
            select(Subscription)
            .where(
                Subscription.user_id == user_id,
                Subscription.is_complimentary == True,
                Subscription.is_active == True,
                Subscription.expires_at > now,
            )
            .order_by(Subscription.expires_at.desc())
        )
        if access_label is not None:
            query = query.where(Subscription.access_label == access_label)

        result = await self.session.execute(query)
        return result.scalar_one_or_none()

    async def create_trial_subscription(self, user_id: int) -> Subscription:
        """Create a trial subscription for new user."""
        now = datetime.utcnow()
        expires_at = now + timedelta(days=settings.trial_days)
        
        subscription = Subscription(
            user_id=user_id,
            plan_id=None,  # Trial has no plan
            status=SubscriptionStatus.TRIAL,
            is_active=True,
            is_trial=True,
            started_at=now,
            expires_at=expires_at,
        )
        
        self.session.add(subscription)
        await self.session.flush()
        await self.session.refresh(subscription)
        
        logger.info(f"[BILLING] Trial subscription created for user {user_id}")
        return subscription

    async def ensure_complimentary_access(
        self,
        user_id: int,
        *,
        access_label: str = "internal-unlimited",
        duration_days: int = 36500,
    ) -> Subscription:
        """Create or reuse explicit complimentary access for internal users."""
        existing = await self.get_active_complimentary_access(
            user_id,
            access_label=access_label,
        )
        if existing is not None:
            logger.info(
                "[Billing][internal][VPN_INTERNAL_ACCESS_GRANTED] "
                f"user_id={user_id} subscription_id={existing.id} "
                f"complimentary=true access_label={access_label} reused=true"
            )
            return existing

        now = datetime.utcnow()
        expires_at = now + timedelta(days=duration_days)

        result = await self.session.execute(
            select(Subscription)
            .where(
                Subscription.user_id == user_id,
                Subscription.is_complimentary == True,
            )
            .order_by(Subscription.created_at.desc())
        )
        subscription = result.scalar_one_or_none()

        if subscription is None:
            subscription = Subscription(
                user_id=user_id,
                plan_id=None,
                status=SubscriptionStatus.ACTIVE,
                is_active=True,
                started_at=now,
                expires_at=expires_at,
                is_trial=False,
                is_complimentary=True,
                access_label=access_label,
            )
            self.session.add(subscription)
        else:
            subscription.status = SubscriptionStatus.ACTIVE
            subscription.is_active = True
            subscription.is_trial = False
            subscription.is_complimentary = True
            subscription.access_label = access_label
            subscription.started_at = subscription.started_at or now
            subscription.expires_at = expires_at
            subscription.updated_at = now

        await self.session.flush()
        await self.session.refresh(subscription)
        logger.info(
            "[Billing][internal][VPN_INTERNAL_ACCESS_GRANTED] "
            f"user_id={user_id} subscription_id={subscription.id} "
            f"complimentary=true access_label={access_label} reused=false"
        )
        return subscription

    async def create_subscription(
        self,
        user_id: int,
        plan: Plan,
        payment: Payment | None = None,
    ) -> Subscription:
        """Create a subscription from a plan."""
        now = datetime.utcnow()
        
        # Check for existing active subscription
        existing = await self.get_user_subscription(user_id)
        
        if existing:
            # Extend existing subscription
            new_expires = existing.expires_at + timedelta(days=plan.duration_days)
            existing.expires_at = new_expires
            existing.status = SubscriptionStatus.ACTIVE
            existing.is_trial = False
            existing.is_complimentary = False
            existing.access_label = None
            existing.plan_id = plan.id
            
            if payment:
                existing.is_recurring = bool(
                    payment.payment_metadata
                    and json.loads(payment.payment_metadata).get("save_payment_method")
                )
            
            await self.session.flush()
            await self.session.refresh(existing)
            
            logger.info(f"[BILLING] Subscription extended for user {user_id}")
            return existing
        
        # Create new subscription
        expires_at = now + timedelta(days=plan.duration_days)
        
        subscription = Subscription(
            user_id=user_id,
            plan_id=plan.id,
            status=SubscriptionStatus.ACTIVE,
            is_active=True,
            is_trial=False,
            is_complimentary=False,
            started_at=now,
            expires_at=expires_at,
        )
        
        self.session.add(subscription)
        await self.session.flush()
        await self.session.refresh(subscription)
        
        logger.info(f"[BILLING] Subscription created for user {user_id}")
        return subscription
    
    async def extend_subscription(
        self,
        subscription: Subscription,
        days: int,
    ) -> Subscription:
        """Extend a subscription by given days."""
        now = datetime.utcnow()
        
        # If expired, start from now
        base = max(subscription.expires_at, now)
        subscription.expires_at = base + timedelta(days=days)
        subscription.status = SubscriptionStatus.ACTIVE
        subscription.is_active = True
        subscription.updated_at = now

        await self.session.flush()
        await self.session.refresh(subscription)
        
        logger.info(f"[BILLING] Subscription {subscription.id} extended by {days} days")
        return subscription
    
    async def deactivate_subscription(self, subscription: Subscription) -> None:
        """Deactivate a subscription."""
        subscription.is_active = False
        subscription.status = SubscriptionStatus.CANCELED
        await self.session.flush()
        
        logger.info(f"[BILLING] Subscription {subscription.id} deactivated")
    
    # ==================== Payments ====================
    
    async def create_payment(
        self,
        user_id: int,
        plan: Plan,
        provider: PaymentProvider = PaymentProvider.YOOKASSA,
        return_url: str | None = None,
    ) -> Payment:
        """Create a payment for a plan."""
        # Create payment record
        payment = Payment(
            user_id=user_id,
            plan_id=plan.id,
            amount=plan.price,
            currency=plan.currency,
            provider=provider,
            status=PaymentStatus.PENDING,
            description=f"Подписка: {plan.name}",
        )
        
        self.session.add(payment)
        await self.session.flush()
        
        # Create payment in provider
        if provider == PaymentProvider.YOOKASSA:
            try:
                yookassa_payment = await self.yookassa.create_payment(
                    amount=plan.price,
                    currency=plan.currency,
                    description=f"KrotVPN - {plan.name}",
                    return_url=return_url,
                    metadata={
                        "user_id": user_id,
                        "plan_id": plan.id,
                        "payment_id": payment.id,
                    },
                )
                
                payment.external_id = yookassa_payment["id"]
                payment.payment_url = yookassa_payment["confirmation"].get("url")
                
                logger.info(f"[BILLING] YooKassa payment created: {payment.external_id}")
                
            except Exception as e:
                logger.error(f"[BILLING] YooKassa error: {e}")
                payment.status = PaymentStatus.FAILED
                payment.description = str(e)
        
        await self.session.flush()
        await self.session.refresh(payment)
        
        return payment
    
    async def process_payment_webhook(
        self,
        provider: PaymentProvider,
        data: dict[str, Any],
    ) -> Payment | None:
        """Process payment webhook from provider."""
        if provider == PaymentProvider.YOOKASSA:
            return await self._process_yookassa_webhook(data)
        
        return None
    
    async def _process_yookassa_webhook(self, data: dict) -> Payment | None:
        """Process YooKassa webhook."""
        # Keep this path idempotent. Providers can resend the same event,
        # and duplicate subscription/referral effects would be a production bug.
        event = data.get("event")
        payment_object = data.get("object", {})
        
        if event not in ("payment.succeeded", "payment.canceled", "payment.waiting_for_capture"):
            logger.debug(f"[BILLING] Ignoring YooKassa event: {event}")
            return None
        
        external_id = payment_object.get("id")
        status = payment_object.get("status")
        
        # Find payment by external ID
        result = await self.session.execute(
            select(Payment).where(Payment.external_id == external_id)
        )
        payment = result.scalar_one_or_none()
        
        if not payment:
            logger.warning(f"[BILLING] Payment not found for external_id: {external_id}")
            return None
        
        # Update payment status
        if status == "succeeded":
            if payment.status == PaymentStatus.SUCCEEDED:
                logger.info(f"[BILLING] Duplicate succeeded webhook ignored for payment {payment.id}")
                return payment

            payment.status = PaymentStatus.SUCCEEDED
            payment.paid_at = datetime.utcnow()
            
            # Create subscription
            plan = await self.get_plan(payment.plan_id)
            if plan:
                await self.create_subscription(payment.user_id, plan, payment)
                
                # Create VPN client if not exists
                from app.vpn.service import VPNService
                vpn_service = VPNService(self.session)
                existing_client = await vpn_service.get_user_client(payment.user_id)
                if not existing_client:
                    await vpn_service.create_client(payment.user_id)

                from app.referrals.service import ReferralService
                referral_service = ReferralService(self.session)
                await referral_service.process_first_payment(
                    payment.user_id,
                    payment.amount,
                )
            
            logger.info(f"[BILLING] Payment {payment.id} succeeded")
            
        elif status == "canceled":
            if payment.status == PaymentStatus.CANCELED:
                logger.info(f"[BILLING] Duplicate canceled webhook ignored for payment {payment.id}")
                return payment

            payment.status = PaymentStatus.CANCELED
            logger.info(f"[BILLING] Payment {payment.id} canceled")
        
        payment.updated_at = datetime.utcnow()
        await self.session.flush()
        
        return payment
    
    async def get_user_payments(
        self, user_id: int, limit: int = 20
    ) -> list[Payment]:
        """Get user's payment history."""
        result = await self.session.execute(
            select(Payment)
            .where(Payment.user_id == user_id)
            .order_by(Payment.created_at.desc())
            .limit(limit)
        )
        return list(result.scalars().all())
    
    # ==================== Stats ====================
    
    async def get_subscription_stats(self) -> dict[str, Any]:
        """Get subscription statistics."""
        now = datetime.utcnow()
        
        # Active subscriptions
        active_result = await self.session.execute(
            select(func.count(Subscription.id)).where(
                Subscription.is_active == True,
                Subscription.is_complimentary == False,
                Subscription.expires_at > now,
            )
        )
        active_count = active_result.scalar() or 0
        
        # Trial subscriptions
        trial_result = await self.session.execute(
            select(func.count(Subscription.id)).where(
                Subscription.is_trial == True,
                Subscription.is_active == True,
                Subscription.is_complimentary == False,
                Subscription.expires_at > now,
            )
        )
        trial_count = trial_result.scalar() or 0
        
        # Expired this month
        month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        expired_result = await self.session.execute(
            select(func.count(Subscription.id)).where(
                Subscription.expires_at >= month_start,
                Subscription.expires_at < now,
            )
        )
        expired_count = expired_result.scalar() or 0
        
        # Revenue this month
        revenue_result = await self.session.execute(
            select(func.sum(Payment.amount)).where(
                Payment.status == PaymentStatus.SUCCEEDED,
                Payment.paid_at >= month_start,
            )
        )
        revenue = revenue_result.scalar() or 0
        
        return {
            "active_subscriptions": active_count,
            "trial_subscriptions": trial_count,
            "expired_this_month": expired_count,
            "revenue_this_month": revenue,
        }

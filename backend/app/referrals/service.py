"""
Referral service for managing referral program.
"""
# <!-- GRACE: module="M-005" contract="referral-service" -->

import random
import string
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.referrals.models import Referral, ReferralCode, ReferralStats
from loguru import logger


class ReferralService:
    """Service for referral operations."""
    
    def __init__(self, session: AsyncSession):
        self.session = session
    
    def _generate_code(self, length: int = 8) -> str:
        """Generate a random referral code."""
        chars = string.ascii_uppercase + string.digits
        return ''.join(random.choices(chars, k=length))
    
    async def get_or_create_code(self, user_id: int) -> ReferralCode:
        """Get or create referral code for user."""
        result = await self.session.execute(
            select(ReferralCode).where(ReferralCode.user_id == user_id)
        )
        code = result.scalar_one_or_none()
        
        if code:
            return code
        
        # Generate unique code
        while True:
            new_code = self._generate_code()
            existing = await self.session.execute(
                select(ReferralCode).where(ReferralCode.code == new_code)
            )
            if not existing.scalar_one_or_none():
                break
        
        code = ReferralCode(
            user_id=user_id,
            code=new_code,
        )
        
        self.session.add(code)
        await self.session.flush()
        await self.session.refresh(code)
        
        logger.info(f"[REFERRAL] Created code {new_code} for user {user_id}")
        return code
    
    async def get_code_by_code(self, code: str) -> ReferralCode | None:
        """Get referral code by code string."""
        result = await self.session.execute(
            select(ReferralCode).where(ReferralCode.code == code.upper())
        )
        return result.scalar_one_or_none()
    
    async def create_referral(
        self,
        referrer_id: int,
        referred_id: int,
    ) -> Referral | None:
        """Create a referral relationship."""
        # Check if already referred
        result = await self.session.execute(
            select(Referral).where(Referral.referred_id == referred_id)
        )
        if result.scalar_one_or_none():
            return None
        
        # Don't allow self-referral
        if referrer_id == referred_id:
            return None
        
        referral = Referral(
            referrer_id=referrer_id,
            referred_id=referred_id,
        )
        
        self.session.add(referral)
        
        # Update code uses count
        code_result = await self.session.execute(
            select(ReferralCode).where(ReferralCode.user_id == referrer_id)
        )
        code = code_result.scalar_one_or_none()
        if code:
            code.uses_count += 1
        
        await self.session.flush()
        await self.session.refresh(referral)
        
        logger.info(f"[REFERRAL] Created referral: {referrer_id} -> {referred_id}")
        return referral
    
    async def process_first_payment(
        self,
        user_id: int,
        amount: float,
    ) -> bool:
        """
        Process referral bonus on first payment.
        
        Returns True if bonus was given.
        """
        # Find referral
        result = await self.session.execute(
            select(Referral).where(Referral.referred_id == user_id)
        )
        referral = result.scalar_one_or_none()
        
        if not referral or referral.bonus_given:
            return False
        
        # Check minimum payment amount
        if amount < settings.referral_min_payment:
            return False
        
        # Give bonus to referrer
        referral.bonus_given = True
        referral.bonus_days = settings.referral_bonus_days
        referral.first_payment_at = datetime.utcnow()
        referral.first_payment_amount = amount
        
        # Update referrer's code stats
        code_result = await self.session.execute(
            select(ReferralCode).where(ReferralCode.user_id == referral.referrer_id)
        )
        code = code_result.scalar_one_or_none()
        if code:
            code.bonus_earned_days += settings.referral_bonus_days
        
        # Extend referrer's subscription
        from app.billing.service import BillingService
        billing_service = BillingService(self.session)
        
        subscription_result = await self.session.execute(
            select(Referral).where(Referral.referred_id == user_id)
        )
        
        # Get referrer's active subscription
        from app.billing.models import Subscription
        sub_result = await self.session.execute(
            select(Subscription)
            .where(
                Subscription.user_id == referral.referrer_id,
                Subscription.is_active == True,
            )
            .order_by(Subscription.expires_at.desc())
        )
        subscription = sub_result.scalar_one_or_none()
        
        if subscription:
            await billing_service.extend_subscription(
                subscription, settings.referral_bonus_days
            )
        
        await self.session.flush()
        
        logger.info(
            f"[REFERRAL] Bonus given: {settings.referral_bonus_days} days "
            f"to user {referral.referrer_id} for referral {user_id}"
        )
        
        return True
    
    async def get_referral_stats(self, user_id: int) -> ReferralStats:
        """Get referral statistics for user."""
        # Get code
        code = await self.get_or_create_code(user_id)
        
        # Get stats
        result = await self.session.execute(
            select(
                func.count(Referral.id).label("total"),
                func.sum(func.case((Referral.bonus_given == True, 1), else_=0)).label("paid"),
                func.coalesce(func.sum(func.case(
                    (Referral.bonus_given == True, Referral.bonus_days),
                    else_=0
                )), 0).label("bonus_days"),
            ).where(Referral.referrer_id == user_id)
        )
        row = result.one()
        
        return ReferralStats(
            code=code.code,
            link=f"https://krotvpn.com/register?ref={code.code}",
            total_referrals=row.total or 0,
            paid_referrals=row.paid or 0,
            bonus_days_earned=row.bonus_days or 0,
            bonus_days_available=code.bonus_earned_days,
        )
    
    async def get_referrals_list(
        self,
        user_id: int,
        limit: int = 50,
    ) -> list[Referral]:
        """Get list of referrals for user."""
        result = await self.session.execute(
            select(Referral)
            .where(Referral.referrer_id == user_id)
            .order_by(Referral.created_at.desc())
            .limit(limit)
        )
        return list(result.scalars().all())

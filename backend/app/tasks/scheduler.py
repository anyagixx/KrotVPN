"""
Background tasks scheduler.
"""
# <!-- GRACE: module="M-012" contract="scheduler" -->

from datetime import datetime

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger
from loguru import logger

from app.core.database import async_session_maker


class TaskScheduler:
    """Scheduler for background tasks."""
    
    def __init__(self):
        self.scheduler = AsyncIOScheduler()
    
    def start(self):
        """Start the scheduler."""
        # Subscription expiry check - every hour
        self.scheduler.add_job(
            check_subscription_expiry,
            IntervalTrigger(hours=1),
            id="check_subscription_expiry",
            replace_existing=True,
        )
        
        # VPN stats update - every 5 minutes
        self.scheduler.add_job(
            update_vpn_stats,
            IntervalTrigger(minutes=5),
            id="update_vpn_stats",
            replace_existing=True,
        )
        
        # Daily cleanup - at 3 AM
        self.scheduler.add_job(
            daily_cleanup,
            CronTrigger(hour=3, minute=0),
            id="daily_cleanup",
            replace_existing=True,
        )
        
        # Weekly report - Monday at 9 AM
        self.scheduler.add_job(
            weekly_report,
            CronTrigger(day_of_week="mon", hour=9, minute=0),
            id="weekly_report",
            replace_existing=True,
        )
        
        self.scheduler.start()
        logger.info("[TASKS] Scheduler started")
    
    def stop(self):
        """Stop the scheduler."""
        self.scheduler.shutdown()
        logger.info("[TASKS] Scheduler stopped")


# Global scheduler
task_scheduler = TaskScheduler()


# ==================== Tasks ====================

async def check_subscription_expiry():
    """
    Check for expired subscriptions and deactivate them.
    """
    logger.info("[TASKS] Checking subscription expiry...")
    
    async with async_session_maker() as session:
        from sqlalchemy import select, update
        from app.billing.models import Subscription, SubscriptionStatus
        
        now = datetime.utcnow()
        
        # Find expired but still active subscriptions
        result = await session.execute(
            select(Subscription)
            .where(
                Subscription.is_active == True,
                Subscription.expires_at <= now,
            )
        )
        expired = result.scalars().all()
        
        for sub in expired:
            sub.is_active = False
            sub.status = SubscriptionStatus.EXPIRED
            
            # Deactivate VPN client
            from app.vpn.models import VPNClient
            from app.vpn.amneziawg import wg_manager
            
            client_result = await session.execute(
                select(VPNClient).where(
                    VPNClient.user_id == sub.user_id,
                    VPNClient.is_active == True,
                )
            )
            client = client_result.scalar_one_or_none()
            
            if client:
                client.is_active = False
                await wg_manager.remove_peer(client.public_key)
            
            logger.info(f"[TASKS] Subscription {sub.id} expired for user {sub.user_id}")
        
        await session.commit()
        
        if expired:
            logger.info(f"[TASKS] Deactivated {len(expired)} expired subscriptions")


async def update_vpn_stats():
    """
    Update VPN client statistics from AmneziaWG.
    """
    logger.debug("[TASKS] Updating VPN stats...")
    
    async with async_session_maker() as session:
        from sqlalchemy import select
        from app.vpn.models import VPNClient
        from app.vpn.amneziawg import wg_manager
        
        result = await session.execute(
            select(VPNClient).where(VPNClient.is_active == True)
        )
        clients = result.scalars().all()
        
        # Get peer stats
        stats = await wg_manager.get_peer_stats()
        
        updated = 0
        for client in clients:
            if client.public_key in stats:
                peer_stats = stats[client.public_key]
                client.total_upload_bytes = peer_stats["upload"]
                client.total_download_bytes = peer_stats["download"]
                client.last_handshake_at = peer_stats["last_handshake"]
                client.updated_at = datetime.utcnow()
                updated += 1
        
        await session.commit()
        
        if updated > 0:
            logger.debug(f"[TASKS] Updated stats for {updated} clients")


async def daily_cleanup():
    """
    Daily cleanup tasks.
    """
    logger.info("[TASKS] Running daily cleanup...")
    
    async with async_session_maker() as session:
        from sqlalchemy import delete
        from datetime import timedelta
        
        # Clean old failed payments (older than 30 days)
        from app.billing.models import Payment, PaymentStatus
        
        cutoff = datetime.utcnow() - timedelta(days=30)
        
        result = await session.execute(
            delete(Payment)
            .where(
                Payment.status == PaymentStatus.FAILED,
                Payment.created_at < cutoff,
            )
        )
        
        await session.commit()
        
        logger.info(f"[TASKS] Cleaned {result.rowcount} old failed payments")


async def weekly_report():
    """
    Generate weekly report.
    """
    logger.info("[TASKS] Generating weekly report...")
    
    async with async_session_maker() as session:
        from app.billing.service import BillingService
        
        service = BillingService(session)
        stats = await service.get_subscription_stats()
        
        # TODO: Send report via email or Telegram
        logger.info(f"[TASKS] Weekly stats: {stats}")

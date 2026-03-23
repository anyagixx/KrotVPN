"""VPN module exports."""
from app.vpn.models import VPNClient, VPNConfig, VPNServer, VPNStats
from app.vpn.amneziawg import AmneziaWGManager, wg_manager
from app.vpn.service import VPNService
from app.vpn.router import router as vpn_router
from app.vpn.router import admin_router as admin_vpn_router

__all__ = [
    # Models
    "VPNClient",
    "VPNServer",
    "VPNConfig",
    "VPNStats",
    # AmneziaWG
    "AmneziaWGManager",
    "wg_manager",
    # Service
    "VPNService",
    # Routers
    "vpn_router",
    "admin_vpn_router",
]

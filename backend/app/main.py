"""
KrotVPN - Commercial VPN Service with AmneziaWG
Main FastAPI application.

GRACE-lite entry contract:
- This is the backend runtime entry point and router assembly root.
- Lifespan startup is side-effectful: DB init, admin bootstrap, VPN bootstrap and scheduler start happen here.
- Production and non-production differ in routing initialization behavior.
- Any startup change here can affect the whole product surface at boot time.
"""
# <!-- GRACE: entry-point="EP-001" -->

from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncGenerator

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from loguru import logger
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

from app.core.config import settings
from app.core.database import init_db, get_db_context
from app.core.init_admin import ensure_admin_user
from app.core.init_vpn import ensure_default_vpn_server, ensure_default_vpn_topology

# Import routers
from app.users.router import router as auth_router
from app.users.router import users_router
from app.users.router import admin_users_router as admin_users_router
from app.vpn.router import router as vpn_router
from app.vpn.router import admin_router as admin_vpn_router
from app.vpn.router import admin_nodes_router as admin_vpn_nodes_router
from app.vpn.router import admin_routes_router as admin_vpn_routes_router
from app.routing.router import router as routing_router
from app.billing.router import router as billing_router
from app.billing.router import admin_router as admin_billing_router
from app.referrals.router import router as referral_router
from app.referrals.router import admin_router as admin_referral_router
from app.admin.router import router as admin_router
from app.devices.router import router as devices_router

# Configure logging
try:
    logs_dir = Path("logs")
    logs_dir.mkdir(parents=True, exist_ok=True)
    logger.add(
        logs_dir / "krotvpn_{time}.log",
        rotation="1 day",
        retention="7 days",
        level="INFO",
        format="{time:YYYY-MM-DD HH:mm:ss} | {level} | {message}",
    )
except OSError as exc:
    logger.warning(f"[APP] File logging disabled: {exc}")

# Rate limiter
limiter = Limiter(key_func=get_remote_address)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Application lifespan handler."""
    # Startup order matters: DB first, bootstrap second, scheduler last.
    # If initialization behavior changes, keep docs/current-status.xml and docs/knowledge-graph.xml in sync.
    # Startup
    logger.info(f"[APP] Starting {settings.app_name} v{settings.app_version}")
    logger.info(f"[APP] Environment: {settings.environment}")
    
    # Initialize database
    await init_db()
    logger.info("[APP] Database initialized")
    
    # Initialize admin user from environment variables
    async with get_db_context() as session:
        admin_user = await ensure_admin_user(session)
        if admin_user:
            logger.info(f"[APP] Admin user ready: {admin_user.email}")
        else:
            logger.info("[APP] No admin credentials configured in .env")

        vpn_server = await ensure_default_vpn_server(session)
        if vpn_server:
            logger.info(f"[APP] VPN server ready: {vpn_server.name} ({vpn_server.endpoint})")
        else:
            logger.info("[APP] No default VPN server configured in .env")

        vpn_route = await ensure_default_vpn_topology(session, legacy_server=vpn_server)
        if vpn_route:
            logger.info(f"[APP] VPN route ready: {vpn_route.name}")
        else:
            logger.info("[APP] VPN route bootstrap skipped or incomplete")
    
    # Production routing is managed by host-level systemd scripts.
    if settings.is_production:
        logger.info("[APP] Routing manager skipped in production (host-managed)")
    else:
        from app.routing import routing_manager
        await routing_manager.initialize()
        logger.info("[APP] Routing manager initialized")
    
    # Start task scheduler
    from app.tasks import task_scheduler
    task_scheduler.start()
    logger.info("[APP] Task scheduler started")
    
    yield
    
    # Shutdown
    from app.tasks import task_scheduler
    task_scheduler.stop()
    logger.info("[APP] Shutting down...")


# Create application
app = FastAPI(
    title=settings.app_name,
    description="Commercial VPN Service with AmneziaWG for bypassing Russian censorship",
    version=settings.app_version,
    docs_url="/docs" if settings.debug else None,
    redoc_url="/redoc" if settings.debug else None,
    lifespan=lifespan,
)

# Rate limiting
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Exception handlers
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Global exception handler."""
    logger.error(f"[ERROR] Unhandled exception: {exc}", exc_info=True)
    
    if settings.debug:
        return JSONResponse(
            status_code=500,
            content={"detail": str(exc)},
        )
    
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error"},
    )


# Health check
@app.get("/health")
async def health_check() -> dict:
    """Health check endpoint."""
    return {
        "status": "healthy",
        "version": settings.app_version,
        "environment": settings.environment,
    }


@app.get("/")
async def root() -> dict:
    """Root endpoint."""
    return {
        "name": settings.app_name,
        "version": settings.app_version,
        "docs": "/docs" if settings.debug else "disabled",
    }


# Include routers - Auth & Users
app.include_router(auth_router)
app.include_router(users_router)
app.include_router(admin_users_router)

# VPN
app.include_router(vpn_router)
app.include_router(devices_router)
app.include_router(admin_vpn_router)
app.include_router(admin_vpn_nodes_router)
app.include_router(admin_vpn_routes_router)

# Routing
app.include_router(routing_router)

# Billing
app.include_router(billing_router)
app.include_router(admin_billing_router)

# Referrals
app.include_router(referral_router)
app.include_router(admin_referral_router)

# Admin
app.include_router(admin_router)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "app.main:app",
        host=settings.host,
        port=settings.port,
        reload=settings.debug,
    )

"""
User API router.

GRACE-lite module contract:
- Exposes auth, current-user and admin user-management endpoints.
- Registration is intentionally side-effectful: it may create trial subscription,
  VPN access and referral linkage in the same request path.
- Telegram auth accepts either a valid Telegram-signed payload or an internal bot call header.
"""
# <!-- GRACE: module="M-002" api-group="Auth API, User API" -->

from datetime import timedelta

from fastapi import APIRouter, Header, HTTPException, Request, status
from slowapi import Limiter
from slowapi.util import get_remote_address

from app.core import (
    CurrentAdmin,
    CurrentUser,
    DBSession,
    create_access_token,
    create_refresh_token,
    settings,
    verify_token,
)
from app.users.telegram_auth import verify_telegram_auth
from app.users.models import UserRole
from app.users.schemas import (
    Token,
    TokenRefresh,
    UserAdminResponse,
    UserAdminUpdate,
    UserChangePassword,
    UserCreate,
    UserCreateTelegram,
    UserListResponse,
    UserLogin,
    UserResponse,
    UserStatsResponse,
    UserUpdate,
)
from app.users.service import UserService
from app.devices.service import DeviceAccessPolicyService
from app.vpn.service import VPNService

router = APIRouter(prefix="/api/auth", tags=["auth"])
users_router = APIRouter(prefix="/api/users", tags=["users"])
admin_users_router = APIRouter(prefix="/api/admin/users", tags=["admin"])

limiter = Limiter(key_func=get_remote_address)


async def _initialize_new_user_resources(
    user_id: int,
    referred_by_id: int | None,
    session: DBSession,
) -> None:
    """Create trial, VPN access, and referral records for newly registered users."""
    # This helper is the main post-registration orchestrator. Failures in VPN provisioning
    # should degrade gracefully instead of blocking account creation.
    from app.billing.service import BillingService
    from app.referrals.service import ReferralService

    billing_service = BillingService(session)
    referral_service = ReferralService(session)
    device_policy = DeviceAccessPolicyService(session)
    vpn_service = VPNService(session)

    history = await billing_service.get_user_subscription_history(user_id, limit=1)
    if not history:
        await billing_service.create_trial_subscription(user_id)

    existing_client = await vpn_service.get_user_client(user_id)
    if not existing_client:
        try:
            primary_device = await device_policy.ensure_primary_device(
                user_id,
                name="Primary device",
                platform="web-default",
            )
            await vpn_service.provision_device_client(
                user_id,
                int(primary_device.id),
                reprovision=False,
            )
        except ValueError as exc:
            # Registration should not fail if infrastructure is not ready yet.
            # The UI will show a clear "config unavailable" state instead.
            from loguru import logger
            logger.warning(f"[AUTH] VPN client was not provisioned for user {user_id}: {exc}")

    if referred_by_id is not None:
        await referral_service.create_referral(referred_by_id, user_id)


# ==================== Auth Endpoints ====================

@router.post("/register", response_model=Token, status_code=status.HTTP_201_CREATED)
@limiter.limit("5/minute")
async def register(
    request: Request,
    data: UserCreate,
    session: DBSession,
):
    """
    Register a new user with email and password.
    Returns JWT tokens.
    """
    service = UserService(session)
    
    try:
        user = await service.create_user(data, referral_code=data.referral_code)
        await _initialize_new_user_resources(user.id, user.referred_by_id, session)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )

    # Create tokens
    access_token = create_access_token(subject=user.id)
    refresh_token = create_refresh_token(subject=user.id)

    return Token(
        access_token=access_token,
        refresh_token=refresh_token,
        expires_in=settings.access_token_expire_minutes * 60,
    )


@router.post("/login", response_model=Token)
@limiter.limit("10/minute")
async def login(
    request: Request,
    data: UserLogin,
    session: DBSession,
):
    """
    Login with email and password.
    Returns JWT tokens.
    """
    service = UserService(session)
    
    user = await service.authenticate_email(data.email, data.password)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
        )

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account is disabled",
        )

    # Create tokens
    access_token = create_access_token(subject=user.id)
    refresh_token = create_refresh_token(subject=user.id)

    return Token(
        access_token=access_token,
        refresh_token=refresh_token,
        expires_in=settings.access_token_expire_minutes * 60,
    )


@router.post("/telegram", response_model=Token)
@limiter.limit("10/minute")
async def telegram_auth(
    request: Request,
    data: UserCreateTelegram,
    session: DBSession,
    x_telegram_bot_token: str | None = Header(default=None),
):
    """
    Authenticate or register via Telegram.
    Returns JWT tokens.
    """
    auth_payload = {
        "id": data.telegram_id,
        "username": data.telegram_username,
        "first_name": data.name,
        "auth_date": data.auth_date,
        "hash": data.auth_hash,
    }
    auth_payload = {key: value for key, value in auth_payload.items() if value is not None}

    is_internal_bot_call = (
        settings.telegram_bot_token is not None
        and x_telegram_bot_token == settings.telegram_bot_token
    )
    is_signed_telegram_auth = verify_telegram_auth(auth_payload, settings.telegram_bot_token or "")

    if not is_internal_bot_call and not is_signed_telegram_auth:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid Telegram authentication data",
        )

    service = UserService(session)
    
    user = await service.create_user_telegram(data, referral_code=data.referral_code)
    await _initialize_new_user_resources(user.id, user.referred_by_id, session)

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account is disabled",
        )

    # Create tokens
    access_token = create_access_token(subject=user.id)
    refresh_token = create_refresh_token(subject=user.id)

    return Token(
        access_token=access_token,
        refresh_token=refresh_token,
        expires_in=settings.access_token_expire_minutes * 60,
    )


@router.post("/refresh", response_model=Token)
@limiter.limit("20/minute")
async def refresh_token(
    request: Request,
    data: TokenRefresh,
    session: DBSession,
):
    """
    Refresh access token using refresh token.
    """
    user_id = verify_token(data.refresh_token, expected_type="refresh")
    if user_id is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired refresh token",
        )

    service = UserService(session)
    user = await service.get_by_id(int(user_id))
    
    if user is None or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found or inactive",
        )

    # Create new tokens
    access_token = create_access_token(subject=user.id)
    new_refresh_token = create_refresh_token(subject=user.id)

    return Token(
        access_token=access_token,
        refresh_token=new_refresh_token,
        expires_in=settings.access_token_expire_minutes * 60,
    )


# ==================== User Endpoints ====================

@users_router.get("/me", response_model=UserResponse)
async def get_current_user_profile(
    current_user: CurrentUser,
):
    """Get current user profile."""
    return UserResponse(
        id=current_user.id,
        email=current_user.email,
        email_verified=current_user.email_verified,
        telegram_id=current_user.telegram_id,
        telegram_username=current_user.telegram_username,
        name=current_user.name,
        display_name=current_user.display_name,
        avatar_url=current_user.avatar_url,
        language=current_user.language,
        role=current_user.role,
        is_active=current_user.is_active,
        created_at=current_user.created_at,
        last_login_at=current_user.last_login_at,
    )


@users_router.put("/me", response_model=UserResponse)
async def update_current_user_profile(
    data: UserUpdate,
    current_user: CurrentUser,
    session: DBSession,
):
    """Update current user profile."""
    service = UserService(session)
    user = await service.update_user(current_user, data)
    
    return UserResponse(
        id=user.id,
        email=user.email,
        email_verified=user.email_verified,
        telegram_id=user.telegram_id,
        telegram_username=user.telegram_username,
        name=user.name,
        display_name=user.display_name,
        avatar_url=user.avatar_url,
        language=user.language,
        role=user.role,
        is_active=user.is_active,
        created_at=user.created_at,
        last_login_at=user.last_login_at,
    )


@users_router.get("/me/stats", response_model=UserStatsResponse)
async def get_current_user_stats(
    current_user: CurrentUser,
    session: DBSession,
):
    """Get current user statistics."""
    service = UserService(session)
    stats = await service.get_user_stats(current_user)
    return UserStatsResponse(**stats)


@users_router.post("/me/change-password")
async def change_password(
    data: UserChangePassword,
    current_user: CurrentUser,
    session: DBSession,
):
    """Change current user password."""
    service = UserService(session)
    
    success = await service.change_password(
        current_user, data.current_password, data.new_password
    )
    
    if not success:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Current password is incorrect",
        )
    
    return {"status": "password_changed"}


# ==================== Admin Endpoints ====================

@admin_users_router.get("", response_model=UserListResponse)
async def list_users(
    page: int = 1,
    per_page: int = 20,
    search: str | None = None,
    role: UserRole | None = None,
    is_active: bool | None = None,
    admin: CurrentAdmin = None,
    session: DBSession = None,
):
    """List all users (admin only)."""
    from sqlalchemy import func, or_, select
    from app.users.models import User

    query = select(User)
    count_query = select(func.count(User.id))

    # Filters
    if search:
        search_filter = or_(
            User.email.ilike(f"%{search}%"),
            User.name.ilike(f"%{search}%"),
            User.telegram_username.ilike(f"%{search}%"),
        )
        query = query.where(search_filter)
        count_query = count_query.where(search_filter)

    if role:
        query = query.where(User.role == role)
        count_query = count_query.where(User.role == role)

    if is_active is not None:
        query = query.where(User.is_active == is_active)
        count_query = count_query.where(User.is_active == is_active)

    # Pagination
    offset = (page - 1) * per_page
    query = query.offset(offset).limit(per_page).order_by(User.created_at.desc())

    result = await session.execute(query)
    users = result.scalars().all()

    total_result = await session.execute(count_query)
    total = total_result.scalar()

    return UserListResponse(
        items=[
            UserResponse(
                id=u.id,
                email=u.email,
                email_verified=u.email_verified,
                telegram_id=u.telegram_id,
                telegram_username=u.telegram_username,
                name=u.name,
                display_name=u.display_name,
                avatar_url=u.avatar_url,
                language=u.language,
                role=u.role,
                is_active=u.is_active,
                created_at=u.created_at,
                last_login_at=u.last_login_at,
            )
            for u in users
        ],
        total=total,
        page=page,
        per_page=per_page,
        pages=(total + per_page - 1) // per_page,
    )


@admin_users_router.get("/{user_id}", response_model=UserAdminResponse)
async def get_user(
    user_id: int,
    admin: CurrentAdmin,
    session: DBSession,
):
    """Get user by ID (admin only)."""
    service = UserService(session)
    user = await service.get_by_id(user_id)
    
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )

    return UserAdminResponse(
        id=user.id,
        email=user.email,
        email_verified=user.email_verified,
        telegram_id=user.telegram_id,
        telegram_username=user.telegram_username,
        name=user.name,
        display_name=user.display_name,
        avatar_url=user.avatar_url,
        language=user.language,
        role=user.role,
        is_active=user.is_active,
        created_at=user.created_at,
        last_login_at=user.last_login_at,
        referred_by_id=user.referred_by_id,
        subscription_count=len(user.subscriptions) if user.subscriptions else 0,
        active_subscription_id=None,
    )


@admin_users_router.put("/{user_id}", response_model=UserResponse)
async def update_user(
    user_id: int,
    data: UserAdminUpdate,
    admin: CurrentAdmin,
    session: DBSession,
):
    """Update user (admin only)."""
    service = UserService(session)
    user = await service.get_by_id(user_id)
    
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )

    update_data = data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(user, field, value)

    await session.flush()
    await session.refresh(user)

    return UserResponse(
        id=user.id,
        email=user.email,
        email_verified=user.email_verified,
        telegram_id=user.telegram_id,
        telegram_username=user.telegram_username,
        name=user.name,
        display_name=user.display_name,
        avatar_url=user.avatar_url,
        language=user.language,
        role=user.role,
        is_active=user.is_active,
        created_at=user.created_at,
        last_login_at=user.last_login_at,
    )


@admin_users_router.post("/{user_id}/activate")
async def activate_user(
    user_id: int,
    admin: CurrentAdmin,
    session: DBSession,
):
    """Activate user account (admin only)."""
    service = UserService(session)
    user = await service.get_by_id(user_id)
    
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )

    await service.activate_user(user)
    return {"status": "activated"}


@admin_users_router.post("/{user_id}/deactivate")
async def deactivate_user(
    user_id: int,
    admin: CurrentAdmin,
    session: DBSession,
):
    """Deactivate user account (admin only)."""
    service = UserService(session)
    user = await service.get_by_id(user_id)
    
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )

    await service.deactivate_user(user)
    return {"status": "deactivated"}

"""
Admin user initialization module.
Automatically creates admin user from environment variables on startup.
"""
# <!-- GRACE: module="M-001" contract="admin-initialization" -->

import warnings
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.security import hash_password
from app.users.models import User, UserRole

# Default password patterns that should be changed
DEFAULT_PASSWORD_PATTERNS = [
    "changeme",
    "changemeimmediately",
    "changemeimmediately123!",
    "admin",
    "password",
    "123456",
]


async def ensure_admin_user(session: AsyncSession) -> User | None:
    """
    Ensure admin user exists in the database.
    
    Creates admin user from ADMIN_EMAIL and ADMIN_PASSWORD environment variables
    if they are set and admin doesn't exist yet.
    
    Args:
        session: Database session
        
    Returns:
        Created or existing admin user, or None if credentials not configured
    """
    # Check if admin credentials are configured
    if not settings.admin_email or not settings.admin_password:
        return None
    
    # Check if admin already exists
    result = await session.execute(
        select(User).where(User.email == settings.admin_email.lower())
    )
    existing_admin = result.scalar_one_or_none()
    
    if existing_admin:
        # Admin exists, ensure it has admin role
        if existing_admin.role not in (UserRole.ADMIN, UserRole.SUPERADMIN):
            existing_admin.role = UserRole.ADMIN
            await session.flush()
        return existing_admin
    
    # Validate password security
    password_lower = settings.admin_password.lower()
    for pattern in DEFAULT_PASSWORD_PATTERNS:
        if pattern in password_lower:
            warnings.warn(
                f"\n{'='*60}\n"
                f"⚠️  SECURITY WARNING: ADMIN_PASSWORD contains '{pattern}'\n"
                f"   Please change the default admin password in .env!\n"
                f"   Current email: {settings.admin_email}\n"
                f"{'='*60}",
                UserWarning,
                stacklevel=2
            )
            break
    
    # Create new admin user
    admin_user = User(
        email=settings.admin_email.lower(),
        password_hash=hash_password(settings.admin_password),
        role=UserRole.ADMIN,
        is_active=True,
        email_verified=True,
        name="Administrator",
        language="ru",
    )
    
    session.add(admin_user)
    await session.flush()
    await session.refresh(admin_user)
    
    return admin_user


async def create_admin_user(
    session: AsyncSession,
    email: str,
    password: str,
    name: str = "Administrator",
    superadmin: bool = False,
) -> User:
    """
    Create a new admin user manually.
    
    Args:
        session: Database session
        email: Admin email
        password: Admin password
        name: Admin display name
        superadmin: If True, create as superadmin
        
    Returns:
        Created admin user
        
    Raises:
        ValueError: If user with this email already exists
    """
    # Check if user already exists
    result = await session.execute(
        select(User).where(User.email == email.lower())
    )
    existing = result.scalar_one_or_none()
    
    if existing:
        raise ValueError(f"User with email '{email}' already exists")
    
    # Create admin
    admin_user = User(
        email=email.lower(),
        password_hash=hash_password(password),
        role=UserRole.SUPERADMIN if superadmin else UserRole.ADMIN,
        is_active=True,
        email_verified=True,
        name=name,
        language="ru",
    )
    
    session.add(admin_user)
    await session.flush()
    await session.refresh(admin_user)
    
    return admin_user


async def reset_admin_password(
    session: AsyncSession,
    email: str,
    new_password: str,
) -> User:
    """
    Reset password for an admin user.
    
    Args:
        session: Database session
        email: Admin email
        new_password: New password
        
    Returns:
        Updated user
        
    Raises:
        ValueError: If user not found
    """
    result = await session.execute(
        select(User).where(User.email == email.lower())
    )
    user = result.scalar_one_or_none()
    
    if not user:
        raise ValueError(f"User with email '{email}' not found")
    
    user.password_hash = hash_password(new_password)
    await session.flush()
    await session.refresh(user)
    
    return user

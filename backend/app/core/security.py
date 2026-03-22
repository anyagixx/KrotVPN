"""
Security module for authentication and authorization.
Handles JWT tokens, password hashing, and encryption.
"""
# <!-- GRACE: module="M-001" contract="authentication" -->

from datetime import datetime, timedelta, timezone
from typing import Any

from cryptography.fernet import Fernet
from jose import JWTError, jwt
from passlib.context import CryptContext

from app.core.config import settings

# Password hashing
# pbkdf2_sha256 avoids bcrypt backend issues and has no 72-byte password limit.
pwd_context = CryptContext(schemes=["pbkdf2_sha256"], deprecated="auto")

# Data encryption (for sensitive data like VPN private keys)
_fernet: Fernet | None = None


def get_fernet() -> Fernet:
    """Get Fernet instance for data encryption."""
    global _fernet
    if _fernet is None:
        if not settings.data_encryption_key:
            # Generate a key from secret_key if not provided
            import base64
            import hashlib
            key = hashlib.sha256(settings.secret_key.encode()).digest()
            _fernet = Fernet(base64.urlsafe_b64encode(key))
        else:
            _fernet = Fernet(settings.data_encryption_key.encode())
    return _fernet


def encrypt_data(data: str) -> str:
    """Encrypt sensitive data."""
    return get_fernet().encrypt(data.encode()).decode()


def decrypt_data(encrypted_data: str) -> str:
    """Decrypt sensitive data."""
    return get_fernet().decrypt(encrypted_data.encode()).decode()


def hash_password(password: str) -> str:
    """Hash a password using pbkdf2_sha256."""
    return pwd_context.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a password against its hash."""
    return pwd_context.verify(plain_password, hashed_password)


def create_access_token(
    subject: str | int,
    expires_delta: timedelta | None = None,
    extra_data: dict[str, Any] | None = None,
) -> str:
    """Create a JWT access token."""
    if expires_delta:
        expire = datetime.now(timezone.utc) + expires_delta
    else:
        expire = datetime.now(timezone.utc) + timedelta(
            minutes=settings.access_token_expire_minutes
        )

    to_encode = {
        "sub": str(subject),
        "exp": expire,
        "type": "access",
    }
    if extra_data:
        to_encode.update(extra_data)

    return jwt.encode(to_encode, settings.secret_key, algorithm="HS256")


def create_refresh_token(
    subject: str | int,
    expires_delta: timedelta | None = None,
) -> str:
    """Create a JWT refresh token."""
    if expires_delta:
        expire = datetime.now(timezone.utc) + expires_delta
    else:
        expire = datetime.now(timezone.utc) + timedelta(
            days=settings.refresh_token_expire_days
        )

    to_encode = {
        "sub": str(subject),
        "exp": expire,
        "type": "refresh",
    }

    return jwt.encode(to_encode, settings.secret_key, algorithm="HS256")


def decode_token(token: str) -> dict[str, Any] | None:
    """Decode and validate a JWT token."""
    try:
        payload = jwt.decode(token, settings.secret_key, algorithms=["HS256"])
        return payload
    except JWTError:
        return None


def verify_token(token: str, expected_type: str = "access") -> str | None:
    """
    Verify a JWT token and return the subject (user ID).
    Returns None if token is invalid or expired.
    """
    payload = decode_token(token)
    if payload is None:
        return None

    if payload.get("type") != expected_type:
        return None

    return payload.get("sub")

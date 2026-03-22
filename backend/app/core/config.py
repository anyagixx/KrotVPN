"""
Application configuration module.
Loads settings from environment variables.
"""
# <!-- GRACE: module="M-001" contract="config-loading" -->

from functools import lru_cache
from typing import Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # Application
    app_name: str = "KrotVPN"
    app_version: str = "2.4.13"
    debug: bool = False
    environment: Literal["development", "staging", "production"] = "development"

    # Server
    host: str = "0.0.0.0"
    port: int = 8000

    # Database
    database_url: str = Field(
        default="sqlite+aiosqlite:///./krotvpn.db",
        description="Database connection URL",
    )

    # Redis
    redis_url: str = Field(
        default="redis://localhost:6379/0",
        description="Redis connection URL",
    )

    # Security
    secret_key: str = Field(
        default="change-this-secret-key-in-production",
        description="Secret key for JWT signing",
    )
    access_token_expire_minutes: int = 15
    refresh_token_expire_days: int = 7

    # CORS
    cors_origins: list[str] = Field(
        default=["http://localhost:3000", "http://localhost:5173"],
        description="Allowed CORS origins",
    )

    # Admin
    admin_email: str | None = None
    admin_password: str | None = None

    # VPN Configuration
    vpn_subnet: str = "10.10.0.0/24"
    vpn_port: int = 51821
    vpn_dns: str = "8.8.8.8, 1.1.1.1"
    vpn_mtu: int = 1360

    # AmneziaWG Obfuscation Parameters (MUST match legacy)
    awg_jc: int = 120
    awg_jmin: int = 50
    awg_jmax: int = 1000
    awg_s1: int = 111
    awg_s2: int = 222
    awg_h1: int = 1
    awg_h2: int = 2
    awg_h3: int = 3
    awg_h4: int = 4

    # Trial
    trial_days: int = 3

    # YooKassa
    yookassa_shop_id: str | None = None
    yookassa_secret_key: str | None = None

    # Tinkoff
    tinkoff_terminal_key: str | None = None
    tinkoff_secret_key: str | None = None

    # Telegram
    telegram_bot_token: str | None = None
    telegram_webhook_url: str | None = None

    # Email
    smtp_host: str = "smtp.gmail.com"
    smtp_port: int = 587
    smtp_user: str | None = None
    smtp_password: str | None = None
    email_from: str | None = None

    # Referral
    referral_bonus_days: int = 7
    referral_min_payment: float = 100.0

    # Data Encryption
    data_encryption_key: str | None = None

    @field_validator("secret_key")
    @classmethod
    def validate_secret_key(cls, v: str) -> str:
        if v == "change-this-secret-key-in-production":
            import warnings
            warnings.warn(
                "Using default secret key! Change SECRET_KEY in production.",
                UserWarning,
            )
        return v

    @field_validator("database_url")
    @classmethod
    def validate_database_url(cls, v: str) -> str:
        # Ensure async driver is used
        if v.startswith("postgresql://"):
            v = v.replace("postgresql://", "postgresql+asyncpg://")
        elif v.startswith("sqlite://"):
            v = v.replace("sqlite://", "sqlite+aiosqlite://")
        return v

    @property
    def is_production(self) -> bool:
        return self.environment == "production"

    @property
    def awg_obfuscation_params(self) -> dict:
        """Return AmneziaWG obfuscation parameters as dict."""
        return {
            "jc": self.awg_jc,
            "jmin": self.awg_jmin,
            "jmax": self.awg_jmax,
            "s1": self.awg_s1,
            "s2": self.awg_s2,
            "h1": self.awg_h1,
            "h2": self.awg_h2,
            "h3": self.awg_h3,
            "h4": self.awg_h4,
        }


@lru_cache
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()


settings = get_settings()

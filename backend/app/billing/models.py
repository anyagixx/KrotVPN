"""
Billing models for subscriptions and payments.

CHANGE_SUMMARY
- 2026-03-26: Added explicit complimentary-access fields so internal non-billable clients can stay inside normal subscription state.
- 2026-03-27: Added per-plan device limits for device-bound access control and anti-sharing enforcement.
"""
# <!-- GRACE: module="M-004" entity="Plan, Subscription, Payment" -->

from datetime import datetime
from enum import Enum
from typing import TYPE_CHECKING

from sqlmodel import Field, Relationship, SQLModel

if TYPE_CHECKING:
    from app.users.models import User


class PaymentProvider(str, Enum):
    """Payment provider options."""
    YOOKASSA = "yookassa"
    TINKOFF = "tinkoff"
    MANUAL = "manual"


class PaymentStatus(str, Enum):
    """Payment status."""
    PENDING = "pending"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELED = "canceled"
    REFUNDED = "refunded"


class SubscriptionStatus(str, Enum):
    """Subscription status."""
    TRIAL = "trial"
    ACTIVE = "active"
    EXPIRED = "expired"
    CANCELED = "canceled"


class Plan(SQLModel, table=True):
    """Subscription plan."""
    
    __tablename__ = "plans"
    
    id: int | None = Field(default=None, primary_key=True)
    name: str = Field(max_length=100)
    description: str | None = Field(default=None, max_length=500)
    
    # Pricing
    price: float = Field(ge=0)
    currency: str = Field(default="RUB", max_length=3)
    
    # Duration
    duration_days: int = Field(ge=1, default=30)
    device_limit: int = Field(ge=1, default=1)
    
    # Features (JSON string)
    features: str | None = Field(default=None)
    
    # Status
    is_active: bool = Field(default=True)
    is_popular: bool = Field(default=False)
    sort_order: int = Field(default=0)
    
    # Timestamps
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    
    # Relationships
    subscriptions: list["Subscription"] = Relationship(back_populates="plan")


class Subscription(SQLModel, table=True):
    """User subscription."""
    
    __tablename__ = "subscriptions"
    
    id: int | None = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="users.id", index=True)
    plan_id: int | None = Field(default=None, foreign_key="plans.id")
    
    # Status
    status: SubscriptionStatus = Field(default=SubscriptionStatus.ACTIVE)
    is_active: bool = Field(default=True)
    
    # Timing
    started_at: datetime = Field(default_factory=datetime.utcnow)
    expires_at: datetime
    
    # Trial
    is_trial: bool = Field(default=False)
    is_complimentary: bool = Field(default=False)
    access_label: str | None = Field(default=None, max_length=100)
    
    # Recurring
    is_recurring: bool = Field(default=False)
    recurring_payment_id: str | None = Field(default=None, max_length=100)
    
    # Timestamps
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    
    # Relationships
    user: "User" = Relationship(back_populates="subscriptions")
    plan: Plan | None = Relationship(back_populates="subscriptions")
    payments: list["Payment"] = Relationship(back_populates="subscription")


class Payment(SQLModel, table=True):
    """Payment record."""
    
    __tablename__ = "payments"
    
    id: int | None = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="users.id", index=True)
    plan_id: int | None = Field(default=None, foreign_key="plans.id")
    subscription_id: int | None = Field(default=None, foreign_key="subscriptions.id")
    
    # Amount
    amount: float = Field(ge=0)
    currency: str = Field(default="RUB", max_length=3)
    
    # Provider
    provider: PaymentProvider = Field(default=PaymentProvider.YOOKASSA)
    status: PaymentStatus = Field(default=PaymentStatus.PENDING)
    
    # External reference
    external_id: str | None = Field(default=None, max_length=100, index=True)
    payment_url: str | None = Field(default=None, max_length=500)
    
    # Metadata
    description: str | None = Field(default=None, max_length=255)
    payment_metadata: str | None = Field(default=None)  # JSON
    
    # Timestamps
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    paid_at: datetime | None = Field(default=None)
    
    # Relationships
    subscription: Subscription | None = Relationship(back_populates="payments")


# Response schemas
class PlanResponse(SQLModel):
    """Plan response for API."""
    id: int
    name: str
    description: str | None
    price: float
    currency: str
    duration_days: int
    features: list[str]
    is_popular: bool
    
    model_config = {"from_attributes": True}


class SubscriptionResponse(SQLModel):
    """Subscription response for API."""
    id: int
    plan_id: int
    plan_name: str
    status: SubscriptionStatus
    is_active: bool
    started_at: datetime
    expires_at: datetime
    days_left: int
    is_trial: bool
    is_complimentary: bool = False
    is_recurring: bool
    
    model_config = {"from_attributes": True}


class PaymentResponse(SQLModel):
    """Payment response for API."""
    id: int
    amount: float
    currency: str
    provider: PaymentProvider
    status: PaymentStatus
    payment_url: str | None
    created_at: datetime
    paid_at: datetime | None
    
    model_config = {"from_attributes": True}

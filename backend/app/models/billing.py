"""Billing models - Subscriptions, Usage Counters, and Usage Events.

These models support the billing and usage tracking system integrated
with Stripe for subscription management.
"""
from __future__ import annotations

import uuid
from datetime import datetime
from enum import Enum
from typing import TYPE_CHECKING, Any, Optional

from sqlalchemy import (
    BigInteger,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base, TimestampMixin

if TYPE_CHECKING:
    from .user import User


class PlanType(str, Enum):
    """Subscription plan types."""
    FREE = "FREE"
    PRO = "PRO"
    ENTERPRISE = "ENTERPRISE"


class SubscriptionStatus(str, Enum):
    """Stripe subscription statuses."""
    ACTIVE = "active"
    PAST_DUE = "past_due"
    CANCELED = "canceled"
    INCOMPLETE = "incomplete"
    INCOMPLETE_EXPIRED = "incomplete_expired"
    TRIALING = "trialing"
    UNPAID = "unpaid"


class UsageEventKind(str, Enum):
    """Types of usage events."""
    JOB_RUN = "job_run"
    CREDIT_CHANGE = "credit_change"
    STRIPE_EVENT = "stripe_event"
    RECONCILIATION = "reconciliation"


class Subscription(Base, TimestampMixin):
    """Current subscription state per user.
    
    Linked to Stripe subscriptions and tracks the user's current plan,
    status, and billing period.
    
    Attributes:
        id: Auto-incrementing primary key
        user_id: Foreign key to users table
        stripe_subscription_id: Stripe subscription ID (sub_xxx)
        plan: Plan type (FREE, PRO, ENTERPRISE)
        status: Subscription status from Stripe
        current_period_start: Start of current billing period
        current_period_end: End of current billing period
    """
    __tablename__ = "subscriptions"

    id: Mapped[int] = mapped_column(
        BigInteger,
        primary_key=True,
        autoincrement=True,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    stripe_subscription_id: Mapped[str] = mapped_column(
        Text(),
        nullable=False,
        unique=True,
    )
    plan: Mapped[str] = mapped_column(
        Text(),
        nullable=False,
    )
    status: Mapped[str] = mapped_column(
        Text(),
        nullable=False,
        index=True,
    )
    current_period_start: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )
    current_period_end: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )

    # Relationships
    user: Mapped["User"] = relationship("User", back_populates="subscriptions")

    def __repr__(self) -> str:
        return f"<Subscription(id={self.id}, plan={self.plan}, status={self.status})>"


class UsageCounter(Base, TimestampMixin):
    """Aggregated usage per user per billing period.
    
    Tracks job usage and remaining credits/limits for each billing period.
    
    Attributes:
        id: Auto-incrementing primary key
        user_id: Foreign key to users table
        period_start: Start of billing period
        period_end: End of billing period
        jobs_used: Number of jobs used in this period
        jobs_limit: Maximum jobs allowed (NULL for unlimited)
        credits_remaining: Remaining credits (for special features)
        last_reconciled_at: When this counter was last reconciled with Stripe
    """
    __tablename__ = "usage_counters"

    id: Mapped[int] = mapped_column(
        BigInteger,
        primary_key=True,
        autoincrement=True,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    period_start: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )
    period_end: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )
    jobs_used: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        server_default="0",
    )
    jobs_limit: Mapped[Optional[int]] = mapped_column(
        Integer,
        nullable=True,
    )
    credits_remaining: Mapped[Optional[int]] = mapped_column(
        Integer,
        nullable=True,
    )
    last_reconciled_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    # Relationships
    user: Mapped["User"] = relationship("User", back_populates="usage_counters")

    # Constraints
    __table_args__ = (
        UniqueConstraint(
            "user_id", "period_start", "period_end",
            name="usage_counters_user_period_uniq",
        ),
    )

    def __repr__(self) -> str:
        return f"<UsageCounter(id={self.id}, jobs_used={self.jobs_used}/{self.jobs_limit})>"

    def is_over_limit(self) -> bool:
        """Check if usage has exceeded the limit."""
        if self.jobs_limit is None:
            return False  # Unlimited
        return self.jobs_used >= self.jobs_limit

    def remaining_jobs(self) -> Optional[int]:
        """Get remaining jobs, or None if unlimited."""
        if self.jobs_limit is None:
            return None
        return max(0, self.jobs_limit - self.jobs_used)


class UsageEvent(Base):
    """Append-only audit log for all usage changes.
    
    Records every usage event for billing reconciliation and auditing.
    Includes idempotency support via stripe_event_id.
    
    Attributes:
        id: Auto-incrementing primary key
        user_id: Foreign key to users table
        kind: Type of usage event (job_run, credit_change, etc.)
        amount: Change in usage (+1 job, -1 credit, etc.)
        job_id: Optional link to the job that caused this event
        stripe_event_id: Stripe event ID for idempotency
        metadata: Additional event context as JSON
        occurred_at: When the event occurred
        created_at: When this record was created
    """
    __tablename__ = "usage_events"

    id: Mapped[int] = mapped_column(
        BigInteger,
        primary_key=True,
        autoincrement=True,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    kind: Mapped[str] = mapped_column(
        Text(),
        nullable=False,
    )
    amount: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )
    job_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        nullable=True,
    )
    stripe_event_id: Mapped[Optional[str]] = mapped_column(
        Text(),
        nullable=True,
    )
    metadata: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
        server_default="'{}'::jsonb",
    )
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    # Relationships
    user: Mapped["User"] = relationship("User", back_populates="usage_events")

    # Indexes
    __table_args__ = (
        Index("usage_events_user_time_idx", "user_id", "occurred_at"),
        Index(
            "usage_events_stripe_event_id_idx",
            "stripe_event_id",
            unique=True,
            postgresql_where="stripe_event_id IS NOT NULL",
        ),
    )

    def __repr__(self) -> str:
        return f"<UsageEvent(id={self.id}, kind={self.kind}, amount={self.amount})>"

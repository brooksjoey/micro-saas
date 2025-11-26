"""User model - mirrors Supabase auth users with Stripe linkage.

This model represents the application-side user record that links
Supabase authentication with Stripe billing.
"""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Optional

from sqlalchemy import DateTime, Text, func
from sqlalchemy.dialects.postgresql import CITEXT, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base, TimestampMixin

if TYPE_CHECKING:
    from .billing import Subscription, UsageCounter, UsageEvent
    from .job import Job


class User(Base, TimestampMixin):
    """Application user record linked to Supabase auth and Stripe.
    
    Attributes:
        id: UUID from Supabase auth.uid()
        email: User's email address (case-insensitive)
        stripe_customer_id: Stripe customer ID (cus_xxx)
        created_at: When the user record was created
        updated_at: When the user record was last modified
    """
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    email: Mapped[str] = mapped_column(
        CITEXT(),
        nullable=False,
        unique=True,
        index=True,
    )
    stripe_customer_id: Mapped[Optional[str]] = mapped_column(
        Text(),
        nullable=True,
    )

    # Relationships
    subscriptions: Mapped[list["Subscription"]] = relationship(
        "Subscription",
        back_populates="user",
        cascade="all, delete-orphan",
    )
    usage_counters: Mapped[list["UsageCounter"]] = relationship(
        "UsageCounter",
        back_populates="user",
        cascade="all, delete-orphan",
    )
    usage_events: Mapped[list["UsageEvent"]] = relationship(
        "UsageEvent",
        back_populates="user",
        cascade="all, delete-orphan",
    )
    jobs: Mapped[list["Job"]] = relationship(
        "Job",
        back_populates="user",
    )

    def __repr__(self) -> str:
        return f"<User(id={self.id}, email={self.email})>"

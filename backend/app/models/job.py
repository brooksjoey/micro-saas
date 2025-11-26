"""Job model - Core job entity for task processing.

Jobs represent units of work submitted by users and processed by workers.
"""
from __future__ import annotations

import uuid
from datetime import datetime
from enum import Enum
from typing import TYPE_CHECKING, Any, Optional

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base, TimestampMixin

if TYPE_CHECKING:
    from .user import User


class JobStatus(str, Enum):
    """Job execution status."""
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class Job(Base, TimestampMixin):
    """Job entity for task processing.
    
    Represents a unit of work submitted by a user and processed by workers.
    Supports retry logic, idempotency, and correlation tracking.
    
    Attributes:
        id: Unique job identifier
        user_id: Optional link to the user who submitted the job
        correlation_id: Request correlation ID for distributed tracing
        status: Current job status
        payload: Job-specific data and parameters
        attempts: Number of execution attempts
        max_attempts: Maximum retry attempts
        last_error: Error message from last failed attempt
        next_run_at: Scheduled time for next retry
        idempotency_key: Optional key for deduplication
    """
    __tablename__ = "jobs"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    user_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    correlation_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        nullable=True,
    )
    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default=JobStatus.PENDING.value,
        index=True,
    )
    payload: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
        server_default="'{}'::jsonb",
    )
    attempts: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
    )
    max_attempts: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=5,
    )
    last_error: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
    )
    next_run_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        index=True,
    )
    idempotency_key: Mapped[Optional[str]] = mapped_column(
        String(128),
        nullable=True,
        unique=True,
        index=True,
    )

    # Relationships
    user: Mapped[Optional["User"]] = relationship("User", back_populates="jobs")

    # Indexes
    __table_args__ = (
        Index("jobs_user_id_idx", "user_id"),
        Index("jobs_user_created_at_idx", "user_id", "created_at"),
        Index("jobs_user_status_idx", "user_id", "status"),
        Index("jobs_correlation_id_idx", "correlation_id"),
        Index("jobs_status_next_run_at_idx", "status", "next_run_at"),
    )

    def __repr__(self) -> str:
        return f"<Job(id={self.id}, status={self.status}, attempts={self.attempts})>"

    def mark_running(self) -> None:
        """Transition job to RUNNING status."""
        self.status = JobStatus.RUNNING.value
        self.attempts += 1

    def mark_completed(self) -> None:
        """Transition job to COMPLETED status."""
        self.status = JobStatus.COMPLETED.value
        self.last_error = None

    def mark_failed(self, error: str, next_run: Optional[datetime] = None) -> None:
        """Transition job to FAILED status with error details."""
        self.status = JobStatus.FAILED.value
        self.last_error = error
        self.next_run_at = next_run

    def mark_cancelled(self) -> None:
        """Transition job to CANCELLED status."""
        self.status = JobStatus.CANCELLED.value

    def can_retry(self) -> bool:
        """Check if job can be retried."""
        return self.attempts < self.max_attempts

    def is_terminal(self) -> bool:
        """Check if job is in a terminal state."""
        return self.status in (
            JobStatus.COMPLETED.value,
            JobStatus.FAILED.value,
            JobStatus.CANCELLED.value,
        )

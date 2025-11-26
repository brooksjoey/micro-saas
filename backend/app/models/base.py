"""SQLAlchemy declarative base and common model utilities.

This module provides the base class for all ORM models and common
mixins for timestamps, soft-delete, etc.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    """Base class for all SQLAlchemy ORM models.
    
    All models should inherit from this class to be included in
    Alembic migrations and share common configuration.
    """
    pass


class TimestampMixin:
    """Mixin providing created_at and updated_at columns.
    
    Usage:
        class MyModel(Base, TimestampMixin):
            __tablename__ = "my_table"
            id: Mapped[int] = mapped_column(primary_key=True)
    """
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

from __future__ import annotations

import asyncio
import logging
import threading
from typing import Any, AsyncIterator, Callable, Coroutine, Optional, TypeVar

from sqlalchemy import exc as sa_exc, text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import declarative_base

from backend.app.config import Settings, get_settings


logger = logging.getLogger(__name__)

Base = declarative_base()

_ENGINE_LOCK = threading.Lock()
_ENGINE: AsyncEngine | None = None
_SESSION_FACTORY: async_sessionmaker[AsyncSession] | None = None

T = TypeVar("T")


def create_engine_from_settings(settings: Settings) -> AsyncEngine:
    """Create an AsyncEngine configured for Postgres/asyncpg.

    Engine creation itself is lazy; no connection is made until first use.
    """
    return create_async_engine(
        settings.POSTGRES_DSN,
        pool_size=settings.DB_POOL_SIZE,
        max_overflow=settings.DB_MAX_OVERFLOW,
        pool_timeout=settings.DB_POOL_TIMEOUT,
        pool_pre_ping=True,
        future=True,
    )


def get_engine() -> AsyncEngine:
    """Return the process-wide AsyncEngine, creating it on first use."""
    global _ENGINE, _SESSION_FACTORY
    if _ENGINE is None:
        with _ENGINE_LOCK:
            if _ENGINE is None:
                settings = get_settings()
                _ENGINE = create_engine_from_settings(settings)
                _SESSION_FACTORY = async_sessionmaker(
                    bind=_ENGINE,
                    expire_on_commit=False,
                    autoflush=False,
                    autocommit=False,
                )
    assert _ENGINE is not None
    return _ENGINE


def get_session_factory() -> async_sessionmaker[AsyncSession]:
    """Return the global async session factory."""
    global _SESSION_FACTORY
    if _SESSION_FACTORY is None:
        get_engine()
    assert _SESSION_FACTORY is not None
    return _SESSION_FACTORY


async def _connect_with_retries(engine: AsyncEngine, *, attempts: int = 3) -> None:
    """Attempt to connect to the database with simple exponential backoff."""
    settings = get_settings()
    delay = 1.0
    max_delay = 10.0

    for idx in range(attempts):
        try:
            async with engine.connect() as conn:
                await conn.execute(text("SELECT 1"))
            return
        except sa_exc.SQLAlchemyError:
            logger.exception("db_connect_attempt_failed", extra={"attempt": idx + 1})
            if idx == attempts - 1:
                raise
            await asyncio.sleep(min(delay, max_delay))
            delay *= 2.0


async def ensure_db_connected() -> None:
    """Optionally used at startup to fail fast if DB is unreachable."""
    engine = get_engine()
    await _connect_with_retries(engine, attempts=3)


async def get_db() -> AsyncIterator[AsyncSession]:
    """FastAPI-style dependency that yields an AsyncSession."""
    session_factory = get_session_factory()
    async with session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


async def run_in_transaction(
    fn: Callable[[AsyncSession], Coroutine[Any, Any, T]],
) -> T:
    """Run a coroutine with its own transaction boundary."""
    session_factory = get_session_factory()
    async with session_factory() as session:
        try:
            result = await fn(session)
            await session.commit()
            return result
        except Exception:
            await session.rollback()
            raise

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from sqlalchemy import Boolean, Column, Integer, String, UniqueConstraint, select, distinct
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.config import Settings, get_settings
from backend.app.utils.db import Base, run_in_transaction
from backend.app.utils.redis_client import cache_get, cache_set, make_key


logger = logging.getLogger(__name__)


class FeatureFlag(Base):
    __tablename__ = "feature_flags"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(length=255), nullable=False)
    env = Column(String(length=64), nullable=True)
    tenant_id = Column(String(length=255), nullable=True)
    user_id = Column(String(length=255), nullable=True)
    enabled = Column(Boolean, nullable=False, default=False)

    __table_args__ = (
        UniqueConstraint(
            "name",
            "env",
            "tenant_id",
            "user_id",
            name="uq_feature_flags_scope",
        ),
    )


class FeatureDisabledError(PermissionError):
    """Raised when a required feature is not enabled."""


# Static defaults (dev/local bootstrap)
STATIC_DEFAULT_FLAGS: Dict[str, bool] = {}


def _encode_bool(value: bool) -> str:
    return "1" if value else "0"


def _decode_bool(value: str | None) -> Optional[bool]:
    if value is None:
        return None
    value = value.strip()
    if value == "1":
        return True
    if value == "0":
        return False
    return None


def _build_cache_keys(
    name: str,
    *,
    env: str,
    tenant_id: str | None,
    user_id: str | None,
) -> Dict[str, str]:
    keys: Dict[str, str] = {}
    if user_id:
        keys["user"] = make_key("feature", name, "user", user_id, "env", env)
    if tenant_id:
        keys["tenant"] = make_key("feature", name, "tenant", tenant_id, "env", env)
    keys["env"] = make_key("feature", name, "env", env)
    keys["global"] = make_key("feature", name, "global")
    return keys


async def _load_flags_from_db(
    session: AsyncSession,
    name: str,
    *,
    env: str,
    tenant_id: str | None,
    user_id: str | None,
) -> Dict[str, Optional[bool]]:
    """Load feature flags for all scopes for a given name."""
    stmt = select(FeatureFlag).where(FeatureFlag.name == name)
    rows = (await session.execute(stmt)).scalars().all()

    result: Dict[str, Optional[bool]] = {
        "user": None,
        "tenant": None,
        "env": None,
        "global": None,
    }

    for row in rows:
        if row.user_id and user_id and row.user_id == user_id and row.env == env:
            result["user"] = bool(row.enabled)
        elif row.tenant_id and tenant_id and row.tenant_id == tenant_id and row.env == env:
            result["tenant"] = bool(row.enabled)
        elif row.env == env and not row.tenant_id and not row.user_id:
            result["env"] = bool(row.enabled)
        elif row.env is None and row.tenant_id is None and row.user_id is None:
            result["global"] = bool(row.enabled)

    return result


async def is_feature_enabled(
    name: str,
    *,
    env: str | None = None,
    tenant_id: str | None = None,
    user_id: str | None = None,
) -> bool:
    """Evaluate whether a feature is enabled using precedence:

    1. User
    2. Tenant
    3. Env/global
    4. Static default
    5. Unknown → disabled
    """
    settings: Settings = get_settings()
    effective_env = env or settings.APP_ENV

    # Static mode (local/dev override)
    if settings.FEATURE_FLAGS_SOURCE != "db+redis":
        static_value = STATIC_DEFAULT_FLAGS.get(name)
        return bool(static_value) if static_value is not None else False

    cache_keys = _build_cache_keys(
        name,
        env=effective_env,
        tenant_id=tenant_id,
        user_id=user_id,
    )

    # 1. User override
    if "user" in cache_keys:
        cached = await cache_get(cache_keys["user"])
        decoded = _decode_bool(cached)
        if decoded is not None:
            return decoded

    # 2. Tenant override
    if "tenant" in cache_keys:
        cached = await cache_get(cache_keys["tenant"])
        decoded = _decode_bool(cached)
        if decoded is not None:
            return decoded

    # 3. Env-level
    cached_env = await cache_get(cache_keys["env"])
    decoded_env = _decode_bool(cached_env)
    if decoded_env is not None:
        return decoded_env

    # 4. Global default
    cached_global = await cache_get(cache_keys["global"])
    decoded_global = _decode_bool(cached_global)
    if decoded_global is not None:
        return decoded_global

    # Cache miss → load from DB and backfill
    async def _load(session: AsyncSession) -> bool:
        try:
            values = await _load_flags_from_db(
                session,
                name,
                env=effective_env,
                tenant_id=tenant_id,
                user_id=user_id,
            )
        except SQLAlchemyError:
            logger.exception("feature_flag_db_error", extra={"name": name})
            static_value = STATIC_DEFAULT_FLAGS.get(name)
            return bool(static_value) if static_value is not None else False

        # Cache backfill
        if values.get("user") is not None and "user" in cache_keys:
            await cache_set(cache_keys["user"], _encode_bool(bool(values["user"])))
        if values.get("tenant") is not None and "tenant" in cache_keys:
            await cache_set(cache_keys["tenant"], _encode_bool(bool(values["tenant"])))
        if values.get("env") is not None:
            await cache_set(cache_keys["env"], _encode_bool(bool(values["env"])))
        if values.get("global") is not None:
            await cache_set(cache_keys["global"], _encode_bool(bool(values["global"])))

        # Apply precedence
        if values.get("user") is not None:
            return bool(values["user"])
        if values.get("tenant") is not None:
            return bool(values["tenant"])
        if values.get("env") is not None:
            return bool(values["env"])
        if values.get("global") is not None:
            return bool(values["global"])

        static_value = STATIC_DEFAULT_FLAGS.get(name)
        return bool(static_value) if static_value is not None else False

    return await run_in_transaction(_load)


async def require_feature(
    name: str,
    *,
    env: str | None = None,
    tenant_id: str | None = None,
    user_id: str | None = None,
) -> None:
    """Raise if a feature is not enabled."""
    enabled = await is_feature_enabled(
        name,
        env=env,
        tenant_id=tenant_id,
        user_id=user_id,
    )
    if not enabled:
        raise FeatureDisabledError(f"feature '{name}' is not enabled")


async def list_flags() -> List[str]:
    """Return a list of all known flags (static + DB)."""
    names = set(STATIC_DEFAULT_FLAGS.keys())

    async def _load(session: AsyncSession) -> None:
        stmt = select(distinct(FeatureFlag.name))
        rows = (await session.execute(stmt)).scalars().all()
        for n in rows:
            names.add(n)

    settings = get_settings()
    if settings.FEATURE_FLAGS_SOURCE == "db+redis":
        try:
            await run_in_transaction(_load)
        except SQLAlchemyError:
            logger.exception("feature_flag_list_db_error")

    return sorted(names)

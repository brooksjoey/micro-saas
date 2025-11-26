from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from sqlalchemy import Boolean, Column, Integer, String, UniqueConstraint, select, distinct
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


class FeatureDisabledError(PermissionError):
    """Raised when a required feature is not enabled.
    
    Attributes:
        feature_name: Name of the disabled feature
        flag_name: Environment variable name for the flag
    """
    
    def __init__(self, feature_name: str, flag_name: Optional[str] = None):
        self.feature_name = feature_name
        self.flag_name = flag_name or f"FF_{feature_name.upper()}_ENABLED"
        super().__init__(f"Feature '{feature_name}' is not enabled")


# =============================================================================
# Environment-based Feature Flags (Simple, Fast)
# =============================================================================

def is_env_flag_enabled(flag_name: str) -> bool:
    """Check if an environment-based feature flag is enabled.
    
    This is the fast path for checking feature flags that are configured
    via environment variables with the FF_ prefix.
    
    Args:
        flag_name: Flag name (e.g., "BROWSER_WORKER", "BILLING_ENFORCEMENT")
        
    Returns:
        True if the flag is enabled, False otherwise
    """
    from app.config import get_settings
    
    settings = get_settings()
    attr_name = f"FF_{flag_name.upper()}_ENABLED"
    
    # Check if the setting exists
    if hasattr(settings, attr_name):
        return getattr(settings, attr_name, False)
    
    return False


def require_env_flag(flag_name: str) -> None:
    """Require an environment-based feature flag to be enabled.
    
    Raises:
        FeatureDisabledError: If the flag is not enabled
    """
    if not is_env_flag_enabled(flag_name):
        raise FeatureDisabledError(flag_name)


def check_task_flag(task_name: str) -> bool:
    """Check if a specific task type is enabled.
    
    Uses the pattern FF_BROWSER_TASK_{TASK_NAME}_ENABLED.
    
    Args:
        task_name: Task name (e.g., "NAVIGATE_EXTRACT")
        
    Returns:
        True if the task is enabled, False otherwise
    """
    from app.config import get_settings
    import os
    
    # Task flags are checked via environment since they're dynamic
    flag_name = f"FF_BROWSER_TASK_{task_name.upper()}_ENABLED"
    value = os.getenv(flag_name, "true").lower()
    return value in ("true", "1", "yes")


# =============================================================================
# Database-backed Feature Flags (Full System)
# =============================================================================

# Late imports to avoid circular dependencies
def _get_db_helpers():
    """Lazy import of database helpers."""
    from app.models.base import Base
    from app.utils.db import run_in_transaction
    from app.utils.redis_client import cache_get, cache_set, make_key
    return Base, run_in_transaction, cache_get, cache_set, make_key


class FeatureFlag:
    """Database model for feature flags.
    
    This is defined dynamically to avoid import issues.
    The actual table is created via Alembic migration.
    """
    __tablename__ = "feature_flags"
    
    # Table is defined in migration, this is just for reference
    # id: int (primary key)
    # name: str
    # env: str (nullable)
    # tenant_id: str (nullable)
    # user_id: str (nullable)
    # enabled: bool


# Static defaults (dev/local bootstrap)
STATIC_DEFAULT_FLAGS: Dict[str, bool] = {
    "BROWSER_WORKER": True,
    "BILLING_ENFORCEMENT": False,
    "AGENTS": False,
}


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
    """Build Redis cache keys for all scopes of a flag."""
    try:
        _, _, _, _, make_key = _get_db_helpers()
    except ImportError:
        # Fallback if redis_client not available
        def make_key(*parts):
            return ":".join(str(p) for p in parts)
    
    keys: Dict[str, str] = {}
    if user_id:
        keys["user"] = make_key("feature", name, "user", user_id, "env", env)
    if tenant_id:
        keys["tenant"] = make_key("feature", name, "tenant", tenant_id, "env", env)
    keys["env"] = make_key("feature", name, "env", env)
    keys["global"] = make_key("feature", name, "global")
    return keys


async def is_feature_enabled(
    name: str,
    *,
    env: str | None = None,
    tenant_id: str | None = None,
    user_id: str | None = None,
) -> bool:
    """Evaluate whether a feature is enabled using precedence:

    1. Environment variable (FF_{NAME}_ENABLED)
    2. User override (database)
    3. Tenant override (database)
    4. Env/global (database)
    5. Static default
    6. Unknown → disabled
    
    For most cases, use is_env_flag_enabled() for fast environment-based checks.
    """
    from app.config import get_settings
    
    settings = get_settings()
    effective_env = env or settings.APP_ENV

    # Fast path: Check environment variable first
    env_attr = f"FF_{name.upper()}_ENABLED"
    if hasattr(settings, env_attr):
        return getattr(settings, env_attr, False)

    # Static mode (local/dev override or if DB not available)
    if settings.FEATURE_FLAGS_SOURCE != "db+redis":
        static_value = STATIC_DEFAULT_FLAGS.get(name.upper())
        return bool(static_value) if static_value is not None else False

    try:
        Base, run_in_transaction, cache_get, cache_set, make_key = _get_db_helpers()
    except ImportError:
        # Fall back to static defaults if helpers not available
        static_value = STATIC_DEFAULT_FLAGS.get(name.upper())
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

    # 5. Static default
    static_value = STATIC_DEFAULT_FLAGS.get(name.upper())
    return bool(static_value) if static_value is not None else False


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
        raise FeatureDisabledError(name)


async def list_flags() -> List[str]:
    """Return a list of all known flags (environment + static)."""
    from app.config import get_settings
    
    names = set(STATIC_DEFAULT_FLAGS.keys())
    
    # Add environment-based flags from settings
    settings = get_settings()
    for attr in dir(settings):
        if attr.startswith("FF_") and attr.endswith("_ENABLED"):
            # Extract flag name (e.g., FF_BROWSER_WORKER_ENABLED -> BROWSER_WORKER)
            flag_name = attr[3:-8]  # Remove FF_ prefix and _ENABLED suffix
            names.add(flag_name)
    
    return sorted(names)


# =============================================================================
# Convenience functions
# =============================================================================

def is_browser_worker_enabled() -> bool:
    """Check if browser worker is enabled."""
    return is_env_flag_enabled("BROWSER_WORKER")


def is_billing_enforcement_enabled() -> bool:
    """Check if billing enforcement is enabled."""
    return is_env_flag_enabled("BILLING_ENFORCEMENT")


def is_agents_enabled() -> bool:
    """Check if agents are enabled."""
    return is_env_flag_enabled("AGENTS")

from __future__ import annotations

import asyncio
import logging
import threading
import uuid
from typing import Any, Optional

from redis.asyncio import ConnectionPool, Redis
from redis.exceptions import RedisError

from backend.app.config import get_settings


logger = logging.getLogger(__name__)

_REDIS_LOCK = threading.Lock()
_REDIS_CLIENT: Redis | None = None
_REDIS_POOL: ConnectionPool | None = None


def _get_prefix() -> str:
    settings = get_settings()
    return f"{settings.MSAAS_REDIS_PREFIX}:{settings.APP_ENV}:"


def make_key(*parts: str) -> str:
    """Construct a namespaced Redis key with the standard msaas:{env}: prefix."""
    suffix = ":".join(part.strip(":") for part in parts if part)
    return f"{_get_prefix()}{suffix}"


def get_redis_client() -> Redis:
    """Return a shared async Redis client instance."""
    global _REDIS_CLIENT, _REDIS_POOL
    if _REDIS_CLIENT is None:
        with _REDis_LOCK:
            if _REDIS_CLIENT is None:
                settings = get_settings()
                _REDIS_POOL = ConnectionPool.from_url(
                    settings.REDIS_URL,
                    max_connections=settings.REDIS_MAX_CONNECTIONS
                    or settings.REDIS_POOL_SIZE,
                    decode_responses=True,
                )
                _REDIS_CLIENT = Redis(connection_pool=_REDIS_POOL)
    assert _REDIS_CLIENT is not None
    return _REDIS_CLIENT


async def cache_get(key: str, default: Any | None = None) -> Any | None:
    """Get a value from Redis cache, returning default on missing key."""
    client = get_redis_client()
    try:
        value = await client.get(key)
    except RedisError:
        logger.exception("redis_cache_get_failed", extra={"key": key})
        return default
    if value is None:
        return default
    return value


async def cache_set(
    key: str,
    value: Any,
    *,
    ex: Optional[float] = None,
) -> None:
    """Set a value in Redis cache, with optional expiry in seconds."""
    client = get_redis_client()
    try:
        await client.set(key, value, ex=ex)
    except RedisError:
        logger.exception("redis_cache_set_failed", extra={"key": key})


_LOCK_RELEASE_SCRIPT = """\
if redis.call('get', KEYS[1]) == ARGV[1] then
  return redis.call('del', KEYS[1])
else
  return 0
end
"""


async def acquire_lock(
    name: str,
    *,
    ttl_seconds: int = 30,
    retry_interval: float = 0.1,
    timeout: Optional[float] = None,
) -> Optional[str]:
    """Acquire a simple distributed lock using SET NX with a TTL.

    Returns the lock token if acquired, or None if the lock could not be
    acquired before the timeout.
    """
    client = get_redis_client()
    token = uuid.uuid4().hex
    lock_key = make_key("lock", name)

    start = asyncio.get_event_loop().time()
    while True:
        try:
            ok = await client.set(lock_key, token, nx=True, ex=ttl_seconds)
        except RedisError:
            logger.exception("redis_acquire_lock_failed", extra={"name": name})
            return None

        if ok:
            return token

        if timeout is not None:
            now = asyncio.get_event_loop().time()
            if now - start >= timeout:
                return None

        await asyncio.sleep(retry_interval)


async def release_lock(name: str, token: str) -> bool:
    """Release a distributed lock previously acquired with acquire_lock."""
    client = get_redis_client()
    lock_key = make_key("lock", name)
    try:
        result = await client.eval(_LOCK_RELEASE_SCRIPT, 1, lock_key, token)
        return bool(result)
    except RedisError:
        logger.exception("redis_release_lock_failed", extra={"name": name})
        return False

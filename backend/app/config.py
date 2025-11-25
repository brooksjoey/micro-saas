from __future__ import annotations

import os
import threading
from typing import Any, Dict, Optional

from pydantic import BaseModel, Field, ValidationError


_ENV_LOCK = threading.Lock()
_SETTINGS: "Settings | None" = None


def _read_bool(value: str | None, default: bool) -> bool:
    if value is None:
        return default
    value = value.strip().lower()
    if value in {"1", "true", "yes", "y", "on"}:
        return True
    if value in {"0", "false", "no", "n", "off"}:
        return False
    return default


class Settings(BaseModel):
    """Application configuration loaded from environment variables.

    Environment precedence is:

    1. Canonical env var names (e.g. POSTGRES_DSN, APP_ENV).
    2. Legacy aliases (e.g. DATABASE_URL, ENV) when canonical is unset.
    3. Built-in defaults where defined.
    """

    # Core
    APP_ENV: str = Field(default="local")
    SERVICE_NAME: str = Field(default="api")
    LOG_LEVEL: str = Field(default="INFO")

    # Database
    POSTGRES_DSN: str
    DB_POOL_SIZE: int = Field(default=10)
    DB_MAX_OVERFLOW: int = Field(default=20)
    DB_POOL_TIMEOUT: float = Field(default=30.0)

    # Redis
    REDIS_URL: str = Field(default="redis://localhost:6379/0")
    MSAAS_REDIS_PREFIX: str = Field(default="msaas")
    REDIS_POOL_SIZE: int = Field(default=10)
    REDIS_MAX_CONNECTIONS: Optional[int] = Field(default=None)

    # Circuit breaker defaults
    CIRCUIT_BREAKER_FAILURE_THRESHOLD: int = Field(default=5)
    CIRCUIT_BREAKER_ROLLING_WINDOW: int = Field(default=60)
    CIRCUIT_BREAKER_RECOVERY_TIMEOUT: int = Field(default=30)
    CIRCUIT_BREAKER_SUCCESS_THRESHOLD: int = Field(default=2)

    # Feature flags
    FEATURE_FLAGS_SOURCE: str = Field(default="db+redis")
    FEATURE_FLAGS_ENABLE_TENANT: bool = Field(default=True)
    FEATURE_FLAGS_ENABLE_USER: bool = Field(default=True)

    # Worker / queues
    WORKER_QUEUE_NAME: Optional[str] = Field(default=None)
    WORKER_QUEUE_KIND: str = Field(default="redis_stream")

    class Config:
        frozen = True

    @property
    def env(self) -> str:
        """Canonical environment label used for metrics and namespacing."""
        return self.APP_ENV

    @property
    def service(self) -> str:
        """Canonical service name label used for metrics."""
        return self.SERVICE_NAME

    @classmethod
    def from_env(cls) -> "Settings":
        """Build Settings from environment with support for legacy aliases.

        Canonical names are preferred; legacy aliases are only consulted if the
        canonical variable is unset.
        """

        env = os.environ

        def pick(
            primary: str,
            *aliases: str,
            default: Optional[str] = None,
        ) -> Optional[str]:
            if primary in env and env[primary]:
                return env[primary]
            for name in aliases:
                if name in env and env[name]:
                    return env[name]
            return default

        data: Dict[str, Any] = {}

        # Core
        data["APP_ENV"] = (pick("APP_ENV", "ENV", default="local") or "local").strip()
        data["SERVICE_NAME"] = (
            pick("SERVICE_NAME", default="api") or "api"
        ).strip()
        data["LOG_LEVEL"] = (
            pick("LOG_LEVEL", default="INFO") or "INFO"
        ).strip()

        # Database
        dsn = pick("POSTGRES_DSN", "DATABASE_URL")
        if not dsn:
            raise RuntimeError(
                "POSTGRES_DSN (or legacy DATABASE_URL) must be set in the environment."
            )
        data["POSTGRES_DSN"] = dsn
        data["DB_POOL_SIZE"] = int(pick("DB_POOL_SIZE", default="10") or "10")
        data["DB_MAX_OVERFLOW"] = int(pick("DB_MAX_OVERFLOW", default="20") or "20")
        data["DB_POOL_TIMEOUT"] = float(
            pick("DB_POOL_TIMEOUT", default="30.0") or "30.0"
        )

        # Redis
        data["REDIS_URL"] = (
            pick("REDIS_URL", default="redis://localhost:6379/0")
            or "redis://localhost:6379/0"
        )
        data["MSAAS_REDIS_PREFIX"] = (
            pick("MSAAS_REDIS_PREFIX", default="msaas") or "msaas"
        )
        data["REDIS_POOL_SIZE"] = int(
            pick("REDIS_POOL_SIZE", default="10") or "10"
        )
        max_conns_raw = pick("REDIS_MAX_CONNECTIONS", default="")
        data["REDIS_MAX_CONNECTIONS"] = (
            int(max_conns_raw) if max_conns_raw not in ("", None) else None
        )

        # Circuit breaker
        data["CIRCUIT_BREAKER_FAILURE_THRESHOLD"] = int(
            pick("CIRCUIT_BREAKER_FAILURE_THRESHOLD", default="5") or "5"
        )
        data["CIRCUIT_BREAKER_ROLLING_WINDOW"] = int(
            pick("CIRCUIT_BREAKER_ROLLING_WINDOW", default="60") or "60"
        )
        data["CIRCUIT_BREAKER_RECOVERY_TIMEOUT"] = int(
            pick("CIRCUIT_BREAKER_RECOVERY_TIMEOUT", default="30") or "30"
        )
        data["CIRCUIT_BREAKER_SUCCESS_THRESHOLD"] = int(
            pick("CIRCUIT_BREAKER_SUCCESS_THRESHOLD", default="2") or "2"
        )

        # Feature flags
        data["FEATURE_FLAGS_SOURCE"] = (
            pick("FEATURE_FLAGS_SOURCE", default="db+redis") or "db+redis"
        )
        data["FEATURE_FLAGS_ENABLE_TENANT"] = _read_bool(
            pick("FEATURE_FLAGS_ENABLE_TENANT", default=None),
            default=True,
        )
        data["FEATURE_FLAGS_ENABLE_USER"] = _read_bool(
            pick("FEATURE_FLAGS_ENABLE_USER", default=None),
            default=True,
        )

        # Worker-specific
        data["WORKER_QUEUE_NAME"] = pick("WORKER_QUEUE_NAME", default=None)
        data["WORKER_QUEUE_KIND"] = (
            pick("WORKER_QUEUE_KIND", default="redis_stream") or "redis_stream"
        )

        try:
            return cls(**data)
        except ValidationError as exc:
            raise RuntimeError(f"Invalid configuration: {exc}") from exc


def get_settings() -> Settings:
    """Return a cached Settings instance (process-wide singleton).

    The first call reads from environment; subsequent calls return the same
    immutable Settings object.
    """
    global _SETTINGS
    if _SETTINGS is None:
        with _ENV_LOCK:
            if _SETTINGS is None:
                _SETTINGS = Settings.from_env()
    return _SETTINGS

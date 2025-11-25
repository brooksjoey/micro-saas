# backend/app/config.py

from __future__ import annotations

import os
from functools import lru_cache
from typing import Any, Optional

from pydantic import Field, PostgresDsn, validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """
    Global application configuration.

    Canonical environment variables are:

    Core:
      - APP_ENV                     -> "local" | "dev" | "staging" | "prod"
      - SERVICE_NAME                -> "api" | "worker-generic" | "worker-browser" | "billing-cron" | "agents"
      - LOG_LEVEL                   -> "DEBUG" | "INFO" | "WARNING" | "ERROR"

    Database:
      - POSTGRES_DSN                -> postgresql+asyncpg://USER:PASS@HOST:PORT/DB_NAME
      - DB_POOL_SIZE                -> int, default 10
      - DB_MAX_OVERFLOW             -> int, default 20
      - DB_POOL_TIMEOUT             -> float seconds, default 30.0
      - DATABASE_URL                -> legacy alias for POSTGRES_DSN (optional)

    Redis:
      - REDIS_URL                   -> redis://...
      - MSAAS_REDIS_PREFIX          -> key prefix, default "msaas"
      - REDIS_POOL_SIZE             -> optional, default 10
      - REDIS_MAX_CONNECTIONS       -> optional, default 50

    Circuit breaker:
      - CIRCUIT_BREAKER_FAILURE_THRESHOLD   -> default 5
      - CIRCUIT_BREAKER_ROLLING_WINDOW      -> seconds, default 60
      - CIRCUIT_BREAKER_RECOVERY_TIMEOUT    -> seconds, default 30
      - CIRCUIT_BREAKER_SUCCESS_THRESHOLD   -> default 2

    Feature flags:
      - FEATURE_FLAGS_SOURCE         -> "db+redis" (default)
      - FEATURE_FLAGS_ENABLE_TENANT  -> bool, default true
      - FEATURE_FLAGS_ENABLE_USER    -> bool, default true

    Service-specific:
      - WORKER_QUEUE_NAME            -> queue/stream name; optional
      - WORKER_QUEUE_KIND            -> "redis_stream" (default)
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # Core
    APP_ENV: str = Field(
        default="local",
        description="Deployment environment: local | dev | staging | prod",
    )
    SERVICE_NAME: str = Field(
        default="api",
        description="Logical service name used for metrics and logging.",
    )
    LOG_LEVEL: str = Field(
        default="INFO",
        description="Root log level: DEBUG | INFO | WARNING | ERROR",
    )

    # Database (async Postgres with asyncpg)
    POSTGRES_DSN: PostgresDsn = Field(
        ...,
        description="Async SQLAlchemy DSN, e.g. postgresql+asyncpg://user:pass@host:5432/dbname",
    )
    DB_POOL_SIZE: int = Field(
        default=10,
        description="Base size of the DB connection pool.",
    )
    DB_MAX_OVERFLOW: int = Field(
        default=20,
        description="Maximum overflow connections beyond pool size.",
    )
    DB_POOL_TIMEOUT: float = Field(
        default=30.0,
        description="Seconds to wait for a connection from the pool.",
    )

    # Redis
    REDIS_URL: str = Field(
        ...,
        description="Redis connection URL, e.g. redis://:pass@host:6379/0",
    )
    MSAAS_REDIS_PREFIX: str = Field(
        default="msaas",
        description='Logical key prefix, combined with APP_ENV as "msaas:{env}:".',
    )
    REDIS_POOL_SIZE: int = Field(
        default=10,
        description="Base size of the Redis connection pool.",
    )
    REDIS_MAX_CONNECTIONS: int = Field(
        default=50,
        description="Upper bound on total Redis connections (if supported by client).",
    )

    # Circuit breaker defaults
    CIRCUIT_BREAKER_FAILURE_THRESHOLD: int = Field(
        default=5,
        description="Number of failures within the rolling window to open the breaker.",
    )
    CIRCUIT_BREAKER_ROLLING_WINDOW: int = Field(
        default=60,
        description="Rolling window size in seconds for counting failures.",
    )
    CIRCUIT_BREAKER_RECOVERY_TIMEOUT: int = Field(
        default=30,
        description="Seconds to remain OPEN before attempting HALF_OPEN.",
    )
    CIRCUIT_BREAKER_SUCCESS_THRESHOLD: int = Field(
        default=2,
        description="Consecutive successes in HALF_OPEN before closing the breaker.",
    )

    # Feature flags
    FEATURE_FLAGS_SOURCE: str = Field(
        default="db+redis",
        description='Source of truth for flags: "db+redis" by default.',
    )
    FEATURE_FLAGS_ENABLE_TENANT: bool = Field(
        default=True,
        description="Enable tenant-level feature flags.",
    )
    FEATURE_FLAGS_ENABLE_USER: bool = Field(
        default=True,
        description="Enable user-level feature flags.",
    )

    # Service-specific / workers
    WORKER_QUEUE_NAME: Optional[str] = Field(
        default=None,
        description="Queue/stream name for worker processes; may be derived from SERVICE_NAME.",
    )
    WORKER_QUEUE_KIND: str = Field(
        default="redis_stream",
        description='Queue kind identifier, default "redis_stream".',
    )

    @validator("APP_ENV")
    def _normalize_env(cls, v: str) -> str:
        """
        Normalize APP_ENV to one of: local | dev | staging | prod.
        Accept common synonyms but collapse them for metrics/labels.
        """
        if not v:
            return "local"

        value = v.lower().strip()
        if value in {"local", "localhost"}:
            return "local"
        if value in {"dev", "development"}:
            return "dev"
        if value in {"staging", "stage"}:
            return "staging"
        if value in {"prod", "production"}:
            return "prod"
        # Fallback: keep as-is but lowercase, to avoid surprising breakage
        return value

    @validator("POSTGRES_DSN", pre=True)
    def _fallback_database_url(cls, v: Any) -> Any:
        """
        Allow DATABASE_URL as a legacy alias for POSTGRES_DSN.

        If POSTGRES_DSN is not set, but DATABASE_URL is, use DATABASE_URL.
        """
        if v is not None and v != "":
            return v
        legacy = os.getenv("DATABASE_URL")
        if legacy:
            return legacy
        return v

    @property
    def env_label(self) -> str:
        """
        Normalized environment label used for metrics (`env` label).
        """
        return self.APP_ENV

    @property
    def service_label(self) -> str:
        """
        Service label used for metrics (`service` label).
        """
        return self.SERVICE_NAME

    def redis_key_prefix(self) -> str:
        """
        Compute the canonical Redis key prefix, e.g. "msaas:dev:".
        """
        return f"{self.MSAAS_REDIS_PREFIX}:{self.env_label}:"

    def describe(self) -> dict[str, Any]:
        """
        Lightweight, non-secret representation suitable for logging/debugging.
        """
        return {
            "APP_ENV": self.APP_ENV,
            "SERVICE_NAME": self.SERVICE_NAME,
            "LOG_LEVEL": self.LOG_LEVEL,
            "DB_POOL_SIZE": self.DB_POOL_SIZE,
            "DB_MAX_OVERFLOW": self.DB_MAX_OVERFLOW,
            "DB_POOL_TIMEOUT": self.DB_POOL_TIMEOUT,
            "REDIS_POOL_SIZE": self.REDIS_POOL_SIZE,
            "REDIS_MAX_CONNECTIONS": self.REDIS_MAX_CONNECTIONS,
            "FEATURE_FLAGS_SOURCE": self.FEATURE_FLAGS_SOURCE,
            "FEATURE_FLAGS_ENABLE_TENANT": self.FEATURE_FLAGS_ENABLE_TENANT,
            "FEATURE_FLAGS_ENABLE_USER": self.FEATURE_FLAGS_ENABLE_USER,
            "WORKER_QUEUE_NAME": self.WORKER_QUEUE_NAME,
            "WORKER_QUEUE_KIND": self.WORKER_QUEUE_KIND,
        }


@lru_cache
def get_settings() -> Settings:
    """
    Return a cached Settings instance.

    This is safe to use across the application (FastAPI app, workers,
    agents, metrics) and avoids re-parsing the environment repeatedly.
    """
    return Settings()

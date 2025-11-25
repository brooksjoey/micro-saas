from __future__ import annotations

import enum
import logging
import threading
import time
from collections import deque
from typing import Callable, Deque, Dict, Generic, Optional, TypeVar

from backend.app.config import get_settings


logger = logging.getLogger(__name__)

T = TypeVar("T")


class CircuitState(str, enum.Enum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


class CircuitOpenError(RuntimeError):
    """Raised when a call is rejected because the circuit is open."""


class CircuitBreaker(Generic[T]):
    """Thread-safe circuit breaker implementation.

    Supports a rolling failure window, open/half-open/closed states, and
    configurable thresholds. Designed to work in async environments but does
    not perform any I/O itself.
    """

    def __init__(
        self,
        name: str,
        *,
        failure_threshold: int,
        rolling_window_seconds: float,
        recovery_timeout_seconds: float,
        success_threshold: int,
    ) -> None:
        self._name = name
        self._failure_threshold = failure_threshold
        self._rolling_window = rolling_window_seconds
        self._recovery_timeout = recovery_timeout_seconds
        self._success_threshold = success_threshold

        self._state: CircuitState = CircuitState.CLOSED
        self._opened_at: Optional[float] = None
        self._failure_timestamps: Deque[float] = deque()
        self._success_count: int = 0
        self._lock = threading.Lock()

    @property
    def name(self) -> str:
        return self._name

    @property
    def current_state(self) -> CircuitState:
        with self._lock:
            return self._state

    def _now(self) -> float:
        return time.monotonic()

    def _prune_failures(self, now: float) -> None:
        window_start = now - self._rolling_window
        while self._failure_timestamps and self._failure_timestamps[0] < window_start:
            self._failure_timestamps.popleft()

    def _before_call(self) -> None:
        now = self._now()
        with self._lock:
            if self._state is CircuitState.OPEN:
                assert self._opened_at is not None
                if now - self._opened_at >= self._recovery_timeout:
                    # Move to HALF_OPEN and allow a trial call.
                    self._state = CircuitState.HALF_OPEN
                    self._success_count = 0
                else:
                    raise CircuitOpenError(f"circuit '{self._name}' is open")
            # CLOSED or HALF_OPEN ⇒ allow call

    def record_success(self) -> None:
        now = self._now()
        with self._lock:
            self._prune_failures(now)
            if self._state is CircuitState.HALF_OPEN:
                self._success_count += 1
                if self._success_count >= self._success_threshold:
                    # Close the breaker
                    self._state = CircuitState.CLOSED
                    self._failure_timestamps.clear()
                    self._success_count = 0
                    self._opened_at = None
            # CLOSED: just prune old failures

    def record_failure(self, exc: BaseException | None = None) -> None:
        now = self._now()
        with self._lock:
            self._prune_failures(now)
            self._failure_timestamps.append(now)

            if self._state is CircuitState.HALF_OPEN:
                # Any failure immediately re-opens circuit.
                self._state = CircuitState.OPEN
                self._opened_at = now
                self._success_count = 0

            elif self._state is CircuitState.CLOSED:
                if len(self._failure_timestamps) >= self._failure_threshold:
                    self._state = CircuitState.OPEN
                    self._opened_at = now
                    self._success_count = 0

        if exc is not None:
            logger.exception(
                "circuit_breaker_failure",
                extra={"breaker": self._name, "state": self.current_state},
            )

    def call(self, fn: Callable[..., T], *args, **kwargs) -> T:
        """Execute a synchronous function under circuit breaker control."""
        self._before_call()
        try:
            result = fn(*args, **kwargs)
        except BaseException as exc:
            self.record_failure(exc)
            raise
        else:
            self.record_success()
            return result

    async def call_async(self, fn: Callable[..., T], *args, **kwargs) -> T:
        """Execute an async function under circuit breaker control."""
        self._before_call()
        try:
            result = await fn(*args, **kwargs)
        except BaseException as exc:
            self.record_failure(exc)
            raise
        else:
            self.record_success()
            return result


_BREAKERS: Dict[str, CircuitBreaker[Any]] = {}
_BREAKERS_LOCK = threading.Lock()


def _default_breaker_params() -> dict:
    settings = get_settings()
    return {
        "failure_threshold": settings.CIRCUIT_BREAKER_FAILURE_THRESHOLD,
        "rolling_window_seconds": float(settings.CIRCUIT_BREAKER_ROLLING_WINDOW),
        "recovery_timeout_seconds": float(settings.CIRCUIT_BREAKER_RECOVERY_TIMEOUT),
        "success_threshold": settings.CIRCUIT_BREAKER_SUCCESS_THRESHOLD,
    }


def get_circuit_breaker(
    name: str,
    **overrides: float | int,
) -> CircuitBreaker[Any]:
    """Get or create a named CircuitBreaker instance.

    The breaker is configured from global settings, with optional overrides.
    """
    global _BREAKERS
    if name in _BREAKERS:
        return _BREAKERS[name]

    with _BREAKERS_LOCK:
        if name in _BREAKERS:
            return _BREAKERS[name]
        params = _default_breaker_params()
        params.update(overrides)
        breaker = CircuitBreaker(
            name=name,
            failure_threshold=int(params["failure_threshold"]),
            rolling_window_seconds=float(params["rolling_window_seconds"]),
            recovery_timeout_seconds=float(params["recovery_timeout_seconds"]),
            success_threshold=int(params["success_threshold"]),
        )
        _BREAKERS[name] = breaker
        return breaker

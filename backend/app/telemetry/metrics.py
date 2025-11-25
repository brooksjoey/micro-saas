from __future__ import annotations

import logging
import os
import threading
import time
from typing import Dict, Mapping, Optional, Tuple

from prometheus_client import CollectorRegistry, Counter, Gauge, Histogram


_logger = logging.getLogger(__name__)


# Single process-wide registry for all Prometheus metrics in this service.
_REGISTRY: CollectorRegistry = CollectorRegistry()

_BASE_LABELS_LOCK = threading.Lock()
_BASE_LABELS: Optional[Dict[str, str]] = None


def _detect_service_and_env() -> Tuple[str, str]:
    """
    Determine the base `service` and `env` labels.

    Preference order:
    1. backend.app.config.get_settings() if available.
    2. Environment variables (MSAAS_SERVICE_NAME / MSAAS_ENV, APP_NAME / APP_ENV, etc.).
    3. Safe defaults: service="api", env="local".
    """
    service = os.getenv("MSAAS_SERVICE_NAME") or os.getenv("SERVICE_NAME") or os.getenv("APP_NAME") or "api"
    env = (
        os.getenv("MSAAS_ENV")
        or os.getenv("APP_ENV")
        or os.getenv("ENVIRONMENT")
        or os.getenv("ENV")
        or "local"
    )

    try:
        # Optional import – config module may not be implemented yet.
        from backend.app.config import get_settings  # type: ignore
    except Exception:
        return service, env

    try:
        settings = get_settings()  # type: ignore[call-arg]
    except Exception:
        # If configuration access fails, fall back to environment.
        return service, env

    # Prefer explicit settings attributes if present.
    service_from_settings = getattr(settings, "SERVICE_NAME", None) or getattr(
        settings, "APP_NAME", None
    ) or getattr(settings, "OTEL_SERVICE_NAME", None)
    env_from_settings = getattr(settings, "ENV", None) or getattr(
        settings, "APP_ENV", None
    ) or getattr(settings, "ENVIRONMENT", None)

    if isinstance(service_from_settings, str) and service_from_settings.strip():
        service = service_from_settings.strip()
    if isinstance(env_from_settings, str) and env_from_settings.strip():
        env = env_from_settings.strip()

    return service, env


def get_base_labels() -> Dict[str, str]:
    """
    Return the mandatory base labels for all metrics.

    Always includes:
    - service
    - env
    """
    global _BASE_LABELS
    if _BASE_LABELS is None:
        with _BASE_LABELS_LOCK:
            if _BASE_LABELS is None:
                service, env = _detect_service_and_env()
                _BASE_LABELS = {"service": service, "env": env}
                _logger.info(
                    "Initialized Prometheus base labels",
                    extra={"service": service, "env": env},
                )
    # Return a shallow copy to prevent accidental mutation.
    return dict(_BASE_LABELS)


def get_registry() -> CollectorRegistry:
    """
    Access the shared CollectorRegistry for this process.
    """
    return _REGISTRY


# ---------------------------------------------------------------------------
# Metric definitions
# ---------------------------------------------------------------------------

# 1) API HTTP metrics
API_REQUEST_LATENCY_SECONDS = Histogram(
    "http_server_request_duration_seconds",
    "HTTP server request latency in seconds.",
    labelnames=["service", "env", "route", "method", "status_code"],
    buckets=[0.05, 0.1, 0.25, 0.5, 1.0, 2.0, 5.0],
    registry=_REGISTRY,
)

API_REQUESTS_TOTAL = Counter(
    "http_server_requests_total",
    "Total HTTP server requests processed.",
    labelnames=["service", "env", "route", "method", "status_code"],
    registry=_REGISTRY,
)


# 2) Job processing metrics (generic and browser workers)

JOB_PROCESSING_DURATION_SECONDS = Histogram(
    "msaas_job_processing_duration_seconds",
    "Job processing duration in seconds.",
    labelnames=["service", "env", "job_type", "result"],
    buckets=[0.05, 0.1, 0.25, 0.5, 1.0, 2.0, 5.0, 10.0, 30.0],
    registry=_REGISTRY,
)

JOB_ERRORS_TOTAL = Counter(
    "msaas_job_errors_total",
    "Total job errors by job type and error type.",
    labelnames=["service", "env", "job_type", "error_type"],
    registry=_REGISTRY,
)

QUEUE_DEPTH = Gauge(
    "msaas_queue_depth",
    "Current depth of internal job/worker queues.",
    labelnames=["service", "env", "queue_name", "queue_kind"],
    registry=_REGISTRY,
)

BROWSER_JOB_PROCESSING_SECONDS = Histogram(
    "jobs_browser_processing_seconds",
    "Browser worker job processing duration in seconds.",
    labelnames=["service", "env", "job_type", "result"],
    buckets=[0.05, 0.1, 0.25, 0.5, 1.0, 2.0, 5.0, 10.0, 30.0],
    registry=_REGISTRY,
)

BROWSER_JOB_ERRORS_TOTAL = Counter(
    "jobs_browser_errors_total",
    "Total browser worker job errors.",
    labelnames=["service", "env", "job_type", "reason"],
    registry=_REGISTRY,
)

BROWSER_JOB_PROCESSED_TOTAL = Counter(
    "jobs_browser_processed_total",
    "Total browser worker jobs processed by status.",
    labelnames=["service", "env", "job_type", "status"],
    registry=_REGISTRY,
)

BROWSER_PENDING_MESSAGES = Gauge(
    "jobs_browser_pending_messages",
    "Number of pending browser worker messages.",
    labelnames=["service", "env", "queue_name"],
    registry=_REGISTRY,
)


# 3) JWT auth metrics

JWT_VALIDATION_DURATION_SECONDS = Histogram(
    "msaas_jwt_validation_duration_seconds",
    "JWT validation latency in seconds.",
    labelnames=["service", "env", "issuer", "outcome"],
    buckets=[0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0],
    registry=_REGISTRY,
)

JWT_INVALID_TOTAL = Counter(
    "auth_jwt_invalid_total",
    "Total invalid JWTs by reason.",
    labelnames=["service", "env", "reason"],
    registry=_REGISTRY,
)


# 4) Circuit breaker metrics

CIRCUIT_BREAKER_STATE = Gauge(
    "circuit_state",
    "Circuit breaker state (0=closed, 1=open, 2=half_open).",
    labelnames=["service", "env", "breaker_name", "target"],
    registry=_REGISTRY,
)


# 5) Billing reconciliation metrics

BILLING_RECONCILIATION_LAST_SUCCESS_UNIXTIME = Gauge(
    "billing_reconciliation_last_success_timestamp",
    "Unix timestamp of the last successful billing reconciliation.",
    labelnames=["service", "env", "provider"],
    registry=_REGISTRY,
)


# 6) Agent workflow metrics

AGENT_WORKFLOW_DURATION_SECONDS = Histogram(
    "agents_workflow_execution_seconds",
    "Agent workflow execution duration in seconds.",
    labelnames=["service", "env", "workflow_name", "outcome"],
    buckets=[0.1, 0.5, 1.0, 2.0, 5.0, 10.0, 30.0, 60.0],
    registry=_REGISTRY,
)

AGENT_FALLBACK_TOTAL = Counter(
    "msaas_agent_fallback_total",
    "Total agent fallback invocations.",
    labelnames=["service", "env", "workflow_name", "fallback_type"],
    registry=_REGISTRY,
)


# ---------------------------------------------------------------------------
# Helper APIs
# ---------------------------------------------------------------------------


def _coerce_non_negative_duration(duration_seconds: float) -> float:
    if duration_seconds < 0:
        _logger.warning(
            "Received negative duration_seconds; coercing to 0.0",
            extra={"duration_seconds": duration_seconds},
        )
        return 0.0
    return duration_seconds


def _is_browser_service(service_name: str) -> bool:
    """
    Heuristic to detect browser worker services.
    Design docs use names like `browser-worker` or `worker-browser`.
    """
    return "browser" in service_name.lower()


def observe_api_request(
    route: str,
    method: str,
    status_code: int,
    duration_seconds: float,
) -> None:
    """
    Record latency and count for a single HTTP API request.

    route: normalized path template, e.g. "/jobs/{job_id}"
    method: HTTP method, e.g. "GET"
    status_code: HTTP status code as integer
    duration_seconds: duration of the request in seconds
    """
    duration = _coerce_non_negative_duration(float(duration_seconds))
    base_labels = get_base_labels()
    labels = {
        **base_labels,
        "route": route,
        "method": method.upper(),
        "status_code": str(int(status_code)),
    }
    API_REQUEST_LATENCY_SECONDS.labels(**labels).observe(duration)
    API_REQUESTS_TOTAL.labels(**labels).inc()


def observe_job_result(
    job_type: str,
    result: str,
    duration_seconds: float,
    error_type: Optional[str] = None,
) -> None:
    """
    Record metrics for a processed job (generic or browser worker).

    job_type: logical job type, e.g. "scrape", "email_notification"
    result: "success", "failed", "timeout", "cancelled", etc.
    duration_seconds: job processing time in seconds
    error_type: optional error classification, e.g. "timeout", "playwright_error"
    """
    duration = _coerce_non_negative_duration(float(duration_seconds))
    base_labels = get_base_labels()
    service_name = base_labels.get("service", "")

    generic_labels = {
        **base_labels,
        "job_type": job_type,
        "result": result,
    }
    JOB_PROCESSING_DURATION_SECONDS.labels(**generic_labels).observe(duration)

    if error_type:
        error_labels = {
            **base_labels,
            "job_type": job_type,
            "error_type": error_type,
        }
        JOB_ERRORS_TOTAL.labels(**error_labels).inc()

    # For browser worker services, also populate the browser-specific metrics.
    if _is_browser_service(service_name):
        browser_labels = {
            **base_labels,
            "job_type": job_type,
            "result": result,
        }
        BROWSER_JOB_PROCESSING_SECONDS.labels(**browser_labels).observe(duration)

        processed_labels = {
            **base_labels,
            "job_type": job_type,
            "status": result,
        }
        BROWSER_JOB_PROCESSED_TOTAL.labels(**processed_labels).inc()

        if result.lower() in {"failed", "timeout"} or error_type:
            reason = error_type or result
            error_labels_browser = {
                **base_labels,
                "job_type": job_type,
                "reason": reason,
            }
            BROWSER_JOB_ERRORS_TOTAL.labels(**error_labels_browser).inc()


def set_queue_depth(
    queue_name: str,
    queue_kind: str,
    depth: int,
) -> None:
    """
    Set the current depth for a given queue.

    queue_kind: e.g. "redis_list", "redis_stream"
    """
    value = int(depth)
    if value < 0:
        _logger.warning(
            "Received negative queue depth; coercing to 0",
            extra={"queue_name": queue_name, "queue_kind": queue_kind, "depth": depth},
        )
        value = 0

    base_labels = get_base_labels()
    labels = {
        **base_labels,
        "queue_name": queue_name,
        "queue_kind": queue_kind,
    }
    QUEUE_DEPTH.labels(**labels).set(value)

    # For browser worker services, keep the browser-specific pending gauge in sync.
    service_name = base_labels.get("service", "")
    if _is_browser_service(service_name):
        browser_labels = {
            **base_labels,
            "queue_name": queue_name,
        }
        BROWSER_PENDING_MESSAGES.labels(**browser_labels).set(value)


def observe_jwt_validation(
    issuer: str,
    outcome: str,
    reason: Optional[str],
    duration_seconds: float,
) -> None:
    """
    Record metrics for JWT validation.

    issuer: JWT issuer / provider, e.g. "auth0", "supabase"
    outcome: "valid", "invalid", "expired", "signature_error", etc.
    reason: more detailed invalid reason; used for auth_jwt_invalid_total
    duration_seconds: validation latency in seconds
    """
    duration = _coerce_non_negative_duration(float(duration_seconds))
    base_labels = get_base_labels()

    labels = {
        **base_labels,
        "issuer": issuer,
        "outcome": outcome,
    }
    JWT_VALIDATION_DURATION_SECONDS.labels(**labels).observe(duration)

    if outcome.lower() != "valid":
        reason_value = reason or outcome
        invalid_labels = {
            **base_labels,
            "reason": reason_value,
        }
        JWT_INVALID_TOTAL.labels(**invalid_labels).inc()


def set_circuit_breaker_state(
    breaker_name: str,
    target_system: str,
    state: int,
) -> None:
    """
    Set the circuit breaker state.

    state: 0 = closed, 1 = open, 2 = half_open
    """
    if state not in (0, 1, 2):
        raise ValueError(f"Invalid circuit breaker state: {state}. Expected 0, 1, or 2.")

    base_labels = get_base_labels()
    labels = {
        **base_labels,
        "breaker_name": breaker_name,
        "target": target_system,
    }
    CIRCUIT_BREAKER_STATE.labels(**labels).set(int(state))


def set_billing_reconciliation_success(
    provider: str,
    timestamp: Optional[float] = None,
) -> None:
    """
    Record the timestamp of the last successful billing reconciliation.

    provider: billing provider, e.g. "stripe"
    timestamp: Unix epoch seconds; defaults to time.time() if omitted.
    """
    ts = float(timestamp) if timestamp is not None else time.time()
    if ts < 0:
        _logger.warning(
            "Received negative billing reconciliation timestamp; coercing to current time",
            extra={"timestamp": timestamp},
        )
        ts = time.time()

    base_labels = get_base_labels()
    labels = {
        **base_labels,
        "provider": provider,
    }
    BILLING_RECONCILIATION_LAST_SUCCESS_UNIXTIME.labels(**labels).set(ts)


def observe_agent_workflow(
    workflow_name: str,
    outcome: str,
    duration_seconds: float,
    fallback_type: Optional[str] = None,
) -> None:
    """
    Record metrics for an agent workflow execution.

    workflow_name: logical workflow name
    outcome: "success", "failed", "timeout", "fallback_used", etc.
    duration_seconds: workflow execution duration
    fallback_type: optional description of the fallback used
    """
    duration = _coerce_non_negative_duration(float(duration_seconds))
    base_labels = get_base_labels()

    labels = {
        **base_labels,
        "workflow_name": workflow_name,
        "outcome": outcome,
    }
    AGENT_WORKFLOW_DURATION_SECONDS.labels(**labels).observe(duration)

    if fallback_type:
        fb_labels = {
            **base_labels,
            "workflow_name": workflow_name,
            "fallback_type": fallback_type,
        }
        AGENT_FALLBACK_TOTAL.labels(**fb_labels).inc()


__all__ = [
    "get_registry",
    "get_base_labels",
    "observe_api_request",
    "observe_job_result",
    "set_queue_depth",
    "observe_jwt_validation",
    "set_circuit_breaker_state",
    "set_billing_reconciliation_success",
    "observe_agent_workflow",
]

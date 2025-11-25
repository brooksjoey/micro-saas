from __future__ import annotations

import logging
import time
from typing import Callable, TypeVar, Coroutine, Any, Awaitable

from backend.app.telemetry.metrics import (
    observe_job_result,
)

T = TypeVar("T")

logger = logging.getLogger(__name__)


def instrumented_job_execution(job_type: str, func: Callable[[], T]) -> T:
    """
    Execute a synchronous job function with full metric instrumentation.

    Records:
    - Job processing duration
    - Job error counters (with error_type derived from exception)
    - Browser-specific metrics automatically (based on service label)

    All exceptions are re-raised after metrics are emitted.
    """
    start = time.perf_counter()
    try:
        result = func()
        duration = time.perf_counter() - start
        observe_job_result(
            job_type=job_type,
            result="success",
            duration_seconds=duration,
            error_type=None,
        )
        return result
    except Exception as exc:
        duration = time.perf_counter() - start
        error_type = exc.__class__.__name__
        observe_job_result(
            job_type=job_type,
            result="failed",
            duration_seconds=duration,
            error_type=error_type,
        )
        logger.exception(
            "job_execution_failed",
            extra={"job_type": job_type, "error_type": error_type},
        )
        raise


async def instrumented_job_execution_async(
    job_type: str,
    coro: Coroutine[Any, Any, T],
) -> T:
    """
    Async equivalent of the synchronous instrumentation wrapper.

    Records:
    - Job processing duration
    - Job error counters
    """
    start = time.perf_counter()
    try:
        result = await coro
        duration = time.perf_counter() - start
        observe_job_result(
            job_type=job_type,
            result="success",
            duration_seconds=duration,
            error_type=None,
        )
        return result
    except Exception as exc:
        duration = time.perf_counter() - start
        error_type = exc.__class__.__name__
        observe_job_result(
            job_type=job_type,
            result="failed",
            duration_seconds=duration,
            error_type=error_type,
        )
        logger.exception(
            "job_execution_failed_async",
            extra={"job_type": job_type, "error_type": error_type},
        )
        raise


# ---------------------------------------------------------------------------
# Example usage for future engineers (real code, commented out)
# ---------------------------------------------------------------------------
#
# from backend.some_queue_lib import pop_job
# from .job_worker import instrumented_job_execution
#
# def worker_loop():
#     while True:
#         job = pop_job("default")
#         instrumented_job_execution(job_type=job.type, func=lambda: process_job(job))
#
# ---------------------------------------------------------------------------

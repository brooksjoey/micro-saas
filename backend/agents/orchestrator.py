from __future__ import annotations

import logging
import time
from typing import Callable, TypeVar, Coroutine, Any

from backend.app.telemetry.metrics import observe_agent_workflow


logger = logging.getLogger(__name__)
T = TypeVar("T")


class FallbackUsed(Exception):
    """Raised internally to signal fallback path execution."""


def run_instrumented_workflow(
    workflow_name: str,
    fn: Callable[[], T],
) -> T:
    """
    Wrap a synchronous agent workflow with complete instrumentation.

    Emits:
      - Workflow duration histogram
      - Fallback counter if fallback path is used
    """
    start = time.perf_counter()
    outcome = "success"
    fallback_type = None

    try:
        result = fn()
        return result

    except FallbackUsed as fb:
        outcome = "fallback_used"
        fallback_type = fb.args[0] if fb.args else "fallback"
        logger.info(
            "agent_workflow_fallback",
            extra={"workflow_name": workflow_name, "fallback_type": fallback_type},
        )
        raise

    except Exception:
        outcome = "failed"
        logger.exception("agent_workflow_failed", extra={"workflow_name": workflow_name})
        raise

    finally:
        duration = time.perf_counter() - start
        observe_agent_workflow(
            workflow_name=workflow_name,
            outcome=outcome,
            duration_seconds=duration,
            fallback_type=fallback_type,
        )


async def run_instrumented_workflow_async(
    workflow_name: str,
    coro_fn: Callable[[], Coroutine[Any, Any, T]],
) -> T:
    """
    Async version of the instrumented workflow wrapper.
    """
    start = time.perf_counter()
    outcome = "success"
    fallback_type = None

    try:
        result = await coro_fn()
        return result

    except FallbackUsed as fb:
        outcome = "fallback_used"
        fallback_type = fb.args[0] if fb.args else "fallback"
        logger.info(
            "agent_workflow_fallback_async",
            extra={"workflow_name": workflow_name, "fallback_type": fallback_type},
        )
        raise

    except Exception:
        outcome = "failed"
        logger.exception(
            "agent_workflow_failed_async", extra={"workflow_name": workflow_name}
        )
        raise

    finally:
        duration = time.perf_counter() - start
        observe_agent_workflow(
            workflow_name=workflow_name,
            outcome=outcome,
            duration_seconds=duration,
            fallback_type=fallback_type,
        )


# ---------------------------------------------------------------------------
# Example for future engineers (real code, commented)
# ---------------------------------------------------------------------------
#
# def example_workflow():
#     if external_api_ok():
#         return call_llm()
#     else:
#         raise FallbackUsed("llm_fallback_static_response")
#
# run_instrumented_workflow("agent_user_support", example_workflow)
#
# ---------------------------------------------------------------------------

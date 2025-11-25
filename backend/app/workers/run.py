from __future__ import annotations

import logging
import random
import time

from backend.app.telemetry.metrics import set_queue_depth
from backend.app.workers.job_worker import instrumented_job_execution


logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Placeholder queue mechanisms — real implementation belongs elsewhere.
# ---------------------------------------------------------------------------

def get_queue_depth(queue_name: str) -> int:
    """
    Placeholder for real queue depth lookup.
    Must be replaced by Redis / SQS / Kafka / Postgres implementation.
    """
    return random.randint(0, 50)


def get_next_job(queue_name: str) -> dict | None:
    """
    Placeholder for job retrieval.
    Returns a dict with at least a 'type' field.
    """
    if random.random() < 0.3:
        return None
    return {"type": "generic_task", "payload": {}}


def process_job(job: dict) -> None:
    """
    Placeholder for actual job execution logic.
    """
    # Simulate variable duration and occasional failures.
    time.sleep(random.uniform(0.01, 0.15))
    if random.random() < 0.05:
        raise RuntimeError("simulated_failure")


# ---------------------------------------------------------------------------
# Worker runtime
# ---------------------------------------------------------------------------

QUEUE_NAME = "jobs:default"
QUEUE_KIND = "redis_list"  # Replace with Streams or SQS in real implementation.


def run_worker() -> None:
    """
    Minimal worker loop showing how queue depth and job execution metrics integrate.

    Future engineers:
      - Replace get_queue_depth / get_next_job / process_job with real implementations.
      - Do NOT change the metric calls; they are the canonical instrumentation path.
    """
    logger.info("worker_started", extra={"queue_name": QUEUE_NAME})

    while True:
        # Emit queue depth gauge
        depth = get_queue_depth(QUEUE_NAME)
        set_queue_depth(QUEUE_name=QUEUE_NAME, queue_kind=QUEUE_KIND, depth=depth)

        # Fetch a job (placeholder)
        job = get_next_job(QUEUE_NAME)
        if job is None:
            time.sleep(0.1)
            continue

        # Execute with full instrumentation
        instrumented_job_execution(
            job_type=job["type"],
            func=lambda: process_job(job),
        )

from __future__ import annotations

import logging
import time

from backend.app.telemetry.metrics import set_billing_reconciliation_success


logger = logging.getLogger(__name__)


def _perform_reconciliation_logic() -> None:
    """
    Placeholder for real Stripe/SaaS usage reconciliation.
    """
    # Simulate real work
    time.sleep(0.05)
    # Simulate occasional error
    # raise RuntimeError("stripe_unavailable")


def run_usage_reconciliation(provider: str = "stripe") -> None:
    """
    Run a full usage reconciliation cycle and emit a success timestamp metric.

    Metric emission rules:
      - The metric MUST be emitted only after a fully successful run.
      - Partial or failed runs must NOT update the metric.
    """
    try:
        _perform_reconciliation_logic()
    except Exception:
        logger.exception("billing_reconciliation_failed", extra={"provider": provider})
        raise

    # Success
    set_billing_reconciliation_success(provider=provider)
    logger.info("billing_reconciliation_success", extra={"provider": provider})

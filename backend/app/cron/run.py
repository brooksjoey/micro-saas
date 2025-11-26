"""Billing reconciliation cron job.

This module provides the entry point for running billing reconciliation
and usage reporting jobs. It can be run as:

    python -m app.cron.run
    python -m app.cron.run reconcile
    python -m app.cron.run reconcile --start-date 2025-01-01 --end-date 2025-01-15

The reconciliation job:
1. Aggregates usage_events for each active subscription
2. Updates usage_counters with the authoritative count
3. Reports usage to Stripe (if not already reported)
4. Flags discrepancies between internal and Stripe usage
5. Records the reconciliation timestamp for monitoring
"""
from __future__ import annotations

import argparse
import asyncio
import logging
import sys
import time
from datetime import datetime, timedelta, timezone
from typing import Optional

logger = logging.getLogger(__name__)


async def reconcile(
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    dry_run: bool = False,
) -> dict:
    """Run billing reconciliation.
    
    Args:
        start_date: Start of date range (ISO format, optional)
        end_date: End of date range (ISO format, optional)
        dry_run: If True, report discrepancies without making changes
        
    Returns:
        Dictionary with reconciliation results:
        - users_processed: Number of users reconciled
        - discrepancies_found: Number of usage discrepancies
        - usage_reported: Number of usage records sent to Stripe
        - errors: List of error messages
    """
    from app.config import get_settings
    
    settings = get_settings()
    
    logger.info(
        "reconciliation_started",
        extra={
            "start_date": start_date,
            "end_date": end_date,
            "dry_run": dry_run,
        }
    )
    
    start_time = time.time()
    
    result = {
        "users_processed": 0,
        "discrepancies_found": 0,
        "usage_reported": 0,
        "errors": [],
        "duration_seconds": 0.0,
    }
    
    try:
        # Import billing reconciliation logic
        # This is a placeholder - actual implementation in app.billing.usage_reconciliation
        try:
            from app.billing.usage_reconciliation import run_reconciliation
            result = await run_reconciliation(
                start_date=start_date,
                end_date=end_date,
                dry_run=dry_run,
            )
        except ImportError:
            logger.warning("reconciliation_module_not_implemented")
            result["errors"].append("Reconciliation module not yet implemented")
        
        # Record success timestamp for monitoring
        try:
            from app.telemetry.metrics import set_billing_reconciliation_success
            set_billing_reconciliation_success(provider="stripe")
        except ImportError:
            pass
        
    except Exception as e:
        logger.exception("reconciliation_failed")
        result["errors"].append(str(e))
    
    result["duration_seconds"] = time.time() - start_time
    
    logger.info(
        "reconciliation_completed",
        extra={
            "users_processed": result.get("users_processed", 0),
            "discrepancies_found": result.get("discrepancies_found", 0),
            "duration_seconds": result.get("duration_seconds", 0),
            "errors": len(result.get("errors", [])),
        }
    )
    
    return result


async def report_usage_to_stripe() -> dict:
    """Report metered usage to Stripe.
    
    This job reports completed jobs as usage records to Stripe
    for metered billing.
    
    Returns:
        Dictionary with reporting results
    """
    logger.info("usage_reporting_started")
    
    result = {
        "records_reported": 0,
        "errors": [],
    }
    
    try:
        # Placeholder - actual implementation in app.billing
        try:
            from app.billing.stripe_client import report_usage
            result = await report_usage()
        except ImportError:
            logger.warning("stripe_client_not_implemented")
            result["errors"].append("Stripe client not yet implemented")
    except Exception as e:
        logger.exception("usage_reporting_failed")
        result["errors"].append(str(e))
    
    logger.info(
        "usage_reporting_completed",
        extra={
            "records_reported": result.get("records_reported", 0),
            "errors": len(result.get("errors", [])),
        }
    )
    
    return result


async def main_async(args: argparse.Namespace) -> int:
    """Async main entry point."""
    # Configure logging
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )
    
    if args.command == "reconcile":
        result = await reconcile(
            start_date=args.start_date,
            end_date=args.end_date,
            dry_run=args.dry_run,
        )
        
        if result.get("errors"):
            for error in result["errors"]:
                logger.error(f"Reconciliation error: {error}")
            return 1
        
        return 0
    
    elif args.command == "report-usage":
        result = await report_usage_to_stripe()
        
        if result.get("errors"):
            return 1
        
        return 0
    
    else:
        # Default: run daily reconciliation
        result = await reconcile()
        return 0 if not result.get("errors") else 1


def main() -> None:
    """Main entry point for the cron module."""
    parser = argparse.ArgumentParser(
        description="Billing cron jobs for Micro-SaaS platform"
    )
    subparsers = parser.add_subparsers(dest="command", help="Command to run")
    
    # reconcile command
    reconcile_parser = subparsers.add_parser(
        "reconcile",
        help="Run billing reconciliation"
    )
    reconcile_parser.add_argument(
        "--start-date",
        type=str,
        help="Start date for reconciliation (ISO format)",
    )
    reconcile_parser.add_argument(
        "--end-date",
        type=str,
        help="End date for reconciliation (ISO format)",
    )
    reconcile_parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Report discrepancies without making changes",
    )
    
    # report-usage command
    subparsers.add_parser(
        "report-usage",
        help="Report metered usage to Stripe"
    )
    
    args = parser.parse_args()
    
    # Run async main
    exit_code = asyncio.run(main_async(args))
    sys.exit(exit_code)


if __name__ == "__main__":
    main()

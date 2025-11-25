from __future__ import annotations

import logging

from fastapi import APIRouter, Response, status
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest

from ..telemetry.metrics import get_registry


_logger = logging.getLogger(__name__)

router = APIRouter(
    tags=["telemetry"],
)


@router.get(
    "/metrics",
    summary="Prometheus metrics endpoint",
    description="Exposes Prometheus metrics for this service in the text exposition format.",
)
async def metrics_endpoint() -> Response:
    """
    Prometheus scrape endpoint.

    Returns:
        A text/plain response in Prometheus exposition format with HTTP 200 on success.
        On failure to generate metrics, returns HTTP 500 with a minimal error body.
    """
    try:
        registry = get_registry()
        payload = generate_latest(registry)
    except Exception:
        _logger.exception("metrics_exposition_failed")
        return Response(
            content="metrics exposition failed\n",
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            media_type="text/plain; version=0.0.4; charset=utf-8",
        )

    return Response(
        content=payload,
        status_code=status.HTTP_200_OK,
        media_type=CONTENT_TYPE_LATEST,
    )

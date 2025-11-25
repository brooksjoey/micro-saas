from __future__ import annotations

from fastapi import FastAPI

from .routes.metrics import router as metrics_router


def create_app() -> FastAPI:
    """
    Application factory for the core FastAPI service.

    This minimal implementation wires the Prometheus /metrics endpoint.
    Additional routers, middleware, and telemetry can be added here as
    other parts of the system are implemented.
    """
    app = FastAPI(title="micro-saas-backend")

    # Metrics endpoint (no prefix) – scraped directly by Prometheus.
    app.include_router(metrics_router)

    return app


app = create_app()

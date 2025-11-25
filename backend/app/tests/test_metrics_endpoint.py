from __future__ import annotations

from fastapi.testclient import TestClient

from backend.app.main import app


client = TestClient(app)


def test_metrics_endpoint_exposes_core_metrics() -> None:
    response = client.get("/metrics")
    assert response.status_code == 200
    content_type = response.headers.get("content-type", "")
    assert content_type.startswith("text/plain")

    body = response.text
    assert body

    # Core API metrics
    assert "http_server_request_duration_seconds" in body
    assert "http_server_requests_total" in body

    # Job and queue metrics
    assert "msaas_job_processing_duration_seconds" in body
    assert "msaas_job_errors_total" in body
    assert "msaas_queue_depth" in body
    assert "jobs_browser_pending_messages" in body

    # JWT and auth metrics
    assert "msaas_jwt_validation_duration_seconds" in body
    assert "auth_jwt_invalid_total" in body

    # Circuit breaker and billing metrics
    assert "circuit_state" in body
    assert "billing_reconciliation_last_success_timestamp" in body

    # Agent workflow metrics
    assert "agents_workflow_execution_seconds" in body
    assert "msaas_agent_fallback_total" in body

"""PaperTrail AI — Phase 17 Observability, Structured Logging, Metrics & Error Taxonomy Tests."""

import json
import logging
from datetime import datetime, timedelta, timezone
import pytest
from fastapi.testclient import TestClient

from app.core.errors import ErrorCategory, classify_error, OperationalError
from app.core.logging import (
    CorrelationContext,
    StructuredJsonFormatter,
    get_current_correlation,
    sanitize_value,
    set_correlation_context,
)
from app.core.metrics import (
    MetricsRegistry,
    metrics,
    record_adapter_execution,
    record_audit_seal,
    record_claim_conflict,
    record_idempotency_duplicate,
    record_report_generation,
    record_retry,
    record_workflow_complete,
    record_workflow_start,
)
from app.core.state import AnalysisWorkflow, WorkflowState
from app.main import app
from app.orchestration.diagnostics import check_workflow_stuck
from app.orchestration.errors import LeaseAcquisitionError, StateSynchronizationError, StaleEventError


@pytest.fixture
def client():
    return TestClient(app)


def test_structured_json_formatter():
    """Verify that StructuredJsonFormatter outputs valid single-line JSON with standard fields."""
    formatter = StructuredJsonFormatter()
    logger = logging.getLogger("test.logger")
    record = logger.makeRecord(
        name="test.logger",
        level=logging.INFO,
        fn="test.py",
        lno=42,
        msg="Workflow state transition initiated",
        args=(),
        exc_info=None,
    )
    record.component = "orchestrator"
    record.operation = "state_transition"
    record.workflow_id = "wf-test-1234"
    record.workflow_revision = 3

    formatted_str = formatter.format(record)
    data = json.loads(formatted_str)

    assert data["severity"] == "INFO"
    assert data["logger"] == "test.logger"
    assert data["message"] == "Workflow state transition initiated"
    assert data["component"] == "orchestrator"
    assert data["operation"] == "state_transition"
    assert data["workflow_id"] == "wf-test-1234"
    assert data["workflow_revision"] == 3
    assert "timestamp" in data


def test_sensitive_data_redaction():
    """Verify that passwords, tokens, connection strings, and keys are redacted."""
    raw_payload = {
        "user": "admin",
        "api_key": "AIzaSyD-Secret1234567890",
        "token": "bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.dummy",
        "connection_string": "AccountName=test;AccountKey=SuperSecretKey1234567890+=",
        "safe_data": "Invoice #1001",
    }
    sanitized = sanitize_value(raw_payload)

    assert sanitized["user"] == "admin"
    assert sanitized["api_key"] == "[REDACTED]"
    assert sanitized["token"] == "[REDACTED]"
    assert sanitized["connection_string"] == "[REDACTED]"
    assert sanitized["safe_data"] == "Invoice #1001"


def test_correlation_context_propagation():
    """Verify that CorrelationContext sets and restores context variables."""
    assert "workflow_id" not in get_current_correlation()

    with CorrelationContext(workflow_id="wf-test-ctx", document_id="doc-test-ctx"):
        ctx = get_current_correlation()
        assert ctx["workflow_id"] == "wf-test-ctx"
        assert ctx["document_id"] == "doc-test-ctx"

    # Restored after context exit
    assert "workflow_id" not in get_current_correlation()


def test_metrics_registry_and_recording():
    """Verify that MetricsRegistry aggregates counters, gauges, and duration summaries."""
    metrics.reset_for_test()

    record_workflow_start("wf-test-01")
    record_workflow_start("wf-test-02")
    record_workflow_complete("wf-test-01", duration_seconds=12.5)
    record_adapter_execution("ForensicAdapter", duration_seconds=0.15, success=True)
    record_claim_conflict("wf-test-01")
    record_idempotency_duplicate("wf-test-01")
    record_report_generation(success=True, duration_seconds=0.35)
    record_audit_seal(success=True)

    snapshot = metrics.get_snapshot()
    assert snapshot["counters"]["workflow_started_total"] == 2.0
    assert snapshot["counters"]["workflow_completed_total"] == 1.0
    assert snapshot["counters"]["claim_conflict_total"] == 1.0
    assert snapshot["counters"]["idempotency_duplicate_total"] == 1.0
    assert snapshot["counters"]["report_generation_total"] == 1.0
    assert snapshot["counters"]["audit_seal_success_total"] == 1.0
    assert "workflow_duration_seconds" in snapshot["durations"]
    assert snapshot["durations"]["workflow_duration_seconds"]["count"] == 1
    assert snapshot["durations"]["workflow_duration_seconds"]["avg_seconds"] == 12.5


def test_metrics_api_endpoint(client):
    """Verify that GET /metrics returns the metrics snapshot."""
    response = client.get("/metrics")
    assert response.status_code == 200
    data = response.json()
    assert "timestamp_utc" in data
    assert "counters" in data
    assert "durations" in data


def test_error_taxonomy_classification():
    """Verify that classify_error accurately maps exception types to ErrorCategory."""
    err1 = ValueError("Invalid document format")
    assert classify_error(err1) == ErrorCategory.VALIDATION_ERROR

    err2 = LeaseAcquisitionError("key", "worker-1", "2026-08-30T00:00:00Z")
    assert classify_error(err2) == ErrorCategory.CLAIM_CONFLICT

    err3 = StaleEventError("wf-1", 1, 2)
    assert classify_error(err3) == ErrorCategory.IDEMPOTENCY_DUPLICATE

    err4 = StateSynchronizationError("wf-1", 1, 2)
    assert classify_error(err4) == ErrorCategory.STATE_TRANSITION_ERROR

    err5 = RuntimeError("Azure Cosmos DB request rate too large (429)")
    assert classify_error(err5) == ErrorCategory.COSMOS_ERROR

    err6 = OperationalError("Failed to seal audit hash", category=ErrorCategory.AUDIT_ERROR)
    assert classify_error(err6) == ErrorCategory.AUDIT_ERROR


def test_stuck_workflow_detection():
    """Verify that check_workflow_stuck identifies stalled workflows beyond threshold."""
    now = datetime.now(timezone.utc)
    old_time = now - timedelta(seconds=400)

    stuck_wf = AnalysisWorkflow(
        workflow_id="wf-stuck-01",
        document_id="doc-stuck-01",
        current_state=WorkflowState.EXTRACTING,
        created_at=old_time,
        updated_at=old_time,
    )
    report = check_workflow_stuck(stuck_wf, threshold_seconds=300, reference_time=now)
    assert report is not None
    assert report.workflow_id == "wf-stuck-01"
    assert report.stuck_duration_seconds >= 400
    assert report.diagnostic_status == "STUCK"

    # Completed workflow should not be flagged as stuck
    completed_wf = AnalysisWorkflow(
        workflow_id="wf-comp-01",
        document_id="doc-comp-01",
        current_state=WorkflowState.COMPLETED,
        created_at=old_time,
        updated_at=old_time,
    )
    assert check_workflow_stuck(completed_wf, threshold_seconds=300, reference_time=now) is None


def test_api_correlation_headers(client):
    """Verify that HTTP requests inject and return X-Correlation-ID and X-Request-ID."""
    response = client.get("/health", headers={"X-Correlation-ID": "test-custom-corr-123"})
    assert response.status_code == 200
    assert response.headers.get("X-Correlation-ID") == "test-custom-corr-123"
    assert "X-Request-ID" in response.headers

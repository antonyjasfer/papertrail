import pytest
from fastapi.testclient import TestClient

from app.core.state import WorkflowState
from app.main import app
from app.orchestration.pipeline import PipelineRunner

client = TestClient(app)


from unittest.mock import MagicMock
from datetime import datetime, timezone
from app.models.analysis import GeminiExtractionPayload, LineItem
from app.models.document import DocumentMetadata
from app.services.document_intelligence import DocumentIntelligenceService
from app.orchestration.adapters.doc_intel_adapter import DocIntelAdapter
from app.orchestration.orchestrator import WorkflowOrchestrator


def test_pipeline_runner_full_e2e():
    mock_agent = MagicMock()
    mock_agent.extract_document_payload.return_value = GeminiExtractionPayload(
        document_type="invoice",
        vendor="Acme Corp",
        customer="Standard Customer",
        invoice_number="INV-E2E-100",
        dates=["2026-01-15"],
        amounts=["1000.00"],
        line_items=[
            LineItem(
                description="Standard Item",
                quantity="1",
                unit_price="1000.00",
                amount="1000.00",
            )
        ],
        extraction_confidence=0.95,
    )
    mock_storage = MagicMock()
    mock_storage.get_document_metadata.return_value = DocumentMetadata(
        document_id="doc-e2e-100",
        filename="invoice.pdf",
        content_type="application/pdf",
        size_bytes=1024,
        storage_bucket="papertrail-documents",
        storage_object="invoices/doc-e2e-100.pdf",
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
        checksum="e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
    )
    mock_storage.get_document_bytes.return_value = b"%PDF-1.4 sample content"

    doc_service = DocumentIntelligenceService(storage_service=mock_storage, agent=mock_agent)
    doc_adapter = DocIntelAdapter(doc_service=doc_service)

    orchestrator = WorkflowOrchestrator()
    orchestrator.adapters[WorkflowState.INGESTING] = doc_adapter
    orchestrator.adapters[WorkflowState.EXTRACTING] = doc_adapter

    runner = PipelineRunner(orchestrator=orchestrator)
    w_id = runner.start_pipeline(document_id="doc-e2e-100")
    assert w_id.startswith("wf-")

    final_workflow = runner.run_to_completion(w_id, max_steps=15)
    assert final_workflow.current_state == WorkflowState.COMPLETED

    status_dict = runner.get_pipeline_status(w_id)
    assert status_dict["current_state"] == "COMPLETED"
    assert status_dict["workflow_revision"] == 10


def test_orchestration_api_endpoints():
    # Start pipeline via API (asynchronous start returns 201 UPLOADED)
    resp_start = client.post(
        "/api/v1/pipeline/start",
        json={"document_id": "doc-api-200", "workflow_id": "wf-api-200"},
    )
    assert resp_start.status_code == 201
    data_start = resp_start.json()
    assert data_start["workflow_id"] == "wf-api-200"
    assert data_start["current_state"] == "UPLOADED"
    assert data_start["workflow_revision"] == 1

    # Inspect pipeline status via API
    resp_status = client.get("/api/v1/pipeline/wf-api-200/status")
    assert resp_status.status_code == 200
    data_status = resp_status.json()
    assert data_status["workflow_id"] == "wf-api-200"
    assert data_status["current_state"] == "UPLOADED"
    assert data_status["workflow_revision"] == 1


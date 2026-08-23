import pytest
from datetime import datetime, timezone

from app.audit.models import AuditEvent, AuditEventType, AuditProvenance
from app.core.state import AnalysisWorkflow, WorkflowState
from app.events.schemas import EventType, WorkflowEvent
from app.infrastructure.azure.blob_storage import AzureBlobStorageProvider
from app.infrastructure.azure.cosmos_repositories import (
    CosmosAuditEventRepository,
    CosmosDocumentRepository,
    CosmosWorkflowRepository,
)
from app.infrastructure.azure.cosmos_state_manager import CosmosStateManager
from app.models.document import DocumentMetadata, DocumentStatus


@pytest.mark.azure
def test_cosmos_workflow_lifecycle():
    """Verify full CRUD workflow lifecycle on CosmosWorkflowRepository."""
    repo = CosmosWorkflowRepository()
    wf = AnalysisWorkflow(
        workflow_id="wf-cosmos-crud-1",
        document_id="doc-crud-1",
        current_state=WorkflowState.UPLOADED,
    )

    created = repo.create(wf)
    assert created.workflow_id == "wf-cosmos-crud-1"
    assert repo.exists("wf-cosmos-crud-1") is True

    fetched = repo.get("wf-cosmos-crud-1")
    assert fetched.current_state == WorkflowState.UPLOADED

    fetched.current_state = WorkflowState.INGESTING
    updated = repo.update(fetched)
    assert updated.current_state == WorkflowState.INGESTING

    assert repo.delete("wf-cosmos-crud-1") is True
    assert repo.exists("wf-cosmos-crud-1") is False


@pytest.mark.azure
def test_cosmos_document_lifecycle():
    """Verify document metadata lifecycle on CosmosDocumentRepository."""
    repo = CosmosDocumentRepository()
    metadata = DocumentMetadata(
        document_id="doc-cosmos-1",
        filename="invoice_2026.pdf",
        content_type="application/pdf",
        size_bytes=12000,
        storage_bucket="papertrail-documents-dev",
        storage_object="documents/doc-cosmos-1/original/invoice_2026.pdf",
        document_status=DocumentStatus.STORED,
        checksum="a" * 64,
    )

    created = repo.create(metadata)
    assert created.document_id == "doc-cosmos-1"
    assert repo.exists("doc-cosmos-1") is True

    fetched = repo.get("doc-cosmos-1")
    assert fetched.filename == "invoice_2026.pdf"

    assert repo.delete("doc-cosmos-1") is True
    assert repo.exists("doc-cosmos-1") is False


@pytest.mark.azure
def test_cosmos_audit_event_chain():
    """Verify append-only audit event chain on CosmosAuditEventRepository."""
    repo = CosmosAuditEventRepository()
    provenance = AuditProvenance(app_version="0.1.0", gemini_model="gemini-3.5-flash")

    event1 = AuditEvent(
        event_id="evt-aud-1",
        document_id="doc-chain-1",
        workflow_id="wf-chain-1",
        event_type=AuditEventType.DOCUMENT_REGISTERED,
        source_phase="Phase 1",
        payload_hash="hash-1",
        previous_event_hash="GENESIS",
        event_hash="hash-event-1",
        provenance=provenance,
    )

    event2 = AuditEvent(
        event_id="evt-aud-2",
        document_id="doc-chain-1",
        workflow_id="wf-chain-1",
        event_type=AuditEventType.FORENSIC_ANALYSIS_COMPLETED,
        source_phase="Phase 8",
        payload_hash="hash-2",
        previous_event_hash="hash-event-1",
        event_hash="hash-event-2",
        provenance=provenance,
    )

    repo.append(event1)
    repo.append(event2)

    chain = repo.get_document_chain("doc-chain-1", "wf-chain-1")
    assert len(chain) == 2
    assert chain[0].event_id == "evt-aud-1"
    assert chain[1].event_id == "evt-aud-2"

    latest = repo.get_latest_event("doc-chain-1", "wf-chain-1")
    assert latest.event_id == "evt-aud-2"

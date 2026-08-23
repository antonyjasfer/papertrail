from datetime import datetime, timezone
import pytest

from app.audit.chain import AuditChainBuilder
from app.audit.constants import GENESIS_PREVIOUS_HASH
from app.audit.models import AuditEventType
from app.models.document import DocumentMetadata, DocumentStatus


@pytest.fixture
def sample_metadata():
    return DocumentMetadata(
        document_id="doc-chain-123",
        filename="sample.pdf",
        content_type="application/pdf",
        size_bytes=512,
        storage_bucket="bucket",
        storage_object="documents/doc-chain-123/original/sample.pdf",
        document_status=DocumentStatus.STORED,
        checksum="e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
    )


def test_create_genesis_event(sample_metadata):
    ts = datetime(2026, 8, 18, 12, 0, 0, 0, tzinfo=timezone.utc)
    genesis = AuditChainBuilder.create_genesis_event(
        document_metadata=sample_metadata,
        workflow_id="wf-chain-123",
        event_timestamp=ts,
    )

    assert genesis.event_id == "evt-gen-doc-chain-123"
    assert genesis.document_id == "doc-chain-123"
    assert genesis.workflow_id == "wf-chain-123"
    assert genesis.event_type == AuditEventType.DOCUMENT_REGISTERED
    assert genesis.previous_event_hash == GENESIS_PREVIOUS_HASH
    assert genesis.provenance.version_status == "DECLARED"
    assert len(genesis.event_hash) == 64


def test_create_subsequent_event(sample_metadata):
    genesis = AuditChainBuilder.create_genesis_event(sample_metadata, "wf-chain-123")
    
    evt2 = AuditChainBuilder.create_event(
        document_id="doc-chain-123",
        workflow_id="wf-chain-123",
        event_type=AuditEventType.EXTRACTION_COMPLETED,
        source_phase="Phase 7",
        payload={"extracted": True},
        previous_event_hash=genesis.event_hash,
    )

    assert evt2.previous_event_hash == genesis.event_hash
    assert evt2.event_type == AuditEventType.EXTRACTION_COMPLETED
    assert len(evt2.event_hash) == 64


def test_input_models_remain_unmutated(sample_metadata):
    """Verify that AuditChainBuilder methods do not mutate input metadata or models."""
    original_dict = sample_metadata.model_dump()
    _ = AuditChainBuilder.create_genesis_event(sample_metadata, "wf-chain-123")
    assert sample_metadata.model_dump() == original_dict

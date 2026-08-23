from datetime import datetime, timezone
from unittest.mock import MagicMock, patch
import pytest

from app.audit.chain import AuditChainBuilder
from app.audit.errors import AuditChainSealedError, AuditDuplicateError, AuditIntegrityError, AuditSecurityError
from app.audit.models import AuditEvent, AuditEventType
from app.database.repositories.audit_repository import AuditEventRepository
from app.models.document import DocumentMetadata, DocumentStatus


@pytest.fixture
def mock_firestore():
    client = MagicMock()
    return client


@pytest.fixture
def sample_metadata():
    return DocumentMetadata(
        document_id="doc-test-123",
        filename="test_invoice.pdf",
        content_type="application/pdf",
        size_bytes=1024,
        storage_bucket="test-bucket",
        storage_object="documents/doc-test-123/original/test_invoice.pdf",
        document_status=DocumentStatus.STORED,
        checksum="e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
    )


def test_repository_prohibits_update(mock_firestore):
    repo = AuditEventRepository(client=mock_firestore)
    with pytest.raises(AuditSecurityError) as exc_info:
        repo.update(None)
    assert "Operation 'update' is strictly prohibited" in str(exc_info.value)


def test_repository_prohibits_delete(mock_firestore):
    repo = AuditEventRepository(client=mock_firestore)
    with pytest.raises(AuditSecurityError) as exc_info:
        repo.delete("evt-123")
    assert "Operation 'delete' is strictly prohibited" in str(exc_info.value)


def test_repository_append_new_event(mock_firestore, sample_metadata):
    repo = AuditEventRepository(client=mock_firestore)
    
    # Mock find_by_event_key returning None (slot open)
    repo.find_by_event_key = MagicMock(return_value=None)
    
    doc_ref = MagicMock()
    doc_ref.get().exists = False
    mock_firestore.collection().document.return_value = doc_ref

    genesis = AuditChainBuilder.create_genesis_event(sample_metadata, "wf-123")
    result = repo.append(genesis)

    assert result.event_id == genesis.event_id
    doc_ref.set.assert_called_once()


def test_repository_append_idempotent_success(mock_firestore, sample_metadata):
    repo = AuditEventRepository(client=mock_firestore)
    genesis = AuditChainBuilder.create_genesis_event(sample_metadata, "wf-123")

    # Mock find_by_event_key returning identical event
    repo.find_by_event_key = MagicMock(return_value=genesis)

    doc_ref = MagicMock()
    doc_ref.get().exists = False
    mock_firestore.collection().document.return_value = doc_ref

    result = repo.append(genesis)
    assert result.event_id == genesis.event_id
    # set should not be called on existing slot match
    doc_ref.set.assert_not_called()


def test_repository_append_slot_conflict(mock_firestore, sample_metadata):
    repo = AuditEventRepository(client=mock_firestore)
    genesis = AuditChainBuilder.create_genesis_event(sample_metadata, "wf-123")

    # Create conflicting event with different payload hash
    conflicting = genesis.model_copy(deep=True)
    conflicting.payload_hash = "ffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffff"

    repo.find_by_event_key = MagicMock(return_value=conflicting)

    doc_ref = MagicMock()
    doc_ref.get().exists = False
    mock_firestore.collection().document.return_value = doc_ref

    with pytest.raises(AuditIntegrityError) as exc_info:
        repo.append(genesis)
    assert "conflicting payload hash" in str(exc_info.value)


def test_repository_append_sealed_chain_rejection(mock_firestore, sample_metadata):
    repo = AuditEventRepository(client=mock_firestore)
    genesis = AuditChainBuilder.create_genesis_event(sample_metadata, "wf-123")
    sealed_event = AuditChainBuilder.create_event(
        document_id="doc-test-123",
        workflow_id="wf-123",
        event_type=AuditEventType.AUDIT_SEALED,
        source_phase="Phase 11",
        payload={"sealed": True},
        previous_event_hash=genesis.event_hash,
    )

    def mock_find(doc_id, wf_id, evt_type):
        if evt_type == AuditEventType.AUDIT_SEALED:
            return sealed_event
        return None

    repo.find_by_event_key = MagicMock(side_effect=mock_find)

    doc_ref = MagicMock()
    doc_ref.get().exists = False
    mock_firestore.collection().document.return_value = doc_ref

    # Attempt to append EXTRACTION_COMPLETED after chain is sealed
    next_event = AuditChainBuilder.create_event(
        document_id="doc-test-123",
        workflow_id="wf-123",
        event_type=AuditEventType.EXTRACTION_COMPLETED,
        source_phase="Phase 7",
        payload={"extracted": True},
        previous_event_hash=genesis.event_hash,
    )

    with pytest.raises(AuditChainSealedError) as exc_info:
        repo.append(next_event)
    assert "is sealed" in str(exc_info.value)

from unittest.mock import MagicMock
import pytest

from app.audit.chain import AuditChainBuilder
from app.audit.errors import AuditDuplicateError, AuditIntegrityError
from app.audit.models import AuditEventType
from app.database.repositories.audit_repository import AuditEventRepository
from app.models.document import DocumentMetadata, DocumentStatus


@pytest.fixture
def sample_metadata():
    return DocumentMetadata(
        document_id="doc-idemp-123",
        filename="invoice.pdf",
        content_type="application/pdf",
        size_bytes=1024,
        storage_bucket="bucket",
        storage_object="documents/doc-idemp-123/original/invoice.pdf",
        document_status=DocumentStatus.STORED,
        checksum="e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
    )


def test_idempotent_retry_same_payload(sample_metadata):
    repo = AuditEventRepository(client=MagicMock())
    genesis = AuditChainBuilder.create_genesis_event(sample_metadata, "wf-idemp-123")

    # Mock slot existing with same event
    repo.find_by_event_key = MagicMock(return_value=genesis)
    
    doc_ref = MagicMock()
    doc_ref.get().exists = False
    repo.client.collection().document.return_value = doc_ref

    res = repo.append(genesis)
    assert res.event_id == genesis.event_id


def test_idempotent_conflict_different_payload(sample_metadata):
    repo = AuditEventRepository(client=MagicMock())
    genesis = AuditChainBuilder.create_genesis_event(sample_metadata, "wf-idemp-123")

    # Mock slot existing with different payload
    conflicting = genesis.model_copy(deep=True)
    conflicting.payload_hash = "ffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffff"

    repo.find_by_event_key = MagicMock(return_value=conflicting)

    doc_ref = MagicMock()
    doc_ref.get().exists = False
    repo.client.collection().document.return_value = doc_ref

    with pytest.raises(AuditIntegrityError):
        repo.append(genesis)

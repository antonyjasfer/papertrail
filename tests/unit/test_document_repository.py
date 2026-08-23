from datetime import datetime, timezone
import pytest
from unittest.mock import MagicMock

from app.models.document import DocumentMetadata, DocumentStatus
from app.database.repositories.document_repository import (
    DocumentRepository,
    DocumentNotFoundError,
    DocumentAlreadyExistsError,
    DocumentPersistenceError,
    serialize_document_metadata,
    deserialize_document_metadata,
)
from tests.unit.test_workflow_repository import MockFirestoreClient


@pytest.fixture
def mock_doc_repo():
    mock_client = MockFirestoreClient()
    return DocumentRepository(client=mock_client)


def test_create_document_metadata(mock_doc_repo):
    """Test creating document metadata persists to mock store."""
    meta = DocumentMetadata(
        document_id="doc-001",
        filename="invoice.pdf",
        content_type="application/pdf",
        size_bytes=1024,
        storage_bucket="test-bucket",
        storage_object="documents/doc-001/original/invoice.pdf",
        checksum="a1b2c3d4",
    )
    created = mock_doc_repo.create(meta)
    assert created.document_id == "doc-001"
    assert mock_doc_repo.exists("doc-001") is True


def test_read_document_metadata(mock_doc_repo):
    """Test reading document metadata returns matching deserialized object."""
    meta = DocumentMetadata(
        document_id="doc-002",
        filename="receipt.png",
        content_type="image/png",
        size_bytes=2048,
        storage_bucket="test-bucket",
        storage_object="documents/doc-002/original/receipt.png",
        checksum="e5f6g7h8",
    )
    mock_doc_repo.create(meta)

    fetched = mock_doc_repo.get("doc-002")
    assert fetched.document_id == "doc-002"
    assert fetched.filename == "receipt.png"
    assert fetched.document_status == DocumentStatus.UPLOADING


def test_document_metadata_not_found(mock_doc_repo):
    """Test getting non-existent metadata raises DocumentNotFoundError."""
    with pytest.raises(DocumentNotFoundError):
        mock_doc_repo.get("non-existent-doc")


def test_duplicate_document_metadata_fails(mock_doc_repo):
    """Test duplicate document metadata creation raises DocumentAlreadyExistsError."""
    meta = DocumentMetadata(
        document_id="doc-004",
        filename="contract.pdf",
        content_type="application/pdf",
        size_bytes=4096,
        storage_bucket="test-bucket",
        storage_object="documents/doc-004/original/contract.pdf",
        checksum="123456",
    )
    mock_doc_repo.create(meta)
    with pytest.raises(DocumentAlreadyExistsError):
        mock_doc_repo.create(meta)


def test_update_document_metadata(mock_doc_repo):
    """Test updating existing document metadata succeeds."""
    meta = DocumentMetadata(
        document_id="doc-005",
        filename="test.pdf",
        content_type="application/pdf",
        size_bytes=512,
        storage_bucket="test-bucket",
        storage_object="documents/doc-005/original/test.pdf",
        checksum="9999",
    )
    mock_doc_repo.create(meta)

    meta.document_status = DocumentStatus.STORED
    mock_doc_repo.update(meta)

    fetched = mock_doc_repo.get("doc-005")
    assert fetched.document_status == DocumentStatus.STORED


def test_document_status_serialization_and_deserialization():
    """Test DocumentStatus Enum serialization and deserialization."""
    meta = DocumentMetadata(
        document_id="doc-006",
        filename="doc.pdf",
        content_type="application/pdf",
        size_bytes=100,
        storage_bucket="bkt",
        storage_object="obj",
        document_status=DocumentStatus.STORED,
        checksum="hash",
    )
    data = serialize_document_metadata(meta)
    assert data["document_status"] == "STORED"
    assert isinstance(data["document_status"], str)

    restored = deserialize_document_metadata(data)
    assert restored.document_status == DocumentStatus.STORED
    assert isinstance(restored.document_status, DocumentStatus)

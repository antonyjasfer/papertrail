import pytest
from unittest.mock import MagicMock
from typing import Any, Dict, Optional, Set

from app.models.document import DocumentStatus, DocumentMetadata
from app.services.document_storage import (
    DocumentStorageService,
    DocumentValidationError,
    DocumentStorageError,
    sanitize_filename,
    calculate_checksum,
    generate_object_path,
)
from tests.unit.test_workflow_repository import MockFirestoreClient
from app.database.repositories.document_repository import DocumentRepository


class MockStorageAdapter:
    """Mock storage adapter conforming to IStorageProvider for unit testing."""

    def __init__(self):
        self.blobs: Dict[str, bytes] = {}
        self.should_fail_upload = False
        self.should_fail_download = False

    def upload_bytes(
        self, bucket_or_container: str, object_path: str, data: bytes, content_type: str
    ) -> None:
        if self.should_fail_upload:
            raise RuntimeError("Storage upload network timeout")
        self.blobs[f"{bucket_or_container}/{object_path}"] = data

    def download_bytes(self, bucket_or_container: str, object_path: str) -> bytes:
        if self.should_fail_download:
            raise RuntimeError("Storage download unreadable")
        key = f"{bucket_or_container}/{object_path}"
        if key not in self.blobs:
            raise FileNotFoundError(f"Blob not found: {key}")
        return self.blobs[key]

    def delete_object(self, bucket_or_container: str, object_path: str) -> bool:
        key = f"{bucket_or_container}/{object_path}"
        return self.blobs.pop(key, None) is not None

    def object_exists(self, bucket_or_container: str, object_path: str) -> bool:
        key = f"{bucket_or_container}/{object_path}"
        return key in self.blobs


@pytest.fixture
def mock_storage_provider():
    return MockStorageAdapter()


@pytest.fixture
def mock_storage_service(mock_storage_provider):
    mock_firestore = MockFirestoreClient()
    repo = DocumentRepository(client=mock_firestore)
    return DocumentStorageService(
        repository=repo,
        storage_provider=mock_storage_provider,
        bucket_name="papertrail-ai-documents-dev",
    )


def test_filename_sanitization_and_path_traversal_protection():
    """Tests 2 & 3: Verify filename sanitization and path traversal prevention."""
    assert sanitize_filename("simple_invoice.pdf") == "simple_invoice.pdf"
    # Path traversal attempt
    assert sanitize_filename("../../etc/passwd") == "passwd"
    assert sanitize_filename("..\\..\\Windows\\System32\\cmd.exe") == "cmd.exe"
    # Special characters
    assert sanitize_filename("my invoice (final!).pdf") == "my_invoice__final__.pdf"
    # Empty filename
    assert sanitize_filename("") == "unnamed_document.bin"


def test_content_type_validation(mock_storage_service):
    """Test 4: Verify supported content types pass and unsupported types fail."""
    sample_bytes = b"Hello Document"
    # Supported types
    assert mock_storage_service.validate_document_input("doc.pdf", "application/pdf", sample_bytes) == "doc.pdf"
    assert mock_storage_service.validate_document_input("img.png", "image/png", sample_bytes) == "img.png"
    assert mock_storage_service.validate_document_input("img.jpg", "image/jpeg", sample_bytes) == "img.jpg"
    assert mock_storage_service.validate_document_input("txt.txt", "text/plain", sample_bytes) == "txt.txt"

    # Unsupported type
    with pytest.raises(DocumentValidationError) as exc_info:
        mock_storage_service.validate_document_input("video.mp4", "video/mp4", sample_bytes)
    assert "Unsupported content type" in str(exc_info.value)


def test_file_size_validation(mock_storage_service):
    """Test 5: Verify exceeding max file size limit raises DocumentValidationError."""
    mock_storage_service.max_size_bytes = 100  # Set low limit for testing
    large_bytes = b"x" * 150
    with pytest.raises(DocumentValidationError) as exc_info:
        mock_storage_service.validate_document_input("large.pdf", "application/pdf", large_bytes)
    assert "exceeds maximum limit" in str(exc_info.value)


def test_sha256_checksum_calculation():
    """Test 6: Verify deterministic SHA-256 calculation."""
    content = b"PaperTrail AI Test Payload"
    checksum1 = calculate_checksum(content)
    checksum2 = calculate_checksum(content)
    assert len(checksum1) == 64
    assert checksum1 == checksum2
    assert checksum1 != calculate_checksum(b"Different Payload")


def test_successful_storage_flow(mock_storage_service):
    """Tests 1, 9, 14: Verify complete document upload and storage flow."""
    payload = b"%PDF-1.4 Mock Document Payload"
    meta = mock_storage_service.store_document(
        filename="invoice_2026.pdf",
        content_type="application/pdf",
        file_bytes=payload,
    )
    assert meta.document_id.startswith("doc-")
    assert meta.document_status == DocumentStatus.STORED
    assert meta.checksum == calculate_checksum(payload)
    assert meta.storage_object.startswith(f"documents/{meta.document_id}/original/")

    # Read back metadata
    fetched_meta = mock_storage_service.get_document_metadata(meta.document_id)
    assert fetched_meta.checksum == meta.checksum


def test_storage_upload_failure(mock_storage_service, mock_storage_provider):
    """Test 15: Verify Storage upload failure updates status and raises DocumentStorageError."""
    mock_storage_provider.should_fail_upload = True  # Trigger simulated upload error

    with pytest.raises(DocumentStorageError) as exc_info:
        mock_storage_service.store_document("test.pdf", "application/pdf", b"test bytes")
    assert "upload_bytes" in str(exc_info.value)


def test_firestore_metadata_failure_and_storage_cleanup(mock_storage_service, mock_storage_provider):
    """Tests 16 & 17: Verify metadata failure cleans up uploaded storage object."""
    mock_storage_service.repository.create = MagicMock(side_effect=Exception("Firestore write error"))

    with pytest.raises(DocumentStorageError) as exc_info:
        mock_storage_service.store_document("fail_meta.pdf", "application/pdf", b"sample content")

    assert "persist_metadata" in str(exc_info.value)
    # Ensure orphaned storage object was cleaned up
    assert len(mock_storage_provider.blobs) == 0


def test_document_retrieval_and_checksum_verification(mock_storage_service):
    """Test 18: Verify document bytes retrieval and download checksum verification."""
    content = b"Authentic document payload bytes"
    meta = mock_storage_service.store_document("sample.txt", "text/plain", content)

    retrieved_bytes = mock_storage_service.get_document_bytes(meta.document_id)
    assert retrieved_bytes == content


def test_controlled_deletion(mock_storage_service):
    """Test 19: Verify controlled deletion deletes storage object and updates metadata to DELETED."""
    content = b"To be deleted"
    meta = mock_storage_service.store_document("delete_me.pdf", "application/pdf", content)

    assert mock_storage_service.delete_document(meta.document_id) is True

    fetched_meta = mock_storage_service.get_document_metadata(meta.document_id)
    assert fetched_meta.document_status == DocumentStatus.DELETED

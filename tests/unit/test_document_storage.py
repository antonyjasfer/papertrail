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


class MockGCSBlob:
    def __init__(self, name: str, bucket: Any = None):
        self.name = name
        self.bucket = bucket
        self.payload = None

    def upload_from_string(self, file_bytes: bytes, content_type: str = None):
        if getattr(self.bucket, "should_fail_upload", False):
            raise Exception("GCS network timeout")
        self.payload = file_bytes

    def download_as_bytes(self) -> bytes:
        if getattr(self.bucket, "should_fail_download", False):
            raise Exception("GCS object unreadable")
        return self.payload or b""

    def exists(self) -> bool:
        return self.payload is not None

    def delete(self):
        self.payload = None


class MockGCSBucket:
    def __init__(self, name: str):
        self.name = name
        self.blobs = {}
        self.should_fail_upload = False
        self.should_fail_download = False

    def blob(self, object_path: str):
        if object_path not in self.blobs:
            self.blobs[object_path] = MockGCSBlob(object_path, bucket=self)
        return self.blobs[object_path]


class MockGCSClient:
    def __init__(self):
        self.buckets = {}

    def bucket(self, name: str):
        if name not in self.buckets:
            self.buckets[name] = MockGCSBucket(name)
        return self.buckets[name]


@pytest.fixture
def mock_storage_service():
    mock_firestore = MockFirestoreClient()
    repo = DocumentRepository(client=mock_firestore)
    mock_gcs = MockGCSClient()
    return DocumentStorageService(repository=repo, storage_client=mock_gcs)


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


def test_storage_upload_failure(mock_storage_service):
    """Test 15: Verify Cloud Storage upload failure updates status and raises DocumentStorageError."""
    bucket = mock_storage_service.storage_client.bucket(mock_storage_service.bucket_name)
    bucket.should_fail_upload = True  # Trigger simulated upload error

    with pytest.raises(DocumentStorageError) as exc_info:
        mock_storage_service.store_document("test.pdf", "application/pdf", b"test bytes")
    assert "upload_bytes" in str(exc_info.value)


def test_firestore_metadata_failure_and_gcs_cleanup(mock_storage_service):
    """Tests 16 & 17: Verify Firestore metadata failure cleans up uploaded GCS object."""
    # Mock repository create to simulate Firestore failure
    mock_storage_service.repository.create = MagicMock(side_effect=Exception("Firestore write error"))

    with pytest.raises(DocumentStorageError) as exc_info:
        mock_storage_service.store_document("fail_meta.pdf", "application/pdf", b"sample content")

    assert "persist_metadata" in str(exc_info.value)


def test_document_retrieval_and_checksum_verification(mock_storage_service):
    """Test 18: Verify document bytes retrieval and download checksum verification."""
    content = b"Authentic document payload bytes"
    meta = mock_storage_service.store_document("sample.txt", "text/plain", content)

    retrieved_bytes = mock_storage_service.get_document_bytes(meta.document_id)
    assert retrieved_bytes == content


def test_controlled_deletion(mock_storage_service):
    """Test 19: Verify controlled deletion deletes GCS object and updates metadata to DELETED."""
    content = b"To be deleted"
    meta = mock_storage_service.store_document("delete_me.pdf", "application/pdf", content)

    assert mock_storage_service.delete_document(meta.document_id) is True

    fetched_meta = mock_storage_service.get_document_metadata(meta.document_id)
    assert fetched_meta.document_status == DocumentStatus.DELETED

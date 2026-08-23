import io
from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from app.api.dependencies import get_document_storage_service
from app.database.repositories.document_repository import (
    DocumentAlreadyExistsError,
    DocumentNotFoundError,
)
from app.core.config import settings
from app.main import app
from app.models.document import DocumentMetadata, DocumentStatus
from app.services.document_storage import DocumentStorageError, DocumentValidationError

client = TestClient(app)


@pytest.fixture
def mock_storage_service():
    mock_service = MagicMock()
    app.dependency_overrides[get_document_storage_service] = lambda: mock_service
    yield mock_service
    app.dependency_overrides.clear()


@pytest.fixture
def sample_metadata():
    return DocumentMetadata(
        document_id="doc-test-123456",
        filename="invoice.pdf",
        content_type="application/pdf",
        size_bytes=1024,
        storage_bucket="papertrail-ai-documents-dev",
        storage_object="documents/doc-test-123456/original/invoice.pdf",
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
        document_status=DocumentStatus.STORED,
        checksum="e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
    )


# Test 1: Successful Document Upload
def test_upload_document_success(mock_storage_service, sample_metadata):
    mock_storage_service.store_document.return_value = sample_metadata

    file_payload = ("invoice.pdf", b"%PDF-1.4 test document content", "application/pdf")
    response = client.post("/documents", files={"file": file_payload})

    assert response.status_code == 201
    data = response.json()
    assert data["document_id"] == "doc-test-123456"
    assert data["filename"] == "invoice.pdf"
    assert data["content_type"] == "application/pdf"
    assert data["size_bytes"] == 1024
    assert data["status"] == "STORED"
    assert data["checksum"] == sample_metadata.checksum
    mock_storage_service.store_document.assert_called_once()


# Test 2: Missing File Upload Payload
def test_upload_document_missing_file():
    response = client.post("/documents")
    assert response.status_code in (400, 422)


# Test 3: Unsupported Content Type
def test_upload_document_unsupported_content_type(mock_storage_service):
    mock_storage_service.store_document.side_effect = DocumentValidationError(
        "Unsupported content type 'video/mp4'."
    )

    file_payload = ("video.mp4", b"fake video bytes", "video/mp4")
    response = client.post("/documents", files={"file": file_payload})

    assert response.status_code == 400
    data = response.json()
    assert "Unsupported content type" in data["detail"]


# Test 4: Oversized File
def test_upload_document_oversized_file(mock_storage_service):
    mock_storage_service.store_document.side_effect = DocumentValidationError(
        "File size exceeds maximum limit."
    )

    file_payload = ("huge.pdf", b"large content", "application/pdf")
    response = client.post("/documents", files={"file": file_payload})

    assert response.status_code == 400
    data = response.json()
    assert "exceeds maximum limit" in data["detail"]


# Test 5: Document Not Found
def test_get_document_not_found(mock_storage_service):
    mock_storage_service.get_document_metadata.side_effect = DocumentNotFoundError("doc-nonexistent")

    response = client.get("/documents/doc-nonexistent")

    assert response.status_code == 404
    data = response.json()
    assert "was not found" in data["detail"]


# Test 6: Metadata Retrieval Success
def test_get_document_metadata_success(mock_storage_service, sample_metadata):
    mock_storage_service.get_document_metadata.return_value = sample_metadata

    response = client.get(f"/documents/{sample_metadata.document_id}")

    assert response.status_code == 200
    data = response.json()
    assert data["document_id"] == sample_metadata.document_id
    assert data["filename"] == sample_metadata.filename
    assert data["status"] == "STORED"


# Test 7: Secure Download Success
def test_download_document_success(mock_storage_service, sample_metadata):
    mock_storage_service.get_document_metadata.return_value = sample_metadata
    mock_storage_service.get_document_bytes.return_value = b"%PDF-1.4 sample file content"

    response = client.get(f"/documents/{sample_metadata.document_id}/download")

    assert response.status_code == 200
    assert response.content == b"%PDF-1.4 sample file content"
    assert response.headers["content-type"] == "application/pdf"
    assert 'filename="invoice.pdf"' in response.headers["content-disposition"]


# Test 8: Document Deletion Success
def test_delete_document_success(mock_storage_service, sample_metadata):
    mock_storage_service.delete_document.return_value = True

    response = client.delete(f"/documents/{sample_metadata.document_id}")

    assert response.status_code == 200
    data = response.json()
    assert data["document_id"] == sample_metadata.document_id
    assert data["status"] == "DELETED"
    assert data["artifact_deleted"] is True
    assert data["metadata_retained"] is True
    mock_storage_service.delete_document.assert_called_once_with(sample_metadata.document_id)


# Test 9: Storage Error Mapping (Internal Server Error 500)
def test_storage_error_mapping(mock_storage_service):
    mock_storage_service.get_document_metadata.side_effect = DocumentStorageError(
        "read", "doc-123", "GCS connection failed"
    )

    response = client.get("/documents/doc-123")

    assert response.status_code == 500
    data = response.json()
    assert data["detail"] == "Document storage operation failed."


# Test 10: Validation Error Mapping (Bad Request 400)
def test_validation_error_mapping(mock_storage_service):
    mock_storage_service.store_document.side_effect = DocumentValidationError("Payload bytes are empty.")

    file_payload = ("empty.pdf", b"", "application/pdf")
    response = client.post("/documents", files={"file": file_payload})

    assert response.status_code == 400
    data = response.json()
    assert "Payload bytes are empty" in data["detail"]


# Test 11: Already-Exists Conflict (Conflict 409)
def test_already_exists_conflict(mock_storage_service):
    mock_storage_service.store_document.side_effect = DocumentAlreadyExistsError("doc-duplicate")

    file_payload = ("invoice.pdf", b"test bytes", "application/pdf")
    response = client.post("/documents", files={"file": file_payload})

    assert response.status_code == 409
    data = response.json()
    assert "already exists" in data["detail"]


# Test 12: Health Endpoint Regression
def test_health_endpoint_regression():
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert data["service"] == "PaperTrail AI"
    assert data["phase"] == settings.phase

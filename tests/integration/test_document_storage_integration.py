import os
import uuid
import pytest
from app.core.gcp import gcp_foundation
from app.models.document import DocumentStatus
from app.services.document_storage import (
    DocumentStorageService,
    calculate_checksum,
)

# Skip integration test unless explicitly enabled via environment variable GCP_INTEGRATION=1
pytestmark = pytest.mark.skipif(
    os.getenv("GCP_INTEGRATION") != "1",
    reason="Live GCP integration tests disabled. Set GCP_INTEGRATION=1 to run.",
)


@pytest.mark.integration
def test_cloud_storage_and_firestore_document_integration():
    """Live Cloud Storage and Firestore integration test.

    Uploads a temporary document artifact to Cloud Storage, persists metadata to Firestore,
    verifies SHA-256 fingerprint matching, reads back document bytes, and cleans up completely.
    """
    storage_service = DocumentStorageService()
    test_id = f"doc-test-integration-{uuid.uuid4().hex[:8]}"
    test_filename = f"integration_test_{test_id}.pdf"
    test_content = b"%PDF-1.4 Cloud Storage Integration Test Byte Payload"
    expected_checksum = calculate_checksum(test_content)

    try:
        # Step 1: Upload document and persist metadata
        meta = storage_service.store_document(
            filename=test_filename,
            content_type="application/pdf",
            file_bytes=test_content,
            document_id=test_id,
        )

        assert meta.document_id == test_id
        assert meta.document_status == DocumentStatus.STORED
        assert meta.checksum == expected_checksum

        # Step 2: Read back document metadata from Firestore
        fetched_meta = storage_service.get_document_metadata(test_id)
        assert fetched_meta.document_id == test_id
        assert fetched_meta.checksum == expected_checksum
        assert fetched_meta.document_status == DocumentStatus.STORED

        # Step 3: Retrieve document bytes from Cloud Storage and verify SHA-256 fingerprint
        retrieved_bytes = storage_service.get_document_bytes(test_id)
        assert retrieved_bytes == test_content
        assert calculate_checksum(retrieved_bytes) == expected_checksum

    finally:
        # Cleanup: Delete document storage object and metadata record
        try:
            storage_service.delete_document(test_id)
            storage_service.repository.delete(test_id)
        except Exception as cleanup_err:
            print(f"Warning: Cleanup failed during integration test: {cleanup_err}")

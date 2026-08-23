import hashlib
import os
import uuid
import pytest
from fastapi.testclient import TestClient

from app.database.repositories.document_repository import DocumentRepository
from app.main import app
from app.models.document import DocumentStatus

pytestmark = pytest.mark.skipif(
    not os.getenv("GCP_INTEGRATION"),
    reason="GCP integration tests require live GCP environment setup (set GCP_INTEGRATION=1).",
)

client = TestClient(app)


def test_documents_api_live_gcp_lifecycle():
    """End-to-end integration test of Document API endpoints against live GCP services (Storage & Firestore)."""
    test_id = uuid.uuid4().hex[:8]
    filename = f"integration_test_{test_id}.pdf"
    file_bytes = f"%PDF-1.4 PaperTrail AI API Integration Test Payload {test_id}".encode("utf-8")
    expected_checksum = hashlib.sha256(file_bytes).hexdigest()
    content_type = "application/pdf"

    document_id = None
    repo = DocumentRepository()

    try:
        # Step 1: POST /documents
        file_payload = (filename, file_bytes, content_type)
        response = client.post("/documents", files={"file": file_payload})
        assert response.status_code == 201, f"POST /documents failed: {response.text}"

        upload_data = response.json()
        document_id = upload_data["document_id"]
        assert upload_data["filename"] == filename
        assert upload_data["content_type"] == content_type
        assert upload_data["size_bytes"] == len(file_bytes)
        assert upload_data["status"] == "STORED"
        assert upload_data["checksum"] == expected_checksum

        # Step 2: GET /documents/{document_id}
        response_get = client.get(f"/documents/{document_id}")
        assert response_get.status_code == 200, f"GET /documents/{{id}} failed: {response_get.text}"
        get_data = response_get.json()
        assert get_data["document_id"] == document_id
        assert get_data["status"] == "STORED"
        assert get_data["checksum"] == expected_checksum

        # Step 3: GET /documents/{document_id}/download
        response_dl = client.get(f"/documents/{document_id}/download")
        assert response_dl.status_code == 200, f"GET /documents/{{id}}/download failed: {response_dl.text}"
        assert response_dl.content == file_bytes
        downloaded_checksum = hashlib.sha256(response_dl.content).hexdigest()
        assert downloaded_checksum == expected_checksum

        # Step 4: DELETE /documents/{document_id}
        response_del = client.delete(f"/documents/{document_id}")
        assert response_del.status_code == 200, f"DELETE /documents/{{id}} failed: {response_del.text}"
        del_data = response_del.json()
        assert del_data["document_id"] == document_id
        assert del_data["status"] == "DELETED"
        assert del_data["artifact_deleted"] is True
        assert del_data["metadata_retained"] is True

        # Verify Firestore metadata document status updated to DELETED
        meta_after = repo.get(document_id)
        assert meta_after.document_status == DocumentStatus.DELETED

    finally:
        # Cleanup metadata from Firestore after test run if document was created
        if document_id:
            try:
                repo.delete(document_id)
            except Exception:
                pass

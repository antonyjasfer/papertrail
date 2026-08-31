import json
import os
import pytest
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

from app.core.config import settings
from app.core.contracts.repositories import (
    IAuditEventRepository,
    IDocumentRepository,
    IWorkflowRepository,
)
from app.core.contracts.secrets import ISecretProvider
from app.core.contracts.state_manager import IWorkflowStateManager
from app.core.contracts.storage import IStorageProvider
from app.core.state import AnalysisWorkflow, WorkflowState
from app.database.repositories.audit_repository import AuditEventRepository
from app.database.repositories.document_repository import DocumentRepository
from app.database.repositories.workflow_repository import WorkflowRepository
from app.events.publisher import BasePublisher, PubSubPublisher
from app.events.schemas import EventType, WorkflowEvent
from app.events.subscriber import BaseSubscriber, PubSubSubscriber
from app.infrastructure.factory import (
    get_audit_repository,
    get_document_repository,
    get_event_publisher,
    get_event_subscriber,
    get_secret_provider,
    get_state_manager,
    get_storage_provider,
    get_workflow_repository,
)
from app.infrastructure.gcp.secret_manager import GCPSecretManagerProvider
from app.infrastructure.gcp.storage import GCSStorageProvider
from app.main import app
from app.audit.models import AuditEvent, AuditEventType
from app.models.document import DocumentMetadata, DocumentStatus
from app.orchestration.state_manager import FirestoreStateManager


class TestGCPProviderFactory:
    """Verify that provider factory explicitly resolves GCP implementations when requested."""

    def test_gcp_state_manager_resolution(self):
        sm = get_state_manager("gcp")
        assert isinstance(sm, FirestoreStateManager)
        assert isinstance(sm, IWorkflowStateManager)

    def test_gcp_workflow_repository_resolution(self):
        repo = get_workflow_repository("gcp")
        assert isinstance(repo, WorkflowRepository)
        assert isinstance(repo, IWorkflowRepository)

    def test_gcp_document_repository_resolution(self):
        repo = get_document_repository("gcp")
        assert isinstance(repo, DocumentRepository)
        assert isinstance(repo, IDocumentRepository)

    def test_gcp_audit_repository_resolution(self):
        repo = get_audit_repository("gcp")
        assert isinstance(repo, AuditEventRepository)
        assert isinstance(repo, IAuditEventRepository)

    def test_gcp_storage_provider_resolution(self):
        storage = get_storage_provider("gcp")
        assert isinstance(storage, GCSStorageProvider)
        assert isinstance(storage, IStorageProvider)

    def test_gcp_event_publisher_resolution(self):
        pub = get_event_publisher("gcp")
        assert isinstance(pub, PubSubPublisher)
        assert isinstance(pub, BasePublisher)
        assert pub.project_id == settings.gcp_project_id
        assert pub.topic_id == settings.pubsub_topic_workflow_events

    def test_gcp_event_subscriber_resolution(self):
        sub = get_event_subscriber("gcp")
        assert isinstance(sub, PubSubSubscriber)
        assert isinstance(sub, BaseSubscriber)
        assert sub.project_id == settings.gcp_project_id
        assert sub.subscription_id == settings.pubsub_subscription_workflow_orchestrator

    def test_gcp_secret_provider_resolution(self):
        sec = get_secret_provider("gcp")
        assert isinstance(sec, GCPSecretManagerProvider)
        assert isinstance(sec, ISecretProvider)


class TestGCSStorageProviderContract:
    """Verify GCSStorageProvider implementation against IStorageProvider contract."""

    def test_gcs_upload_bytes(self):
        mock_client = MagicMock()
        mock_bucket = MagicMock()
        mock_blob = MagicMock()
        mock_client.bucket.return_value = mock_bucket
        mock_bucket.blob.return_value = mock_blob

        provider = GCSStorageProvider(storage_client=mock_client)
        data = b"%PDF-1.4 test invoice content"
        provider.upload_bytes(
            bucket_or_container="test-bucket",
            object_path="documents/doc-1/original.pdf",
            data=data,
            content_type="application/pdf",
        )

        mock_client.bucket.assert_called_once_with("test-bucket")
        mock_bucket.blob.assert_called_once_with("documents/doc-1/original.pdf")
        mock_blob.upload_from_string.assert_called_once_with(data, content_type="application/pdf")

    def test_gcs_download_bytes(self):
        mock_client = MagicMock()
        mock_bucket = MagicMock()
        mock_blob = MagicMock()
        mock_blob.download_as_bytes.return_value = b"downloaded bytes"
        mock_client.bucket.return_value = mock_bucket
        mock_bucket.blob.return_value = mock_blob

        provider = GCSStorageProvider(storage_client=mock_client)
        result = provider.download_bytes("test-bucket", "documents/doc-1/original.pdf")

        assert result == b"downloaded bytes"
        mock_blob.download_as_bytes.assert_called_once()

    def test_gcs_delete_and_exists(self):
        mock_client = MagicMock()
        mock_bucket = MagicMock()
        mock_blob = MagicMock()
        mock_blob.exists.return_value = True
        mock_client.bucket.return_value = mock_bucket
        mock_bucket.blob.return_value = mock_blob

        provider = GCSStorageProvider(storage_client=mock_client)
        assert provider.object_exists("test-bucket", "documents/doc-1/original.pdf") is True
        assert provider.delete_object("test-bucket", "documents/doc-1/original.pdf") is True
        mock_blob.delete.assert_called_once()

    def test_gcs_fail_closed_without_client(self):
        provider = GCSStorageProvider(storage_client=None)
        with patch.object(GCSStorageProvider, "client", None):
            with pytest.raises(RuntimeError) as exc:
                provider.upload_bytes("test-bucket", "obj", b"test", "text/plain")
            assert "unavailable" in str(exc.value)


class TestGCPSecretManagerProviderContract:
    """Verify GCPSecretManagerProvider implementation against ISecretProvider contract."""

    def test_secret_manager_retrieval_success(self):
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.payload.data = b"super-secret-gemini-key"
        mock_client.access_secret_version.return_value = mock_response

        provider = GCPSecretManagerProvider(project_id="test-gcp-proj", secret_client=mock_client)
        secret_val = provider.get_secret("gemini-api-key")

        assert secret_val == "super-secret-gemini-key"
        mock_client.access_secret_version.assert_called_once_with(
            request={"name": "projects/test-gcp-proj/secrets/gemini-api-key/versions/latest"}
        )

    def test_secret_manager_in_memory_override(self):
        provider = GCPSecretManagerProvider(project_id="test-gcp-proj", secret_client=None)
        provider.set_in_memory_secret("custom-secret", "custom-val-123")
        assert provider.get_secret("custom-secret") == "custom-val-123"

    def test_secret_manager_env_fallback(self):
        provider = GCPSecretManagerProvider(project_id="test-gcp-proj", secret_client=None)
        with patch.dict(os.environ, {"MY_TEST_KEY": "env-provided-secret"}):
            val = provider.get_secret("my-test-key")
            assert val == "env-provided-secret"

    def test_secret_manager_missing_fails_closed(self):
        provider = GCPSecretManagerProvider(project_id="test-gcp-proj", secret_client=None)
        with pytest.raises(KeyError):
            provider.get_secret("nonexistent-key-xyz")


class TestGCPPubSubContract:
    """Verify PubSubPublisher serialization and dispatch contract."""

    def test_pubsub_publisher_serializes_workflow_event(self):
        publisher = PubSubPublisher(project_id="test-proj", topic_id="test-topic")
        mock_client = MagicMock()
        mock_future = MagicMock()
        mock_future.result.return_value = "msg-pubsub-123"
        mock_client.publish.return_value = mock_future
        mock_client.topic_path.return_value = "projects/test-proj/topics/test-topic"
        publisher._client = mock_client

        event = WorkflowEvent(
            event_id="evt-pubsub-1",
            event_type=EventType.DOCUMENT_UPLOADED,
            workflow_id="wf-pubsub-1",
            document_id="doc-pubsub-1",
            current_state="UPLOADED",
            workflow_revision=1,
            event_timestamp=datetime.now(timezone.utc),
            correlation_id="corr-pubsub-123",
            payload={"document_id": "doc-pubsub-1"},
            payload_hash="hash123",
        )

        msg_id = publisher.publish(event)
        assert msg_id == "msg-pubsub-123"
        mock_client.publish.assert_called_once()
        published_bytes = mock_client.publish.call_args[1]["data"]
        payload_dict = json.loads(published_bytes.decode("utf-8"))
        assert payload_dict["workflow_id"] == "wf-pubsub-1"
        assert payload_dict["event_type"] == "DOCUMENT_UPLOADED"


class TestCloudRunReadinessAPI:
    """Verify API application readiness and health endpoints in GCP mode."""

    def test_health_endpoint_returns_ok(self):
        client = TestClient(app)
        response = client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
        assert data["service"] == "PaperTrail AI"

    def test_readiness_endpoint_in_gcp_mode(self):
        with patch.object(settings, "papertrail_cloud_provider", "gcp"):
            client = TestClient(app)
            response = client.get("/health/ready")
            assert response.status_code == 200
            data = response.json()
            assert data["status"] == "ready"
            assert data["provider"] == "gcp"
            assert "dependencies" in data
            assert data["dependencies"]["firestore"] == "configured"
            assert data["dependencies"]["cloud_storage"] == "configured"
            assert data["dependencies"]["pubsub"] == "configured"

from app.core.config import settings
from app.core.gcp import gcp_foundation, GCPFoundation


def test_gcp_config_defaults():
    """Verify default Google Cloud configuration settings."""
    assert settings.gcp_project_id == "papertrail-ai-dev"
    assert settings.gcp_region == "us-central1"
    assert "papertrail-runtime" in settings.gcp_service_account
    assert settings.firestore_database_id == "(default)"
    assert settings.gcs_bucket_documents == "papertrail-ai-documents-dev"
    assert settings.gcs_bucket_reports == "papertrail-ai-reports-dev"
    assert settings.pubsub_topic_events == "papertrail-events-topic"
    assert settings.secret_name_gemini_api_key == "papertrail-gemini-api-key"


def test_gcp_foundation_initialization():
    """Verify GCPFoundation manager initialization."""
    foundation = GCPFoundation()
    assert foundation.project_id == settings.gcp_project_id
    assert foundation.environment == settings.environment


def test_gcp_client_helpers_development_mode():
    """Verify that client factory methods execute without unhandled exceptions.

    In development mode without active GCP credentials, factory methods should
    gracefully log a warning and return None rather than crashing.
    """
    firestore_client = gcp_foundation.get_firestore_client()
    storage_client = gcp_foundation.get_storage_client()
    publisher = gcp_foundation.get_pubsub_publisher()
    subscriber = gcp_foundation.get_pubsub_subscriber()
    secret_client = gcp_foundation.get_secret_manager_client()

    # Verify return types (either actual client or None in dev mode)
    assert firestore_client is None or hasattr(firestore_client, "collection")
    assert storage_client is None or hasattr(storage_client, "bucket")
    assert publisher is None or hasattr(publisher, "publish")
    assert subscriber is None or hasattr(subscriber, "subscribe")
    assert secret_client is None or hasattr(secret_client, "access_secret_version")

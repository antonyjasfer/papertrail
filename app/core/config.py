from typing import Optional
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings for PaperTrail AI."""

    # App Core Settings
    app_name: str = "PaperTrail AI"
    app_version: str = "0.1.0"
    environment: str = "development"
    host: str = "127.0.0.1"
    port: int = 8080
    phase: str = "Phase 13 - Deterministic Workflow Orchestration & End-to-End Pipeline"
    log_level: str = "INFO"

    # Gemini AI Model & Document Intelligence Settings
    gemini_model: str = "gemini-3.6-flash"
    document_extraction_confidence_threshold: float = 0.70
    max_retries: int = 2

    # Document Validation Limits
    max_file_size_bytes: int = 26214400  # 25 MB default limit

    # Google Cloud Infrastructure Settings
    gcp_project_id: str = "papertrail-ai-dev"
    gcp_region: str = "us-central1"
    gcp_service_account: str = "papertrail-runtime@papertrail-ai-dev.iam.gserviceaccount.com"

    # Firestore Database Settings
    firestore_database_id: str = "(default)"

    # Cloud Storage Bucket Settings
    gcs_bucket_documents: str = "papertrail-ai-documents-dev"
    gcs_bucket_reports: str = "papertrail-ai-reports-dev"

    # Pub/Sub Messaging Settings
    pubsub_topic_events: str = "papertrail-events-topic"
    pubsub_subscription_events: str = "papertrail-events-sub"
    pubsub_topic_workflow_events: str = "papertrail-workflow-events"
    pubsub_subscription_workflow_orchestrator: str = "papertrail-orchestrator-sub"
    pubsub_emulator_host: Optional[str] = None
    orchestration_max_retries: int = 3
    lease_ttl_seconds: int = 300

    # Secret Manager Secret Names
    secret_name_gemini_api_key: str = "papertrail-gemini-api-key"

    # Optional Gemini Key (Fallback to Secret Manager or Mock in Dev)
    gemini_api_key: Optional[str] = None

    # Frontend CORS Origin (secure, no wildcard)
    frontend_origin: str = "http://localhost:5173"

    # Multi-Cloud Provider Selection ('gcp' | 'azure' | 'mock')
    papertrail_cloud_provider: str = "gcp"

    # Fine-grained capability overrides (optional; defaults derive from papertrail_cloud_provider)
    workflow_provider: Optional[str] = None
    storage_provider: Optional[str] = None
    event_provider: Optional[str] = None
    secret_provider: Optional[str] = None

    # Azure Infrastructure Settings
    azure_cosmos_endpoint: Optional[str] = None
    azure_cosmos_key: Optional[str] = None
    azure_cosmos_database: str = "papertrail-db"
    azure_cosmos_container_workflow_state: str = "workflow_state"
    azure_cosmos_container_documents: str = "documents"
    azure_cosmos_container_audit_events: str = "audit_events"

    azure_storage_account_url: Optional[str] = None
    azure_storage_connection_string: Optional[str] = None
    azure_blob_container_documents: str = "papertrail-documents-dev"
    azure_blob_container_reports: str = "papertrail-reports-dev"

    azure_servicebus_namespace: Optional[str] = None
    azure_servicebus_connection_string: Optional[str] = None
    azure_servicebus_topic_workflow_events: str = "papertrail-workflow-events"
    azure_servicebus_subscription_orchestrator: str = "papertrail-orchestrator-sub"

    azure_keyvault_url: Optional[str] = None

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


settings = Settings()


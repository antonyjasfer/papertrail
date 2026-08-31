import logging
from typing import Optional

from app.core.config import settings
from app.core.contracts.repositories import (
    IAuditEventRepository,
    IDocumentRepository,
    IWorkflowRepository,
)
from app.core.contracts.secrets import ISecretProvider
from app.core.contracts.state_manager import IWorkflowStateManager
from app.core.contracts.storage import IStorageProvider
from app.events.publisher import BasePublisher, MockPubSubPublisher, PubSubPublisher
from app.events.subscriber import BaseSubscriber, MockPubSubSubscriber, PubSubSubscriber

logger = logging.getLogger("papertrail.infrastructure.factory")


def _resolve_provider(capability: str, override: Optional[str] = None) -> str:
    """Resolve active provider for a capability, honoring overrides before global setting."""
    if override:
        return override.lower()
    override_attr = f"{capability}_provider"
    val = getattr(settings, override_attr, None)
    if val:
        return val.lower()
    return settings.papertrail_cloud_provider.lower()


def get_state_manager(provider: Optional[str] = None) -> IWorkflowStateManager:
    """Dependency injection factory for state managers."""
    selected = _resolve_provider("workflow", provider)
    if selected in ("azure", "cosmos"):
        from app.infrastructure.azure.cosmos_state_manager import CosmosStateManager
        return CosmosStateManager()
    elif selected in ("gcp", "firestore"):
        from app.orchestration.state_manager import FirestoreStateManager
        return FirestoreStateManager()
    elif selected in ("mock", "in_memory"):
        from app.infrastructure.mock.state_manager import InMemoryStateManager
        return InMemoryStateManager()
    raise ValueError(f"Unsupported workflow state provider: '{selected}'")


def get_workflow_repository(provider: Optional[str] = None) -> IWorkflowRepository:
    """Dependency injection factory for workflow repositories."""
    selected = _resolve_provider("workflow", provider)
    if selected in ("azure", "cosmos"):
        from app.infrastructure.azure.cosmos_repositories import CosmosWorkflowRepository
        return CosmosWorkflowRepository()
    elif selected in ("gcp", "firestore", "mock", "in_memory"):
        from app.database.repositories.workflow_repository import WorkflowRepository
        return WorkflowRepository()
    raise ValueError(f"Unsupported workflow repository provider: '{selected}'")


def get_document_repository(provider: Optional[str] = None) -> IDocumentRepository:
    """Dependency injection factory for document repositories."""
    selected = _resolve_provider("workflow", provider)
    if selected in ("azure", "cosmos"):
        from app.infrastructure.azure.cosmos_repositories import CosmosDocumentRepository
        return CosmosDocumentRepository()
    elif selected in ("gcp", "firestore", "mock", "in_memory"):
        from app.database.repositories.document_repository import DocumentRepository
        return DocumentRepository()
    raise ValueError(f"Unsupported document repository provider: '{selected}'")


def get_audit_repository(provider: Optional[str] = None) -> IAuditEventRepository:
    """Dependency injection factory for audit event repositories."""
    selected = _resolve_provider("workflow", provider)
    if selected in ("azure", "cosmos"):
        from app.infrastructure.azure.cosmos_repositories import CosmosAuditEventRepository
        return CosmosAuditEventRepository()
    elif selected in ("gcp", "firestore", "mock", "in_memory"):
        from app.database.repositories.audit_repository import AuditEventRepository
        return AuditEventRepository()
    raise ValueError(f"Unsupported audit repository provider: '{selected}'")


def get_storage_provider(provider: Optional[str] = None) -> IStorageProvider:
    """Dependency injection factory for object storage providers."""
    selected = _resolve_provider("storage", provider)
    if selected in ("azure", "azure_blob", "blob"):
        from app.infrastructure.azure.blob_storage import AzureBlobStorageProvider
        return AzureBlobStorageProvider()
    elif selected in ("gcp", "gcs"):
        from app.infrastructure.gcp.storage import GCSStorageProvider
        return GCSStorageProvider()
    elif selected in ("mock", "local", "in_memory"):
        from app.infrastructure.mock.storage import MockStorageProvider
        return MockStorageProvider()
    raise ValueError(f"Unsupported storage provider: '{selected}'")


def get_event_publisher(provider: Optional[str] = None) -> BasePublisher:
    """Dependency injection factory for event publishers."""
    selected = _resolve_provider("event", provider)
    if selected in ("azure", "service_bus"):
        from app.infrastructure.azure.service_bus_publisher import ServiceBusPublisher
        return ServiceBusPublisher()
    elif selected in ("gcp", "pubsub"):
        return PubSubPublisher(
            project_id=settings.gcp_project_id,
            topic_id=settings.pubsub_topic_workflow_events,
        )
    elif selected in ("mock", "in_memory"):
        return MockPubSubPublisher()
    raise ValueError(f"Unsupported event publisher provider: '{selected}'")


def get_event_subscriber(provider: Optional[str] = None) -> BaseSubscriber:
    """Dependency injection factory for event subscribers."""
    selected = _resolve_provider("event", provider)
    if selected in ("azure", "service_bus"):
        from app.infrastructure.azure.service_bus_subscriber import ServiceBusSubscriber
        return ServiceBusSubscriber()
    elif selected in ("gcp", "pubsub"):
        return PubSubSubscriber(
            project_id=settings.gcp_project_id,
            subscription_id=settings.pubsub_subscription_workflow_orchestrator,
        )
    elif selected in ("mock", "in_memory"):
        return MockPubSubSubscriber()
    raise ValueError(f"Unsupported event subscriber provider: '{selected}'")


def get_secret_provider(provider: Optional[str] = None) -> ISecretProvider:
    """Dependency injection factory for secret providers."""
    selected = _resolve_provider("secret", provider)
    if selected in ("azure", "key_vault"):
        from app.infrastructure.azure.key_vault_provider import AzureKeyVaultSecretProvider
        return AzureKeyVaultSecretProvider()
    elif selected in ("gcp", "secret_manager", "google"):
        from app.infrastructure.gcp.secret_manager import GCPSecretManagerProvider
        return GCPSecretManagerProvider()
    elif selected in ("mock", "env"):
        from app.infrastructure.gcp.secret_manager import GCPSecretManagerProvider
        return GCPSecretManagerProvider()
    raise ValueError(f"Unsupported secret provider: '{selected}'")

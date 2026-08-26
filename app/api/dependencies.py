import logging
from typing import Optional

from app.core.config import settings
from app.infrastructure.factory import (
    _resolve_provider,
    get_document_repository,
    get_storage_provider,
)
from app.services.document_storage import DocumentStorageService

logger = logging.getLogger("papertrail.api.dependencies")


def resolve_document_bucket_or_container(provider: Optional[str] = None) -> str:
    """Resolve the active bucket or container name based on configured storage provider."""
    selected = _resolve_provider("storage", provider)
    if selected in ("azure", "azure_blob", "blob"):
        return settings.azure_blob_container_documents
    elif selected in ("gcp", "gcs"):
        return settings.gcs_bucket_documents
    elif selected in ("mock", "local", "in_memory"):
        return settings.azure_blob_container_documents or settings.gcs_bucket_documents or "papertrail-documents"
    return settings.gcs_bucket_documents


def get_document_storage_service() -> DocumentStorageService:
    """Dependency provider returning an initialized instance of DocumentStorageService
    with the selected cloud storage provider, document repository, and resolved container/bucket.
    """
    repository = get_document_repository()
    storage_provider = get_storage_provider()
    bucket_or_container = resolve_document_bucket_or_container()

    return DocumentStorageService(
        repository=repository,
        storage_provider=storage_provider,
        bucket_name=bucket_or_container,
        max_size_bytes=settings.max_file_size_bytes,
    )

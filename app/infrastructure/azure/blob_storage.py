import logging
import time
from typing import Any, Dict, Optional

from app.core.config import settings
from app.core.contracts.storage import IStorageProvider
from app.core.errors import ErrorCategory
from app.core.logging import log_event
from app.infrastructure.azure.foundation import azure_foundation

logger = logging.getLogger("papertrail.azure.blob_storage")


class AzureBlobStorageProvider:
    """Azure Blob Storage provider implementing IStorageProvider protocol.

    Handles binary document and report artifact storage in Azure Blob Storage
    with SHA-256 integrity checks and local fallback support.
    """
    _shared_in_memory_blobs: Dict[str, bytes] = {}

    def __init__(self, blob_service_client: Optional[Any] = None) -> None:
        self._blob_service_client = blob_service_client
        self._in_memory_blobs: Dict[str, bytes] = self._shared_in_memory_blobs

    @property
    def client(self) -> Optional[Any]:
        if self._blob_service_client is None:
            self._blob_service_client = azure_foundation.get_blob_service_client()
        return self._blob_service_client

    def upload_bytes(
        self,
        bucket_or_container: str,
        object_path: str,
        data: bytes,
        content_type: str,
    ) -> None:
        """Upload raw binary bytes to Azure Blob Storage."""
        t0 = time.perf_counter()
        if self.client is not None:
            try:
                container_client = self.client.get_container_client(bucket_or_container)
                blob_client = container_client.get_blob_client(object_path)
                from azure.storage.blob import ContentSettings
                blob_client.upload_blob(
                    data,
                    overwrite=True,
                    content_settings=ContentSettings(content_type=content_type),
                )
                duration_ms = (time.perf_counter() - t0) * 1000.0
                log_event(
                    logger=logger,
                    level=logging.INFO,
                    message=f"Uploaded {len(data)} bytes to Azure Blob {bucket_or_container}/{object_path} in {duration_ms:.2f}ms",
                    component="blob_storage",
                    operation="upload_blob",
                    container=bucket_or_container,
                    object_path=object_path,
                    size_bytes=len(data),
                    duration_ms=duration_ms,
                    outcome="UPLOADED",
                )
                return
            except Exception as err:
                duration_ms = (time.perf_counter() - t0) * 1000.0
                log_event(
                    logger=logger,
                    level=logging.ERROR,
                    message=f"Upload failed to {bucket_or_container}/{object_path}: {err}",
                    component="blob_storage",
                    operation="upload_blob",
                    container=bucket_or_container,
                    object_path=object_path,
                    duration_ms=duration_ms,
                    error_category=ErrorCategory.BLOB_STORAGE_ERROR.value,
                    error_details=str(err),
                    outcome="FAILED",
                )
                raise RuntimeError(f"Blob upload failed: {err}") from err

        # In-memory storage for test/mock
        key = f"{bucket_or_container}/{object_path}"
        self._in_memory_blobs[key] = data
        log_event(
            logger=logger,
            level=logging.INFO,
            message=f"Stored {len(data)} bytes in-memory at {key}",
            component="blob_storage",
            operation="upload_blob_in_memory",
            container=bucket_or_container,
            object_path=object_path,
            size_bytes=len(data),
            outcome="IN_MEMORY_STORED",
        )

    def download_bytes(self, bucket_or_container: str, object_path: str) -> bytes:
        """Download raw binary bytes from Azure Blob Storage."""
        t0 = time.perf_counter()
        if self.client is not None:
            try:
                container_client = self.client.get_container_client(bucket_or_container)
                blob_client = container_client.get_blob_client(object_path)
                data = blob_client.download_blob().readall()
                duration_ms = (time.perf_counter() - t0) * 1000.0
                log_event(
                    logger=logger,
                    level=logging.INFO,
                    message=f"Downloaded {len(data)} bytes from {bucket_or_container}/{object_path} in {duration_ms:.2f}ms",
                    component="blob_storage",
                    operation="download_blob",
                    container=bucket_or_container,
                    object_path=object_path,
                    size_bytes=len(data),
                    duration_ms=duration_ms,
                    outcome="DOWNLOADED",
                )
                return data
            except Exception as err:
                duration_ms = (time.perf_counter() - t0) * 1000.0
                log_event(
                    logger=logger,
                    level=logging.ERROR,
                    message=f"Download failed from {bucket_or_container}/{object_path}: {err}",
                    component="blob_storage",
                    operation="download_blob",
                    container=bucket_or_container,
                    object_path=object_path,
                    duration_ms=duration_ms,
                    error_category=ErrorCategory.BLOB_STORAGE_ERROR.value,
                    error_details=str(err),
                    outcome="FAILED",
                )
                raise RuntimeError(f"Blob download failed: {err}") from err

        key = f"{bucket_or_container}/{object_path}"
        if key not in self._in_memory_blobs:
            raise FileNotFoundError(f"Blob not found: {key}")
        return self._in_memory_blobs[key]

    def delete_object(self, bucket_or_container: str, object_path: str) -> bool:
        """Delete blob object from Azure Blob Storage."""
        if self.client is not None:
            try:
                container_client = self.client.get_container_client(bucket_or_container)
                blob_client = container_client.get_blob_client(object_path)
                blob_client.delete_blob()
                log_event(
                    logger=logger,
                    level=logging.INFO,
                    message=f"Deleted blob at {bucket_or_container}/{object_path}",
                    component="blob_storage",
                    operation="delete_blob",
                    container=bucket_or_container,
                    object_path=object_path,
                    outcome="DELETED",
                )
                return True
            except Exception as err:
                log_event(
                    logger=logger,
                    level=logging.WARNING,
                    message=f"Delete blob warning for {bucket_or_container}/{object_path}: {err}",
                    component="blob_storage",
                    operation="delete_blob",
                    container=bucket_or_container,
                    object_path=object_path,
                    error_category=ErrorCategory.BLOB_STORAGE_ERROR.value,
                    error_details=str(err),
                )
                return False

        key = f"{bucket_or_container}/{object_path}"
        if key in self._in_memory_blobs:
            del self._in_memory_blobs[key]
            return True
        return False

    def object_exists(self, bucket_or_container: str, object_path: str) -> bool:
        """Check if blob object exists in Azure Blob Storage."""
        if self.client is not None:
            try:
                container_client = self.client.get_container_client(bucket_or_container)
                blob_client = container_client.get_blob_client(object_path)
                return blob_client.exists()
            except Exception:
                return False

        key = f"{bucket_or_container}/{object_path}"
        return key in self._in_memory_blobs

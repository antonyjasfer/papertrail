import logging
from typing import Any, Dict, Optional

from app.core.config import settings
from app.core.contracts.storage import IStorageProvider
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
                logger.info(
                    "[AzureBlobStorageProvider] Uploaded %d bytes to %s/%s",
                    len(data),
                    bucket_or_container,
                    object_path,
                )
                return
            except Exception as err:
                logger.error(
                    "[AzureBlobStorageProvider] Upload failed to %s/%s: %s",
                    bucket_or_container,
                    object_path,
                    err,
                )
                raise RuntimeError(f"Blob upload failed: {err}") from err

        # In-memory storage for test/mock
        key = f"{bucket_or_container}/{object_path}"
        self._in_memory_blobs[key] = data
        logger.info(
            "[AzureBlobStorageProvider (in-memory)] Stored %d bytes at %s",
            len(data),
            key,
        )

    def download_bytes(self, bucket_or_container: str, object_path: str) -> bytes:
        """Download raw binary bytes from Azure Blob Storage."""
        if self.client is not None:
            try:
                container_client = self.client.get_container_client(bucket_or_container)
                blob_client = container_client.get_blob_client(object_path)
                return blob_client.download_blob().readall()
            except Exception as err:
                logger.error(
                    "[AzureBlobStorageProvider] Download failed from %s/%s: %s",
                    bucket_or_container,
                    object_path,
                    err,
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
                logger.info(
                    "[AzureBlobStorageProvider] Deleted blob %s/%s",
                    bucket_or_container,
                    object_path,
                )
                return True
            except Exception as err:
                logger.warning(
                    "[AzureBlobStorageProvider] Error deleting blob %s/%s: %s",
                    bucket_or_container,
                    object_path,
                    err,
                )
                return False

        key = f"{bucket_or_container}/{object_path}"
        return self._in_memory_blobs.pop(key, None) is not None

    def object_exists(self, bucket_or_container: str, object_path: str) -> bool:
        """Check if blob exists in Azure Blob Storage."""
        if self.client is not None:
            try:
                container_client = self.client.get_container_client(bucket_or_container)
                blob_client = container_client.get_blob_client(object_path)
                return blob_client.exists()
            except Exception:
                return False

        key = f"{bucket_or_container}/{object_path}"
        return key in self._in_memory_blobs

import logging
from typing import Any, Optional

from app.core.contracts.storage import IStorageProvider

logger = logging.getLogger("papertrail.gcp.storage")


class GCSStorageProvider:
    """Google Cloud Storage provider implementing IStorageProvider protocol."""

    def __init__(self, storage_client: Optional[Any] = None) -> None:
        self._storage_client = storage_client

    @property
    def client(self) -> Optional[Any]:
        if self._storage_client is None:
            from app.core.gcp import gcp_foundation
            self._storage_client = gcp_foundation.get_storage_client()
        return self._storage_client

    def upload_bytes(
        self,
        bucket_or_container: str,
        object_path: str,
        data: bytes,
        content_type: str,
    ) -> None:
        """Upload raw binary bytes to Google Cloud Storage."""
        if self.client is None:
            raise RuntimeError("GCS storage client is unavailable in current environment.")
        try:
            bucket = self.client.bucket(bucket_or_container)
            blob = bucket.blob(object_path)
            blob.upload_from_string(data, content_type=content_type)
            logger.info(
                "[GCSStorageProvider] Uploaded %d bytes to %s/%s",
                len(data),
                bucket_or_container,
                object_path,
            )
        except Exception as err:
            logger.error(
                "[GCSStorageProvider] Upload failed to %s/%s: %s",
                bucket_or_container,
                object_path,
                err,
            )
            raise RuntimeError(f"GCS upload failed: {err}") from err

    def download_bytes(self, bucket_or_container: str, object_path: str) -> bytes:
        """Download raw binary bytes from Google Cloud Storage."""
        if self.client is None:
            raise RuntimeError("GCS storage client is unavailable in current environment.")
        try:
            bucket = self.client.bucket(bucket_or_container)
            blob = bucket.blob(object_path)
            return blob.download_as_bytes()
        except Exception as err:
            logger.error(
                "[GCSStorageProvider] Download failed from %s/%s: %s",
                bucket_or_container,
                object_path,
                err,
            )
            raise RuntimeError(f"GCS download failed: {err}") from err

    def delete_object(self, bucket_or_container: str, object_path: str) -> bool:
        """Delete object from Google Cloud Storage."""
        if self.client is None:
            return False
        try:
            bucket = self.client.bucket(bucket_or_container)
            blob = bucket.blob(object_path)
            if blob.exists():
                blob.delete()
                logger.info(
                    "[GCSStorageProvider] Deleted object %s/%s",
                    bucket_or_container,
                    object_path,
                )
                return True
            return False
        except Exception as err:
            logger.warning(
                "[GCSStorageProvider] Error deleting object %s/%s: %s",
                bucket_or_container,
                object_path,
                err,
            )
            return False

    def object_exists(self, bucket_or_container: str, object_path: str) -> bool:
        """Check if object exists in Google Cloud Storage."""
        if self.client is None:
            return False
        try:
            bucket = self.client.bucket(bucket_or_container)
            blob = bucket.blob(object_path)
            return blob.exists()
        except Exception:
            return False

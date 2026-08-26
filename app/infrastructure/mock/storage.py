import logging
from typing import Dict

from app.core.contracts.storage import IStorageProvider

logger = logging.getLogger("papertrail.mock.storage")


class MockStorageProvider:
    """In-memory Mock storage provider implementing IStorageProvider protocol."""

    def __init__(self) -> None:
        self._storage: Dict[str, bytes] = {}

    def upload_bytes(
        self,
        bucket_or_container: str,
        object_path: str,
        data: bytes,
        content_type: str,
    ) -> None:
        """Store binary bytes in memory."""
        key = f"{bucket_or_container}/{object_path}"
        self._storage[key] = data
        logger.info(
            "[MockStorageProvider] Stored %d bytes at %s",
            len(data),
            key,
        )

    def download_bytes(self, bucket_or_container: str, object_path: str) -> bytes:
        """Retrieve binary bytes from memory."""
        key = f"{bucket_or_container}/{object_path}"
        if key not in self._storage:
            raise FileNotFoundError(f"Object not found: {key}")
        return self._storage[key]

    def delete_object(self, bucket_or_container: str, object_path: str) -> bool:
        """Delete object from memory."""
        key = f"{bucket_or_container}/{object_path}"
        return self._storage.pop(key, None) is not None

    def object_exists(self, bucket_or_container: str, object_path: str) -> bool:
        """Check if object exists in memory."""
        key = f"{bucket_or_container}/{object_path}"
        return key in self._storage

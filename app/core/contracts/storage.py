from typing import Protocol, runtime_checkable


@runtime_checkable
class IStorageProvider(Protocol):
    """Protocol for binary object storage providers (GCS, Azure Blob, Local FS)."""

    def upload_bytes(
        self,
        bucket_or_container: str,
        object_path: str,
        data: bytes,
        content_type: str,
    ) -> None: ...

    def download_bytes(self, bucket_or_container: str, object_path: str) -> bytes: ...

    def delete_object(self, bucket_or_container: str, object_path: str) -> bool: ...

    def object_exists(self, bucket_or_container: str, object_path: str) -> bool: ...

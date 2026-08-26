import hashlib
import logging
import os
import re
import uuid
from typing import Any, Optional, Set

from app.core.config import settings
from app.core.contracts.repositories import IDocumentRepository
from app.core.contracts.storage import IStorageProvider
from app.models.document import DocumentMetadata, DocumentStatus

logger = logging.getLogger("papertrail.services.document_storage")


class DocumentValidationError(Exception):
    """Exception raised when document validation (size, MIME type, filename) fails."""

    def __init__(self, message: str):
        super().__init__(f"Document validation error: {message}")


class DocumentStorageError(Exception):
    """Exception raised when document storage operations or partial failures occur."""

    def __init__(self, operation: str, document_id: str, message: str):
        self.operation = operation
        self.document_id = document_id
        super().__init__(f"Document storage error during {operation} for '{document_id}': {message}")


SUPPORTED_CONTENT_TYPES: Set[str] = {
    "application/pdf",
    "image/png",
    "image/jpeg",
    "text/plain",
}


def sanitize_filename(filename: str) -> str:
    """Sanitize uploaded filename to prevent path traversal and shell injection.

    Strips directory paths, path traversal sequences ('../', '..\\'), and invalid characters.
    Returns a safe base filename.
    """
    if not filename:
        return "unnamed_document.bin"

    # Extract base filename ignoring any directory paths
    base_name = os.path.basename(filename.replace("\\", "/"))

    # Remove any remaining path traversal markers
    base_name = base_name.replace("..", "").strip()

    # Retain safe alphanumeric, dot, dash, and underscore characters
    sanitized = re.sub(r"[^a-zA-Z0-9._-]", "_", base_name)
    sanitized = sanitized.strip("._")

    if not sanitized:
        return "unnamed_document.bin"

    return sanitized


def calculate_checksum(file_bytes: bytes) -> str:
    """Calculate deterministic SHA-256 cryptographic hash over file bytes."""
    return hashlib.sha256(file_bytes).hexdigest()


def generate_object_path(document_id: str, sanitized_filename: str) -> str:
    """Generate deterministic Storage object path."""
    return f"documents/{document_id}/original/{sanitized_filename}"


class DocumentStorageService:
    """Service managing document validation, SHA-256 fingerprinting, binary artifact upload,
    and metadata persistence via injected IStorageProvider and IDocumentRepository.
    """

    def __init__(
        self,
        repository: Optional[IDocumentRepository] = None,
        storage_provider: Optional[IStorageProvider] = None,
        bucket_name: Optional[str] = None,
        max_size_bytes: Optional[int] = None,
    ):
        self.repository = repository
        self._storage_provider = storage_provider
        self.bucket_name = bucket_name or settings.gcs_bucket_documents
        self.max_size_bytes = (
            max_size_bytes if max_size_bytes is not None else settings.max_file_size_bytes
        )

    def validate_document_input(self, filename: str, content_type: str, file_bytes: bytes) -> str:
        """Validate input file metadata, content type, and file size limits."""
        if not file_bytes:
            raise DocumentValidationError("Document byte payload is empty.")

        if len(file_bytes) > self.max_size_bytes:
            raise DocumentValidationError(
                f"File size ({len(file_bytes)} bytes) exceeds maximum limit of {self.max_size_bytes} bytes."
            )

        if content_type.lower() not in SUPPORTED_CONTENT_TYPES:
            raise DocumentValidationError(
                f"Unsupported content type '{content_type}'. Supported types: {sorted(list(SUPPORTED_CONTENT_TYPES))}."
            )

        return sanitize_filename(filename)

    def store_document(
        self,
        filename: str,
        content_type: str,
        file_bytes: bytes,
        document_id: Optional[str] = None,
    ) -> DocumentMetadata:
        """Validate, fingerprint, and store document payload to Storage Provider and metadata repository.

        Handles partial failures explicitly to prevent orphaned false-success records.
        """
        sanitized_filename = self.validate_document_input(filename, content_type, file_bytes)

        if not document_id:
            document_id = f"doc-{uuid.uuid4().hex[:12]}"

        size_bytes = len(file_bytes)
        checksum = calculate_checksum(file_bytes)
        object_path = generate_object_path(document_id, sanitized_filename)

        metadata = DocumentMetadata(
            document_id=document_id,
            filename=sanitized_filename,
            content_type=content_type,
            size_bytes=size_bytes,
            storage_bucket=self.bucket_name,
            storage_object=object_path,
            document_status=DocumentStatus.UPLOADING,
            checksum=checksum,
        )

        # Fail closed if no storage provider is configured
        if self._storage_provider is None:
            metadata.document_status = DocumentStatus.STORAGE_FAILED
            raise DocumentStorageError(
                "upload_bytes",
                document_id,
                "No storage provider configured (fail-closed).",
            )

        # Step 1: Attempt Storage Provider Object Upload
        storage_uploaded = False
        try:
            self._storage_provider.upload_bytes(
                bucket_or_container=self.bucket_name,
                object_path=object_path,
                data=file_bytes,
                content_type=content_type,
            )
            storage_uploaded = True
            logger.info("Successfully uploaded object '%s' to '%s'", object_path, self.bucket_name)
        except Exception as err:
            metadata.document_status = DocumentStatus.STORAGE_FAILED
            logger.error("Storage upload failed for document '%s': %s", document_id, err)
            raise DocumentStorageError("upload_bytes", document_id, f"Storage upload failed: {err}") from err

        # Step 2: Persist Metadata to Repository
        try:
            metadata.document_status = DocumentStatus.STORED
            if self.repository is None:
                raise RuntimeError("No document repository configured.")
            self.repository.create(metadata)
            logger.info("Successfully persisted document metadata for '%s'", document_id)
            return metadata
        except Exception as err:
            # Handle Case B: Upload succeeded but Metadata persistence failed
            logger.error(
                "Metadata persistence failed for '%s' after upload. Executing cleanup fallback: %s",
                document_id,
                err,
            )
            metadata.document_status = DocumentStatus.STORAGE_FAILED
            if storage_uploaded:
                try:
                    self._storage_provider.delete_object(
                        bucket_or_container=self.bucket_name,
                        object_path=object_path,
                    )
                    logger.info("Cleaned up orphaned storage object '%s' after metadata failure", object_path)
                except Exception as cleanup_err:
                    logger.error("Failed to cleanup orphaned storage object '%s': %s", object_path, cleanup_err)

            raise DocumentStorageError(
                "persist_metadata",
                document_id,
                f"Metadata persistence failed; storage object was cleaned up: {err}",
            ) from err

    def get_document_metadata(self, document_id: str) -> DocumentMetadata:
        """Retrieve DocumentMetadata from repository."""
        if self.repository is None:
            raise DocumentStorageError("get_metadata", document_id, "No repository configured.")
        return self.repository.get(document_id)

    def get_document_bytes(self, document_id: str) -> bytes:
        """Retrieve raw document payload bytes from Storage Provider using metadata object path."""
        metadata = self.get_document_metadata(document_id)
        if metadata.document_status != DocumentStatus.STORED:
            raise DocumentStorageError(
                "download_bytes", document_id, f"Document status is '{metadata.document_status.value}', not STORED."
            )

        if self._storage_provider is None:
            raise DocumentStorageError(
                "download_bytes",
                document_id,
                "No storage provider configured (fail-closed).",
            )

        try:
            file_bytes = self._storage_provider.download_bytes(
                bucket_or_container=metadata.storage_bucket,
                object_path=metadata.storage_object,
            )

            # Verify checksum integrity upon retrieval
            downloaded_checksum = calculate_checksum(file_bytes)
            if downloaded_checksum != metadata.checksum:
                raise DocumentStorageError(
                    "checksum_integrity",
                    document_id,
                    f"Checksum mismatch on download. Stored: {metadata.checksum}, Downloaded: {downloaded_checksum}",
                )

            return file_bytes
        except DocumentStorageError:
            raise
        except Exception as err:
            raise DocumentStorageError("download_bytes", document_id, str(err)) from err

    def delete_document(self, document_id: str) -> bool:
        """Perform controlled deletion of storage artifact and update metadata record to DELETED."""
        metadata = self.get_document_metadata(document_id)

        if self._storage_provider is None:
            raise DocumentStorageError(
                "delete_object",
                document_id,
                "No storage provider configured (fail-closed).",
            )

        # Step 1: Delete Storage Object if present
        try:
            self._storage_provider.delete_object(
                bucket_or_container=metadata.storage_bucket,
                object_path=metadata.storage_object,
            )
            logger.info("Deleted storage object '%s'", metadata.storage_object)
        except Exception as err:
            logger.warning("Error deleting storage object '%s': %s", metadata.storage_object, err)

        # Step 2: Update Metadata status to DELETED
        metadata.document_status = DocumentStatus.DELETED
        if self.repository is not None:
            self.repository.update(metadata)
        logger.info("Updated document metadata for '%s' to DELETED", document_id)
        return True

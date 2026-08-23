import hashlib
import logging
import os
import re
import uuid
from typing import Any, Optional, Set
from app.core.config import settings
from app.core.gcp import gcp_foundation
from app.database.repositories.document_repository import DocumentRepository
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
    """Generate deterministic Cloud Storage object path."""
    return f"documents/{document_id}/original/{sanitized_filename}"


class DocumentStorageService:
    """Service managing document validation, SHA-256 fingerprinting, Cloud Storage artifact upload,
    and Firestore metadata persistence.
    """

    def __init__(
        self,
        repository: Optional[DocumentRepository] = None,
        storage_client: Optional[Any] = None,
    ):
        self.repository = repository or DocumentRepository()
        self._storage_client = storage_client
        self.bucket_name = settings.gcs_bucket_documents
        self.max_size_bytes = settings.max_file_size_bytes

    @property
    def storage_client(self) -> Any:
        """Lazily retrieve or return initialized Cloud Storage client."""
        if self._storage_client is None:
            self._storage_client = gcp_foundation.get_storage_client()
        if self._storage_client is None:
            raise DocumentStorageError(
                "connect", "N/A", "Cloud Storage client is unavailable in current environment."
            )
        return self._storage_client

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
        """Validate, fingerprint, and store document payload to Cloud Storage and Firestore.

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

        # Step 1: Attempt Cloud Storage Object Upload
        gcs_uploaded = False
        try:
            bucket = self.storage_client.bucket(self.bucket_name)
            blob = bucket.blob(object_path)
            blob.upload_from_string(file_bytes, content_type=content_type)
            gcs_uploaded = True
            logger.info("Successfully uploaded object '%s' to bucket '%s'", object_path, self.bucket_name)
        except Exception as err:
            metadata.document_status = DocumentStatus.STORAGE_FAILED
            logger.error("Cloud Storage upload failed for document '%s': %s", document_id, err)
            raise DocumentStorageError("upload_bytes", document_id, f"Cloud Storage upload failed: {err}") from err

        # Step 2: Persist Metadata to Firestore
        try:
            metadata.document_status = DocumentStatus.STORED
            self.repository.create(metadata)
            logger.info("Successfully persisted document metadata for '%s'", document_id)
            return metadata
        except Exception as err:
            # Handle Case B: GCS Upload succeeded but Firestore Metadata persistence failed
            logger.error(
                "Firestore metadata persistence failed for '%s' after GCS upload. Executing cleanup fallback: %s",
                document_id,
                err,
            )
            metadata.document_status = DocumentStatus.STORAGE_FAILED
            if gcs_uploaded:
                try:
                    bucket = self.storage_client.bucket(self.bucket_name)
                    blob = bucket.blob(object_path)
                    blob.delete()
                    logger.info("Cleaned up orphaned GCS object '%s' after metadata failure", object_path)
                except Exception as cleanup_err:
                    logger.error("Failed to cleanup orphaned GCS object '%s': %s", object_path, cleanup_err)

            raise DocumentStorageError(
                "persist_metadata",
                document_id,
                f"Firestore metadata persistence failed; GCS object was cleaned up: {err}",
            ) from err

    def get_document_metadata(self, document_id: str) -> DocumentMetadata:
        """Retrieve DocumentMetadata from Firestore repository."""
        return self.repository.get(document_id)

    def get_document_bytes(self, document_id: str) -> bytes:
        """Retrieve raw document payload bytes from Cloud Storage using metadata object path."""
        metadata = self.get_document_metadata(document_id)
        if metadata.document_status != DocumentStatus.STORED:
            raise DocumentStorageError(
                "download_bytes", document_id, f"Document status is '{metadata.document_status.value}', not STORED."
            )

        try:
            bucket = self.storage_client.bucket(metadata.storage_bucket)
            blob = bucket.blob(metadata.storage_object)
            file_bytes = blob.download_as_bytes()

            # Verify checksum integrity upon retrieval
            downloaded_checksum = calculate_checksum(file_bytes)
            if downloaded_checksum != metadata.checksum:
                raise DocumentStorageError(
                    "checksum_integrity",
                    document_id,
                    f"Checksum mismatch on download. Stored: {metadata.checksum}, Downloaded: {downloaded_checksum}",
                )

            return file_bytes
        except Exception as err:
            raise DocumentStorageError("download_bytes", document_id, str(err)) from err

    def delete_document(self, document_id: str) -> bool:
        """Perform controlled deletion of GCS storage artifact and Firestore metadata record."""
        metadata = self.get_document_metadata(document_id)

        # Step 1: Delete GCS Object if present
        try:
            bucket = self.storage_client.bucket(metadata.storage_bucket)
            blob = bucket.blob(metadata.storage_object)
            if blob.exists():
                blob.delete()
                logger.info("Deleted GCS object '%s'", metadata.storage_object)
        except Exception as err:
            logger.warning("Error deleting GCS object '%s': %s", metadata.storage_object, err)

        # Step 2: Update Metadata status to DELETED
        metadata.document_status = DocumentStatus.DELETED
        self.repository.update(metadata)
        logger.info("Updated document metadata for '%s' to DELETED", document_id)
        return True

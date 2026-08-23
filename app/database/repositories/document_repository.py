import logging
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from app.core.gcp import gcp_foundation
from app.models.document import DocumentMetadata, DocumentStatus

logger = logging.getLogger("papertrail.database.document_repository")


class DocumentNotFoundError(Exception):
    """Exception raised when a document metadata record is not found in Firestore."""

    def __init__(self, document_id: str):
        self.document_id = document_id
        super().__init__(f"Document metadata for ID '{document_id}' was not found in database.")


class DocumentAlreadyExistsError(Exception):
    """Exception raised when creating a document metadata record that already exists."""

    def __init__(self, document_id: str):
        self.document_id = document_id
        super().__init__(f"Document metadata for ID '{document_id}' already exists in database.")


class DocumentPersistenceError(Exception):
    """Exception raised when a Firestore document metadata operation fails."""

    def __init__(self, operation: str, document_id: str, message: str):
        self.operation = operation
        self.document_id = document_id
        super().__init__(f"Failed to {operation} document metadata '{document_id}': {message}")


def serialize_document_metadata(metadata: DocumentMetadata) -> Dict[str, Any]:
    """Serialize DocumentMetadata model into a Firestore-compatible dictionary."""
    return {
        "document_id": metadata.document_id,
        "filename": metadata.filename,
        "content_type": metadata.content_type,
        "size_bytes": metadata.size_bytes,
        "storage_bucket": metadata.storage_bucket,
        "storage_object": metadata.storage_object,
        "created_at": metadata.created_at.isoformat(),
        "updated_at": metadata.updated_at.isoformat(),
        "document_status": metadata.document_status.value,
        "checksum": metadata.checksum,
    }


def deserialize_document_metadata(data: Dict[str, Any]) -> DocumentMetadata:
    """Deserialize Firestore document dictionary into a DocumentMetadata model."""
    try:
        created_at_val = data["created_at"]
        if isinstance(created_at_val, str):
            created_at = datetime.fromisoformat(created_at_val)
        elif isinstance(created_at_val, datetime):
            created_at = created_at_val
        else:
            created_at = datetime.now(timezone.utc)

        updated_at_val = data["updated_at"]
        if isinstance(updated_at_val, str):
            updated_at = datetime.fromisoformat(updated_at_val)
        elif isinstance(updated_at_val, datetime):
            updated_at = updated_at_val
        else:
            updated_at = datetime.now(timezone.utc)

        return DocumentMetadata(
            document_id=data["document_id"],
            filename=data["filename"],
            content_type=data["content_type"],
            size_bytes=data["size_bytes"],
            storage_bucket=data["storage_bucket"],
            storage_object=data["storage_object"],
            created_at=created_at,
            updated_at=updated_at,
            document_status=DocumentStatus(data["document_status"]),
            checksum=data["checksum"],
        )
    except Exception as err:
        raise ValueError(f"Error deserializing document metadata payload: {err}") from err


class DocumentRepository:
    """Repository handling Firestore persistence for DocumentMetadata instances."""

    COLLECTION_NAME = "documents"

    def __init__(self, client: Optional[Any] = None):
        self._client = client

    @property
    def client(self) -> Any:
        """Lazily retrieve or return initialized Firestore client."""
        if self._client is None:
            self._client = gcp_foundation.get_firestore_client()
        if self._client is None:
            raise DocumentPersistenceError(
                "connect", "N/A", "Firestore client is unavailable in current environment."
            )
        return self._client

    def _get_doc_ref(self, document_id: str) -> Any:
        """Get Firestore document reference for a document_id."""
        return self.client.collection(self.COLLECTION_NAME).document(document_id)

    def create(self, metadata: DocumentMetadata) -> DocumentMetadata:
        """Persist a new DocumentMetadata instance to Firestore.

        Raises DocumentAlreadyExistsError if document already exists.
        """
        try:
            doc_ref = self._get_doc_ref(metadata.document_id)
            doc_snapshot = doc_ref.get()
            if doc_snapshot.exists:
                raise DocumentAlreadyExistsError(metadata.document_id)

            payload = serialize_document_metadata(metadata)
            doc_ref.set(payload)
            logger.info("Successfully created document metadata '%s'", metadata.document_id)
            return metadata
        except DocumentAlreadyExistsError:
            raise
        except Exception as err:
            raise DocumentPersistenceError("create", metadata.document_id, str(err)) from err

    def get(self, document_id: str) -> DocumentMetadata:
        """Retrieve DocumentMetadata instance from Firestore by document_id.

        Raises DocumentNotFoundError if document metadata does not exist.
        """
        try:
            doc_ref = self._get_doc_ref(document_id)
            doc_snapshot = doc_ref.get()
            if not doc_snapshot.exists:
                raise DocumentNotFoundError(document_id)

            data = doc_snapshot.to_dict()
            return deserialize_document_metadata(data)
        except DocumentNotFoundError:
            raise
        except Exception as err:
            raise DocumentPersistenceError("get", document_id, str(err)) from err

    def exists(self, document_id: str) -> bool:
        """Check whether a document metadata record exists in Firestore."""
        try:
            doc_ref = self._get_doc_ref(document_id)
            doc_snapshot = doc_ref.get()
            return doc_snapshot.exists
        except Exception as err:
            logger.warning("Error checking existence of document metadata '%s': %s", document_id, err)
            return False

    def update(self, metadata: DocumentMetadata) -> DocumentMetadata:
        """Update an existing DocumentMetadata instance in Firestore.

        Preserves original created_at timestamp in database payload.
        Raises DocumentNotFoundError if document metadata does not exist.
        """
        try:
            doc_ref = self._get_doc_ref(metadata.document_id)
            doc_snapshot = doc_ref.get()
            if not doc_snapshot.exists:
                raise DocumentNotFoundError(metadata.document_id)

            existing_data = doc_snapshot.to_dict()
            metadata.updated_at = datetime.now(timezone.utc)
            payload = serialize_document_metadata(metadata)

            if "created_at" in existing_data:
                payload["created_at"] = existing_data["created_at"]

            doc_ref.set(payload)
            logger.info("Successfully updated document metadata '%s'", metadata.document_id)
            return metadata
        except DocumentNotFoundError:
            raise
        except Exception as err:
            raise DocumentPersistenceError("update", metadata.document_id, str(err)) from err

    def delete(self, document_id: str) -> bool:
        """Delete a document metadata record from Firestore (for cleanup tasks)."""
        try:
            doc_ref = self._get_doc_ref(document_id)
            doc_snapshot = doc_ref.get()
            if not doc_snapshot.exists:
                return False

            doc_ref.delete()
            logger.info("Deleted document metadata '%s'", document_id)
            return True
        except Exception as err:
            raise DocumentPersistenceError("delete", document_id, str(err)) from err

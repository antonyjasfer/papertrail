from datetime import datetime
from enum import Enum
from pydantic import BaseModel, ConfigDict
from app.models.document import DocumentMetadata


class DocumentResponse(BaseModel):
    """API Response Schema for Document Metadata."""

    document_id: str
    filename: str
    content_type: str
    size_bytes: int
    created_at: datetime
    updated_at: datetime
    status: str
    checksum: str

    model_config = ConfigDict(from_attributes=True)

    @classmethod
    def from_metadata(cls, meta: DocumentMetadata) -> "DocumentResponse":
        """Convert a DocumentMetadata domain model instance into an API DocumentResponse schema."""
        status_str = (
            meta.document_status.value
            if isinstance(meta.document_status, Enum)
            else str(meta.document_status)
        )
        return cls(
            document_id=meta.document_id,
            filename=meta.filename,
            content_type=meta.content_type,
            size_bytes=meta.size_bytes,
            created_at=meta.created_at,
            updated_at=meta.updated_at,
            status=status_str,
            checksum=meta.checksum,
        )


class DocumentDeleteResponse(BaseModel):
    """API Response Schema for Document Deletion Operations."""

    document_id: str
    status: str
    artifact_deleted: bool
    metadata_retained: bool

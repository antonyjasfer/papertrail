from datetime import datetime, timezone
from enum import Enum
from typing import Optional
from pydantic import BaseModel, Field


class DocumentStatus(str, Enum):
    """PaperTrail AI Document Lifecycle Statuses."""

    UPLOADING = "UPLOADING"
    STORED = "STORED"
    DELETED = "DELETED"
    STORAGE_FAILED = "STORAGE_FAILED"


class DocumentMetadata(BaseModel):
    """Document Metadata model tracking storage artifacts and SHA-256 checksums."""

    document_id: str
    filename: str
    content_type: str
    size_bytes: int
    storage_bucket: str
    storage_object: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    document_status: DocumentStatus = DocumentStatus.UPLOADING
    checksum: str  # SHA-256 hex string fingerprint of document bytes

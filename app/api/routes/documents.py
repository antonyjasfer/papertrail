from fastapi import APIRouter, Depends, File, Response, UploadFile, status
from app.api.dependencies import get_document_storage_service
from app.schemas.document import DocumentDeleteResponse, DocumentResponse
from app.services.document_storage import DocumentStorageService, DocumentValidationError

router = APIRouter(prefix="/documents", tags=["Documents"])


@router.post("", response_model=DocumentResponse, status_code=status.HTTP_201_CREATED)
async def upload_document(
    file: UploadFile = File(...),
    storage_service: DocumentStorageService = Depends(get_document_storage_service),
):
    """Upload a document binary file via multipart request.

    Stores document artifact in Cloud Storage and metadata in Firestore.
    """
    if not file or not file.filename:
        raise DocumentValidationError("Upload file payload or filename is missing.")

    file_bytes = await file.read()
    content_type = file.content_type or "application/octet-stream"

    metadata = storage_service.store_document(
        filename=file.filename,
        content_type=content_type,
        file_bytes=file_bytes,
    )
    return DocumentResponse.from_metadata(metadata)


@router.get("/{document_id}", response_model=DocumentResponse)
def get_document_metadata(
    document_id: str,
    storage_service: DocumentStorageService = Depends(get_document_storage_service),
):
    """Retrieve metadata for a stored document by document_id."""
    metadata = storage_service.get_document_metadata(document_id)
    return DocumentResponse.from_metadata(metadata)


@router.get("/{document_id}/download")
def download_document(
    document_id: str,
    storage_service: DocumentStorageService = Depends(get_document_storage_service),
):
    """Securely download raw document payload bytes from Cloud Storage."""
    metadata = storage_service.get_document_metadata(document_id)
    file_bytes = storage_service.get_document_bytes(document_id)

    headers = {
        "Content-Disposition": f'attachment; filename="{metadata.filename}"',
    }
    return Response(
        content=file_bytes,
        media_type=metadata.content_type,
        headers=headers,
    )


@router.delete("/{document_id}", response_model=DocumentDeleteResponse)
def delete_document(
    document_id: str,
    storage_service: DocumentStorageService = Depends(get_document_storage_service),
):
    """Perform controlled deletion of document GCS artifact while retaining metadata record with status DELETED."""
    storage_service.delete_document(document_id)
    return DocumentDeleteResponse(
        document_id=document_id,
        status="DELETED",
        artifact_deleted=True,
        metadata_retained=True,
    )

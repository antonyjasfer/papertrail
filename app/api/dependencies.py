from app.services.document_storage import DocumentStorageService


def get_document_storage_service() -> DocumentStorageService:
    """Dependency provider returning an initialized instance of DocumentStorageService."""
    return DocumentStorageService()

from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse
from app.api.routes import documents, health, orchestration
from app.core.config import settings
from app.database.repositories.document_repository import (
    DocumentAlreadyExistsError,
    DocumentNotFoundError,
)
from app.services.document_storage import DocumentStorageError, DocumentValidationError

app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    description="Autonomous Document Intelligence, Forensic Fraud Detection, Compliance Risk & Cryptographic Audit Platform",
)

# Register Routers
app.include_router(health.router)
app.include_router(documents.router)
app.include_router(orchestration.router)



# Global Exception Handlers
@app.exception_handler(DocumentNotFoundError)
async def document_not_found_exception_handler(request: Request, exc: DocumentNotFoundError):
    return JSONResponse(
        status_code=status.HTTP_404_NOT_FOUND,
        content={"detail": f"Document with ID '{exc.document_id}' was not found."},
    )


@app.exception_handler(DocumentAlreadyExistsError)
async def document_already_exists_exception_handler(request: Request, exc: DocumentAlreadyExistsError):
    return JSONResponse(
        status_code=status.HTTP_409_CONFLICT,
        content={"detail": f"Document with ID '{exc.document_id}' already exists."},
    )


@app.exception_handler(DocumentValidationError)
async def document_validation_exception_handler(request: Request, exc: DocumentValidationError):
    return JSONResponse(
        status_code=status.HTTP_400_BAD_REQUEST,
        content={"detail": str(exc)},
    )


@app.exception_handler(DocumentStorageError)
async def document_storage_exception_handler(request: Request, exc: DocumentStorageError):
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={"detail": "Document storage operation failed."},
    )

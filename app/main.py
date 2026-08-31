import logging
from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.middleware import ObservabilityMiddleware
from app.api.routes import documents, health, orchestration
from app.core.config import settings
from app.core.errors import ErrorCategory, classify_error
from app.core.logging import get_current_correlation, setup_structured_logging
from app.database.repositories.document_repository import (
    DocumentAlreadyExistsError,
    DocumentNotFoundError,
)
from app.services.document_storage import DocumentStorageError, DocumentValidationError

# Initialize machine-readable structured logging
setup_structured_logging(level=settings.log_level)
logger = logging.getLogger("papertrail.app")

app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    description="Autonomous Document Intelligence, Forensic Fraud Detection, Compliance Risk & Cryptographic Audit Platform",
)

# Attach Observability Middleware
app.add_middleware(ObservabilityMiddleware)

# Attach secure CORS Middleware (explicit origins only, no wildcard)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register Routers
app.include_router(health.router)
app.include_router(documents.router)
app.include_router(orchestration.router)


def _format_error_response(status_code: int, detail: str, category: ErrorCategory) -> JSONResponse:
    ctx = get_current_correlation()
    content = {
        "detail": detail,
        "error_category": category.value,
        "correlation_id": ctx.get("correlation_id"),
        "request_id": ctx.get("request_id"),
    }
    return JSONResponse(status_code=status_code, content=content)


# Global Exception Handlers
@app.exception_handler(DocumentNotFoundError)
async def document_not_found_exception_handler(request: Request, exc: DocumentNotFoundError):
    return _format_error_response(
        status_code=status.HTTP_404_NOT_FOUND,
        detail=f"Document with ID '{exc.document_id}' was not found.",
        category=ErrorCategory.VALIDATION_ERROR,
    )


@app.exception_handler(DocumentAlreadyExistsError)
async def document_already_exists_exception_handler(request: Request, exc: DocumentAlreadyExistsError):
    return _format_error_response(
        status_code=status.HTTP_409_CONFLICT,
        detail=f"Document with ID '{exc.document_id}' already exists.",
        category=ErrorCategory.IDEMPOTENCY_DUPLICATE,
    )


@app.exception_handler(DocumentValidationError)
async def document_validation_exception_handler(request: Request, exc: DocumentValidationError):
    return _format_error_response(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail=str(exc),
        category=ErrorCategory.VALIDATION_ERROR,
    )


@app.exception_handler(DocumentStorageError)
async def document_storage_exception_handler(request: Request, exc: DocumentStorageError):
    return _format_error_response(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        detail="Document storage operation failed.",
        category=ErrorCategory.BLOB_STORAGE_ERROR,
    )

# Phase 6 — FastAPI Gateway Architecture & Specification

## 1. Overview & Architecture

The **FastAPI Gateway Layer** serves as the primary HTTP API boundary for **PaperTrail AI**. It connects external HTTP clients to the underlying `DocumentStorageService` and `DocumentRepository` without mixing API routing logic with analysis workflows or storage persistence.

```text
HTTP Client
      │
      ▼
FastAPI Gateway (app/main.py & app/api/routes)
      │
      ▼
Request Validation & Schemas (app/schemas/document.py)
      │
      ▼
Dependency Injection (app/api/dependencies.py)
      │
      ▼
DocumentStorageService (app/services/document_storage.py)
      │                                    │
      ▼                                    ▼
Cloud Storage Payload                Firestore Metadata
(gcs_bucket_documents)              (documents/{document_id})
```

---

## 2. Endpoint Specifications

### Health Endpoint
- **`GET /health`**
  - **Description**: Public health check endpoint verifying application version and phase.
  - **Response (200 OK)**:
    ```json
    {
      "status": "ok",
      "service": "PaperTrail AI",
      "version": "0.1.0",
      "phase": "Phase 6 - FastAPI Gateway"
    }
    ```

### Document Endpoints
- **`POST /documents`**
  - **Description**: Upload raw document file payload (multipart/form-data).
  - **Request**: Multipart form containing `file` binary payload.
  - **Response (201 Created)**: `DocumentResponse`

- **`GET /documents/{document_id}`**
  - **Description**: Retrieve structured metadata record for a document.
  - **Response (200 OK)**: `DocumentResponse`

- **`GET /documents/{document_id}/download`**
  - **Description**: Securely download raw document payload bytes from Cloud Storage.
  - **Response (200 OK)**: Binary byte stream with `Content-Type` matching original MIME type and `Content-Disposition: attachment; filename="..."`.

- **`DELETE /documents/{document_id}`**
  - **Description**: Controlled document deletion. Deletes Cloud Storage object artifact while preserving Firestore metadata with status `DELETED`.
  - **Response (200 OK)**: `DocumentDeleteResponse`

---

## 3. Request & Response Schemas

### `DocumentResponse`
```json
{
  "document_id": "doc-a1b2c3d4e5f6",
  "filename": "invoice.pdf",
  "content_type": "application/pdf",
  "size_bytes": 125430,
  "created_at": "2026-08-16T20:00:00.000000+00:00",
  "updated_at": "2026-08-16T20:00:00.000000+00:00",
  "status": "STORED",
  "checksum": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
}
```

### `DocumentDeleteResponse`
```json
{
  "document_id": "doc-a1b2c3d4e5f6",
  "status": "DELETED",
  "artifact_deleted": true,
  "metadata_retained": true
}
```

---

## 4. Error Mapping Policy

PaperTrail AI handles exceptions using global FastAPI exception handlers to prevent exposing internal tracebacks, module structures, or credentials:

| Domain Exception | HTTP Status Code | Response Body Example |
| :--- | :--- | :--- |
| `DocumentNotFoundError` | `404 Not Found` | `{"detail": "Document with ID '...' was not found."}` |
| `DocumentAlreadyExistsError` | `409 Conflict` | `{"detail": "Document with ID '...' already exists."}` |
| `DocumentValidationError` | `400 Bad Request` | `{"detail": "Document validation error: File size exceeds maximum limit."}` |
| `DocumentStorageError` | `500 Internal Server Error` | `{"detail": "Document storage operation failed."}` |
| `Malformed Request` | `422 Unprocessable` | Standard FastAPI validation payload |

---

## 5. Dependency Injection

FastAPI dependency injection (`app/api/dependencies.py`) provides decoupled resolution:

```python
def get_document_storage_service() -> DocumentStorageService:
    return DocumentStorageService()
```

Routes inject services via `Depends(get_document_storage_service)`. Unit tests cleanly override dependencies without patching global clients:

```python
app.dependency_overrides[get_document_storage_service] = lambda: mock_storage_service
```

---

## 6. Security Governance

1. **Untrusted Upload Sanitization**: Filenames are sanitized via regex stripping directory traversal sequences (`../`, `..\`) and dangerous characters.
2. **Access Control & Privacy**: Buckets remain private. Signed or streamed byte delivery prevents public GCS URL exposure.
3. **Information Disclosure Prevention**: Internal GCS paths, service account keys, and database connections are excluded from response schemas.
4. **Validation Enforcement**: Content-type filtering and max size limits are strictly enforced.

---

## 7. OpenAPI Documentation

FastAPI automatically generates interactive OpenAPI documentation accessible at:
- Swagger UI: `/docs`
- OpenAPI JSON: `/openapi.json`

---

## 8. Testing Strategy

### Unit Tests (`tests/unit/test_documents_api.py`)
12 mock-based test cases validating endpoints, HTTP error mappings, request validations, downloads, and deletion behavior offline without GCP credentials.

### Integration Tests (`tests/integration/test_documents_api_integration.py`)
Conditional live roundtrip test (`GCP_INTEGRATION=1`) validating live GCS upload, Firestore metadata lookup, byte retrieval integrity, checksum matching, and artifact deletion lifecycle.

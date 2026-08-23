# PaperTrail AI — Document Storage Layer Documentation

## 1. Overview

The **Document Storage Layer** (`app/services/document_storage.py` and `app/database/repositories/document_repository.py`) provides secure, decoupled artifact storage and structured metadata tracking for PaperTrail AI.

Actual binary files are stored in private **Google Cloud Storage (GCS)** buckets, while structured metadata records, cryptographic SHA-256 fingerprints, and storage object paths are persisted in **Google Cloud Firestore** under `/documents/{document_id}`.

---

## 2. Decoupled Architecture

```text
User / Application Upload
           │
           ▼
DocumentStorageService ── (1. Validate Size, MIME Type & Filename)
           │
           ├────────────► 2. Cloud Storage Bucket (papertrail-ai-documents-dev)
           │                 Path: documents/{document_id}/original/{sanitized_filename}
           │
           └────────────► 3. DocumentRepository (Firestore)
                             Collection: /documents/{document_id}
```

### Architectural Separation
- **Cloud Storage**: Holds raw binary file artifacts (`application/pdf`, `image/png`, `image/jpeg`, `text/plain`).
- **Firestore Repository**: Holds document metadata models (`DocumentMetadata`).
- **Core State Machine**: Maintains workflow analysis states (`WorkflowState`), decoupled from binary storage lifecycles.

---

## 3. Data Models (`app/models/document.py`)

### `DocumentStatus` Enum
Defines document storage lifecycles (distinct from workflow analysis states):
- `UPLOADING`: Document binary is being uploaded to Cloud Storage.
- `STORED`: Document binary is safely stored in Cloud Storage and metadata is committed to Firestore.
- `DELETED`: Document has been deleted from Cloud Storage and metadata is marked as deleted.
- `STORAGE_FAILED`: Upload or metadata persistence encountered an explicit failure.

### `DocumentMetadata` Model
```python
class DocumentMetadata(BaseModel):
    document_id: str
    filename: str
    content_type: str
    size_bytes: int
    storage_bucket: str
    storage_object: str
    created_at: datetime
    updated_at: datetime
    document_status: DocumentStatus
    checksum: str  # SHA-256 hex string fingerprint
```

---

## 4. Firestore Metadata Schema

- **Collection Path**: `/documents`
- **Document Path**: `/documents/{document_id}`

### Sample Document Payload
```json
{
  "document_id": "doc-8841-b992",
  "filename": "invoice_2026.pdf",
  "content_type": "application/pdf",
  "size_bytes": 125430,
  "storage_bucket": "papertrail-ai-documents-dev",
  "storage_object": "documents/doc-8841-b992/original/invoice_2026.pdf",
  "created_at": "2026-08-16T18:00:00.000000+00:00",
  "updated_at": "2026-08-16T18:00:00.000000+00:00",
  "document_status": "STORED",
  "checksum": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
}
```

---

## 5. Cloud Storage Object Layout

- **Bucket**: Configured via `settings.gcs_bucket_documents` (`papertrail-ai-documents-dev`).
- **Object Path Convention**:
  ```text
  documents/{document_id}/original/{sanitized_filename}
  ```
- **Example**: `documents/doc-8841-b992/original/invoice_2026.pdf`

---

## 6. SHA-256 Cryptographic Checksum

Every stored document artifact is fingerprinted using **SHA-256**:
- **Purpose**: Creates a reproducible, cryptographic fingerprint of raw byte payloads.
- **Verification**: On retrieval (`get_document_bytes()`), the downloaded payload's SHA-256 is re-calculated and verified against the stored metadata fingerprint.
- **Scope Note**: SHA-256 proves payload match with the recorded fingerprint; full document authenticity and provenance validation are performed in downstream analysis phases.

---

## 7. Input Validation & Filename Safety

1. **Filename Sanitization**:
   - Strips path traversal markers (`../`, `..\`, `/`, `\`).
   - Prevents arbitrary directory injection (`../../etc/passwd` -> `passwd`).
   - Retains safe alphanumeric, dot, dash, and underscore characters.
2. **Supported MIME Types**:
   - `application/pdf`
   - `image/png`
   - `image/jpeg`
   - `text/plain`
   - Raises `DocumentValidationError` for unsupported content types.
3. **File Size Limits**:
   - Enforces configurable maximum size limit (`settings.max_file_size_bytes`, default 25MB).
   - Raises `DocumentValidationError` if byte payload exceeds the configured limit.

---

## 8. Failure Atomicity & Partial-Failure Handling

To avoid partial-failure states where Firestore reports `STORED` while Cloud Storage upload failed (or vice versa):
1. **Cloud Storage Failure**: If GCS upload fails, metadata status is set to `STORAGE_FAILED`, no false `STORED` record is created, and `DocumentStorageError` is raised.
2. **Firestore Metadata Failure**: If GCS upload succeeds but Firestore metadata persistence fails, the orphaned GCS object is deleted immediately during rollback cleanup, metadata status is set to `STORAGE_FAILED`, and `DocumentStorageError` is raised.

---

## 9. Access & Retrieval Security

- **Private Buckets**: Cloud Storage buckets remain private with zero public object access.
- **Authenticated Retrieval**: Backend service (`get_document_bytes()`) retrieves raw bytes on behalf of authenticated backend requests.
- **Integrity Validation**: Downloaded byte payloads undergo SHA-256 verification before being returned.

---

## 10. Controlled Deletion

- Executed via `delete_document(document_id)`.
- Deletes the GCS object `documents/{document_id}/original/{filename}` if present.
- Updates Firestore document metadata status to `DELETED`.

---

## 11. Test Modes

- **Unit Tests (`pytest -q`)**: Run 100% offline using in-memory mock Firestore and GCS clients.
- **Cloud Integration Tests (`GCP_INTEGRATION=1 pytest -q`)**: Uploads test bytes to live Cloud Storage, creates Firestore metadata, verifies SHA-256 fingerprinting, and cleans up completely.

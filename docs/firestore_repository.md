# PaperTrail AI — Firestore Repository Specification

This document defines the **Firestore Persistence Layer** (`app/database/repositories/workflow_repository.py`) for **PaperTrail AI**, prepared for the **All Things Agentic Hackathon 2026**.

---

## 1. Architecture Overview & Decoupling

```text
               Core Architecture Layering
┌─────────────────────────────────────────────────────────┐
│ AnalysisWorkflow Model (Pydantic Data Model)           │
│ app/core/state.py                                       │
└───────────────────────────┬─────────────────────────────┘
                            │ Delegates Validation
                            ▼
┌─────────────────────────────────────────────────────────┐
│ WorkflowState Machine (Deterministic Lifecycle Rules)   │
│ app/core/state.py                                       │
└───────────────────────────┬─────────────────────────────┘
                            │ Validated Model Update
                            ▼
┌─────────────────────────────────────────────────────────┐
│ WorkflowRepository (CRUD & Persistence Layer)           │
│ app/database/repositories/workflow_repository.py       │
└───────────────────────────┬─────────────────────────────┘
                            │ Reads / Writes Payload
                            ▼
┌─────────────────────────────────────────────────────────┐
│ Google Cloud Firestore Database                         │
│ Document Path: /workflows/{workflow_id}                 │
└─────────────────────────────────────────────────────────┘
```

---

## 2. Key Architectural Principles

1. **State Machine remains Authority**: `WorkflowRepository` persists `AnalysisWorkflow` state objects but does NOT define or evaluate state transition rules. All transitions are validated by `AnalysisWorkflow.transition_to()`.
2. **Immutability of `created_at`**: During updates, original `created_at` timestamps are preserved in Firestore payloads.
3. **Timestamp Refresh on Update**: `updated_at` timestamps are refreshed upon valid state transitions and persisted to Firestore. Invalid transitions fail before reaching the repository layer.
4. **Explicit Operations**:
   - `create()`: Persists a new workflow document. Raises `WorkflowAlreadyExistsError` if document exists.
   - `get()`: Fetches document by ID. Raises `WorkflowNotFoundError` if document is missing.
   - `update()`: Updates an existing workflow document. Raises `WorkflowNotFoundError` if document is missing.
   - `save()`: Utility method that executes `update()` if document exists or `create()` if missing.
   - `delete()`: Deletes a document for administrative or integration test cleanup.
5. **Deletion Policy**: Document deletion is reserved strictly for test cleanup or explicit administrative operations. Production business processes MUST NOT delete workflow documents to maintain a complete cryptographic audit trail.

---

## 3. Firestore Collection Schema

- **Collection Path**: `/workflows`
- **Document ID**: `{workflow_id}`
- **Sample Document Payload**:
```json
{
  "workflow_id": "wf-1042-8aef",
  "document_id": "doc-8841-b992",
  "current_state": "FORENSIC_ANALYSIS",
  "created_at": "2026-08-16T18:00:00.000000+00:00",
  "updated_at": "2026-08-16T18:05:00.000000+00:00",
  "failure_reason": null,
  "escalation_reason": null,
  "review_reason": null
}
```

---

## 4. Serialization & Deserialization

- `WorkflowState` Enum values are stored as standard strings (e.g. `"FORENSIC_ANALYSIS"`).
- `created_at` and `updated_at` datetimes are stored as ISO 8601 strings (e.g. `"2026-08-16T18:00:00+00:00"`).
- Python object pickling is strictly forbidden.

---

## 5. Repository Exceptions

- `WorkflowNotFoundError`: Raised when attempting to fetch or update a non-existent document.
- `WorkflowAlreadyExistsError`: Raised when attempting to create a document with a duplicate ID.
- `WorkflowPersistenceError`: Raised when Firestore client operations fail.

---

## 6. Testing Strategy

- **Unit Tests (`tests/unit/test_workflow_repository.py`)**: Uses an in-memory mock Firestore client dictionary (`MockFirestoreClient`). Runs fast and offline without requiring GCP network access.
- **Integration Tests (`tests/integration/test_firestore_integration.py`)**: Uses real Firestore client via `gcp_foundation.get_firestore_client()`. Automatically skips when live GCP credentials are not supplied.

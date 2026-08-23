# PaperTrail AI

**PaperTrail AI** is an enterprise-grade Autonomous Document Intelligence, Forensic Fraud Detection, Compliance Risk Evaluation, Cryptographic Provenance, and Deterministic Audit Report Generation Platform built for the **All Things Agentic Hackathon 2026**.

---

## Current Status: Phase 12 — Deterministic Audit Report Generation Layer (VERIFIED)

- **Phase 1 (Project Scaffold)**: Complete & Verified.
- **Phase 2 (Dependencies & GCP Foundation)**: Complete & Verified.
- **Phase 3 (Core State Machine)**: Complete & Verified.
- **Phase 4 (Firestore Repository)**: Complete & Verified.
- **Phase 5 (Document Storage Layer)**: Complete & Verified.
- **Phase 6 (FastAPI Gateway)**: Complete & Verified.
- **Phase 7 (Document Intelligence Agent)**: Complete & Verified.
- **Phase 8 (Deterministic Forensic Engine)**: Complete & Verified.
- **Phase 9 (Deterministic Compliance Engine)**: Complete & Verified.
- **Phase 10 (Deterministic Risk Assessment Engine)**: Complete & Verified.
- **Phase 11 (Cryptographic Audit & Provenance Layer)**: Complete & Verified.
- **Phase 12 (Deterministic Audit Report Generation Layer)**: Complete & Verified.

---

## System Architecture

PaperTrail AI is architected cleanly into modular, decoupled layers:

```text
HTTP Client
      │
      ▼
FastAPI Gateway (Phase 6)
      │
      ▼
Document Storage Service (Phase 5)
   │                       │
   ▼                       ▼
Cloud Storage          Document Repository (Phase 5)
(Raw Artifacts)            │
                           ▼
                       Firestore (/documents/{document_id})
                           │
                           ▼
             Document Intelligence Service (Phase 7)
                           │
                           ▼
             Document Intelligence Agent (Phase 7)
                           │
                           ▼
                   Gemini 3.5 Flash (Factual Extraction)
                           │
                           ▼
             Deterministic Python Validation (Phase 7)
                           │
                           ▼
             Deterministic Forensic Engine (Phase 8)
                           │
                           ▼
             Evidence-Backed Forensic Findings (Phase 8)
                           │
                           ▼
             Deterministic Compliance Engine (Phase 9)
                           │
                           ▼
             Evidence-Backed Compliance Findings (Phase 9)
                           │
                           ▼
             Deterministic Risk Assessment Engine (Phase 10)
                           │
                           ▼
             Auditable Multi-Dimensional Decimal Risk Assessment (Phase 10)
                           │
                           ▼
             Cryptographic Audit & Provenance Layer (Phase 11)
                           │
                           ▼
             Immutable SHA-256 Prev-Hash Audit Chain & Evidence Bundle (Phase 11)
                           │
                           ▼
             Deterministic Audit Report Generation Layer (Phase 12)
                           │
                           ▼
             Canonical Report JSON (content_hash) & Human-Readable PDF (artifact_hash) (Phase 12)
```

### Key Architectural Principles
1. **Deterministic State Machine**: Lifecycle transitions (`app/core/state.py`) are strictly governed by Python domain logic.
2. **Decoupled Persistence**: `WorkflowRepository` persists state to Firestore `/workflows/{workflow_id}`.
3. **Artifact & Metadata Storage**: `DocumentStorageService` stores raw file payloads in Google Cloud Storage (`documents/{document_id}/original/{sanitized_filename}`) and structured metadata in Firestore (`/documents/{document_id}`).
4. **Cryptographic Checksum**: Every document is fingerprinted using SHA-256 for cryptographic provenance tracking.
5. **RESTful FastAPI Gateway**: Clean, validated endpoints (`POST /documents`, `GET /documents/{id}`, `GET /documents/{id}/download`, `DELETE /documents/{id}`, `GET /health`) with global exception mapping and OpenAPI schema generation.
6. **Document Intelligence Agent**: Powered by Gemini 3.5 Flash via `google-genai` SDK for multimodal understanding, classification, precise string monetary decimal extractions, prompt injection defense, and deterministic Python `AnalysisStatus` calculation.
7. **Deterministic Forensic Engine**: 100% Python deterministic rule validation (`Decimal` financial arithmetic, ISO date checks, structural verification, duplicate detection) producing reproducible, evidence-backed `ForensicFinding` records with zero LLM/database coupling.
8. **Deterministic Compliance Engine**: 100% Python deterministic policy evaluation against versioned organizational policies, controls, and rules producing evidence-backed `ComplianceFinding` records with explicit clock isolation (`ComplianceContext.reference_datetime`) and zero LLM/database/state-machine coupling.
9. **Deterministic Risk Assessment Engine**: 100% Python multi-dimensional risk evaluation using exact `Decimal` arithmetic, dynamic weight reweighting for missing evidence, evidence lineage deduplication (`RiskAggregationPolicy`), strict clock isolation (`RiskContext.reference_datetime`), and reproducible calculation audit traces with zero LLM/database/state-machine coupling.
10. **Cryptographic Audit & Provenance Layer**: Immutable, append-only SHA-256 hash chaining of canonical payload digests, microsecond UTC ISO-8601 formatting, sequence completeness verification, declared engine provenance metadata, and evidence bundle sealing with zero LLM/state-machine mutation coupling.
11. **Deterministic Audit Report Generation Layer**: Presentation-only report synthesis generating canonical machine-readable JSON (`content_hash`) and in-memory ReportLab PDF (`artifact_hash`) with single-source clock isolation (`ReportContext.reference_datetime`), path-traversal-safe identifier validation (`validate_identifier`), and zero LLM/state-machine mutation coupling.

---

## Technical Documentation

- [GCP Foundation Architecture](file:///c:/Users/anton/OneDrive/Desktop/papertrail/papertrail/docs/gcp_foundation.md)
- [Core State Machine Specification](file:///c:/Users/anton/OneDrive/Desktop/papertrail/papertrail/docs/state_machine.md)
- [Firestore Workflow Repository Documentation](file:///c:/Users/anton/OneDrive/Desktop/papertrail/papertrail/docs/firestore_repository.md)
- [Document Storage Layer Documentation](file:///c:/Users/anton/OneDrive/Desktop/papertrail/papertrail/docs/document_storage.md)
- [FastAPI Gateway Documentation](file:///c:/Users/anton/OneDrive/Desktop/papertrail/papertrail/docs/fastapi_gateway.md)
- [Document Intelligence Agent Documentation](file:///c:/Users/anton/OneDrive/Desktop/papertrail/papertrail/docs/document_intelligence_agent.md)
- [Deterministic Forensic Engine Documentation](file:///c:/Users/anton/OneDrive/Desktop/papertrail/papertrail/docs/forensic_engine.md)
- [Deterministic Compliance Engine Documentation](file:///c:/Users/anton/OneDrive/Desktop/papertrail/papertrail/docs/compliance_engine.md)
- [Deterministic Risk Assessment Engine Documentation](file:///c:/Users/anton/OneDrive/Desktop/papertrail/papertrail/docs/risk_engine.md)
- [Cryptographic Audit & Provenance Documentation](file:///c:/Users/anton/OneDrive/Desktop/papertrail/papertrail/docs/audit_provenance.md)
- [Deterministic Audit Report Generation Documentation](file:///c:/Users/anton/OneDrive/Desktop/papertrail/papertrail/docs/report_generation.md)

---

## Running Verification Tests

Run the offline unit test suite (no GCP credentials required):

```bash
.\venv\Scripts\pytest -q
```

To run live Google Cloud integration tests (requires GCP credentials & environment setup):

```bash
set GCP_INTEGRATION=1
.\venv\Scripts\pytest -q
```

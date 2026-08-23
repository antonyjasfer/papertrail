# Phase 12 — Deterministic Audit Report Generation Layer

## Overview

**Phase 12 (Deterministic Audit Report Generation Layer)** transforms verified outputs from Phase 7 (Document Intelligence), Phase 8 (Deterministic Forensic Engine), Phase 9 (Deterministic Compliance Engine), Phase 10 (Deterministic Risk Engine), and Phase 11 (Cryptographic Audit & Provenance Layer) into structured, reproducible, evidence-backed audit reports.

Phase 12 is a **pure-computation, presentation-only module**. It produces two canonical artifacts:
1. **Canonical Report JSON**: Authoritative machine-readable JSON serialized via Phase 11 canonicalization rules with a deterministic `content_hash` (SHA-256).
2. **PDF Report Artifact**: Human-readable PDF rendered via ReportLab with an `artifact_hash` (SHA-256).

---

## Architectural Principles

1. **Clock Isolation & Single Time Source**: `ReportContext.reference_datetime` is the sole timestamp anchor. All report timestamp representations (`generated_at`, `generated_at_label`) derive exclusively from `reference_datetime`. The system clock (`datetime.now()`) is never accessed.
2. **Identifier Safety & Validation**: `document_id` and `workflow_id` are validated against project rules (`validate_identifier()`) before constructing `report_id` (`rpt-{document_id}-{workflow_id}`) or `filename` (`papertrail-report-{document_id}.pdf`). Identifiers containing path traversal sequences (`/`, `\`, `..`) or control characters are strictly rejected with `ReportIntegrityError`.
3. **Presentation-Only Boundary**: Phase 12 does not execute forensic rules, compliance checks, risk scoring, or audit verification. It consumes pre-computed immutable inputs.
4. **Zero State Machine Mutations**: Phase 12 does not call `workflow.transition_to()` or mutate state. It returns a `ReportGenerationResult` envelope in memory.
5. **Dual-Hash Architecture**:
   - `content_hash`: SHA-256 of Canonical Report JSON bytes. Guaranteed 100% deterministic given identical inputs and context.
   - `artifact_hash`: SHA-256 of rendered PDF bytes. Tracks specific PDF output.
6. **Network & AI Isolation**: 100% offline Python execution. Zero calls to Gemini, Firestore, Cloud Storage, or external network APIs.

---

## Package Architecture (`app/reports/`)

```text
app/reports/
├── __init__.py          # Public API exports
├── models.py            # ReportType, ReportStatus, ReportContext, ReportViewModel,
│                        #   ReportGenerationResult, ReportArtifact, ReportProvenance,
│                        #   DocumentSummary, ExtractionSummary, ForensicSummary,
│                        #   ComplianceSummary, RiskSummary, AuditIntegritySummary
├── constants.py         # REPORT_SCHEMA_VERSION, REPORT_TEMPLATE_VERSION,
│                        #   SCOPE_STATEMENT, LEGAL_DISCLAIMER
├── validators.py        # validate_identifier() path traversal & safety check
├── builder.py           # ReportBuilder constructing ReportViewModel
├── generator.py         # ReportGenerator orchestrating ViewModel -> JSON -> PDF -> Result
├── pdf.py               # ReportLab PDF renderer (in-memory io.BytesIO)
├── hashing.py           # build_canonical_report_json(), compute_content_hash(), compute_artifact_hash()
└── errors.py            # ReportError, ReportGenerationError, UnsupportedTemplateVersion, ReportIntegrityError
```

---

## Data Flow & Generation Pipeline

```text
Phase 5-11 Domain Outputs + ReportContext
            │
            ▼
  validate_identifier(doc_id, wf_id)
            │
            ▼
   ReportBuilder.build_view_model()
            │
            ▼
      ReportViewModel
      ┌─────┴────────────────────────┐
      ▼                              ▼
build_canonical_report_json()    render_pdf(view_model)
      │                              │
      ▼                              ▼
Canonical JSON bytes             PDF bytes
      │                              │
      ▼                              ▼
compute_content_hash()         compute_artifact_hash()
      │                              │
      └──────────────┬───────────────┘
                     ▼
          ReportGenerationResult
```

---

## Audit Verification & Report Status

- **`VERIFIED` Status**: Assigned when `VerificationResult.status == VerificationStatus.VALID`. PDF displays a green verification banner.
- **`UNVERIFIED` Status**: Assigned when `VerificationResult.status == VerificationStatus.INVALID`. PDF displays a red warning banner ("CAUTION: Audit chain verification failed"). Report generation is not blocked, preserving visibility into flawed chains.

---

## Testing Strategy

Phase 12 features a 100% offline unit test suite across 5 modules:
- `tests/unit/test_report_builder.py`: Tests ViewModel construction, timestamp binding, and section mapping.
- `tests/unit/test_report_hashing.py`: Tests canonical JSON determinism and dual hash computation.
- `tests/unit/test_report_pdf.py`: Tests ReportLab PDF rendering, page structure, and `%PDF-` byte header.
- `tests/unit/test_report_generator.py`: Tests end-to-end report generation, `VERIFIED`/`UNVERIFIED` status, and template validation.
- `tests/unit/test_report_security.py`: Tests path traversal rejection, identifier safety, zero Gemini imports, and zero state machine mutations.
- `tests/fixtures/reports/`: 8 golden JSON fixture files.

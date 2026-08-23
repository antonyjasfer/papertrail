# Phase 11 — Cryptographic Audit & Provenance Layer Architecture & Specification

## 1. Executive Summary & Core Principle

The **Cryptographic Audit & Provenance Layer** provides PaperTrail AI with a deterministic, verifiable proof layer for document analysis lifecycles. Operating with **zero LLM/Gemini dependencies**, the audit layer captures immutable cryptographic records (`AuditEvent`) for every analysis phase from document registration to risk assessment, linking events into a SHA-256 hash chain and sealing the workflow with an auditable `AnalysisEvidenceBundle`.

### Core Principle
> **The Audit Layer does not execute business logic, alter risk scores, or trigger workflow state mutations. It records canonical payload digests, builds prev-hash linked audit chains, and provides deterministic verification against tampering, sequence reordering, or missing events.**

---

## 2. Architecture & Data Flow

```text
Document Registration (Phase 5) ────► AuditEvent (DOCUMENT_REGISTERED) [Genesis]
                                               │
Document Intelligence (Phase 7) ────► AuditEvent (EXTRACTION_COMPLETED)
                                               │
Forensic Engine (Phase 8)       ────► AuditEvent (FORENSIC_ANALYSIS_COMPLETED)
                                               │
Compliance Engine (Phase 9)     ────► AuditEvent (COMPLIANCE_ANALYSIS_COMPLETED)
                                               │
Risk Assessment (Phase 10)      ────► AuditEvent (RISK_ASSESSMENT_COMPLETED)
                                               │
Analysis Evidence Bundle        ────► AuditEvent (AUDIT_SEALED) [Terminal]
                                               │
                                               ▼
                              AuditEventRepository (Firestore /audit_events)
                                               │
                                               ▼
                              AuditVerificationService (Offline Verifier)
```

---

## 3. Key Features & Guarantees

1. **Microsecond-Precise UTC Canonical Serialization**: All datetimes format as `YYYY-MM-DDTHH:MM:SS.ffffff+00:00`. Keys are lexicographically sorted, `Decimal` scale is preserved, and float values are safely converted to string numbers.
2. **SHA-256 Hash Chaining**: Every non-genesis event's `previous_event_hash` MUST equal the preceding event's `event_hash`.
3. **Declared Provenance Versioning**: Provenance metadata tags engine version constants with `version_status = "DECLARED"`.
4. **Append-Only Database Repository**: `AuditEventRepository` exposes ONLY `append()` and `get()` methods. Attempting `update()` or `delete()` raises `AuditSecurityError`.
5. **First-Class Chain Completeness Check**: Verification checks chains against `EXPECTED_AUDIT_EVENT_SEQUENCE` (`DOCUMENT_REGISTERED`, `EXTRACTION_COMPLETED`, `FORENSIC_ANALYSIS_COMPLETED`, `COMPLIANCE_ANALYSIS_COMPLETED`, `RISK_ASSESSMENT_COMPLETED`, `AUDIT_SEALED`). Chains with missing events fail verification.
6. **Side-Effect-Free Verification**: `AuditVerificationService` performs 100% offline verification with optional `document_bytes` checksum matching (`MATCH`/`MISMATCH`/`NOT_AVAILABLE`).

---

## 4. Verification & Testing

Run the complete audit unit test suite:

```bash
.\venv\Scripts\pytest tests/unit/test_audit_*.py -q
```

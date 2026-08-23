# Phase 9 — Deterministic Compliance Engine Architecture & Specification

## 1. Executive Summary & Core Principle

The **Deterministic Compliance Engine** provides PaperTrail AI with an independent, reproducible, and evidence-backed compliance evaluation layer. Operating with **zero LLM/Gemini dependencies**, the engine applies versioned, immutable compliance policies containing controls and deterministic rules against Phase 7 structured extractions (`DocumentExtractionResult`), Phase 5 document metadata (`DocumentMetadata`), and Phase 8 forensic findings (`ForensicAnalysisResult`) within an explicitly supplied `ComplianceContext`.

### Core Principle
> **Forensic Engine detects anomalies. Compliance Engine evaluates facts and anomalies against organizational policies.** Neither engine is a judge — both produce evidence for human decision-makers.

### Determinism & Clock Isolation Guarantee
> **Compliance evaluation is deterministic only relative to an explicit `ComplianceContext`. The Compliance Engine does not read the system clock directly.**
>
> **Reference Time**: Explicit input (`ComplianceContext.reference_datetime`). System clock calls (`datetime.now()`, `datetime.utcnow()`) inside the engine boundary are strictly prohibited and enforced via unit tests.

---

## 2. Architecture & Layer Separation

```text
DocumentExtractionResult (Phase 7)
DocumentMetadata (Phase 5)
ForensicAnalysisResult (Phase 8)
ComplianceContext (Phase 9 — explicit reference_datetime)
                │
                ▼ Input Parameters Only
       Deterministic Compliance Engine (Phase 9)
                │
                ├── Policy Registry Resolution (Active & Applicable Policies)
                ├── Rule Registry Execution (Deterministic Compliance Rules)
                ├── Control Applicability Filtering
                ├── Forensic Finding & Absence Semantics (Cross-referencing skipped checks)
                ▼
      ComplianceAnalysisResult
  (ComplianceFinding List + Policy Summaries + Verifiable Evidence)
```

---

## 3. Explicit Execution Context & Determinism (`ComplianceContext`)

To guarantee strict determinism across execution environments, `ComplianceContext` requires an explicit `reference_datetime` passed by the caller:

```python
class ComplianceContext(BaseModel):
    reference_datetime: datetime
    organization_scope: Optional[str] = None
    policy_scope: Optional[str] = None
    jurisdiction_label: Optional[str] = None
    configured_thresholds: Dict[str, str] = Field(default_factory=dict)
```

### Determinism Guarantee
```text
Same ExtractionPayload + Same Metadata + Same ForensicResult + Same ComplianceContext + Same Policy Version == EXACT SAME FINDINGS
```

---

## 4. Policy, Control, Rule & Evidence Domain Hierarchy

```text
CompliancePolicy (POL-FIN-001 v1.0.0)
    │
    ├── ComplianceControl (C-FIN-001: Line Item Arithmetic)
    │       ├── Rule: CR-FIN-001 (Forensic Line Item Arithmetic Integrity)
    │       └── Required Evidence: ["line_items", "amounts"]
    │
    ├── ComplianceControl (C-FIN-002: Duplicate Document)
    │       ├── Rule: CR-FIN-002 (Duplicate Verification)
    │       └── Required Evidence: ["invoice_number", "checksum"]
    │
    ├── ComplianceControl (C-STR-001: Structural Field Completeness)
    │       ├── Rule: CR-STR-001 (Required Structural Field Compliance)
    │       └── Required Evidence: ["vendor", "customer", "invoice_number"]
    │
    ├── ComplianceControl (C-TMP-001: Temporal Date Validity)
    │       ├── Rule: CR-TMP-001 (Document Temporal Date Validity)
    │       └── Required Evidence: ["dates"]
    │
    ├── ComplianceControl (C-MET-001: Metadata Integrity)
    │       ├── Rule: CR-MET-001 (Metadata Integrity)
    │       ├── Rule: CR-PRV-001 (Cryptographic Checksum Provenance)
    │       └── Required Evidence: ["size_bytes", "checksum"]
    │
    └── ComplianceControl (C-EXT-001: Extraction Quality Confidence)
            ├── Rule: CR-EXT-001 (Extraction Quality Confidence Compliance)
            └── Required Evidence: ["extraction_confidence"]
```

---

## 5. Compliance Statuses & Absence Semantics

| ComplianceStatus | Description |
|:-----------------|:------------|
| `PASS` | All rule conditions satisfied; evidence confirms compliance. |
| `FAIL` | Policy condition violated; evidence documents non-compliance. |
| `REVIEW` | Condition ambiguous; manual review required. |
| `NOT_APPLICABLE` | Control does not apply to the document type, scope, or jurisdiction. |
| `INSUFFICIENT_EVIDENCE` | Underlying extraction, metadata, or forensic check was missing or skipped. |

### Absence Semantics
- If a referenced Phase 8 forensic rule executed with **zero findings**, the compliance rule returns `PASS`.
- If a referenced Phase 8 forensic rule was in `checks_skipped`, the compliance rule returns `INSUFFICIENT_EVIDENCE` (does not falsely report `PASS`).

---

## 6. Legal Disclaimer

PaperTrail AI's Compliance Engine evaluates documents against configured software policies only. It does **NOT** issue legal verdicts, confirm statutory violations, or establish regulatory liability. All results serve as evidence for human decision-makers.

---

## 7. Verification & Offline Testing

The test suite in [`tests/unit/test_compliance_engine.py`](file:///c:/Users/anton/OneDrive/Desktop/papertrail/papertrail/tests/unit/test_compliance_engine.py) runs 100% offline with zero external API calls or database connections:
- **Test A**: Deterministic output guarantee.
- **Test B**: Reference datetime context variation.
- **Test C**: Clock isolation verification (monkeypatching system clock access to raise error if called).

# Phase 8 — Deterministic Forensic Engine Architecture & Specification

## 1. Executive Summary & Core Principle

The **Deterministic Forensic Engine** provides PaperTrail AI with independent, reproducible, and verifiable forensic validation. Operating with **zero LLM/Gemini dependencies**, the engine applies deterministic Python rules against Phase 7 structured extractions (`DocumentExtractionResult`), Phase 5 document metadata (`DocumentMetadata`), and read-only historical context (`HistoricalContext`) within a explicit `ForensicContext` to produce evidence-backed forensic findings.

### Core Principle
> **AI Extraction != Forensic Truth**
> Gemini extracts factual payload data observed in a document. The Python Forensic Engine independently verifies those facts against deterministic business logic, mathematical precision, explicit reference timestamps, and temporal rules.

---

## 2. Architecture & Layer Separation

```text
Phase 7 Structured Extraction Payload (GeminiExtractionPayload)
Phase 5 Document Metadata (DocumentMetadata)
Read-Only Historical Context (HistoricalContext)
Explicit Execution Context (ForensicContext: reference_datetime)
                      │
                      ▼ Input Parameters Only
       Deterministic Forensic Engine (Phase 8)
                      │
                      ├── Rule Registry Execution
                      ├── Decimal Financial Arithmetic & Rounding Policy
                      ├── Deduplication & Skipped Rule Tracking
                      ▼
            ForensicAnalysisResult
       (ForensicFinding List + Evidence)
```

---

## 3. Explicit Execution Context & Determinism (`ForensicContext`)

To guarantee strict determinism across execution environments, time-sensitive rules do **NOT** invoke implicit functions like `datetime.now()` or `datetime.utcnow()`.

Instead, execution time is passed via `ForensicContext`:
```python
class ForensicContext(BaseModel):
    reference_datetime: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
```

### Determinism Guarantee
```text
Same ExtractionPayload + Same Metadata + Same HistoricalContext + Same reference_datetime == EXACT SAME FINDINGS
```

---

## 4. Financial Quantization & Rounding Policy

All monetary calculations use Python's `Decimal` type converted from string representations (e.g. `"1320.50"`). Floating-point `float` types are strictly prohibited.

### Rounding Policy
- **Places**: 2 decimal places (`Decimal("0.01")`).
- **Rounding Mode**: `ROUND_HALF_UP` (standard financial rounding policy).
- **Function**: `quantize_currency(value: Decimal, places: int = 2) -> Decimal`.

---

## 5. Deterministic Rule Registry

| Rule ID | Name | Category | Severity | Finding Code | Description & Execution Logic |
| :--- | :--- | :--- | :--- | :--- | :--- |
| `LINE_ITEM_AMOUNT_MISMATCH` | Line Item Amount Arithmetic | `FINANCIAL` | `HIGH` | `LINE_ITEM_AMOUNT_MISMATCH` | Validates `quantize_currency(Decimal(quantity) * Decimal(unit_price)) == quantize_currency(Decimal(amount))` per line item. |
| `FUTURE_DOCUMENT_DATE` | Future Document Date | `TEMPORAL` | `HIGH` | `FUTURE_DOCUMENT_DATE` | Flags extracted dates exceeding `context.reference_datetime`. |
| `INVALID_DATE_FORMAT` | ISO Date Format Verification | `TEMPORAL` | `MEDIUM` | `INVALID_DATE_FORMAT` | Flags extracted date strings failing standard ISO-8601 parsing. |
| `DATE_ORDER_INVALID` | Semantic Date Ordering | `TEMPORAL` | `HIGH` | `DATE_ORDER_INVALID` | Executed **only** when explicit semantic date fields (`issue_date`, `due_date`) exist. Flags `due_date < issue_date`. Skipped if fields absent. |
| `MISSING_REQUIRED_FIELD` | Structural Required Field | `STRUCTURAL` | `MEDIUM` | `MISSING_REQUIRED_FIELD` | Validates structural required fields per `DocumentType` (e.g. `invoice_number`, `vendor`, `customer` for invoices). |
| `INVALID_DOCUMENT_METADATA` | Metadata Consistency | `METADATA` | `HIGH` / `MEDIUM` | `INVALID_DOCUMENT_METADATA` | Validates `DocumentMetadata` properties (e.g. size 0 bytes, missing SHA-256 checksum). |
| `DUPLICATE_IDENTIFIER` | Duplicate Identifier | `DUPLICATE` | `CRITICAL` | `DUPLICATE_IDENTIFIER` | Checks extracted `invoice_number` or `checksum` against read-only `HistoricalContext`. |

---

## 6. Insufficient Evidence Handling (`SkippedCheck`)

Rules requiring missing semantic fields or payloads log an explicit `SkippedCheck` rather than guessing or inferring values:
```json
{
  "rule_id": "DATE_ORDER_INVALID",
  "reason": "Required semantic date ordering fields ('issue_date', 'due_date') are unavailable."
}
```

---

## 7. Testing Strategy (100% Offline)

All Phase 8 unit tests in [`tests/unit/test_forensic_engine.py`](file:///c:/Users/anton/OneDrive/Desktop/papertrail/papertrail/tests/unit/test_forensic_engine.py) run completely offline without external APIs, network access, or Gemini calls.

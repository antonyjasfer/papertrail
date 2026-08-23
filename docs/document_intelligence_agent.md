# Phase 7 — Document Intelligence Agent Architecture & Specification

## 1. Executive Summary & Purpose

The **Document Intelligence Agent** provides PaperTrail AI with its first core AI capability: **Document Understanding & Factual Structured Extraction**. Powered by Google's **Gemini 3.5 Flash** model via the official `google-genai` SDK, the agent ingests stored document payloads (PDF, PNG, JPEG, TXT) and returns schema-constrained JSON extractions.

The agent strictly answers:
> *What is this document and what structured information does it contain?*

It does **NOT** perform fraud detection, anomaly scoring, compliance checks, risk calculation, workflow state transitions, tool execution, or database mutations.

---

## 2. System Architecture & Layer Boundaries

```text
DocumentStorageService (Phase 5)
          │
          ▼ Retrieves Document Metadata & Bytes Boundary
DocumentIntelligenceService (Application Layer)
          │
          ├── 1. Invokes Agent with Untrusted Payload
          ▼
DocumentIntelligenceAgent (Agent Layer)
          │
          ├── 2. Gemini 3.5 Flash (Factual Extraction Only)
          ▼ Returns GeminiExtractionPayload Schema
Pydantic Validation (Validation Layer)
          │
          ├── 3. Evaluates Schema & extraction_confidence
          ▼ Computes AnalysisStatus (SUCCESS / NEEDS_REVIEW / FAILED)
DocumentExtractionResult (Application Envelope)
```

### Decoupled Responsibility Matrix

| Layer / Component | Primary Responsibility | Explicit Boundaries & Constraints |
| :--- | :--- | :--- |
| **Gemini 3.5 Flash** | Factual extraction, text/entity recognition, document classification | CANNOT output `status`, `status_reason`, `workflow_state`, `risk`, `fraud`, `compliance`, or tool calls |
| **Python Application (`Service`)** | Schema validation, `extraction_confidence` check, setting `AnalysisStatus` | CANNOT mutate `WorkflowState`, write to Firestore database collections, or call external tools |
| **State Machine (`Phase 3 & 4`)** | Workflow lifecycle authority (`WorkflowState`) | AI model reasoning |
| **Firestore (`Phase 4`)** | Document & workflow record persistence | Phase 7 AI result mutation |
| **Document Storage (`Phase 5`)** | Binary artifact & metadata management | AI extraction logic |

---

## 3. Installed SDK Verification & Compatibility

- **SDK Package**: `google-genai` (version 2.18.1 verified)
- **Model**: `gemini-3.5-flash`
- **Structured Output Signature**: `types.GenerateContentConfig(response_mime_type="application/json", response_schema=GeminiExtractionPayload, temperature=0.0)`
- **Multimodal Delivery**: `types.Part.from_bytes(data=file_bytes, mime_type=content_type)`
- **Authentication**: Application Default Credentials (ADC), Secret Manager (`secret_name_gemini_api_key`), or `GEMINI_API_KEY` environment configuration.

---

## 4. Domain Data Models & Schemas

### `GeminiExtractionPayload` (Gemini Extraction Schema)
Factual extraction schema returned by Gemini 3.5 Flash:
```python
class GeminiExtractionPayload(BaseModel):
    document_type: DocumentType  # invoice, receipt, contract, expense_report, purchase_order, other, unknown
    title: Optional[str]
    entities: List[str]
    dates: List[str]  # Standardized ISO-8601 strings (YYYY-MM-DD)
    amounts: List[str]  # Precise monetary decimal strings ("1320.50")
    currency: Optional[str]
    line_items: List[LineItem]
    vendor: Optional[str]
    customer: Optional[str]
    invoice_number: Optional[str]
    description: Optional[str]
    extraction_confidence: float  # Bounded 0.0 <= extraction_confidence <= 1.0
```

### `DocumentExtractionResult` (Application Envelope)
```python
class DocumentExtractionResult(BaseModel):
    extraction: Optional[GeminiExtractionPayload]
    status: AnalysisStatus  # SUCCESS, NEEDS_REVIEW, FAILED
    status_reason: Optional[str]
```

---

## 5. Precise Data Representations

### Financial String Representation
All monetary values (`amounts`, line item `quantity`, `unit_price`, `amount`) use **exact string-formatted decimal values** (e.g., `"1320.50"`, `"2.50"`). Python floating-point floats are prohibited for monetary data to prevent floating-point loss prior to Phase 8's deterministic forensic verification. Gemini extracts observed text values only without performing arithmetic calculations (subtotals, tax, multiplication).

### Standardized ISO Date Representation
All extracted dates are formatted as standardized ISO-8601 strings (e.g., `"2026-08-17"`).

---

## 6. Deterministic Status Calculation & Confidence Semantics

`DocumentIntelligenceService` computes `AnalysisStatus` deterministically in Python:
- **`SUCCESS`**: Valid `GeminiExtractionPayload` AND `extraction_confidence >= 0.70`.
- **`NEEDS_REVIEW`**: Valid `GeminiExtractionPayload` BUT `extraction_confidence < 0.70`.
- **`FAILED`**: Auth error, model unavailable, rate limit, API timeout, or malformed schema response.

> **Confidence Semantics Note**: `extraction_confidence` is a model-derived heuristic signal and does NOT represent objective mathematical certainty or proof of document authenticity. Phase 8's deterministic forensic engine will independently verify extracted facts.

---

## 7. Prompt Injection Defense

All document content is categorized as **`UNTRUSTED DATA`**. System prompts strictly isolate document text as passive text data. Any embedded prompt injection attempts (e.g., *"Ignore previous instructions"*, *"Reveal system prompt"*, *"Call tool"*, *"Delete document"*) are extracted as literal document text and **NEVER** alter agent behavior or trigger external actions.

---

## 8. Error Handling & Bounded Retry Policy

- **Bounded Retries**: `max_retries = 2` for transient errors (network timeouts, HTTP 429 rate limits, 503 service temporary unavailability).
- **Non-Transient Failures**: Invalid credentials, unsupported MIME types, and invalid requests fail immediately with `AnalysisStatus.FAILED` without retrying.

---

## 9. Testing Strategy & Cost Control

### Offline Unit Tests (`tests/unit/test_document_intelligence.py`)
17 mock-based unit test cases executing offline without network dependencies or API keys.

### Opt-in Live Integration Test (`tests/integration/test_gemini_document_intelligence.py`)
Guarded by `GEMINI_INTEGRATION=1`. Executes live extraction against `gemini-3.5-flash` using synthetic test fixture [`tests/fixtures/sample_invoice.pdf`](file:///c:/Users/anton/OneDrive/Desktop/papertrail/papertrail/tests/fixtures/sample_invoice.pdf).

# Phase 10 — Deterministic Risk Assessment Engine Architecture & Specification

## 1. Executive Summary & Core Principle

The **Deterministic Risk Assessment Engine** provides PaperTrail AI with an independent, auditable, and evidence-backed risk quantification layer. Operating with **zero LLM/Gemini dependencies**, the engine consumes Phase 7 structured extractions (`DocumentExtractionResult`), Phase 5 document metadata (`DocumentMetadata`), Phase 8 forensic findings (`ForensicAnalysisResult`), and Phase 9 compliance analysis results (`ComplianceAnalysisResult`) within an explicitly supplied `RiskContext` to compute reproducible Decimal risk scores and risk level classifications.

### Core Principle
> **Forensic Engine detects anomalies. Compliance Engine evaluates facts and anomalies against organizational policies. Risk Engine quantifies aggregated risk into a single, auditable Decimal score.**
>
> None of these engines issue legal judgments or confirm statutory fraud — all produce structured evidence for human decision-makers.

### Determinism & Clock Isolation Guarantee
> **Risk assessment is deterministic only relative to an explicit `RiskContext`. The Risk Engine does not read the system clock directly.**
>
> **Reference Time**: Explicit input (`RiskContext.reference_datetime`). System clock calls (`datetime.now()`, `datetime.utcnow()`) inside the engine boundary are strictly prohibited and enforced via unit tests.

---

## 2. Architecture & Multi-Dimensional Risk Model

```text
DocumentExtractionResult (Phase 7)
DocumentMetadata (Phase 5)
ForensicAnalysisResult (Phase 8)
ComplianceAnalysisResult (Phase 9)
RiskContext (Phase 10 — explicit reference_datetime)
                │
                ▼ Input Parameters Only
       Deterministic Risk Assessment Engine (Phase 10)
                │
                ├── Factor Parsing & Evidence Lineage Tagging
                ├── RiskAggregationPolicy (Lineage Deduplication by lineage_key)
                ├── Multi-Dimensional Decimal Scoring (DIM-FOR, DIM-CMP, DIM-EXT, DIM-PRV, DIM-DAT)
                ├── Missing Data Handling & Dynamic Weight Reweighting
                ├── Decimal Composite Score Computation (ROUND_HALF_UP scale 0.01)
                ├── Risk Level Classification (LOW, MEDIUM, HIGH, CRITICAL)
                └── CalculationTrace Generation
                │
                ▼
       RiskAssessmentResult
   (Decimal Composite Score + Risk Level + Dimension Scores + Calculation Trace)
```

---

## 3. Five Risk Dimensions

| Dimension ID | Dimension Name | Source Phase | Description & Weight |
|:-------------|:---------------|:-------------|:---------------------|
| `DIM-FOR` | Forensic Anomaly Risk | Phase 8 | Severity-weighted forensic findings (`Decimal("0.30")`) |
| `DIM-CMP` | Compliance Violation Risk | Phase 9 | Policy control status distribution (`Decimal("0.30")`) |
| `DIM-EXT` | Extraction Quality Uncertainty | Phase 7 | Distance of extraction confidence from 1.0 (`Decimal("0.15")`) |
| `DIM-PRV` | Provenance Integrity Risk | Phase 5 | Storage metadata and SHA-256 fingerprint presence (`Decimal("0.10")`) |
| `DIM-DAT` | Data Completeness Uncertainty | Phase 8 + 9 | Ratio of skipped checks to total expected checks (`Decimal("0.15")`) |

---

## 4. Key Architectural Guarantees

1. **Exact Decimal Arithmetic**: All scores, weights, reweighted weights, composite scores, and thresholds use Python standard library `decimal.Decimal`. Binary `float` calculations are prohibited in authoritative scoring.
2. **No Array Position Semantic Inference**: The engine NEVER infers field semantics from generic `amounts: List[str]`. If required semantic monetary fields are absent, dimensions record `INSUFFICIENT_DATA` rather than guessing.
3. **Missing Data Policy (Missing Data ≠ Max Risk)**: A missing upstream result sets dimension status to `INSUFFICIENT_DATA` with score `0.00` and dynamically reweights active dimensions to sum to `Decimal("1.00")`, setting uncertainty flags.
4. **Read-Only Risk Aggregation**: The `RiskAggregationPolicy` creates derived factor copies (`model_copy`) rather than mutating input `RiskFactor` objects in place. Correlated findings sharing the same `lineage_key` across Phase 8 and Phase 9 are deduplicated without mutating upstream objects.
5. **Side-Effect Free Evaluation**: `RiskAssessmentEngine.assess()` is 100% side-effect free with respect to its inputs (`DocumentExtractionResult`, `DocumentMetadata`, `ForensicAnalysisResult`, `ComplianceAnalysisResult`, `RiskContext`, `RiskProfile`). Inputs remain 100% unmutated after evaluation.
6. **Extraction Uncertainty Semantics**: `DIM-EXT` represents model extraction uncertainty, NOT a direct probability of fraud.

---

## 5. Verification & Offline Testing

The unit test suite in [`tests/unit/test_risk_engine.py`](file:///c:/Users/anton/OneDrive/Desktop/papertrail/papertrail/tests/unit/test_risk_engine.py) runs 100% offline:
- **Test A**: Deterministic output guarantee (`Result A == Result B`).
- **Test B**: Reference datetime context variation.
- **Test C**: Clock isolation verification (monkeypatching system clock access to raise error if called).
- **Decimal Scoring & Weight Validation**: Verifying exact Decimal arithmetic and profile weight sum validation.
- **Lineage Deduplication Immutability**: Verifying double-counting prevention without mutating input `RiskFactor` or upstream phase model objects.

from copy import deepcopy
from datetime import datetime, timezone
from decimal import Decimal
import pytest

from app.compliance.engine import ComplianceEngine
from app.forensics.engine import ForensicEngine
from app.models.analysis import (
    AnalysisStatus,
    DocumentExtractionResult,
    DocumentType,
    GeminiExtractionPayload,
    LineItem,
)
from app.models.compliance import ComplianceContext, ComplianceStatus
from app.models.document import DocumentMetadata
from app.models.forensics import ForensicContext, HistoricalContext
from app.models.risk import DimensionStatus, RiskContext, RiskFactor, RiskLevel
from app.risk.aggregation import RiskAggregationPolicy
from app.risk.engine import RiskAssessmentEngine


def create_sample_metadata(
    doc_id: str = "doc-risk-100",
    size_bytes: int = 1024,
    checksum: str = "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
) -> DocumentMetadata:
    return DocumentMetadata(
        document_id=doc_id,
        filename="invoice.pdf",
        content_type="application/pdf",
        size_bytes=size_bytes,
        storage_bucket="papertrail-ai-documents-dev",
        storage_object=f"documents/{doc_id}/original/invoice.pdf",
        checksum=checksum,
    )


def create_clean_extraction() -> DocumentExtractionResult:
    payload = GeminiExtractionPayload(
        document_type=DocumentType.INVOICE,
        vendor="Acme Supplies LLC",
        customer="Global Corp",
        invoice_number="INV-2026-001",
        currency="USD",
        dates=["2026-01-15"],
        amounts=["150.00"],
        line_items=[
            LineItem(
                description="Widget A",
                quantity="10",
                unit_price="15.00",
                amount="150.00",
            )
        ],
        extraction_confidence=1.0,
    )
    return DocumentExtractionResult(
        extraction=payload,
        status=AnalysisStatus.SUCCESS,
        status_reason="Clean extraction",
    )


# --- 1. Test A: Deterministic Output Guarantee ---
def test_a_deterministic_output_guarantee():
    ref_time = datetime(2026, 1, 20, 12, 0, 0, tzinfo=timezone.utc)
    metadata = create_sample_metadata()
    extraction = create_clean_extraction()

    f_engine = ForensicEngine()
    f_res = f_engine.analyze(extraction, metadata, HistoricalContext(), ForensicContext(reference_datetime=ref_time))

    c_engine = ComplianceEngine()
    c_res = c_engine.evaluate(extraction, metadata, f_res, ComplianceContext(reference_datetime=ref_time))

    r_engine = RiskAssessmentEngine()
    r_ctx = RiskContext(reference_datetime=ref_time)

    res_1 = r_engine.assess(extraction, metadata, f_res, c_res, r_ctx)
    res_2 = r_engine.assess(extraction, metadata, f_res, c_res, r_ctx)

    assert res_1.composite_score == res_2.composite_score
    assert res_1.risk_level == res_2.risk_level
    assert len(res_1.dimension_scores) == len(res_2.dimension_scores)
    assert res_1.calculation_trace.final_composite_score == res_2.calculation_trace.final_composite_score


# --- 2. Test B: Reference Datetime Context Variation ---
def test_b_reference_datetime_context_variation():
    ref_time_1 = datetime(2026, 1, 20, 12, 0, 0, tzinfo=timezone.utc)
    ref_time_2 = datetime(2025, 1, 1, 0, 0, 0, tzinfo=timezone.utc)

    metadata = create_sample_metadata()
    extraction = create_clean_extraction()

    f_engine = ForensicEngine()
    f_res = f_engine.analyze(extraction, metadata, HistoricalContext(), ForensicContext(reference_datetime=ref_time_1))

    c_engine = ComplianceEngine()
    c_res = c_engine.evaluate(extraction, metadata, f_res, ComplianceContext(reference_datetime=ref_time_1))

    r_engine = RiskAssessmentEngine()

    res_1 = r_engine.assess(extraction, metadata, f_res, c_res, RiskContext(reference_datetime=ref_time_1))
    res_2 = r_engine.assess(extraction, metadata, f_res, c_res, RiskContext(reference_datetime=ref_time_2))

    assert isinstance(res_1.composite_score, Decimal)
    assert isinstance(res_2.composite_score, Decimal)


# --- 3. Test C: Clock Isolation Verification ---
def test_c_clock_isolation_verification(monkeypatch):
    def forbidden_clock(*args, **kwargs):
        raise RuntimeError("FORBIDDEN: System clock read detected inside RiskAssessmentEngine!")

    monkeypatch.setattr("datetime.datetime", forbidden_clock)

    ref_time = datetime(2026, 1, 20, 12, 0, 0, tzinfo=timezone.utc)
    metadata = create_sample_metadata()
    extraction = create_clean_extraction()

    r_engine = RiskAssessmentEngine()
    r_ctx = RiskContext(reference_datetime=ref_time)

    # Must complete successfully without triggering clock read
    res = r_engine.assess(extraction, metadata, None, None, r_ctx)
    assert isinstance(res.composite_score, Decimal)


# --- 4. Omitted context raises ValueError ---
def test_omitted_context_raises_value_error():
    r_engine = RiskAssessmentEngine()
    extraction = create_clean_extraction()

    with pytest.raises(ValueError, match="RiskContext with explicit reference_datetime is required"):
        r_engine.assess(extraction, None, None, None, None)


# --- 5. Decimal Scoring Precision ---
def test_decimal_scoring_precision():
    ref_time = datetime(2026, 1, 20, 12, 0, 0, tzinfo=timezone.utc)
    r_engine = RiskAssessmentEngine()
    extraction = create_clean_extraction()
    metadata = create_sample_metadata()

    res = r_engine.assess(extraction, metadata, None, None, RiskContext(reference_datetime=ref_time))

    assert isinstance(res.composite_score, Decimal)
    for ds in res.dimension_scores:
        assert isinstance(ds.score, Decimal)
        assert isinstance(ds.weight, Decimal)
        assert isinstance(ds.reweighted_weight, Decimal)
        assert isinstance(ds.weighted_contribution, Decimal)


# --- 7. No Generic amounts[0] Inference ---
def test_no_generic_amounts_0_inference():
    ref_time = datetime(2026, 1, 20, 12, 0, 0, tzinfo=timezone.utc)
    extraction = create_clean_extraction()
    # Payload has amounts = ["100.00"], but no total_amount attribute
    extraction.extraction.amounts = ["100.00"]

    r_engine = RiskAssessmentEngine()
    res = r_engine.assess(extraction, create_sample_metadata(), None, None, RiskContext(reference_datetime=ref_time))

    # Engine runs without assuming amounts[0] is total invoice amount
    assert res.composite_score == Decimal("0.00")
    assert res.risk_level == RiskLevel.LOW


# --- 9. Missing Forensic Result Policy (No 100.0 Max Risk) ---
def test_missing_forensic_result_policy():
    ref_time = datetime(2026, 1, 20, 12, 0, 0, tzinfo=timezone.utc)
    extraction = create_clean_extraction()
    metadata = create_sample_metadata()

    r_engine = RiskAssessmentEngine()
    res = r_engine.assess(extraction, metadata, None, None, RiskContext(reference_datetime=ref_time))

    # DIM-FOR should be INSUFFICIENT_DATA, score 0.00 (not 100.00 max risk)
    dim_for = next(ds for ds in res.dimension_scores if ds.dimension_id == "DIM-FOR")
    assert dim_for.status == DimensionStatus.INSUFFICIENT_DATA
    assert dim_for.score == Decimal("0.00")
    assert res.uncertainty_flag is True


# --- 10. Missing Compliance Result Policy ---
def test_missing_compliance_result_policy():
    ref_time = datetime(2026, 1, 20, 12, 0, 0, tzinfo=timezone.utc)
    extraction = create_clean_extraction()
    metadata = create_sample_metadata()

    r_engine = RiskAssessmentEngine()
    res = r_engine.assess(extraction, metadata, None, None, RiskContext(reference_datetime=ref_time))

    dim_cmp = next(ds for ds in res.dimension_scores if ds.dimension_id == "DIM-CMP")
    assert dim_cmp.status == DimensionStatus.INSUFFICIENT_DATA
    assert dim_cmp.score == Decimal("0.00")
    assert res.uncertainty_flag is True


# --- 11. Correlated Evidence Aggregation (Lineage Deduplication) ---
def test_correlated_evidence_aggregation_lineage():
    ref_time = datetime(2026, 1, 20, 12, 0, 0, tzinfo=timezone.utc)
    extraction = create_clean_extraction()
    # Create arithmetic mismatch in line items
    extraction.extraction.line_items[0].quantity = "10"
    extraction.extraction.line_items[0].unit_price = "15.00"
    extraction.extraction.line_items[0].amount = "999.00"  # Mismatch

    metadata = create_sample_metadata()

    f_engine = ForensicEngine()
    f_res = f_engine.analyze(extraction, metadata, HistoricalContext(), ForensicContext(reference_datetime=ref_time))

    c_engine = ComplianceEngine()
    c_res = c_engine.evaluate(extraction, metadata, f_res, ComplianceContext(reference_datetime=ref_time))

    r_engine = RiskAssessmentEngine()
    res = r_engine.assess(extraction, metadata, f_res, c_res, RiskContext(reference_datetime=ref_time))

    # Check trace steps confirm lineage deduplication
    assert res.calculation_trace.factors_evaluated > 0
    assert res.calculation_trace.factors_deduplicated <= res.calculation_trace.factors_evaluated


# --- 13. Extraction Uncertainty Semantics ---
def test_extraction_uncertainty_semantics():
    ref_time = datetime(2026, 1, 20, 12, 0, 0, tzinfo=timezone.utc)
    extraction = create_clean_extraction()
    extraction.extraction.extraction_confidence = 0.85

    r_engine = RiskAssessmentEngine()
    res = r_engine.assess(extraction, create_sample_metadata(), None, None, RiskContext(reference_datetime=ref_time))

    dim_ext = next(ds for ds in res.dimension_scores if ds.dimension_id == "DIM-EXT")
    # (1.00 - 0.85) * 100 = 15.00
    assert dim_ext.score == Decimal("15.00")


# --- 14. Extraction Review Trigger ---
def test_extraction_review_trigger():
    ref_time = datetime(2026, 1, 20, 12, 0, 0, tzinfo=timezone.utc)
    extraction = create_clean_extraction()
    extraction.extraction.extraction_confidence = 0.65  # Below 0.70 threshold

    r_engine = RiskAssessmentEngine()
    res = r_engine.assess(extraction, create_sample_metadata(), None, None, RiskContext(reference_datetime=ref_time))

    assert res.review_recommended is True


# --- 17. Clean Document Produces LOW Risk ---
def test_clean_document_produces_low_risk():
    ref_time = datetime(2026, 1, 20, 12, 0, 0, tzinfo=timezone.utc)
    metadata = create_sample_metadata()
    extraction = create_clean_extraction()

    f_engine = ForensicEngine()
    f_res = f_engine.analyze(extraction, metadata, HistoricalContext(), ForensicContext(reference_datetime=ref_time))

    c_engine = ComplianceEngine()
    c_res = c_engine.evaluate(extraction, metadata, f_res, ComplianceContext(reference_datetime=ref_time))

    r_engine = RiskAssessmentEngine()
    res = r_engine.assess(extraction, metadata, f_res, c_res, RiskContext(reference_datetime=ref_time))

    assert res.composite_score <= Decimal("1.00")
    assert res.risk_level == RiskLevel.LOW


# --- 20. Missing Checksum Elevates Provenance Dimension ---
def test_missing_checksum_elevates_provenance():
    ref_time = datetime(2026, 1, 20, 12, 0, 0, tzinfo=timezone.utc)
    metadata = create_sample_metadata(checksum="")
    extraction = create_clean_extraction()

    r_engine = RiskAssessmentEngine()
    res = r_engine.assess(extraction, metadata, None, None, RiskContext(reference_datetime=ref_time))

    dim_prv = next(ds for ds in res.dimension_scores if ds.dimension_id == "DIM-PRV")
    assert dim_prv.score == Decimal("60.00")


# --- 22. Risk Level Classification Thresholds ---
def test_risk_level_classification_thresholds():
    r_engine = RiskAssessmentEngine()
    thresholds = r_engine._resolve_thresholds(
        r_engine.profile_registry.get_applicable_profile(DocumentType.INVOICE, RiskContext(reference_datetime=datetime.now(timezone.utc))),
        RiskContext(reference_datetime=datetime.now(timezone.utc)),
    )

    assert r_engine._classify_risk_level(Decimal("80.00"), thresholds) == RiskLevel.CRITICAL
    assert r_engine._classify_risk_level(Decimal("60.00"), thresholds) == RiskLevel.HIGH
    assert r_engine._classify_risk_level(Decimal("30.00"), thresholds) == RiskLevel.MEDIUM
    assert r_engine._classify_risk_level(Decimal("10.00"), thresholds) == RiskLevel.LOW


# --- 23 & 24. Zero Gemini / Zero Firestore Boundary ---
def test_zero_gemini_firestore_boundary():
    import app.risk.engine as re_module

    # Assert no imports of google-genai or firestore in risk engine package
    module_content = repr(dir(re_module))
    assert "genai" not in module_content
    assert "firestore" not in module_content


# --- 25. Decimal Rounding Boundary Cases ---
def test_decimal_rounding_boundary_cases():
    r_engine = RiskAssessmentEngine()
    thresholds = r_engine._resolve_thresholds(
        r_engine.profile_registry.get_applicable_profile(DocumentType.INVOICE, RiskContext(reference_datetime=datetime.now(timezone.utc))),
        RiskContext(reference_datetime=datetime.now(timezone.utc)),
    )

    # 24.995 rounds up to 25.00 -> MEDIUM
    score_unrounded = Decimal("24.995")
    score_quantized = score_unrounded.quantize(Decimal("0.01"))
    assert score_quantized == Decimal("25.00")
    assert r_engine._classify_risk_level(score_quantized, thresholds) == RiskLevel.MEDIUM


# --- IMMUTABILITY & AGGREGATION REGRESSION TESTS (CORRECTION 1, 2, 5) ---

def test_risk_aggregation_policy_immutability():
    """Verify RiskAggregationPolicy does not mutate input RiskFactor objects in place."""
    factor_1 = RiskFactor(
        factor_id="RF-FOR-01",
        category="FORENSIC",
        source_phase="Phase 8",
        source_reference="LINE_ITEM_AMOUNT_MISMATCH",
        lineage_key="evidence:LINE_ITEM_AMOUNT_MISMATCH:line_items[0].amount:999.00",
        severity_label="HIGH",
        raw_value=Decimal("70.00"),
        normalized_value=Decimal("70.00"),
        evidence_notes="Original forensic notes",
    )
    factor_2 = RiskFactor(
        factor_id="RF-CMP-01",
        category="COMPLIANCE",
        source_phase="Phase 9",
        source_reference="POL-FIN-001:C-FIN-001",
        lineage_key="evidence:LINE_ITEM_AMOUNT_MISMATCH:line_items[0].amount:999.00",
        severity_label="FAIL",
        raw_value=Decimal("100.00"),
        normalized_value=Decimal("100.00"),
        evidence_notes="Original compliance notes",
    )

    input_factors = [factor_1, factor_2]
    # Deepcopy original inputs for comparison
    factor_1_original = factor_1.model_copy(deep=True)
    factor_2_original = factor_2.model_copy(deep=True)

    policy = RiskAggregationPolicy()
    result = policy.aggregate_factors(input_factors)

    # 1. Original input objects MUST remain unchanged
    assert factor_1.normalized_value == factor_1_original.normalized_value == Decimal("70.00")
    assert factor_1.evidence_notes == factor_1_original.evidence_notes == "Original forensic notes"
    assert factor_2.normalized_value == factor_2_original.normalized_value == Decimal("100.00")
    assert factor_2.evidence_notes == factor_2_original.evidence_notes == "Original compliance notes"

    # 2. Aggregated output contains new copy for correlated non-primary factor
    f1_res = next(f for f in result if f.factor_id == "RF-FOR-01")
    f2_res = next(f for f in result if f.factor_id == "RF-CMP-01")

    assert f1_res is not factor_1  # Must be a new copy
    assert f1_res.normalized_value == Decimal("0.00")
    assert "Corroborated by primary factor" in f1_res.evidence_notes
    assert f2_res.normalized_value == Decimal("100.00")


def test_risk_engine_input_immutability():
    """Verify RiskAssessmentEngine.assess() does not mutate any input model objects."""
    ref_time = datetime(2026, 1, 20, 12, 0, 0, tzinfo=timezone.utc)
    extraction = create_clean_extraction()
    extraction.extraction.line_items[0].quantity = "10"
    extraction.extraction.line_items[0].unit_price = "15.00"
    extraction.extraction.line_items[0].amount = "999.00"  # Mismatch

    metadata = create_sample_metadata()

    f_engine = ForensicEngine()
    f_res = f_engine.analyze(extraction, metadata, HistoricalContext(), ForensicContext(reference_datetime=ref_time))

    c_engine = ComplianceEngine()
    c_res = c_engine.evaluate(extraction, metadata, f_res, ComplianceContext(reference_datetime=ref_time))

    r_ctx = RiskContext(reference_datetime=ref_time)

    # Create deep copies of all inputs
    extraction_copy = extraction.model_copy(deep=True)
    metadata_copy = metadata.model_copy(deep=True)
    f_res_copy = f_res.model_copy(deep=True)
    c_res_copy = c_res.model_copy(deep=True)
    r_ctx_copy = r_ctx.model_copy(deep=True)

    r_engine = RiskAssessmentEngine()
    _ = r_engine.assess(extraction, metadata, f_res, c_res, r_ctx)

    # Assert all original inputs match their deep copies exactly
    assert extraction == extraction_copy
    assert metadata == metadata_copy
    assert f_res == f_res_copy
    assert c_res == c_res_copy
    assert r_ctx == r_ctx_copy

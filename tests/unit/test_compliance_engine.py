from datetime import datetime, timezone
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
from app.models.compliance import (
    ComplianceContext,
    ComplianceStatus,
)
from app.models.document import DocumentMetadata, DocumentStatus
from app.models.forensics import ForensicContext, HistoricalContext


@pytest.fixture
def clean_extraction_result():
    payload = GeminiExtractionPayload(
        document_type=DocumentType.INVOICE,
        title="ACME Clean Invoice",
        entities=["ACME Corp", "PaperTrail AI"],
        dates=["2026-08-15"],
        amounts=["1320.50"],
        currency="USD",
        line_items=[
            LineItem(
                description="Cloud Audit Services",
                quantity="2",
                unit_price="660.25",
                amount="1320.50",
            )
        ],
        vendor="ACME Corp",
        customer="PaperTrail AI",
        invoice_number="INV-2026-001",
        description="Clean invoice test payload",
        extraction_confidence=0.95,
    )
    return DocumentExtractionResult(
        extraction=payload,
        status=AnalysisStatus.SUCCESS,
        status_reason="Extraction successful.",
    )


@pytest.fixture
def sample_metadata():
    return DocumentMetadata(
        document_id="doc-cmp-100",
        filename="invoice.pdf",
        content_type="application/pdf",
        size_bytes=2048,
        storage_bucket="papertrail-ai-documents-dev",
        storage_object="documents/doc-cmp-100/original/invoice.pdf",
        created_at=datetime(2026, 8, 16, 12, 0, 0, tzinfo=timezone.utc),
        updated_at=datetime(2026, 8, 16, 12, 0, 0, tzinfo=timezone.utc),
        document_status=DocumentStatus.STORED,
        checksum="a1b2c3d4e5f678901234567890abcdef1234567890abcdef1234567890abcdef",
    )


@pytest.fixture
def clean_forensic_result(clean_extraction_result, sample_metadata):
    forensic_engine = ForensicEngine()
    ctx = ForensicContext(reference_datetime=datetime(2026, 8, 17, 12, 0, 0, tzinfo=timezone.utc))
    return forensic_engine.analyze(clean_extraction_result, metadata=sample_metadata, context=ctx)


# 1. TEST A: Deterministic Output Guarantee (Same input + same ComplianceContext + same policy version)
def test_a_deterministic_output_guarantee(clean_extraction_result, sample_metadata, clean_forensic_result):
    context = ComplianceContext(reference_datetime=datetime(2026, 8, 17, 12, 0, 0, tzinfo=timezone.utc))
    engine = ComplianceEngine()

    res_a = engine.evaluate(clean_extraction_result, metadata=sample_metadata, forensic_result=clean_forensic_result, context=context)
    res_b = engine.evaluate(clean_extraction_result, metadata=sample_metadata, forensic_result=clean_forensic_result, context=context)

    assert res_a.finding_count == res_b.finding_count
    assert res_a.evidence_summary == res_b.evidence_summary
    assert len(res_a.findings) == len(res_b.findings)
    for f1, f2 in zip(res_a.findings, res_b.findings):
        assert f1.status == f2.status
        assert f1.rule_id == f2.rule_id


# 2. TEST B: Explicit Reference Datetime Variation
def test_b_explicit_reference_datetime_variation(clean_extraction_result, sample_metadata):
    # Set document date to 2026-08-18
    clean_extraction_result.extraction.dates = ["2026-08-18"]
    engine = ComplianceEngine()

    # Ref Time 1: 2026-08-17 (Document date IS in future)
    ctx1 = ComplianceContext(reference_datetime=datetime(2026, 8, 17, 0, 0, 0, tzinfo=timezone.utc))
    forensic_res1 = ForensicEngine().analyze(clean_extraction_result, metadata=sample_metadata, context=ForensicContext(reference_datetime=ctx1.reference_datetime))
    res1 = engine.evaluate(clean_extraction_result, metadata=sample_metadata, forensic_result=forensic_res1, context=ctx1)

    # Ref Time 2: 2026-08-19 (Document date IS NOT in future)
    ctx2 = ComplianceContext(reference_datetime=datetime(2026, 8, 19, 0, 0, 0, tzinfo=timezone.utc))
    forensic_res2 = ForensicEngine().analyze(clean_extraction_result, metadata=sample_metadata, context=ForensicContext(reference_datetime=ctx2.reference_datetime))
    res2 = engine.evaluate(clean_extraction_result, metadata=sample_metadata, forensic_result=forensic_res2, context=ctx2)

    # Future date control CR-TMP-001 should FAIL in res1 and PASS in res2
    tmp_fnd1 = [f for f in res1.findings if f.rule_id == "CR-TMP-001"][0]
    tmp_fnd2 = [f for f in res2.findings if f.rule_id == "CR-TMP-001"][0]

    assert tmp_fnd1.status == ComplianceStatus.FAIL
    assert tmp_fnd2.status == ComplianceStatus.PASS


# 3. TEST C: Clock Isolation Verification (datetime.now() and datetime.utcnow() prohibited during evaluation)
def test_c_clock_isolation_verification(clean_extraction_result, sample_metadata, clean_forensic_result):
    context = ComplianceContext(reference_datetime=datetime(2026, 8, 17, 12, 0, 0, tzinfo=timezone.utc))
    engine = ComplianceEngine()

    # Verify app.compliance modules do not import datetime functions directly for system clock reads
    import app.compliance.engine as engine_mod
    import app.compliance.rules as rules_mod

    assert not hasattr(engine_mod, "datetime")
    assert not hasattr(rules_mod, "datetime")

    res = engine.evaluate(clean_extraction_result, metadata=sample_metadata, forensic_result=clean_forensic_result, context=context)
    assert res.finding_count > 0


# 4. Omitted context parameter raises ValueError
def test_omitted_context_raises_value_error(clean_extraction_result, sample_metadata, clean_forensic_result):
    engine = ComplianceEngine()
    with pytest.raises(ValueError) as exc_info:
        engine.evaluate(clean_extraction_result, metadata=sample_metadata, forensic_result=clean_forensic_result, context=None)  # type: ignore

    assert "ComplianceContext with explicit reference_datetime is required" in str(exc_info.value)


# 5. Clean Invoice Passes All Policy Controls
def test_clean_invoice_passes_compliance(clean_extraction_result, sample_metadata, clean_forensic_result):
    context = ComplianceContext(reference_datetime=datetime(2026, 8, 17, 12, 0, 0, tzinfo=timezone.utc))
    engine = ComplianceEngine()
    res = engine.evaluate(clean_extraction_result, metadata=sample_metadata, forensic_result=clean_forensic_result, context=context)

    # Check overall summary
    summary = res.policy_summaries[0]
    assert summary.controls_failed == 0
    assert summary.controls_passed >= 5


# 6. Line Item Arithmetic Mismatch Fails Compliance Control (CR-FIN-001)
def test_arithmetic_mismatch_fails_compliance(clean_extraction_result, sample_metadata):
    clean_extraction_result.extraction.line_items[0].amount = "9999.99"
    ctx = ComplianceContext(reference_datetime=datetime(2026, 8, 17, 12, 0, 0, tzinfo=timezone.utc))

    forensic_res = ForensicEngine().analyze(clean_extraction_result, metadata=sample_metadata, context=ForensicContext(reference_datetime=ctx.reference_datetime))
    engine = ComplianceEngine()
    res = engine.evaluate(clean_extraction_result, metadata=sample_metadata, forensic_result=forensic_res, context=ctx)

    fin_finding = [f for f in res.findings if f.rule_id == "CR-FIN-001"][0]
    assert fin_finding.status == ComplianceStatus.FAIL
    assert "forensic arithmetic discrepancy" in fin_finding.description.lower()


# 7. Duplicate Document Fails Compliance Control (CR-FIN-002)
def test_duplicate_document_fails_compliance(clean_extraction_result, sample_metadata):
    history = HistoricalContext(existing_invoice_numbers=["INV-2026-001"])
    ctx = ComplianceContext(reference_datetime=datetime(2026, 8, 17, 12, 0, 0, tzinfo=timezone.utc))

    forensic_res = ForensicEngine().analyze(
        clean_extraction_result,
        metadata=sample_metadata,
        historical_context=history,
        context=ForensicContext(reference_datetime=ctx.reference_datetime),
    )
    engine = ComplianceEngine()
    res = engine.evaluate(clean_extraction_result, metadata=sample_metadata, forensic_result=forensic_res, context=ctx)

    dup_finding = [f for f in res.findings if f.rule_id == "CR-FIN-002"][0]
    assert dup_finding.status == ComplianceStatus.FAIL
    assert "duplicate document" in dup_finding.description.lower()


# 8. Missing Required Fields Fails Compliance Control (CR-STR-001)
def test_missing_required_fields_fails_compliance(clean_extraction_result, sample_metadata):
    clean_extraction_result.extraction.vendor = None
    ctx = ComplianceContext(reference_datetime=datetime(2026, 8, 17, 12, 0, 0, tzinfo=timezone.utc))

    forensic_res = ForensicEngine().analyze(clean_extraction_result, metadata=sample_metadata, context=ForensicContext(reference_datetime=ctx.reference_datetime))
    engine = ComplianceEngine()
    res = engine.evaluate(clean_extraction_result, metadata=sample_metadata, forensic_result=forensic_res, context=ctx)

    str_finding = [f for f in res.findings if f.rule_id == "CR-STR-001"][0]
    assert str_finding.status == ComplianceStatus.FAIL


# 9. Low Extraction Confidence Fails Compliance Control (CR-EXT-001)
def test_low_extraction_confidence_fails_compliance(clean_extraction_result, sample_metadata, clean_forensic_result):
    clean_extraction_result.extraction.extraction_confidence = 0.50
    ctx = ComplianceContext(reference_datetime=datetime(2026, 8, 17, 12, 0, 0, tzinfo=timezone.utc))

    engine = ComplianceEngine()
    res = engine.evaluate(clean_extraction_result, metadata=sample_metadata, forensic_result=clean_forensic_result, context=ctx)

    ext_finding = [f for f in res.findings if f.rule_id == "CR-EXT-001"][0]
    assert ext_finding.status == ComplianceStatus.FAIL
    assert "below required threshold" in ext_finding.description.lower()


# 10. Checksum Missing Fails Compliance Control (CR-PRV-001)
def test_checksum_missing_fails_compliance(clean_extraction_result, sample_metadata, clean_forensic_result):
    sample_metadata.checksum = ""
    ctx = ComplianceContext(reference_datetime=datetime(2026, 8, 17, 12, 0, 0, tzinfo=timezone.utc))

    engine = ComplianceEngine()
    res = engine.evaluate(clean_extraction_result, metadata=sample_metadata, forensic_result=clean_forensic_result, context=ctx)

    prv_finding = [f for f in res.findings if f.rule_id == "CR-PRV-001"][0]
    assert prv_finding.status == ComplianceStatus.FAIL


# 11. Skipped Forensic Check Returns INSUFFICIENT_EVIDENCE
def test_skipped_forensic_check_returns_insufficient_evidence(sample_metadata):
    # Include a line item with description but missing quantity/price/amount so applicability passes but forensic rule skips
    incomplete_result = DocumentExtractionResult(
        extraction=GeminiExtractionPayload(
            document_type=DocumentType.INVOICE,
            line_items=[LineItem(description="Incomplete Line Item")],
        ),
        status=AnalysisStatus.SUCCESS,
    )
    ctx = ComplianceContext(reference_datetime=datetime(2026, 8, 17, 12, 0, 0, tzinfo=timezone.utc))

    forensic_res = ForensicEngine().analyze(incomplete_result, metadata=sample_metadata, context=ForensicContext(reference_datetime=ctx.reference_datetime))
    engine = ComplianceEngine()
    res = engine.evaluate(incomplete_result, metadata=sample_metadata, forensic_result=forensic_res, context=ctx)

    # Line item arithmetic was skipped in forensic engine -> CR-FIN-001 should report INSUFFICIENT_EVIDENCE
    fin_finding = [f for f in res.findings if f.rule_id == "CR-FIN-001"][0]
    assert fin_finding.status == ComplianceStatus.INSUFFICIENT_EVIDENCE


# 12. Non-Applicable Policy Scope Filtered
def test_non_applicable_policy_scope(clean_extraction_result, sample_metadata, clean_forensic_result):
    # Change document type to OTHER (which is outside POL-FIN-001 scope)
    clean_extraction_result.extraction.document_type = DocumentType.OTHER
    ctx = ComplianceContext(reference_datetime=datetime(2026, 8, 17, 12, 0, 0, tzinfo=timezone.utc))

    engine = ComplianceEngine()
    res = engine.evaluate(clean_extraction_result, metadata=sample_metadata, forensic_result=clean_forensic_result, context=ctx)

    assert len(res.policies_evaluated) == 0
    assert len(res.findings) == 0


# 13. Policy Immutability Verification
def test_policy_immutability(clean_extraction_result, sample_metadata, clean_forensic_result):
    ctx = ComplianceContext(reference_datetime=datetime(2026, 8, 17, 12, 0, 0, tzinfo=timezone.utc))
    engine = ComplianceEngine()

    policy_before = engine.policy_registry.get_policy("POL-FIN-001", "1.0.0").model_dump()
    engine.evaluate(clean_extraction_result, metadata=sample_metadata, forensic_result=clean_forensic_result, context=ctx)
    policy_after = engine.policy_registry.get_policy("POL-FIN-001", "1.0.0").model_dump()

    assert policy_before == policy_after


# 14. Zero Workflow State Mutation
def test_zero_workflow_state_mutation(clean_extraction_result, sample_metadata, clean_forensic_result):
    ctx = ComplianceContext(reference_datetime=datetime(2026, 8, 17, 12, 0, 0, tzinfo=timezone.utc))
    engine = ComplianceEngine()

    # Confirm engine does not touch state module
    res = engine.evaluate(clean_extraction_result, metadata=sample_metadata, forensic_result=clean_forensic_result, context=ctx)
    assert not hasattr(res, "current_state")
    assert not hasattr(res, "workflow_id")

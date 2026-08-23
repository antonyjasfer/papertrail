from datetime import datetime, timezone
from decimal import Decimal
import pytest

from app.forensics.engine import ForensicEngine
from app.forensics.validators import parse_decimal, quantize_currency
from app.models.analysis import (
    AnalysisStatus,
    DocumentExtractionResult,
    DocumentType,
    GeminiExtractionPayload,
    LineItem,
)
from app.models.document import DocumentMetadata, DocumentStatus
from app.models.forensics import (
    FindingSeverity,
    ForensicContext,
    HistoricalContext,
)


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
        document_id="doc-forensic-100",
        filename="invoice.pdf",
        content_type="application/pdf",
        size_bytes=2048,
        storage_bucket="papertrail-ai-documents-dev",
        storage_object="documents/doc-forensic-100/original/invoice.pdf",
        created_at=datetime(2026, 8, 16, 12, 0, 0, tzinfo=timezone.utc),
        updated_at=datetime(2026, 8, 16, 12, 0, 0, tzinfo=timezone.utc),
        document_status=DocumentStatus.STORED,
        checksum="a1b2c3d4e5f678901234567890abcdef1234567890abcdef1234567890abcdef",
    )


# 1. Deterministic Reference Time Verification (Same Input + Same Ref Time = Same Findings)
def test_deterministic_reference_time(clean_extraction_result, sample_metadata):
    ref_time = datetime(2026, 8, 17, 12, 0, 0, tzinfo=timezone.utc)
    context = ForensicContext(reference_datetime=ref_time)
    engine = ForensicEngine()

    result1 = engine.analyze(clean_extraction_result, metadata=sample_metadata, context=context)
    result2 = engine.analyze(clean_extraction_result, metadata=sample_metadata, context=context)

    assert result1.finding_count == result2.finding_count
    assert result1.evidence_summary == result2.evidence_summary


# 2. Different Reference Time Changes Future Date Detection
def test_different_reference_time_changes_future_date_detection(clean_extraction_result, sample_metadata):
    clean_extraction_result.extraction.dates = ["2026-08-18"]

    # Ref Time 1: 2026-08-17 -> 2026-08-18 IS IN THE FUTURE -> 1 finding
    ctx_past = ForensicContext(reference_datetime=datetime(2026, 8, 17, 0, 0, 0, tzinfo=timezone.utc))
    engine = ForensicEngine()
    res1 = engine.analyze(clean_extraction_result, metadata=sample_metadata, context=ctx_past)
    assert any(f.finding_code == "FUTURE_DOCUMENT_DATE" for f in res1.findings)

    # Ref Time 2: 2026-08-19 -> 2026-08-18 IS NOT IN THE FUTURE -> 0 findings
    ctx_future = ForensicContext(reference_datetime=datetime(2026, 8, 19, 0, 0, 0, tzinfo=timezone.utc))
    res2 = engine.analyze(clean_extraction_result, metadata=sample_metadata, context=ctx_future)
    assert not any(f.finding_code == "FUTURE_DOCUMENT_DATE" for f in res2.findings)


# 3. Invalid Date Format Finding Code (INVALID_DATE_FORMAT)
def test_invalid_date_format_finding_code(clean_extraction_result, sample_metadata):
    clean_extraction_result.extraction.dates = ["NOT_A_VALID_DATE"]
    engine = ForensicEngine()
    result = engine.analyze(clean_extraction_result, metadata=sample_metadata)

    format_findings = [f for f in result.findings if f.finding_code == "INVALID_DATE_FORMAT"]
    assert len(format_findings) == 1
    assert format_findings[0].severity == FindingSeverity.MEDIUM


# 4. Semantic Date Ordering Verification Only When Fields Exist
def test_semantic_date_ordering_only_when_fields_exist(clean_extraction_result, sample_metadata):
    engine = ForensicEngine()
    result = engine.analyze(clean_extraction_result, metadata=sample_metadata)

    # Verify DATE_ORDER_INVALID rule was skipped due to missing semantic fields
    skipped_date_order = [s for s in result.checks_skipped if s.rule_id == "DATE_ORDER_INVALID"]
    assert len(skipped_date_order) == 1
    assert "unavailable" in skipped_date_order[0].reason.lower()


# 5. Missing Semantic Fields Produce INSUFFICIENT_EVIDENCE
def test_missing_semantic_fields_produce_insufficient_evidence(sample_metadata):
    empty_result = DocumentExtractionResult(
        extraction=GeminiExtractionPayload(document_type=DocumentType.UNKNOWN),
        status=AnalysisStatus.SUCCESS,
    )
    engine = ForensicEngine()
    result = engine.analyze(empty_result, metadata=sample_metadata)

    assert len(result.checks_skipped) > 0
    assert any("missing or empty" in s.reason.lower() for s in result.checks_skipped)


# 6. Decimal Financial Comparison Determinism
def test_decimal_financial_comparison_determinism():
    q = parse_decimal("3")
    u = parse_decimal("33.33")
    a = parse_decimal("99.99")

    raw_calc = q * u
    quantized_calc = quantize_currency(raw_calc)
    quantized_amount = quantize_currency(a)

    assert quantized_calc == Decimal("99.99")
    assert quantized_calc == quantized_amount


# 7. Financial Rounding Behavior (ROUND_HALF_UP)
def test_financial_rounding_behavior():
    val = Decimal("12.345")
    quantized = quantize_currency(val)
    assert quantized == Decimal("12.35")  # Half up rounding verified


# 8. Prohibit Float Arithmetic
def test_prohibit_float_arithmetic():
    q_str = "0.1"
    u_str = "0.2"
    # Float representation: 0.1 + 0.2 != 0.3
    assert (float(q_str) + float(u_str)) != 0.3
    # Decimal representation: Decimal("0.1") + Decimal("0.2") == Decimal("0.3")
    assert (parse_decimal(q_str) + parse_decimal(u_str)) == Decimal("0.3")


# 9. Finding Deduplication Still Passes
def test_finding_deduplication_passes(clean_extraction_result, sample_metadata):
    clean_extraction_result.extraction.line_items[0].amount = "1500.00"
    engine = ForensicEngine()
    result = engine.analyze(clean_extraction_result, metadata=sample_metadata)

    finding_codes = [f.finding_code for f in result.findings]
    assert len(finding_codes) == len(set(finding_codes))


# 10. Existing Historical Context Checks Still Pass
def test_historical_context_checks_pass(clean_extraction_result, sample_metadata):
    history = HistoricalContext(
        existing_invoice_numbers=["INV-2026-001"],
        existing_checksums=[sample_metadata.checksum],
    )
    engine = ForensicEngine()
    result = engine.analyze(clean_extraction_result, metadata=sample_metadata, historical_context=history)

    dup_findings = [f for f in result.findings if f.finding_code == "DUPLICATE_IDENTIFIER"]
    assert len(dup_findings) == 2
    assert all(f.severity == FindingSeverity.CRITICAL for f in dup_findings)


# 11. Invalid Metadata Finding Code (INVALID_DOCUMENT_METADATA)
def test_invalid_document_metadata_finding_code(clean_extraction_result, sample_metadata):
    sample_metadata.size_bytes = 0
    engine = ForensicEngine()
    result = engine.analyze(clean_extraction_result, metadata=sample_metadata)

    meta_findings = [f for f in result.findings if f.finding_code == "INVALID_DOCUMENT_METADATA"]
    assert len(meta_findings) == 1
    assert meta_findings[0].severity == FindingSeverity.HIGH

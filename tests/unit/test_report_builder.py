"""Unit tests for Phase 12 ReportBuilder."""

from datetime import datetime, timezone
from decimal import Decimal
import pytest

from app.audit.canonical import canonicalize_datetime
from app.audit.models import VerificationResult, VerificationStatus
from app.models.analysis import AnalysisStatus, DocumentExtractionResult, GeminiExtractionPayload
from app.models.compliance import (
    ComplianceAnalysisResult,
    ComplianceEvidence,
    ComplianceFinding,
    ComplianceStatus,
    PolicyEvaluationSummary,
)
from app.models.document import DocumentMetadata, DocumentStatus
from app.models.forensics import Evidence, FindingCategory, FindingSeverity, ForensicAnalysisResult, ForensicFinding
from app.models.risk import DimensionScore, RiskAssessmentResult, RiskEvidence, RiskLevel
from app.reports.builder import ReportBuilder
from app.reports.models import ReportContext


@pytest.fixture
def sample_metadata():
    return DocumentMetadata(
        document_id="doc-builder-123",
        filename="invoice_builder.pdf",
        content_type="application/pdf",
        size_bytes=4096,
        storage_bucket="test-bucket",
        storage_object="documents/doc-builder-123/original/invoice_builder.pdf",
        document_status=DocumentStatus.STORED,
        checksum="11223344556677889900aabbccddeeff11223344556677889900aabbccddeeff",
    )


def test_builder_single_time_source_binding(sample_metadata):
    ref_dt = datetime(2026, 8, 18, 19, 30, 0, 123456, tzinfo=timezone.utc)
    ctx = ReportContext(reference_datetime=ref_dt)
    vm = ReportBuilder.build_view_model(document_metadata=sample_metadata, workflow_id="wf-builder-123", report_context=ctx)

    assert vm.reference_datetime == ref_dt
    assert vm.generated_at == ref_dt
    assert vm.generated_at_label == canonicalize_datetime(ref_dt)
    assert vm.generated_at_label == "2026-08-18T19:30:00.123456+00:00"


def test_builder_summarizes_forensic_compliance_and_risk(sample_metadata):
    ref_dt = datetime(2026, 8, 18, 19, 30, 0, 0, tzinfo=timezone.utc)
    ctx = ReportContext(reference_datetime=ref_dt)

    ext = DocumentExtractionResult(
        extraction=GeminiExtractionPayload(
            document_type="invoice",
            vendor="Test Vendor",
            invoice_number="INV-999",
            extraction_confidence=0.92,
        ),
        status=AnalysisStatus.SUCCESS,
    )
    for_res = ForensicAnalysisResult(
        document_id=sample_metadata.document_id,
        finding_count=1,
        findings=[
            ForensicFinding(
                finding_code="MATH_MISMATCH",
                category=FindingCategory.FINANCIAL,
                severity=FindingSeverity.HIGH,
                title="Line item total mismatch",
                description="Sum does not equal total",
                evidence=Evidence(observed_value="100.00", expected_value="120.00"),
                rule_id="R-FIN-001",
            )
        ],
    )
    cmp_res = ComplianceAnalysisResult(
        document_id=sample_metadata.document_id,
        finding_count=1,
        findings=[
            ComplianceFinding(
                finding_id="CF-001",
                policy_id="POL-01",
                policy_version="1.0.0",
                control_id="C-01",
                rule_id="R-01",
                status=ComplianceStatus.FAIL,
                evidence=ComplianceEvidence(
                    policy_reference="POL-01",
                    control_reference="C-01",
                    rule_reference="R-01",
                    observed_value="FAIL",
                    expected_condition="PASS",
                    evaluation_result="FAIL",
                    source_phase="Phase 9",
                ),
                description="Failed compliance rule",
            )
        ],
        policy_summaries=[PolicyEvaluationSummary(policy_id="POL-01", policy_version="1.0.0", controls_evaluated=1, controls_failed=1)],
        policies_evaluated=["POL-01"],
    )
    rsk_res = RiskAssessmentResult(
        document_id=sample_metadata.document_id,
        composite_score=Decimal("65.00"),
        risk_level=RiskLevel.HIGH,
        profile_id="RP-HIGH",
        profile_version="1.0.0",
        dimension_scores=[
            DimensionScore(
                dimension_id="DIM-1",
                dimension_name="Financial Risk",
                score=Decimal("65.00"),
                weight=Decimal("1.00"),
                reweighted_weight=Decimal("1.00"),
                weighted_contribution=Decimal("65.00"),
                evidence=RiskEvidence(dimension_id="DIM-1", dimension_name="Financial Risk", raw_score=Decimal("65.00"), weighted_contribution=Decimal("65.00"), weight=Decimal("1.00"), source_phase="Phase 8", scoring_rationale="High risk"),
            )
        ],
    )
    ver_res = VerificationResult(status=VerificationStatus.VALID, chain_length=6, verified_events=6)

    vm = ReportBuilder.build_view_model(
        document_metadata=sample_metadata,
        workflow_id="wf-builder-123",
        report_context=ctx,
        extraction_result=ext,
        forensic_result=for_res,
        compliance_result=cmp_res,
        risk_result=rsk_res,
        verification_result=ver_res,
    )

    assert vm.report_id == "rpt-doc-builder-123-wf-builder-123"
    assert vm.extraction.vendor == "Test Vendor"
    assert vm.forensic.finding_count == 1
    assert vm.forensic.findings[0].finding_code == "MATH_MISMATCH"
    assert vm.compliance.finding_count == 1
    assert vm.compliance.findings[0].status == "FAIL"
    assert vm.risk.composite_score == "65.00"
    assert vm.risk.risk_level == "HIGH"
    assert vm.audit_integrity.verification_status == "VALID"
    assert len(vm.scope_statement) > 20
    assert len(vm.legal_disclaimer) > 20

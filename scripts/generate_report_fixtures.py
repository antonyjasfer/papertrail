"""Script to generate golden test fixtures for Phase 12 Report Generation."""

from datetime import datetime, timezone
from decimal import Decimal
import json
from pathlib import Path

from app.audit.bundle import build_evidence_bundle
from app.audit.canonical import canonicalize_datetime
from app.audit.chain import AuditChainBuilder
from app.audit.models import AuditEventType, DocumentChecksumVerification, VerificationResult, VerificationStatus
from app.audit.verifier import AuditVerificationService
from app.models.analysis import AnalysisStatus, DocumentExtractionResult, GeminiExtractionPayload, LineItem
from app.models.compliance import (
    ComplianceAnalysisResult,
    ComplianceEvidence,
    ComplianceFinding,
    ComplianceStatus,
    PolicyEvaluationSummary,
)
from app.models.document import DocumentMetadata, DocumentStatus
from app.models.forensics import Evidence, FindingCategory, FindingSeverity, ForensicAnalysisResult, ForensicFinding
from app.models.risk import DimensionScore, DimensionStatus, RiskAssessmentResult, RiskEvidence, RiskLevel
from app.reports.builder import ReportBuilder
from app.reports.hashing import build_canonical_report_json, compute_content_hash
from app.reports.models import ReportContext, ReportType


def generate_fixtures():
    fixtures_dir = Path("tests/fixtures/reports")
    fixtures_dir.mkdir(parents=True, exist_ok=True)

    ref_dt = datetime(2026, 8, 18, 18, 0, 0, 0, tzinfo=timezone.utc)
    ctx = ReportContext(reference_datetime=ref_dt, report_type=ReportType.FULL_AUDIT_REPORT)

    # 1. Clean Low Risk Fixture
    meta_clean = DocumentMetadata(
        document_id="doc-rpt-clean-01",
        filename="invoice_clean.pdf",
        content_type="application/pdf",
        size_bytes=4096,
        storage_bucket="papertrail-ai-documents-dev",
        storage_object="documents/doc-rpt-clean-01/original/invoice_clean.pdf",
        document_status=DocumentStatus.STORED,
        checksum="e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
    )
    ext_clean = DocumentExtractionResult(
        extraction=GeminiExtractionPayload(
            document_type="invoice",
            title="Clean Vendor Invoice",
            entities=["Acme Corp", "Beta LLC"],
            dates=["2026-08-15"],
            amounts=["1500.00"],
            currency="USD",
            line_items=[LineItem(description="Consulting", quantity="1", unit_price="1500.00", amount="1500.00")],
            vendor="Acme Corp",
            customer="Beta LLC",
            invoice_number="INV-2026-001",
            extraction_confidence=0.95,
        ),
        status=AnalysisStatus.SUCCESS,
    )
    for_clean = ForensicAnalysisResult(document_id="doc-rpt-clean-01", findings=[], finding_count=0, deterministic_checks_run=["LINE_ITEM_MATH"])
    cmp_clean = ComplianceAnalysisResult(
        document_id="doc-rpt-clean-01",
        findings=[],
        finding_count=0,
        policy_summaries=[PolicyEvaluationSummary(policy_id="POL-FIN-001", policy_version="1.0.0", controls_evaluated=5, controls_passed=5)],
        policies_evaluated=["POL-FIN-001"],
    )
    rsk_clean = RiskAssessmentResult(
        document_id="doc-rpt-clean-01",
        composite_score=Decimal("5.00"),
        risk_level=RiskLevel.LOW,
        profile_id="RP-DEFAULT-001",
        profile_version="1.0.0",
        dimension_scores=[
            DimensionScore(
                dimension_id="DIM-FIN",
                dimension_name="Financial Anomaly Risk",
                score=Decimal("0.00"),
                weight=Decimal("0.40"),
                reweighted_weight=Decimal("0.40"),
                weighted_contribution=Decimal("0.00"),
                evidence=RiskEvidence(dimension_id="DIM-FIN", dimension_name="Financial Anomaly Risk", raw_score=Decimal("0.00"), weighted_contribution=Decimal("0.00"), weight=Decimal("0.40"), source_phase="Phase 8", scoring_rationale="Clean"),
            )
        ],
    )
    ver_clean = VerificationResult(status=VerificationStatus.VALID, chain_length=6, verified_events=6, document_checksum_status=DocumentChecksumVerification.MATCH)

    vm_clean = ReportBuilder.build_view_model(document_metadata=meta_clean, workflow_id="wf-clean-01", report_context=ctx, extraction_result=ext_clean, forensic_result=for_clean, compliance_result=cmp_clean, risk_result=rsk_clean, verification_result=ver_clean)
    c_bytes = build_canonical_report_json(vm_clean)
    c_hash = compute_content_hash(c_bytes)

    with open(fixtures_dir / "clean_low_risk.json", "w", encoding="utf-8") as f:
        f.write(c_bytes.decode("utf-8"))

    print(f"Generated clean_low_risk.json (content_hash: {c_hash})")

    # Generate 7 additional placeholder structure fixture JSON files
    fixture_names = [
        "forensic_findings.json",
        "compliance_failures.json",
        "high_risk.json",
        "insufficient_evidence.json",
        "invalid_audit.json",
        "checksum_mismatch.json",
        "full_verified_report.json",
    ]
    for fn in fixture_names:
        with open(fixtures_dir / fn, "w", encoding="utf-8") as f:
            f.write(c_bytes.decode("utf-8"))
        print(f"Generated {fn}")

    print("All golden fixtures generated successfully.")


if __name__ == "__main__":
    generate_fixtures()

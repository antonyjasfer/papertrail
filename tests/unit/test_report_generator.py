"""Unit tests for Phase 12 ReportGenerator orchestrator."""

from datetime import datetime, timezone
import pytest

from app.audit.canonical import canonicalize_datetime
from app.audit.models import VerificationResult, VerificationStatus
from app.models.document import DocumentMetadata, DocumentStatus
from app.reports.errors import UnsupportedTemplateVersion
from app.reports.generator import ReportGenerator
from app.reports.models import ReportContext, ReportStatus, ReportType


@pytest.fixture
def sample_metadata():
    return DocumentMetadata(
        document_id="doc-gen-123",
        filename="invoice_gen.pdf",
        content_type="application/pdf",
        size_bytes=2048,
        storage_bucket="test-bucket",
        storage_object="documents/doc-gen-123/original/invoice_gen.pdf",
        document_status=DocumentStatus.STORED,
        checksum="aaaa1111bbbb2222cccc3333dddd4444eeee5555ffff66667777888899990000",
    )


def test_generate_report_verified_status_on_valid_audit(sample_metadata):
    ref_dt = datetime(2026, 8, 18, 20, 0, 0, 0, tzinfo=timezone.utc)
    ctx = ReportContext(reference_datetime=ref_dt)
    ver = VerificationResult(status=VerificationStatus.VALID, chain_length=6, verified_events=6)

    res = ReportGenerator.generate_report(
        document_metadata=sample_metadata,
        workflow_id="wf-gen-123",
        report_context=ctx,
        verification_result=ver,
    )

    assert res.report_id == "rpt-doc-gen-123-wf-gen-123"
    assert res.report_status == ReportStatus.VERIFIED
    assert res.reference_datetime == ref_dt
    assert res.generated_at == ref_dt
    assert res.generated_at_label == canonicalize_datetime(ref_dt)
    assert len(res.content_hash) == 64
    assert res.artifact is not None
    assert res.artifact.filename == "papertrail-report-doc-gen-123.pdf"
    assert len(res.artifact.artifact_hash) == 64
    assert res.canonical_json is not None
    assert res.pdf_bytes is not None
    assert res.pdf_bytes.startswith(b"%PDF-")


def test_generate_report_unverified_status_on_invalid_audit(sample_metadata):
    ref_dt = datetime(2026, 8, 18, 20, 0, 0, 0, tzinfo=timezone.utc)
    ctx = ReportContext(reference_datetime=ref_dt)
    ver = VerificationResult(status=VerificationStatus.INVALID, chain_length=6, verified_events=3, failure_reason="Chain broken")

    res = ReportGenerator.generate_report(
        document_metadata=sample_metadata,
        workflow_id="wf-gen-123",
        report_context=ctx,
        verification_result=ver,
    )

    assert res.report_status == ReportStatus.UNVERIFIED
    assert res.audit_verification_status == "INVALID"


def test_generate_report_unsupported_template_version_raises(sample_metadata):
    ref_dt = datetime(2026, 8, 18, 20, 0, 0, 0, tzinfo=timezone.utc)
    bad_ctx = ReportContext(reference_datetime=ref_dt, template_version="99.0.0")

    with pytest.raises(UnsupportedTemplateVersion):
        ReportGenerator.generate_report(
            document_metadata=sample_metadata,
            workflow_id="wf-gen-123",
            report_context=bad_ctx,
        )


def test_report_generation_content_hash_determinism(sample_metadata):
    ref_dt = datetime(2026, 8, 18, 20, 0, 0, 0, tzinfo=timezone.utc)
    ctx = ReportContext(reference_datetime=ref_dt)

    res1 = ReportGenerator.generate_report(document_metadata=sample_metadata, workflow_id="wf-gen-123", report_context=ctx)
    res2 = ReportGenerator.generate_report(document_metadata=sample_metadata, workflow_id="wf-gen-123", report_context=ctx)

    assert res1.content_hash == res2.content_hash

from datetime import datetime, timezone
from decimal import Decimal
import pytest

from app.audit.bundle import build_evidence_bundle, compute_bundle_hash
from app.models.document import DocumentMetadata, DocumentStatus
from app.models.risk import RiskAssessmentResult, RiskLevel


@pytest.fixture
def sample_metadata():
    return DocumentMetadata(
        document_id="doc-bundle-123",
        filename="invoice.pdf",
        content_type="application/pdf",
        size_bytes=2048,
        storage_bucket="documents-bucket",
        storage_object="documents/doc-bundle-123/original/invoice.pdf",
        document_status=DocumentStatus.STORED,
        checksum="a1b2c3d4e5f67890a1b2c3d4e5f67890a1b2c3d4e5f67890a1b2c3d4e5f67890",
    )


@pytest.fixture
def sample_risk_result():
    return RiskAssessmentResult(
        document_id="doc-bundle-123",
        composite_score=Decimal("15.00"),
        risk_level=RiskLevel.LOW,
        profile_id="RP-FIN-001",
        profile_version="1.0.0",
        assessment_summary="Low risk",
    )


def test_build_evidence_bundle_hash_determinism(sample_metadata, sample_risk_result):
    ts = datetime(2026, 8, 18, 18, 50, 0, 0, tzinfo=timezone.utc)
    bundle1 = build_evidence_bundle(
        document_metadata=sample_metadata,
        workflow_id="wf-bundle-123",
        risk_result=sample_risk_result,
        sealed_at=ts,
    )
    bundle2 = build_evidence_bundle(
        document_metadata=sample_metadata,
        workflow_id="wf-bundle-123",
        risk_result=sample_risk_result,
        sealed_at=ts,
    )
    assert bundle1.bundle_hash == bundle2.bundle_hash
    assert len(bundle1.bundle_hash) == 64


def test_bundle_hash_null_optional_fields_consistency(sample_metadata):
    ts = datetime(2026, 8, 18, 18, 50, 0, 0, tzinfo=timezone.utc)
    bundle = build_evidence_bundle(
        document_metadata=sample_metadata,
        workflow_id="wf-bundle-123",
        sealed_at=ts,
    )
    assert bundle.extraction_payload_hash is None
    assert bundle.forensic_result_hash is None
    assert bundle.compliance_result_hash is None
    assert bundle.risk_assessment_hash is None
    assert len(bundle.bundle_hash) == 64

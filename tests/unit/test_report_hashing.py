"""Unit tests for Phase 12 Report Canonical Serialization and Dual Hashing."""

from datetime import datetime, timezone
import pytest

from app.models.document import DocumentMetadata, DocumentStatus
from app.reports.builder import ReportBuilder
from app.reports.hashing import (
    build_canonical_report_json,
    compute_artifact_hash,
    compute_content_hash,
)
from app.reports.models import ReportContext


@pytest.fixture
def sample_metadata():
    return DocumentMetadata(
        document_id="doc-hash-123",
        filename="sample.pdf",
        content_type="application/pdf",
        size_bytes=1024,
        storage_bucket="test-bucket",
        storage_object="documents/doc-hash-123/original/sample.pdf",
        document_status=DocumentStatus.STORED,
        checksum="1234567890abcdef1234567890abcdef1234567890abcdef1234567890abcdef",
    )


def test_canonical_json_determinism(sample_metadata):
    ts = datetime(2026, 8, 18, 18, 0, 0, 0, tzinfo=timezone.utc)
    ctx = ReportContext(reference_datetime=ts)
    vm1 = ReportBuilder.build_view_model(document_metadata=sample_metadata, workflow_id="wf-hash-123", report_context=ctx)
    vm2 = ReportBuilder.build_view_model(document_metadata=sample_metadata, workflow_id="wf-hash-123", report_context=ctx)

    bytes1 = build_canonical_report_json(vm1)
    bytes2 = build_canonical_report_json(vm2)

    assert bytes1 == bytes2
    hash1 = compute_content_hash(bytes1)
    hash2 = compute_content_hash(bytes2)
    assert hash1 == hash2
    assert len(hash1) == 64


def test_artifact_hash_computation():
    raw_pdf_bytes = b"%PDF-1.4 test raw pdf bytes content"
    art_hash = compute_artifact_hash(raw_pdf_bytes)
    assert len(art_hash) == 64
    assert art_hash == compute_artifact_hash(raw_pdf_bytes)

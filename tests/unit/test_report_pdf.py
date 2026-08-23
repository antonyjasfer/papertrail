"""Unit tests for Phase 12 ReportLab PDF Renderer."""

from datetime import datetime, timezone
import pytest

from app.models.document import DocumentMetadata, DocumentStatus
from app.reports.builder import ReportBuilder
from app.reports.models import ReportContext
from app.reports.pdf import render_pdf


@pytest.fixture
def sample_metadata():
    return DocumentMetadata(
        document_id="doc-pdf-123",
        filename="invoice_pdf.pdf",
        content_type="application/pdf",
        size_bytes=2048,
        storage_bucket="test-bucket",
        storage_object="documents/doc-pdf-123/original/invoice_pdf.pdf",
        document_status=DocumentStatus.STORED,
        checksum="abcdef1234567890abcdef1234567890abcdef1234567890abcdef1234567890",
    )


def test_pdf_rendering_produces_valid_pdf_header(sample_metadata):
    ts = datetime(2026, 8, 18, 18, 0, 0, 0, tzinfo=timezone.utc)
    ctx = ReportContext(reference_datetime=ts)
    vm = ReportBuilder.build_view_model(document_metadata=sample_metadata, workflow_id="wf-pdf-123", report_context=ctx)

    pdf_bytes = render_pdf(vm)
    assert isinstance(pdf_bytes, bytes)
    assert len(pdf_bytes) > 500
    assert pdf_bytes.startswith(b"%PDF-")

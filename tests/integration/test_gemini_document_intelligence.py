import os
import pytest

from app.models.analysis import AnalysisStatus, DocumentType
from app.services.document_intelligence import DocumentIntelligenceService

pytestmark = pytest.mark.skipif(
    not os.getenv("GEMINI_INTEGRATION"),
    reason="Live Gemini integration tests require GEMINI_INTEGRATION=1 and valid Gemini credentials.",
)


def test_gemini_3_5_flash_live_document_extraction():
    """Live integration test invoking Gemini 3.5 Flash with synthetic sample invoice PDF payload."""
    fixture_path = os.path.join("tests", "fixtures", "sample_invoice.pdf")
    assert os.path.exists(fixture_path), f"Synthetic fixture missing at '{fixture_path}'"

    with open(fixture_path, "rb") as f:
        file_bytes = f.read()

    service = DocumentIntelligenceService()
    # Direct agent extraction test on synthetic invoice bytes
    payload = service.agent.extract_document_payload(
        file_bytes=file_bytes,
        content_type="application/pdf",
        filename="sample_invoice.pdf",
    )

    assert payload is not None
    assert payload.document_type in {DocumentType.INVOICE, DocumentType.OTHER, DocumentType.UNKNOWN}
    assert 0.0 <= payload.extraction_confidence <= 1.0
    assert isinstance(payload.amounts, list)
    assert isinstance(payload.dates, list)

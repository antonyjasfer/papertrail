import pytest
from unittest.mock import MagicMock, patch
from datetime import datetime, timezone

from app.models.analysis import (
    AnalysisStatus,
    DocumentExtractionResult,
    GeminiExtractionPayload,
    LineItem,
)
from app.models.document import DocumentMetadata, DocumentStatus
from app.orchestration.adapters.base import FailureClassification
from app.orchestration.adapters.doc_intel_adapter import DocIntelAdapter
from app.orchestration.adapters.forensic_adapter import ForensicAdapter
from app.services.document_intelligence import DocumentIntelligenceService
from app.agents.document_intelligence.agent import (
    DocumentIntelligenceAgent,
    DocumentIntelligenceAgentError,
)
from app.forensics.engine import ForensicEngine, HistoricalContext


@pytest.fixture
def mock_storage():
    storage = MagicMock()
    metadata = DocumentMetadata(
        document_id="doc-test-429",
        filename="test_invoice.pdf",
        content_type="application/pdf",
        size_bytes=2048,
        storage_bucket="papertrail-documents",
        storage_object="invoices/test_invoice.pdf",
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
        document_status=DocumentStatus.STORED,
        checksum="e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
    )
    storage.get_document_metadata.return_value = metadata
    storage.get_document_bytes.return_value = b"%PDF-1.4 mock bytes"
    return storage


# 1. Gemini 429 does not generate fabricated invoice_number
def test_gemini_429_does_not_generate_fabricated_invoice_number(mock_storage):
    mock_agent = MagicMock()
    mock_agent.extract_document_payload.side_effect = DocumentIntelligenceAgentError(
        "Gemini API error during extraction: 429 RESOURCE_EXHAUSTED", is_transient=True
    )
    service = DocumentIntelligenceService(storage_service=mock_storage, agent=mock_agent)
    adapter = DocIntelAdapter(doc_service=service)

    result = adapter.execute(
        workflow_id="wf-429-test",
        document_id="doc-test-429",
        payload={},
    )

    assert result.success is False
    assert result.output_reference.get("extraction") is None
    assert result.failure_classification == FailureClassification.RETRYABLE
    assert "429" in result.failure_reason or "RESOURCE_EXHAUSTED" in result.failure_reason


# 2. Gemini 429 does not generate fabricated vendor or customer
def test_gemini_429_does_not_generate_fabricated_vendor_or_customer(mock_storage):
    mock_agent = MagicMock()
    mock_agent.extract_document_payload.side_effect = DocumentIntelligenceAgentError(
        "Gemini API error: 429 RESOURCE_EXHAUSTED", is_transient=True
    )
    service = DocumentIntelligenceService(storage_service=mock_storage, agent=mock_agent)
    adapter = DocIntelAdapter(doc_service=service)

    result = adapter.execute(
        workflow_id="wf-429-test",
        document_id="doc-test-429",
        payload={},
    )

    assert result.success is False
    extraction = result.output_reference.get("extraction")
    assert extraction is None
    # Verify no downstream dictionary contains fake commercial entities
    assert "Standard Vendor" not in str(result.output_reference)
    assert "Standard Customer" not in str(result.output_reference)
    assert "INV-1001" not in str(result.output_reference)


# 3. Gemini 429 cannot trigger a false duplicate solely from fallback values
def test_gemini_429_cannot_trigger_false_duplicate(mock_storage):
    # Set up historical context containing previous fallback value "INV-1001"
    mock_repo = MagicMock()
    mock_repo.get_historical_context.return_value = HistoricalContext(
        existing_invoice_numbers={"INV-1001", "36259"},
        existing_checksums={"1111111111111111111111111111111111111111111111111111111111111111"},
        existing_document_fingerprints={"SuperStore:Aaron Bergman:36259"},
    )

    mock_agent = MagicMock()
    mock_agent.extract_document_payload.side_effect = DocumentIntelligenceAgentError(
        "Gemini API error: 429 RESOURCE_EXHAUSTED", is_transient=True
    )
    service = DocumentIntelligenceService(storage_service=mock_storage, agent=mock_agent)
    doc_adapter = DocIntelAdapter(doc_service=service)

    doc_result = doc_adapter.execute(
        workflow_id="wf-429-test",
        document_id="doc-test-429",
        payload={},
    )

    assert doc_result.success is False

    # When forensic adapter receives the output from failed extraction
    forensic_adapter = ForensicAdapter(document_repository=mock_repo)
    forensic_result = forensic_adapter.execute(
        workflow_id="wf-429-test",
        document_id="doc-test-429",
        payload={"previous_output": doc_result.output_reference},
    )

    findings = forensic_result.output_reference["forensic_result"]["findings"]
    # Verify no DUPLICATE_IDENTIFIER finding was raised
    dup_findings = [f for f in findings if f["rule_id"] == "DUPLICATE_IDENTIFIER"]
    assert len(dup_findings) == 0, f"Unexpected duplicate finding triggered: {dup_findings}"


# 4. Extraction failure is represented explicitly
def test_extraction_failure_represented_explicitly(mock_storage):
    mock_agent = MagicMock()
    mock_agent.extract_document_payload.side_effect = DocumentIntelligenceAgentError(
        "Gemini API error during extraction: 429 RESOURCE_EXHAUSTED", is_transient=True
    )
    service = DocumentIntelligenceService(storage_service=mock_storage, agent=mock_agent)
    adapter = DocIntelAdapter(doc_service=service)

    result = adapter.execute(
        workflow_id="wf-failed-test",
        document_id="doc-test-429",
        payload={},
    )

    assert result.success is False
    assert result.failure_classification == FailureClassification.RETRYABLE
    assert result.output_reference == {
        "document_id": "doc-test-429",
        "extraction": None,
        "status_reason": "Document Intelligence Agent error: Gemini API error during extraction: 429 RESOURCE_EXHAUSTED",
    }
    assert result.observations == {"confidence": 0.0}


# 5. Existing successful Gemini extraction remains unchanged
def test_existing_successful_gemini_extraction_remains_unchanged(mock_storage):
    payload = GeminiExtractionPayload(
        document_type="invoice",
        vendor="SuperStore",
        customer="Nicole Hansen",
        invoice_number="30938",
        dates=["2012-10-05"],
        amounts=["1778.72"],
        line_items=[
            LineItem(
                description="Ikea Classic Bookcase",
                quantity="2",
                unit_price="822.42",
                amount="1644.84",
            )
        ],
        extraction_confidence=0.95,
    )
    mock_agent = MagicMock()
    mock_agent.extract_document_payload.return_value = payload

    service = DocumentIntelligenceService(storage_service=mock_storage, agent=mock_agent)
    adapter = DocIntelAdapter(doc_service=service)

    result = adapter.execute(
        workflow_id="wf-success-test",
        document_id="doc-test-429",
        payload={},
    )

    assert result.success is True
    assert result.output_reference["extraction"]["invoice_number"] == "30938"
    assert result.output_reference["extraction"]["vendor"] == "SuperStore"
    assert result.output_reference["extraction"]["customer"] == "Nicole Hansen"
    assert result.observations["confidence"] == 0.95


# 6. Existing duplicate detection remains unchanged
def test_existing_duplicate_detection_remains_unchanged():
    mock_repo = MagicMock()
    mock_repo.get_historical_context.return_value = HistoricalContext(
        existing_invoice_numbers={"36259"},
        existing_checksums={"ea0e878b2b4d949a947b7ed11ecb213d9718446f5e4a774c7646270d2f200e6e"},
        existing_document_fingerprints={"SuperStore:Aaron Bergman:36259"},
    )

    adapter = ForensicAdapter(document_repository=mock_repo)
    result = adapter.execute(
        workflow_id="wf-dup-test",
        document_id="doc-dup-1",
        payload={
            "extraction": {
                "document_type": "invoice",
                "vendor": "SuperStore",
                "customer": "Aaron Bergman",
                "invoice_number": "36259",
                "dates": ["2011-01-04"],
                "amounts": ["57.68"],
                "line_items": [
                    {
                        "description": "Eldon Fold 'N Roll Cart System",
                        "quantity": "2",
                        "unit_price": "28.84",
                        "amount": "57.68",
                    }
                ],
                "extraction_confidence": 0.98,
            }
        },
    )

    # Must route to review due to CRITICAL duplicate detection
    assert result.success is False
    assert result.failure_classification == FailureClassification.REQUIRES_REVIEW
    findings = result.output_reference["forensic_result"]["findings"]
    dup_finding = next(f for f in findings if f["rule_id"] == "DUPLICATE_IDENTIFIER")
    assert dup_finding["severity"] == "CRITICAL"
    assert dup_finding["evidence"]["observed_value"] == "36259"
    assert dup_finding["requires_review"] is True


# 7. Existing workflow safety / review semantics remain intact
def test_existing_workflow_safety_and_review_semantics_intact():
    # Verify low-confidence extraction routes to REQUIRES_REVIEW
    mock_storage = MagicMock()
    metadata = DocumentMetadata(
        document_id="doc-low-conf",
        filename="test.pdf",
        content_type="application/pdf",
        size_bytes=1024,
        storage_bucket="papertrail-documents",
        storage_object="invoices/test.pdf",
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
        checksum="e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
    )
    mock_storage.get_document_metadata.return_value = metadata
    mock_storage.get_document_bytes.return_value = b"%PDF-1.4 mock bytes"

    mock_agent = MagicMock()
    mock_agent.extract_document_payload.return_value = GeminiExtractionPayload(
        document_type="invoice",
        vendor="Acme",
        invoice_number="INV-001",
        extraction_confidence=0.50,  # Below threshold 0.70
    )
    service = DocumentIntelligenceService(storage_service=mock_storage, agent=mock_agent, confidence_threshold=0.70)
    adapter = DocIntelAdapter(doc_service=service)

    result = adapter.execute("wf-low-conf", "doc-low-conf", {})
    assert result.success is False
    assert result.failure_classification == FailureClassification.REQUIRES_REVIEW
    assert "below confidence threshold" in result.failure_reason

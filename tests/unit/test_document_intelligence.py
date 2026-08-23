from datetime import datetime, timezone
from unittest.mock import MagicMock, patch
import pytest

from app.agents.document_intelligence.agent import (
    DocumentIntelligenceAgent,
    DocumentIntelligenceAgentError,
)
from app.agents.document_intelligence.prompts import SYSTEM_PROMPT
from app.models.analysis import (
    AnalysisStatus,
    DocumentExtractionResult,
    DocumentType,
    GeminiExtractionPayload,
    LineItem,
)
from app.models.document import DocumentMetadata, DocumentStatus
from app.services.document_intelligence import DocumentIntelligenceService
from app.services.document_storage import DocumentStorageError


@pytest.fixture
def mock_storage_service():
    mock_service = MagicMock()
    metadata = DocumentMetadata(
        document_id="doc-unit-123456",
        filename="invoice.pdf",
        content_type="application/pdf",
        size_bytes=1024,
        storage_bucket="papertrail-ai-documents-dev",
        storage_object="documents/doc-unit-123456/original/invoice.pdf",
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
        document_status=DocumentStatus.STORED,
        checksum="e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
    )
    mock_service.get_document_metadata.return_value = metadata
    mock_service.get_document_bytes.return_value = b"%PDF-1.4 sample pdf content"
    return mock_service


@pytest.fixture
def sample_payload():
    return GeminiExtractionPayload(
        document_type=DocumentType.INVOICE,
        title="Acme Invoice",
        entities=["Acme Corp", "PaperTrail AI"],
        dates=["2026-08-17"],
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
        vendor="Acme Corp",
        customer="PaperTrail AI",
        invoice_number="INV-2026-001",
        description="Invoice for services rendered",
        extraction_confidence=0.95,
    )


# 1. Valid Extraction & Classification
def test_valid_structured_extraction(sample_payload):
    assert sample_payload.document_type == DocumentType.INVOICE
    assert sample_payload.vendor == "Acme Corp"
    assert sample_payload.amounts == ["1320.50"]
    assert len(sample_payload.line_items) == 1
    assert sample_payload.line_items[0].amount == "1320.50"


# 2. Document Classification
@pytest.mark.parametrize(
    "doc_type_str,expected_enum",
    [
        ("invoice", DocumentType.INVOICE),
        ("receipt", DocumentType.RECEIPT),
        ("contract", DocumentType.CONTRACT),
        ("expense_report", DocumentType.EXPENSE_REPORT),
        ("purchase_order", DocumentType.PURCHASE_ORDER),
        ("other", DocumentType.OTHER),
        ("unknown", DocumentType.UNKNOWN),
    ],
)
def test_document_classification_types(doc_type_str, expected_enum):
    payload = GeminiExtractionPayload(document_type=expected_enum, extraction_confidence=0.9)
    assert payload.document_type == doc_type_str


# 3. Pydantic Validation
def test_pydantic_schema_validation(sample_payload):
    json_str = sample_payload.model_dump_json()
    deserialized = GeminiExtractionPayload.model_validate_json(json_str)
    assert deserialized.document_type == DocumentType.INVOICE
    assert deserialized.extraction_confidence == 0.95


# 4. Financial String Validation
def test_financial_string_representation():
    item = LineItem(description="Test Item", quantity="3", unit_price="10.50", amount="31.50")
    assert isinstance(item.amount, str)
    assert item.amount == "31.50"
    assert not isinstance(item.amount, float)


# 5. ISO Date Representation
def test_iso_date_validation():
    payload = GeminiExtractionPayload(dates=["2026-08-17", "2026-08-17T12:00:00Z"], extraction_confidence=0.90)
    assert payload.dates[0] == "2026-08-17"
    assert "T" in payload.dates[1]


# 6. Confidence Validation
def test_confidence_validation():
    payload = GeminiExtractionPayload(extraction_confidence=0.85)
    assert 0.0 <= payload.extraction_confidence <= 1.0


# 7. SUCCESS Status Calculation
def test_status_calculation_success(mock_storage_service, sample_payload):
    mock_agent = MagicMock()
    mock_agent.extract_document_payload.return_value = sample_payload

    service = DocumentIntelligenceService(storage_service=mock_storage_service, agent=mock_agent, confidence_threshold=0.70)
    result: DocumentExtractionResult = service.analyze_document("doc-unit-123456")

    assert result.status == AnalysisStatus.SUCCESS
    assert result.extraction is not None
    assert result.extraction.extraction_confidence == 0.95
    assert "completed successfully" in result.status_reason


# 8. NEEDS_REVIEW Status Calculation
def test_status_calculation_needs_review(mock_storage_service, sample_payload):
    sample_payload.extraction_confidence = 0.55
    mock_agent = MagicMock()
    mock_agent.extract_document_payload.return_value = sample_payload

    service = DocumentIntelligenceService(storage_service=mock_storage_service, agent=mock_agent, confidence_threshold=0.70)
    result: DocumentExtractionResult = service.analyze_document("doc-unit-123456")

    assert result.status == AnalysisStatus.NEEDS_REVIEW
    assert result.extraction is not None
    assert result.extraction.extraction_confidence == 0.55
    assert "below confidence threshold" in result.status_reason


# 9. FAILED Status Calculation on Storage Error
def test_status_calculation_failed_storage_error(mock_storage_service):
    mock_storage_service.get_document_bytes.side_effect = DocumentStorageError("download_bytes", "doc-123", "GCS error")
    mock_agent = MagicMock()

    service = DocumentIntelligenceService(storage_service=mock_storage_service, agent=mock_agent)
    result: DocumentExtractionResult = service.analyze_document("doc-unit-123456")

    assert result.status == AnalysisStatus.FAILED
    assert result.extraction is None
    assert "Storage access error" in result.status_reason


# 10. Missing Fields Handling (Null/Empty Values)
def test_missing_fields_handling():
    payload = GeminiExtractionPayload(
        document_type=DocumentType.UNKNOWN,
        title=None,
        entities=[],
        vendor=None,
        extraction_confidence=0.50,
    )
    assert payload.title is None
    assert payload.vendor is None
    assert payload.entities == []


# 11. Malformed Output Handling
def test_malformed_output_handling(mock_storage_service):
    mock_agent = MagicMock()
    mock_agent.extract_document_payload.side_effect = DocumentIntelligenceAgentError(
        "Schema validation failure on extraction output", is_transient=False
    )

    service = DocumentIntelligenceService(storage_service=mock_storage_service, agent=mock_agent)
    result = service.analyze_document("doc-unit-123456")

    assert result.status == AnalysisStatus.FAILED
    assert result.extraction is None
    assert "Schema validation failure" in result.status_reason


# 12. Out of Bounds Confidence Handling
def test_invalid_confidence_bounds_handling(mock_storage_service, sample_payload):
    sample_payload.extraction_confidence = 1.5  # Out of bounds (> 1.0)
    mock_agent = MagicMock()
    mock_agent.extract_document_payload.return_value = sample_payload

    service = DocumentIntelligenceService(storage_service=mock_storage_service, agent=mock_agent)
    result = service.analyze_document("doc-unit-123456")

    assert result.status == AnalysisStatus.FAILED
    assert "Out-of-bounds confidence score" in result.status_reason


# 13. Timeout Handling
def test_gemini_timeout_handling(mock_storage_service):
    mock_agent = MagicMock()
    mock_agent.extract_document_payload.side_effect = DocumentIntelligenceAgentError(
        "Gemini API timeout", is_transient=True
    )

    service = DocumentIntelligenceService(storage_service=mock_storage_service, agent=mock_agent)
    result = service.analyze_document("doc-unit-123456")

    assert result.status == AnalysisStatus.FAILED
    assert "timeout" in result.status_reason.lower()


# 14. Authentication Error Handling
def test_authentication_error_handling(mock_storage_service):
    mock_agent = MagicMock()
    mock_agent.extract_document_payload.side_effect = DocumentIntelligenceAgentError(
        "Invalid API Key", is_transient=False
    )

    service = DocumentIntelligenceService(storage_service=mock_storage_service, agent=mock_agent)
    result = service.analyze_document("doc-unit-123456")

    assert result.status == AnalysisStatus.FAILED
    assert "Invalid API Key" in result.status_reason


# 15. Bounded Retry Verification
def test_bounded_retry_policy():
    mock_client = MagicMock()
    mock_client.models.generate_content.side_effect = Exception("API rate limit 429")

    agent = DocumentIntelligenceAgent(client=mock_client, max_retries=2)

    with patch("time.sleep"):  # Speed up retry delay
        with pytest.raises(DocumentIntelligenceAgentError) as exc_info:
            agent.extract_document_payload(b"test pdf content", "application/pdf", "test.pdf")

    assert mock_client.models.generate_content.call_count == 3  # Initial + 2 retries
    assert exc_info.value.is_transient is True


# 16. Prompt Injection Isolation
def test_prompt_injection_system_prompt_rules():
    assert "UNTRUSTED DATA" in SYSTEM_PROMPT
    assert "Ignore previous instructions" in SYSTEM_PROMPT
    assert "System Prompt:" in SYSTEM_PROMPT
    assert "NO GOVERNANCE OR RISK DECISIONS" in SYSTEM_PROMPT


# 17. No WorkflowState Mutation Assertion
def test_no_workflow_state_mutation(mock_storage_service, sample_payload):
    mock_agent = MagicMock()
    mock_agent.extract_document_payload.return_value = sample_payload

    service = DocumentIntelligenceService(storage_service=mock_storage_service, agent=mock_agent)
    result = service.analyze_document("doc-unit-123456")

    assert hasattr(result, "status")
    # Verify result does not contain or mutate workflow state fields
    assert not hasattr(result, "workflow_state")
    assert not hasattr(result, "current_state")

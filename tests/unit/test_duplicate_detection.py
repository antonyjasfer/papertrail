import pytest
from datetime import datetime, timezone
from unittest.mock import MagicMock

from app.compliance.engine import ComplianceEngine
from app.infrastructure.azure.cosmos_repositories import CosmosDocumentRepository
from app.models.analysis import (
    AnalysisStatus,
    DocumentExtractionResult,
    GeminiExtractionPayload,
    LineItem,
)
from app.models.document import DocumentMetadata, DocumentStatus
from app.models.forensics import FindingSeverity, HistoricalContext
from app.orchestration.adapters.base import FailureClassification
from app.orchestration.adapters.compliance_adapter import ComplianceAdapter
from app.orchestration.adapters.forensic_adapter import ForensicAdapter
from app.orchestration.adapters.risk_adapter import RiskAdapter
from app.risk.engine import RiskAssessmentEngine


def test_cosmos_get_historical_context_in_memory_self_exclusion():
    """Verify CosmosDocumentRepository.get_historical_context excludes current document."""
    repo = CosmosDocumentRepository()
    repo._items.clear()

    # Add prior document
    doc1 = DocumentMetadata(
        document_id="doc-prior-01",
        filename="invoice_01.pdf",
        content_type="application/pdf",
        size_bytes=1000,
        storage_bucket="test-bucket",
        storage_object="documents/doc-prior-01/original/invoice_01.pdf",
        checksum="sha256-prior-checksum-01",
    )
    repo.create(doc1)

    # Add current document
    doc2 = DocumentMetadata(
        document_id="doc-current-02",
        filename="invoice_02.pdf",
        content_type="application/pdf",
        size_bytes=2000,
        storage_bucket="test-bucket",
        storage_object="documents/doc-current-02/original/invoice_02.pdf",
        checksum="sha256-current-checksum-02",
    )
    repo.create(doc2)

    # Historical context for current document
    ctx = repo.get_historical_context(exclude_document_id="doc-current-02")
    assert "sha256-prior-checksum-01" in ctx.existing_checksums
    assert "sha256-current-checksum-02" not in ctx.existing_checksums


def test_forensic_adapter_triggers_duplicate_checksum():
    """Verify ForensicAdapter detects duplicate checksum and returns REQUIRES_REVIEW."""
    mock_repo = MagicMock()
    mock_repo.get.return_value = DocumentMetadata(
        document_id="doc-dup-01",
        filename="dup_invoice.pdf",
        content_type="application/pdf",
        size_bytes=1500,
        storage_bucket="test-bucket",
        storage_object="documents/doc-dup-01/original/dup_invoice.pdf",
        checksum="ea0e878b2b4d949a947b7ed11ecb213d9718446f5e4a774c7646270d2f200e6e",
    )
    mock_repo.get_historical_context.return_value = HistoricalContext(
        existing_invoice_numbers=["INV-9999"],
        existing_checksums=["ea0e878b2b4d949a947b7ed11ecb213d9718446f5e4a774c7646270d2f200e6e"],
    )

    adapter = ForensicAdapter(document_repository=mock_repo)
    payload = {
        "document_id": "doc-dup-01",
        "extraction": {
            "document_type": "invoice",
            "vendor": "SuperStore",
            "customer": "Aaron Bergman",
            "invoice_number": "36259",
            "dates": ["2012-03-06"],
            "amounts": ["58.11", "53.82", "17.94", "4.29"],
            "line_items": [
                {
                    "description": "Newell 330 Art, Office Supplies, OFF-AR-5309",
                    "quantity": "3",
                    "unit_price": "17.94",
                    "amount": "53.82",
                }
            ],
            "extraction_confidence": 0.98,
        },
    }

    result = adapter.execute(
        workflow_id="wf-test-dup",
        document_id="doc-dup-01",
        payload=payload,
    )

    assert result.success is False
    assert result.failure_classification == FailureClassification.REQUIRES_REVIEW
    f_res = result.output_reference["forensic_result"]
    assert f_res["finding_count"] >= 1
    dup_findings = [f for f in f_res["findings"] if f["finding_code"] == "DUPLICATE_IDENTIFIER"]
    assert len(dup_findings) >= 1
    assert any(f["severity"] == "CRITICAL" for f in dup_findings)


def test_forensic_adapter_triggers_duplicate_invoice_number():
    """Verify ForensicAdapter detects duplicate invoice number and returns REQUIRES_REVIEW."""
    mock_repo = MagicMock()
    mock_repo.get.return_value = DocumentMetadata(
        document_id="doc-dup-02",
        filename="dup_invoice_diff_file.pdf",
        content_type="application/pdf",
        size_bytes=1800,
        storage_bucket="test-bucket",
        storage_object="documents/doc-dup-02/original/dup_invoice_diff_file.pdf",
        checksum="unique-sha-9999",
    )
    mock_repo.get_historical_context.return_value = HistoricalContext(
        existing_invoice_numbers=["36259"],
        existing_checksums=["other-sha-1111"],
    )

    adapter = ForensicAdapter(document_repository=mock_repo)
    payload = {
        "document_id": "doc-dup-02",
        "extraction": {
            "document_type": "invoice",
            "vendor": "SuperStore",
            "customer": "Aaron Bergman",
            "invoice_number": "36259",
            "dates": ["2012-03-06"],
            "amounts": ["58.11", "53.82", "17.94", "4.29"],
            "line_items": [
                {
                    "description": "Newell 330 Art, Office Supplies, OFF-AR-5309",
                    "quantity": "3",
                    "unit_price": "17.94",
                    "amount": "53.82",
                }
            ],
            "extraction_confidence": 0.98,
        },
    }

    result = adapter.execute(
        workflow_id="wf-test-dup-inv",
        document_id="doc-dup-02",
        payload=payload,
    )

    assert result.success is False
    assert result.failure_classification == FailureClassification.REQUIRES_REVIEW
    f_res = result.output_reference["forensic_result"]
    dup_findings = [f for f in f_res["findings"] if f["finding_code"] == "DUPLICATE_IDENTIFIER"]
    assert len(dup_findings) >= 1
    assert dup_findings[0]["title"] == "Duplicate Invoice Number Detected"


def test_forensic_adapter_passes_clean_when_no_duplicates():
    """Verify ForensicAdapter passes with success=True when document is genuinely new."""
    mock_repo = MagicMock()
    mock_repo.get.return_value = DocumentMetadata(
        document_id="doc-clean-01",
        filename="clean_invoice_02.pdf",
        content_type="application/pdf",
        size_bytes=14779,
        storage_bucket="test-bucket",
        storage_object="documents/doc-clean-01/original/clean_invoice_02.pdf",
        checksum="ea0e878b2b4d949a947b7ed11ecb213d9718446f5e4a774c7646270d2f200e6e",
    )
    mock_repo.get_historical_context.return_value = HistoricalContext(
        existing_invoice_numbers=["INV-OTHER-1", "INV-OTHER-2"],
        existing_checksums=["other-sha-1", "other-sha-2"],
    )

    adapter = ForensicAdapter(document_repository=mock_repo)
    payload = {
        "document_id": "doc-clean-01",
        "extraction": {
            "document_type": "invoice",
            "vendor": "SuperStore",
            "customer": "Aaron Bergman",
            "invoice_number": "36259",
            "dates": ["2012-03-06"],
            "amounts": ["58.11", "53.82", "17.94", "4.29"],
            "line_items": [
                {
                    "description": "Newell 330 Art, Office Supplies, OFF-AR-5309",
                    "quantity": "3",
                    "unit_price": "17.94",
                    "amount": "53.82",
                }
            ],
            "extraction_confidence": 0.98,
        },
    }

    result = adapter.execute(
        workflow_id="wf-test-clean",
        document_id="doc-clean-01",
        payload=payload,
    )

    assert result.success is True
    f_res = result.output_reference["forensic_result"]
    assert f_res["finding_count"] == 0
    assert len(f_res["findings"]) == 0


def test_compliance_and_risk_with_duplicate_forensic_evidence():
    """Verify compliance control C-FIN-002 evaluates to FAIL and RiskAdapter triggers review for duplicate."""
    # Forensic finding for duplicate
    forensic_dict = {
        "document_id": "doc-dup-01",
        "finding_count": 1,
        "findings": [
            {
                "finding_code": "DUPLICATE_IDENTIFIER",
                "category": "DUPLICATE",
                "severity": "CRITICAL",
                "title": "Duplicate Invoice Number Detected",
                "description": "Invoice number '36259' matches a previously processed document.",
                "evidence": {
                    "observed_value": "36259",
                    "expected_value": "Unique invoice_number",
                    "field_reference": "extraction.invoice_number",
                    "context_notes": "Extracted invoice number exists in historical context records.",
                },
                "rule_id": "DUPLICATE_IDENTIFIER",
                "stage": "FORENSIC",
            }
        ],
        "deterministic_checks_run": ["DUPLICATE_IDENTIFIER"],
        "checks_skipped": [],
    }

    extraction_dict = {
        "document_type": "invoice",
        "vendor": "SuperStore",
        "customer": "Aaron Bergman",
        "invoice_number": "36259",
        "dates": ["2012-03-06"],
        "amounts": ["58.11"],
        "line_items": [
            {
                "description": "Item 1",
                "quantity": "1",
                "unit_price": "58.11",
                "amount": "58.11",
            }
        ],
        "extraction_confidence": 0.98,
    }

    # Execute ComplianceAdapter
    cmp_adapter = ComplianceAdapter()
    cmp_res = cmp_adapter.execute(
        workflow_id="wf-test-cmp",
        document_id="doc-dup-01",
        payload={
            "document_id": "doc-dup-01",
            "extraction": extraction_dict,
            "forensic_result": forensic_dict,
        },
    )
    assert cmp_res.success is True
    findings = cmp_res.output_reference["compliance_result"]["findings"]
    c_fin_002 = [f for f in findings if f["control_id"] == "C-FIN-002"][0]
    assert c_fin_002["status"] == "FAIL"

    # Execute RiskAdapter
    risk_adapter = RiskAdapter()
    risk_res = risk_adapter.execute(
        workflow_id="wf-test-risk",
        document_id="doc-dup-01",
        payload={
            "document_id": "doc-dup-01",
            "extraction": extraction_dict,
            "forensic_result": forensic_dict,
            "compliance_result": cmp_res.output_reference["compliance_result"],
        },
    )
    # RiskAdapter should request review due to CRITICAL/HIGH risk
    assert risk_res.success is False
    assert risk_res.failure_classification == FailureClassification.REQUIRES_REVIEW
    assessment = risk_res.output_reference["risk_result"]
    assert assessment["review_recommended"] is True
    assert assessment["risk_level"] in ("HIGH", "CRITICAL")

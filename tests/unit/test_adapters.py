import pytest
from app.orchestration.adapters import (
    AuditAdapter,
    ComplianceAdapter,
    DocIntelAdapter,
    ForensicAdapter,
    ReportAdapter,
    RiskAdapter,
)


def test_doc_intel_adapter():
    adapter = DocIntelAdapter()
    result = adapter.execute("wf-1", "doc-1", {})
    assert adapter.adapter_name == "DocIntelAdapter (Phase 7)"


def test_forensic_adapter():
    adapter = ForensicAdapter()
    result = adapter.execute("wf-2", "doc-2", {})
    assert result.success is True
    assert "forensic_result" in result.output_reference


def test_compliance_adapter():
    adapter = ComplianceAdapter()
    result = adapter.execute("wf-3", "doc-3", {})
    assert result.success is True
    assert "compliance_result" in result.output_reference


def test_risk_adapter():
    adapter = RiskAdapter()
    result = adapter.execute("wf-4", "doc-4", {})
    assert result.success is True
    assert "risk_result" in result.output_reference


def test_audit_adapter():
    adapter = AuditAdapter()
    result = adapter.execute("wf-5", "doc-5", {})
    assert result.success is True
    assert "sealed_hash" in result.output_reference


def test_report_adapter():
    adapter = ReportAdapter()
    result = adapter.execute("wf-6", "doc-6", {})
    assert result.success is True
    assert "pdf_sha256" in result.output_reference

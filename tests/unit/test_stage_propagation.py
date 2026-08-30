from datetime import datetime, timezone
from decimal import Decimal
import pytest

from app.core.state import AnalysisWorkflow, WorkflowState
from app.events.schemas import EventType, WorkflowEvent
from app.models.analysis import AnalysisStatus, DocumentExtractionResult, GeminiExtractionPayload, LineItem
from app.models.compliance import ComplianceStatus
from app.models.document import DocumentMetadata
from app.models.forensics import FindingSeverity
from app.orchestration.adapters import (
    ComplianceAdapter,
    DocIntelAdapter,
    ForensicAdapter,
    ReportAdapter,
    RiskAdapter,
)
from app.orchestration.orchestrator import WorkflowOrchestrator
from app.orchestration.state_manager import FirestoreStateManager


@pytest.fixture
def anomalous_extraction_dict():
    return {
        "document_type": "invoice",
        "title": "INVOICE",
        "entities": ["SuperStore", "Charlotte Melton"],
        "dates": ["2012-06-05"],
        "amounts": ["6234.32", "12195.89", "6097.95", "136.38"],
        "currency": "USD",
        "line_items": [
            {
                "description": "Brother Personal Copier, Color Copiers, Technology, TEC-CO-3604",
                "quantity": "13",
                "unit_price": "938.15",
                "amount": "12195.89",
            }
        ],
        "vendor": "SuperStore",
        "customer": "Charlotte Melton",
        "invoice_number": "27583",
        "description": "Order ID : ID-2012-CM1219097-41065",
        "extraction_confidence": 0.98,
    }


def test_forensic_adapter_detects_r_fin_001(anomalous_extraction_dict):
    """Verify ForensicAdapter receives extraction dict and triggers R-FIN-001."""
    adapter = ForensicAdapter()
    payload = {"document_id": "doc-test-1", "extraction": anomalous_extraction_dict}
    result = adapter.execute("wf-test-1", "doc-test-1", payload)

    assert result.success is True
    assert "forensic_result" in result.output_reference
    f_res = result.output_reference["forensic_result"]

    assert f_res["finding_count"] == 1
    finding = f_res["findings"][0]
    assert finding["finding_code"] == "LINE_ITEM_AMOUNT_MISMATCH"
    assert finding["severity"] == "HIGH"
    assert finding["evidence"]["observed_value"] == "12195.89"
    assert finding["evidence"]["expected_value"] == "12195.95"
    assert "13 * 938.15 = 12195.95" in finding["evidence"]["calculation"]


def test_compliance_adapter_receives_forensic_finding(anomalous_extraction_dict):
    """Verify ComplianceAdapter receives extraction and forensic findings, flagging C-FIN-001."""
    forensic_adapter = ForensicAdapter()
    payload = {"document_id": "doc-test-2", "extraction": anomalous_extraction_dict}
    f_res = forensic_adapter.execute("wf-test-2", "doc-test-2", payload)

    comp_adapter = ComplianceAdapter()
    comp_payload = {
        "document_id": "doc-test-2",
        "extraction": anomalous_extraction_dict,
        "forensic_result": f_res.output_reference["forensic_result"],
    }
    c_res = comp_adapter.execute("wf-test-2", "doc-test-2", comp_payload)

    assert c_res.success is True
    assert "compliance_result" in c_res.output_reference
    findings = c_res.output_reference["compliance_result"]["findings"]

    c_fin_001 = next(f for f in findings if f["control_id"] == "C-FIN-001")
    assert c_fin_001["status"] == "FAIL"
    assert c_fin_001["rule_id"] == "CR-FIN-001"
    assert "12195.95" in c_fin_001["description"]


def test_risk_adapter_incorporates_anomaly_and_flags_high_risk(anomalous_extraction_dict):
    """Verify RiskAdapter receives prior results, computes HIGH risk (score 53.18), and returns REQUIRES_REVIEW."""
    f_res = ForensicAdapter().execute("wf-test-3", "doc-test-3", {"document_id": "doc-test-3", "extraction": anomalous_extraction_dict})
    c_res = ComplianceAdapter().execute(
        "wf-test-3",
        "doc-test-3",
        {
            "document_id": "doc-test-3",
            "extraction": anomalous_extraction_dict,
            "forensic_result": f_res.output_reference["forensic_result"],
        },
    )

    risk_payload = {
        "document_id": "doc-test-3",
        "extraction": anomalous_extraction_dict,
        "forensic_result": f_res.output_reference["forensic_result"],
        "compliance_result": c_res.output_reference["compliance_result"],
    }
    r_res = RiskAdapter().execute("wf-test-3", "doc-test-3", risk_payload)

    # Risk level HIGH returns success=False with FailureClassification.REQUIRES_REVIEW
    assert r_res.success is False
    assert r_res.failure_classification.value == "REQUIRES_REVIEW"
    assert "risk_result" in r_res.output_reference
    risk_data = r_res.output_reference["risk_result"]
    assert risk_data["risk_level"] == "HIGH"
    assert Decimal(str(risk_data["composite_score"])) == Decimal("53.18")
    assert risk_data["review_recommended"] is True


def test_orchestrator_end_to_end_data_propagation_anomalous(anomalous_extraction_dict):
    """Verify complete WorkflowOrchestrator pipeline preserves stage data and routes anomalous invoice to REQUIRES_REVIEW."""
    state_mgr = FirestoreStateManager()
    orchestrator = WorkflowOrchestrator(state_manager=state_mgr)

    from app.orchestration.adapters.base import AdapterResult

    class MockDocIntelAdapter:
        def __init__(self, extraction_dict):
            self.extraction_dict = extraction_dict
            self.adapter_name = "DocIntelAdapter (Phase 7)"

        def execute(self, workflow_id, document_id, payload):
            return AdapterResult(
                success=True,
                output_reference={
                    "document_id": document_id,
                    "extraction": self.extraction_dict,
                    "status_reason": "Extraction successful",
                },
                observations={"extraction_confidence": 0.98},
            )

    orchestrator.adapters[WorkflowState.INGESTING] = MockDocIntelAdapter(anomalous_extraction_dict)
    orchestrator.adapters[WorkflowState.EXTRACTING] = MockDocIntelAdapter(anomalous_extraction_dict)

    wf_id = "wf-orch-anomaly-1"
    doc_id = "doc-orch-anomaly-1"
    wf, init_evt = orchestrator.start_workflow(wf_id, doc_id)
    assert wf.current_state == WorkflowState.UPLOADED

    # Step 1: UPLOADED -> INGESTING
    evt = WorkflowEvent(
        workflow_id=wf_id,
        document_id=doc_id,
        event_type=EventType.DOCUMENT_UPLOADED,
        current_state="UPLOADED",
        workflow_revision=1,
        payload={"document_id": doc_id, "extraction": anomalous_extraction_dict},
        event_timestamp=datetime.now(timezone.utc),
        correlation_id="corr-1",
    )
    wf, outbox = orchestrator.dispatch(evt)
    assert wf.current_state == WorkflowState.INGESTING

    # Step 2: INGESTING -> EXTRACTING
    evt = WorkflowEvent(
        workflow_id=wf_id,
        document_id=doc_id,
        event_type=EventType.INGESTION_COMPLETED,
        current_state="INGESTING",
        workflow_revision=2,
        payload=outbox.payload,
        event_timestamp=datetime.now(timezone.utc),
        correlation_id="corr-2",
    )
    wf, outbox = orchestrator.dispatch(evt)
    assert wf.current_state == WorkflowState.EXTRACTING

    # Step 3: EXTRACTING -> EXTRACTED
    evt = WorkflowEvent(
        workflow_id=wf_id,
        document_id=doc_id,
        event_type=EventType.EXTRACTION_COMPLETED,
        current_state="EXTRACTING",
        workflow_revision=3,
        payload=outbox.payload,
        event_timestamp=datetime.now(timezone.utc),
        correlation_id="corr-3",
    )
    wf, outbox = orchestrator.dispatch(evt)
    assert wf.current_state == WorkflowState.EXTRACTED

    # Step 4: EXTRACTED -> FORENSIC_ANALYSIS
    evt = WorkflowEvent(
        workflow_id=wf_id,
        document_id=doc_id,
        event_type=EventType.ANALYSIS_TRIGGERED,
        current_state="EXTRACTED",
        workflow_revision=4,
        payload=outbox.payload,
        event_timestamp=datetime.now(timezone.utc),
        correlation_id="corr-4",
    )
    wf, outbox = orchestrator.dispatch(evt)
    assert wf.current_state == WorkflowState.FORENSIC_ANALYSIS

    # Step 5: FORENSIC_ANALYSIS -> COMPLIANCE_ANALYSIS
    evt = WorkflowEvent(
        workflow_id=wf_id,
        document_id=doc_id,
        event_type=EventType.FORENSICS_COMPLETED,
        current_state="FORENSIC_ANALYSIS",
        workflow_revision=5,
        payload=outbox.payload,
        event_timestamp=datetime.now(timezone.utc),
        correlation_id="corr-5",
    )
    wf, outbox = orchestrator.dispatch(evt)
    assert wf.current_state == WorkflowState.COMPLIANCE_ANALYSIS

    # Step 6: COMPLIANCE_ANALYSIS -> RISK_ASSESSED
    evt = WorkflowEvent(
        workflow_id=wf_id,
        document_id=doc_id,
        event_type=EventType.COMPLIANCE_COMPLETED,
        current_state="COMPLIANCE_ANALYSIS",
        workflow_revision=6,
        payload=outbox.payload,
        event_timestamp=datetime.now(timezone.utc),
        correlation_id="corr-6",
    )
    wf, outbox = orchestrator.dispatch(evt)
    assert wf.current_state == WorkflowState.RISK_ASSESSED

    # Step 7: RISK_ASSESSED -> REQUIRES_REVIEW (due to HIGH risk from forensic & compliance failures)
    evt = WorkflowEvent(
        workflow_id=wf_id,
        document_id=doc_id,
        event_type=EventType.RISK_COMPLETED,
        current_state="RISK_ASSESSED",
        workflow_revision=7,
        payload=outbox.payload,
        event_timestamp=datetime.now(timezone.utc),
        correlation_id="corr-7",
    )
    wf, outbox = orchestrator.dispatch(evt)
    assert wf.current_state == WorkflowState.REQUIRES_REVIEW
    assert "indicates HIGH/CRITICAL risk" in wf.review_reason


def test_orchestrator_end_to_end_clean_invoice_completes():
    """Verify complete clean invoice progresses through all 9 stages to COMPLETED."""
    clean_extraction = {
        "document_type": "invoice",
        "vendor": "SuperStore",
        "customer": "Charlotte Melton",
        "invoice_number": "36259",
        "dates": ["2012-03-06"],
        "amounts": ["58.11", "53.82", "4.29"],
        "currency": "USD",
        "line_items": [
            {
                "description": "Art, Office Supplies, OFF-AR-5309",
                "quantity": "3",
                "unit_price": "17.94",
                "amount": "53.82",
            }
        ],
        "extraction_confidence": 0.98,
    }

    state_mgr = FirestoreStateManager()
    orchestrator = WorkflowOrchestrator(state_manager=state_mgr)
    from app.orchestration.adapters.base import AdapterResult

    class MockDocIntelAdapter:
        def __init__(self, extraction_dict):
            self.extraction_dict = extraction_dict
            self.adapter_name = "DocIntelAdapter (Phase 7)"

        def execute(self, workflow_id, document_id, payload):
            return AdapterResult(
                success=True,
                output_reference={
                    "document_id": document_id,
                    "extraction": self.extraction_dict,
                    "status_reason": "Extraction successful",
                },
                observations={"extraction_confidence": 0.98},
            )

    orchestrator.adapters[WorkflowState.INGESTING] = MockDocIntelAdapter(clean_extraction)
    orchestrator.adapters[WorkflowState.EXTRACTING] = MockDocIntelAdapter(clean_extraction)

    wf_id = "wf-orch-clean-1"
    doc_id = "doc-orch-clean-1"
    wf, _ = orchestrator.start_workflow(wf_id, doc_id)

    # Ingesting
    evt = WorkflowEvent(
        workflow_id=wf_id,
        document_id=doc_id,
        event_type=EventType.DOCUMENT_UPLOADED,
        current_state="UPLOADED",
        workflow_revision=1,
        payload={"document_id": doc_id, "extraction": clean_extraction},
        event_timestamp=datetime.now(timezone.utc),
        correlation_id="corr-c-1",
    )
    wf, outbox = orchestrator.dispatch(evt)

    # Extracting
    evt = WorkflowEvent(
        workflow_id=wf_id,
        document_id=doc_id,
        event_type=EventType.INGESTION_COMPLETED,
        current_state="INGESTING",
        workflow_revision=2,
        payload=outbox.payload,
        event_timestamp=datetime.now(timezone.utc),
        correlation_id="corr-c-2",
    )
    wf, outbox = orchestrator.dispatch(evt)

    # Extracted
    evt = WorkflowEvent(
        workflow_id=wf_id,
        document_id=doc_id,
        event_type=EventType.EXTRACTION_COMPLETED,
        current_state="EXTRACTING",
        workflow_revision=3,
        payload=outbox.payload,
        event_timestamp=datetime.now(timezone.utc),
        correlation_id="corr-c-3",
    )
    wf, outbox = orchestrator.dispatch(evt)

    # Forensics
    evt = WorkflowEvent(
        workflow_id=wf_id,
        document_id=doc_id,
        event_type=EventType.ANALYSIS_TRIGGERED,
        current_state="EXTRACTED",
        workflow_revision=4,
        payload=outbox.payload,
        event_timestamp=datetime.now(timezone.utc),
        correlation_id="corr-c-4",
    )
    wf, outbox = orchestrator.dispatch(evt)
    assert wf.current_state == WorkflowState.FORENSIC_ANALYSIS

    # Compliance
    evt = WorkflowEvent(
        workflow_id=wf_id,
        document_id=doc_id,
        event_type=EventType.FORENSICS_COMPLETED,
        current_state="FORENSIC_ANALYSIS",
        workflow_revision=5,
        payload=outbox.payload,
        event_timestamp=datetime.now(timezone.utc),
        correlation_id="corr-c-5",
    )
    wf, outbox = orchestrator.dispatch(evt)
    assert wf.current_state == WorkflowState.COMPLIANCE_ANALYSIS

    # Risk
    evt = WorkflowEvent(
        workflow_id=wf_id,
        document_id=doc_id,
        event_type=EventType.COMPLIANCE_COMPLETED,
        current_state="COMPLIANCE_ANALYSIS",
        workflow_revision=6,
        payload=outbox.payload,
        event_timestamp=datetime.now(timezone.utc),
        correlation_id="corr-c-6",
    )
    wf, outbox = orchestrator.dispatch(evt)
    assert wf.current_state == WorkflowState.RISK_ASSESSED

    # Audit Seal
    evt = WorkflowEvent(
        workflow_id=wf_id,
        document_id=doc_id,
        event_type=EventType.RISK_COMPLETED,
        current_state="RISK_ASSESSED",
        workflow_revision=7,
        payload=outbox.payload,
        event_timestamp=datetime.now(timezone.utc),
        correlation_id="corr-c-7",
    )
    wf, outbox = orchestrator.dispatch(evt)
    assert wf.current_state == WorkflowState.AUDIT_SEALED

    # Report Generated
    evt = WorkflowEvent(
        workflow_id=wf_id,
        document_id=doc_id,
        event_type=EventType.AUDIT_COMPLETED,
        current_state="AUDIT_SEALED",
        workflow_revision=8,
        payload=outbox.payload,
        event_timestamp=datetime.now(timezone.utc),
        correlation_id="corr-c-8",
    )
    wf, outbox = orchestrator.dispatch(evt)
    assert wf.current_state == WorkflowState.REPORT_GENERATED

    # Completed
    evt = WorkflowEvent(
        workflow_id=wf_id,
        document_id=doc_id,
        event_type=EventType.REPORT_COMPLETED,
        current_state="REPORT_GENERATED",
        workflow_revision=9,
        payload=outbox.payload,
        event_timestamp=datetime.now(timezone.utc),
        correlation_id="corr-c-9",
    )
    wf, outbox = orchestrator.dispatch(evt)
    assert wf.current_state == WorkflowState.COMPLETED

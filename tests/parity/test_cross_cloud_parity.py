import json
import os
import pytest
from datetime import datetime, timezone

from app.core.contracts.clock import DeterministicTestClock
from app.core.state import AnalysisWorkflow, WorkflowState
from app.events.schemas import EventType, WorkflowEvent, compute_payload_hash
from app.infrastructure.azure.cosmos_state_manager import CosmosStateManager
from app.orchestration.orchestrator import WorkflowOrchestrator
from app.orchestration.state_manager import FirestoreStateManager


@pytest.mark.parity
def test_frozen_phase7_deterministic_parity():
    """Verify bit-identical deterministic pipeline behavior across GCP and Azure state managers.
    
    Uses frozen Phase 7 extraction fixture to avoid non-deterministic LLM variance.
    """
    fixture_path = os.path.join(
        os.path.dirname(__file__), "..", "fixtures", "frozen_phase7_extraction.json"
    )
    with open(fixture_path, "r", encoding="utf-8") as f:
        frozen_extraction = json.load(f)

    fixed_time = datetime(2026, 8, 20, 12, 0, 0, tzinfo=timezone.utc)
    clock = DeterministicTestClock(fixed_time)

    # 1. Initialize GCP state manager
    gcp_sm = FirestoreStateManager()
    gcp_wf, gcp_outbox = gcp_sm.create_workflow("wf-parity-gcp", "doc-parity-1")

    # 2. Initialize Azure state manager
    azure_sm = CosmosStateManager(clock=clock)
    azure_wf, azure_outbox = azure_sm.create_workflow("wf-parity-azure", "doc-parity-1")

    # Assert initial creation parity
    assert gcp_wf.current_state == azure_wf.current_state == WorkflowState.UPLOADED
    assert gcp_sm.get_workflow_revision("wf-parity-gcp") == azure_sm.get_workflow_revision("wf-parity-azure") == 1
    assert gcp_outbox.event_type == azure_outbox.event_type == EventType.DOCUMENT_UPLOADED
    assert gcp_outbox.to_workflow_event().payload_hash == azure_outbox.to_workflow_event().payload_hash == compute_payload_hash({"document_id": "doc-parity-1"})

    # 3. Simulate step 1: UPLOADED -> INGESTING
    gcp_sm.acquire_execution_claim("wf-parity-gcp", "wf-parity-gcp:1:DOCUMENT_UPLOADED", "worker-1")
    azure_sm.acquire_execution_claim("wf-parity-azure", "wf-parity-azure:1:DOCUMENT_UPLOADED", "worker-1")

    gcp_sm.commit_transaction(
        workflow_id="wf-parity-gcp",
        expected_revision=1,
        target_state=WorkflowState.INGESTING,
        output_reference={"ingestion": "ok"},
        next_event_type=EventType.INGESTION_COMPLETED,
        next_event_payload={"document_id": "doc-parity-1"},
    )
    azure_sm.commit_transaction(
        workflow_id="wf-parity-azure",
        expected_revision=1,
        target_state=WorkflowState.INGESTING,
        output_reference={"ingestion": "ok"},
        next_event_type=EventType.INGESTION_COMPLETED,
        next_event_payload={"document_id": "doc-parity-1"},
    )

    # 4. Simulate step 2: INGESTING -> EXTRACTING
    gcp_sm.acquire_execution_claim("wf-parity-gcp", "wf-parity-gcp:2:INGESTION_COMPLETED", "worker-1")
    azure_sm.acquire_execution_claim("wf-parity-azure", "wf-parity-azure:2:INGESTION_COMPLETED", "worker-1")

    gcp_sm.commit_transaction(
        workflow_id="wf-parity-gcp",
        expected_revision=2,
        target_state=WorkflowState.EXTRACTING,
        output_reference={"extracting": "ok"},
        next_event_type=EventType.EXTRACTION_COMPLETED,
        next_event_payload={"document_id": "doc-parity-1"},
    )
    azure_sm.commit_transaction(
        workflow_id="wf-parity-azure",
        expected_revision=2,
        target_state=WorkflowState.EXTRACTING,
        output_reference={"extracting": "ok"},
        next_event_type=EventType.EXTRACTION_COMPLETED,
        next_event_payload={"document_id": "doc-parity-1"},
    )

    # 5. Simulate step 3: EXTRACTING -> EXTRACTED with frozen extraction output
    gcp_sm.acquire_execution_claim("wf-parity-gcp", "wf-parity-gcp:3:EXTRACTION_COMPLETED", "worker-1")
    azure_sm.acquire_execution_claim("wf-parity-azure", "wf-parity-azure:3:EXTRACTION_COMPLETED", "worker-1")

    gcp_next_wf, gcp_next_outbox = gcp_sm.commit_transaction(
        workflow_id="wf-parity-gcp",
        expected_revision=3,
        target_state=WorkflowState.EXTRACTED,
        output_reference=frozen_extraction,
        next_event_type=EventType.ANALYSIS_TRIGGERED,
        next_event_payload={"document_id": "doc-parity-1", "extraction": frozen_extraction},
    )

    azure_next_wf, azure_next_outbox = azure_sm.commit_transaction(
        workflow_id="wf-parity-azure",
        expected_revision=3,
        target_state=WorkflowState.EXTRACTED,
        output_reference=frozen_extraction,
        next_event_type=EventType.ANALYSIS_TRIGGERED,
        next_event_payload={"document_id": "doc-parity-1", "extraction": frozen_extraction},
    )

    # 6. Assert bit-identical state and outbox hashes
    assert gcp_next_wf.current_state == azure_next_wf.current_state == WorkflowState.EXTRACTED
    assert gcp_sm.get_workflow_revision("wf-parity-gcp") == azure_sm.get_workflow_revision("wf-parity-azure") == 4
    assert gcp_next_outbox.to_workflow_event().payload_hash == azure_next_outbox.to_workflow_event().payload_hash
    assert gcp_next_outbox.event_type == azure_next_outbox.event_type == EventType.ANALYSIS_TRIGGERED

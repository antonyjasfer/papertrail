import pytest
from app.core.state import AnalysisWorkflow, WorkflowState
from app.events.schemas import EventType, WorkflowEvent
from app.infrastructure.azure.cosmos_state_manager import CosmosStateManager
from app.orchestration.orchestrator import STAGE_TRANSITION_MAP, WorkflowOrchestrator


@pytest.mark.e2e
def test_azure_e2e_pipeline_execution():
    """Verify full end-to-end pipeline execution on Azure CosmosStateManager."""
    sm = CosmosStateManager()
    orchestrator = WorkflowOrchestrator(state_manager=sm)

    workflow_id = "wf-e2e-azure-1"
    document_id = "doc-e2e-1"

    # Step 1: Start workflow
    workflow, outbox = orchestrator.start_workflow(workflow_id, document_id)
    assert workflow.current_state == WorkflowState.UPLOADED
    assert sm.get_workflow_revision(workflow_id) == 1

    # Step 2: Step through stages to completion
    current_state = workflow.current_state
    step_count = 0
    max_steps = 15

    while current_state != WorkflowState.COMPLETED and step_count < max_steps:
        # Find latest pending/recorded outbox event
        outbox_items = [v for k, v in sm._items.items() if k.startswith(f"{workflow_id}:outbox:")]
        assert len(outbox_items) > 0

        latest_outbox_item = sorted(outbox_items, key=lambda x: x["workflow_revision"])[-1]
        outbox_event = sm._deserialize_workflow(sm.get_workflow(workflow_id).model_dump(mode="json"))

        # Convert to WorkflowEvent
        event = WorkflowEvent(
            event_id=latest_outbox_item["event_id"],
            workflow_id=workflow_id,
            document_id=document_id,
            event_type=EventType(latest_outbox_item["event_type"]),
            current_state=current_state.value,
            workflow_revision=latest_outbox_item["workflow_revision"],
            payload=latest_outbox_item["payload"],
            event_timestamp=workflow.created_at,
            correlation_id=workflow_id,
        )

        workflow, next_outbox = orchestrator.dispatch(event)
        current_state = workflow.current_state
        step_count += 1

    assert workflow.current_state == WorkflowState.COMPLETED
    assert sm.get_workflow_revision(workflow_id) >= 8

import pytest
from fastapi.testclient import TestClient

from app.core.state import WorkflowState
from app.main import app
from app.orchestration.pipeline import PipelineRunner

client = TestClient(app)


def test_pipeline_runner_full_e2e():
    runner = PipelineRunner()
    w_id = runner.start_pipeline(document_id="doc-e2e-100")
    assert w_id.startswith("wf-")

    final_workflow = runner.run_to_completion(w_id, max_steps=15)
    assert final_workflow.current_state == WorkflowState.COMPLETED

    status_dict = runner.get_pipeline_status(w_id)
    assert status_dict["current_state"] == "COMPLETED"
    assert status_dict["workflow_revision"] == 10


def test_orchestration_api_endpoints():
    # Start pipeline via API
    resp_start = client.post(
        "/api/v1/pipeline/start",
        json={"document_id": "doc-api-200", "workflow_id": "wf-api-200"},
    )
    assert resp_start.status_code == 201
    data_start = resp_start.json()
    assert data_start["workflow_id"] == "wf-api-200"
    assert data_start["current_state"] == "COMPLETED"

    # Inspect pipeline status via API
    resp_status = client.get("/api/v1/pipeline/wf-api-200/status")
    assert resp_status.status_code == 200
    data_status = resp_status.json()
    assert data_status["workflow_id"] == "wf-api-200"
    assert data_status["current_state"] == "COMPLETED"

import os
import uuid
import pytest

from app.core.gcp import gcp_foundation
from app.core.state import WorkflowState, AnalysisWorkflow
from app.database.repositories.workflow_repository import (
    WorkflowRepository,
    WorkflowNotFoundError,
)


@pytest.mark.integration
def test_real_firestore_crud_lifecycle():
    """Integration Test: Real Firestore CRUD lifecycle.

    Skips safely if GCP authentication or Firestore connection is unavailable.
    When active, creates a temporary test document, reads it back, updates state,
    and cleans up by deleting the test document.
    """
    client = gcp_foundation.get_firestore_client()
    if client is None and not os.getenv("GCP_INTEGRATION"):
        pytest.skip("Live GCP Firestore credentials/connection unavailable. Skipping integration test.")

    repo = WorkflowRepository(client=client)
    test_id = f"wf-test-integration-{uuid.uuid4().hex[:8]}"
    doc_id = f"doc-test-{uuid.uuid4().hex[:8]}"

    try:
        # 1. Create workflow
        wf = AnalysisWorkflow(workflow_id=test_id, document_id=doc_id)
        created_wf = repo.create(wf)
        assert created_wf.workflow_id == test_id

        # 2. Check existence & Read back
        assert repo.exists(test_id) is True
        fetched_wf = repo.get(test_id)
        assert fetched_wf.workflow_id == test_id
        assert fetched_wf.document_id == doc_id
        assert fetched_wf.current_state == WorkflowState.UPLOADED

        # 3. Valid transition & Update
        fetched_wf.transition_to(WorkflowState.INGESTING)
        updated_wf = repo.update(fetched_wf)
        assert updated_wf.current_state == WorkflowState.INGESTING

        # 4. Read back updated state
        refetched_wf = repo.get(test_id)
        assert refetched_wf.current_state == WorkflowState.INGESTING

    finally:
        # Cleanup test document
        if repo.exists(test_id):
            repo.delete(test_id)

    # 5. Verify deletion
    assert repo.exists(test_id) is False
    with pytest.raises(WorkflowNotFoundError):
        repo.get(test_id)

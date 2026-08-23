from datetime import datetime, timezone
import pytest
from unittest.mock import MagicMock

from app.core.state import WorkflowState, AnalysisWorkflow, StateTransitionError
from app.database.repositories.workflow_repository import (
    WorkflowRepository,
    WorkflowNotFoundError,
    WorkflowAlreadyExistsError,
    WorkflowPersistenceError,
    serialize_workflow,
    deserialize_workflow,
)


class MockDocSnapshot:
    """Mock Firestore document snapshot."""

    def __init__(self, doc_id: str, data: dict = None, exists: bool = True):
        self.id = doc_id
        self._data = data
        self.exists = exists

    def to_dict(self):
        return self._data


class MockDocRef:
    """Mock Firestore document reference."""

    def __init__(self, doc_id: str, store: dict):
        self.id = doc_id
        self.store = store

    def get(self):
        if self.id in self.store:
            return MockDocSnapshot(self.id, data=self.store[self.id], exists=True)
        return MockDocSnapshot(self.id, data=None, exists=False)

    def set(self, payload: dict):
        self.store[self.id] = payload

    def delete(self):
        if self.id in self.store:
            del self.store[self.id]


class MockCollectionRef:
    """Mock Firestore collection reference."""

    def __init__(self, store: dict):
        self.store = store

    def document(self, doc_id: str):
        return MockDocRef(doc_id, self.store)


class MockFirestoreClient:
    """In-memory mock Firestore client for unit tests."""

    def __init__(self):
        self.store = {}

    def collection(self, collection_name: str):
        return MockCollectionRef(self.store)


@pytest.fixture
def mock_repo():
    mock_client = MockFirestoreClient()
    return WorkflowRepository(client=mock_client)


def test_create_workflow(mock_repo):
    """Test 1: Verify creating a workflow persists payload to mock store."""
    wf = AnalysisWorkflow(workflow_id="wf-001", document_id="doc-001")
    created = mock_repo.create(wf)
    assert created.workflow_id == "wf-001"
    assert mock_repo.exists("wf-001") is True


def test_read_workflow(mock_repo):
    """Test 2: Verify reading a workflow returns matching deserialized object."""
    wf = AnalysisWorkflow(workflow_id="wf-002", document_id="doc-002")
    mock_repo.create(wf)

    retrieved = mock_repo.get("wf-002")
    assert retrieved.workflow_id == "wf-002"
    assert retrieved.document_id == "doc-002"
    assert retrieved.current_state == WorkflowState.UPLOADED


def test_workflow_not_found(mock_repo):
    """Test 3: Verify getting non-existent workflow raises WorkflowNotFoundError."""
    with pytest.raises(WorkflowNotFoundError):
        mock_repo.get("non-existent-wf")


def test_duplicate_create_fails(mock_repo):
    """Test 4: Verify creating an existing workflow raises WorkflowAlreadyExistsError."""
    wf = AnalysisWorkflow(workflow_id="wf-004", document_id="doc-004")
    mock_repo.create(wf)
    with pytest.raises(WorkflowAlreadyExistsError):
        mock_repo.create(wf)


def test_update_existing_workflow(mock_repo):
    """Test 5: Verify updating an existing workflow succeeds."""
    wf = AnalysisWorkflow(workflow_id="wf-005", document_id="doc-005")
    mock_repo.create(wf)

    wf.transition_to(WorkflowState.INGESTING)
    mock_repo.update(wf)

    retrieved = mock_repo.get("wf-005")
    assert retrieved.current_state == WorkflowState.INGESTING


def test_update_missing_workflow_fails(mock_repo):
    """Test 6: Verify updating non-existent workflow raises WorkflowNotFoundError."""
    wf = AnalysisWorkflow(workflow_id="wf-missing", document_id="doc-missing")
    with pytest.raises(WorkflowNotFoundError):
        mock_repo.update(wf)


def test_state_enum_serialization():
    """Test 7: Verify WorkflowState Enum is serialized to string."""
    wf = AnalysisWorkflow(workflow_id="wf-007", document_id="doc-007", current_state=WorkflowState.EXTRACTED)
    data = serialize_workflow(wf)
    assert data["current_state"] == "EXTRACTED"
    assert isinstance(data["current_state"], str)


def test_state_enum_deserialization():
    """Test 8: Verify dictionary payload deserializes to WorkflowState Enum."""
    data = {
        "workflow_id": "wf-008",
        "document_id": "doc-008",
        "current_state": "FORENSIC_ANALYSIS",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    wf = deserialize_workflow(data)
    assert wf.current_state == WorkflowState.FORENSIC_ANALYSIS
    assert isinstance(wf.current_state, WorkflowState)


def test_created_at_immutability(mock_repo):
    """Test 9: Verify created_at timestamp in stored payload remains unchanged during updates."""
    wf = AnalysisWorkflow(workflow_id="wf-009", document_id="doc-009")
    original_created_at = wf.created_at.isoformat()
    mock_repo.create(wf)

    wf.transition_to(WorkflowState.INGESTING)
    mock_repo.update(wf)

    doc_data = mock_repo._get_doc_ref("wf-009").get().to_dict()
    assert doc_data["created_at"] == original_created_at


def test_updated_at_persistence(mock_repo):
    """Test 10: Verify updated_at is persisted correctly after a valid state transition."""
    wf = AnalysisWorkflow(workflow_id="wf-010", document_id="doc-010")
    mock_repo.create(wf)

    wf.transition_to(WorkflowState.INGESTING)
    mock_repo.update(wf)

    retrieved = mock_repo.get("wf-010")
    assert retrieved.updated_at == wf.updated_at


def test_persistence_failure_raises_error():
    """Test 11: Verify client failures raise WorkflowPersistenceError."""
    failing_client = MagicMock()
    failing_client.collection.side_effect = Exception("Firestore connection timeout")
    repo = WorkflowRepository(client=failing_client)

    wf = AnalysisWorkflow(workflow_id="wf-fail", document_id="doc-fail")
    with pytest.raises(WorkflowPersistenceError) as exc_info:
        repo.create(wf)
    assert "Firestore connection timeout" in str(exc_info.value)


def test_repository_does_not_invent_transitions(mock_repo):
    """Test 12: Verify repository relies on State Machine for validation."""
    wf = AnalysisWorkflow(workflow_id="wf-012", document_id="doc-012")
    mock_repo.create(wf)

    # Attempting invalid state transition on workflow instance must raise StateTransitionError
    with pytest.raises(StateTransitionError):
        wf.transition_to(WorkflowState.COMPLETED)

    # State in repository remains UPLOADED
    stored_wf = mock_repo.get("wf-012")
    assert stored_wf.current_state == WorkflowState.UPLOADED

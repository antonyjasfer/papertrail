import logging
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from app.core.gcp import gcp_foundation
from app.core.state import AnalysisWorkflow, WorkflowState

logger = logging.getLogger("papertrail.database.workflow_repository")


class WorkflowNotFoundError(Exception):
    """Exception raised when a requested workflow document is not found in Firestore."""

    def __init__(self, workflow_id: str):
        self.workflow_id = workflow_id
        super().__init__(f"Workflow with ID '{workflow_id}' was not found in database.")


class WorkflowAlreadyExistsError(Exception):
    """Exception raised when creating a workflow that already exists in Firestore."""

    def __init__(self, workflow_id: str):
        self.workflow_id = workflow_id
        super().__init__(f"Workflow with ID '{workflow_id}' already exists in database.")


class WorkflowPersistenceError(Exception):
    """Exception raised when a Firestore persistence operation fails."""

    def __init__(self, operation: str, workflow_id: str, message: str):
        self.operation = operation
        self.workflow_id = workflow_id
        super().__init__(f"Failed to {operation} workflow '{workflow_id}': {message}")


def serialize_workflow(workflow: AnalysisWorkflow) -> Dict[str, Any]:
    """Serialize AnalysisWorkflow model into a Firestore-compatible dictionary."""
    return {
        "workflow_id": workflow.workflow_id,
        "document_id": workflow.document_id,
        "current_state": workflow.current_state.value,
        "created_at": workflow.created_at.isoformat(),
        "updated_at": workflow.updated_at.isoformat(),
        "failure_reason": workflow.failure_reason,
        "escalation_reason": workflow.escalation_reason,
        "review_reason": workflow.review_reason,
    }


def deserialize_workflow(data: Dict[str, Any]) -> AnalysisWorkflow:
    """Deserialize Firestore document dictionary into an AnalysisWorkflow model."""
    try:
        created_at_val = data["created_at"]
        if isinstance(created_at_val, str):
            created_at = datetime.fromisoformat(created_at_val)
        elif isinstance(created_at_val, datetime):
            created_at = created_at_val
        else:
            created_at = datetime.now(timezone.utc)

        updated_at_val = data["updated_at"]
        if isinstance(updated_at_val, str):
            updated_at = datetime.fromisoformat(updated_at_val)
        elif isinstance(updated_at_val, datetime):
            updated_at = updated_at_val
        else:
            updated_at = datetime.now(timezone.utc)

        return AnalysisWorkflow(
            workflow_id=data["workflow_id"],
            document_id=data["document_id"],
            current_state=WorkflowState(data["current_state"]),
            created_at=created_at,
            updated_at=updated_at,
            failure_reason=data.get("failure_reason"),
            escalation_reason=data.get("escalation_reason"),
            review_reason=data.get("review_reason"),
        )
    except Exception as err:
        raise ValueError(f"Error deserializing workflow document payload: {err}") from err


class WorkflowRepository:
    """Repository handling Firestore persistence for AnalysisWorkflow instances."""

    COLLECTION_NAME = "workflows"

    def __init__(self, client: Optional[Any] = None):
        self._client = client

    @property
    def client(self) -> Any:
        """Lazily retrieve or return initialized Firestore client."""
        if self._client is None:
            self._client = gcp_foundation.get_firestore_client()
        if self._client is None:
            raise WorkflowPersistenceError(
                "connect", "N/A", "Firestore client is unavailable in current environment."
            )
        return self._client

    def _get_doc_ref(self, workflow_id: str) -> Any:
        """Get Firestore document reference for a workflow_id."""
        return self.client.collection(self.COLLECTION_NAME).document(workflow_id)

    def create(self, workflow: AnalysisWorkflow) -> AnalysisWorkflow:
        """Persist a new AnalysisWorkflow instance to Firestore.

        Raises WorkflowAlreadyExistsError if document already exists.
        """
        try:
            doc_ref = self._get_doc_ref(workflow.workflow_id)
            doc_snapshot = doc_ref.get()
            if doc_snapshot.exists:
                raise WorkflowAlreadyExistsError(workflow.workflow_id)

            payload = serialize_workflow(workflow)
            doc_ref.set(payload)
            logger.info("Successfully created workflow document '%s'", workflow.workflow_id)
            return workflow
        except WorkflowAlreadyExistsError:
            raise
        except Exception as err:
            raise WorkflowPersistenceError("create", workflow.workflow_id, str(err)) from err

    def get(self, workflow_id: str) -> AnalysisWorkflow:
        """Retrieve AnalysisWorkflow instance from Firestore by workflow_id.

        Raises WorkflowNotFoundError if document does not exist.
        """
        try:
            doc_ref = self._get_doc_ref(workflow_id)
            doc_snapshot = doc_ref.get()
            if not doc_snapshot.exists:
                raise WorkflowNotFoundError(workflow_id)

            data = doc_snapshot.to_dict()
            return deserialize_workflow(data)
        except WorkflowNotFoundError:
            raise
        except Exception as err:
            raise WorkflowPersistenceError("get", workflow_id, str(err)) from err

    def exists(self, workflow_id: str) -> bool:
        """Check whether a workflow document exists in Firestore."""
        try:
            doc_ref = self._get_doc_ref(workflow_id)
            doc_snapshot = doc_ref.get()
            return doc_snapshot.exists
        except Exception as err:
            logger.warning("Error checking existence of workflow '%s': %s", workflow_id, err)
            return False

    def update(self, workflow: AnalysisWorkflow) -> AnalysisWorkflow:
        """Update an existing AnalysisWorkflow instance in Firestore.

        Preserves original created_at timestamp in database.
        Raises WorkflowNotFoundError if document does not exist.
        """
        try:
            doc_ref = self._get_doc_ref(workflow.workflow_id)
            doc_snapshot = doc_ref.get()
            if not doc_snapshot.exists:
                raise WorkflowNotFoundError(workflow.workflow_id)

            existing_data = doc_snapshot.to_dict()
            payload = serialize_workflow(workflow)

            # Enforce created_at immutability from stored document
            if "created_at" in existing_data:
                payload["created_at"] = existing_data["created_at"]

            doc_ref.set(payload)
            logger.info("Successfully updated workflow document '%s'", workflow.workflow_id)
            return workflow
        except WorkflowNotFoundError:
            raise
        except Exception as err:
            raise WorkflowPersistenceError("update", workflow.workflow_id, str(err)) from err

    def save(self, workflow: AnalysisWorkflow) -> AnalysisWorkflow:
        """Save a workflow instance. Updates if document exists, creates if missing."""
        if self.exists(workflow.workflow_id):
            return self.update(workflow)
        else:
            return self.create(workflow)

    def delete(self, workflow_id: str) -> bool:
        """Delete a workflow document from Firestore (for cleanup or admin tasks)."""
        try:
            doc_ref = self._get_doc_ref(workflow_id)
            doc_snapshot = doc_ref.get()
            if not doc_snapshot.exists:
                return False

            doc_ref.delete()
            logger.info("Deleted workflow document '%s'", workflow_id)
            return True
        except Exception as err:
            raise WorkflowPersistenceError("delete", workflow_id, str(err)) from err

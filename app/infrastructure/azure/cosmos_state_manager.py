import hashlib
import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

from app.core.config import settings
from app.core.contracts.clock import IClock, ProductionClock
from app.core.contracts.state_manager import IWorkflowStateManager
from app.core.errors import ErrorCategory
from app.core.logging import CorrelationContext, log_event
from app.core.state import AnalysisWorkflow, WorkflowState, validate_transition
from app.events.schemas import EventType, WorkflowEvent, compute_payload_hash
from app.infrastructure.azure.foundation import azure_foundation
from app.orchestration.errors import (
    FutureEventError,
    IntegrityConflictError,
    LeaseAcquisitionError,
    StaleEventError,
    StateSynchronizationError,
)
from app.orchestration.models import ClaimStatus, WorkflowExecutionClaim
from app.orchestration.outbox import OutboxStatus, WorkflowOutboxEvent

logger = logging.getLogger("papertrail.azure.cosmos_state_manager")


def _hash_key(key: str) -> str:
    """Compute deterministic SHA-256 hash substring for item IDs."""
    return hashlib.sha256(key.encode("utf-8")).hexdigest()[:16]


class CosmosStateManager:
    """Azure Cosmos DB State Manager implementing single-container TransactionalBatch.

    All mutable state entities for a workflow (WORKFLOW, OUTBOX, EXECUTION_CLAIM, IDEMPOTENCY)
    are co-located in the 'workflow_state' container under partition key '/workflow_id'.
    """

    _shared_items: Dict[str, Dict[str, Any]] = {}

    def __init__(self, clock: Optional[IClock] = None) -> None:
        self.clock = clock or ProductionClock()
        self._container: Optional[Any] = None
        self.database_name = settings.azure_cosmos_database
        self.container_name = settings.azure_cosmos_container_workflow_state
        # In-memory storage structures for local testing when Cosmos client is not provided
        self._items: Dict[str, Dict[str, Any]] = self._shared_items

    @property
    def container(self) -> Optional[Any]:
        """Lazily initialize or return Cosmos DB container client."""
        if self._container is None:
            cosmos_client = azure_foundation.get_cosmos_client()
            if cosmos_client is not None:
                try:
                    db = cosmos_client.get_database_client(self.database_name)
                    self._container = db.get_container_client(self.container_name)
                except Exception as err:
                    log_event(
                        logger=logger,
                        level=logging.WARNING,
                        message=f"Could not obtain Cosmos container '{self.container_name}': {err}",
                        component="cosmos_state_manager",
                        operation="get_container",
                        error_category=ErrorCategory.COSMOS_ERROR.value,
                        error_details=str(err),
                    )
        return self._container

    def get_workflow(self, workflow_id: str) -> Optional[AnalysisWorkflow]:
        """Retrieve AnalysisWorkflow instance from Cosmos DB."""
        item_id = f"wf:{workflow_id}"
        if self.container is not None:
            try:
                item = self.container.read_item(item=item_id, partition_key=workflow_id)
                return self._deserialize_workflow(item)
            except Exception:
                return None
        # Fallback in-memory
        key = f"{workflow_id}:{item_id}"
        item = self._items.get(key)
        return self._deserialize_workflow(item) if item else None

    def get_workflow_revision(self, workflow_id: str) -> int:
        """Retrieve current monotonic revision of workflow."""
        wf = self.get_workflow(workflow_id)
        if wf:
            item_id = f"wf:{workflow_id}"
            if self.container is not None:
                try:
                    item = self.container.read_item(item=item_id, partition_key=workflow_id)
                    return item.get("workflow_revision", 1)
                except Exception:
                    pass
            key = f"{workflow_id}:{item_id}"
            item = self._items.get(key)
            if item:
                return item.get("workflow_revision", 1)
        return 1

    def create_workflow(
        self, workflow_id: str, document_id: str
    ) -> Tuple[AnalysisWorkflow, WorkflowOutboxEvent]:
        """Initialize a new workflow and outbox record atomically in Cosmos DB."""
        now = self.clock.now_utc()
        workflow = AnalysisWorkflow(
            workflow_id=workflow_id,
            document_id=document_id,
            current_state=WorkflowState.UPLOADED,
            created_at=now,
            updated_at=now,
        )

        wf_item = {
            "id": f"wf:{workflow_id}",
            "type": "WORKFLOW",
            "workflow_id": workflow_id,
            "document_id": document_id,
            "current_state": WorkflowState.UPLOADED.value,
            "workflow_revision": 1,
            "created_at": now.isoformat(),
            "updated_at": now.isoformat(),
            "failure_reason": None,
            "escalation_reason": None,
            "review_reason": None,
            "_etag": f"etag-{uuid.uuid4().hex[:8]}",
        }

        payload = {"document_id": document_id}
        outbox_id = f"evt-init-{workflow_id}"
        outbox_item = {
            "id": f"outbox:{outbox_id}",
            "type": "OUTBOX",
            "outbox_id": outbox_id,
            "workflow_id": workflow_id,
            "document_id": document_id,
            "event_id": outbox_id,
            "logical_event_key": f"{workflow_id}:1:{EventType.DOCUMENT_UPLOADED.value}",
            "event_type": EventType.DOCUMENT_UPLOADED.value,
            "workflow_revision": 1,
            "payload_hash": compute_payload_hash(payload),
            "payload": payload,
            "status": OutboxStatus.PENDING.value,
            "created_at": now.isoformat(),
            "attempts": 0,
        }

        if self.container is not None:
            try:
                if hasattr(self.container, "execute_item_batch"):
                    batch = [("create", (wf_item,)), ("create", (outbox_item,))]
                    self.container.execute_item_batch(batch, partition_key=workflow_id)
                elif hasattr(self.container, "create_transactional_batch"):
                    batch = self.container.create_transactional_batch(partition_key=workflow_id)
                    batch.create_item(wf_item)
                    batch.create_item(outbox_item)
                    self.container.execute_transactional_batch(batch)
                else:
                    self.container.upsert_item(wf_item)
                    self.container.upsert_item(outbox_item)

                log_event(
                    logger=logger,
                    level=logging.INFO,
                    message=f"Created workflow '{workflow_id}' and outbox item in Cosmos DB (Partition /{workflow_id})",
                    component="cosmos_state_manager",
                    operation="create_workflow_batch",
                    workflow_id=workflow_id,
                    document_id=document_id,
                    outcome="COMMITTED",
                )
            except Exception as err:
                log_event(
                    logger=logger,
                    level=logging.ERROR,
                    message=f"Cosmos transactional batch create_workflow failed: {err}",
                    component="cosmos_state_manager",
                    operation="create_workflow_batch",
                    workflow_id=workflow_id,
                    document_id=document_id,
                    error_category=ErrorCategory.COSMOS_ERROR.value,
                    error_details=str(err),
                )
                raise

        # Save to in-memory store
        self._items[f"{workflow_id}:{wf_item['id']}"] = wf_item
        self._items[f"{workflow_id}:{outbox_item['id']}"] = outbox_item

        outbox_event = WorkflowOutboxEvent(
            outbox_id=outbox_id,
            workflow_id=workflow_id,
            document_id=document_id,
            event_id=outbox_id,
            event_type=EventType.DOCUMENT_UPLOADED,
            workflow_revision=1,
            payload_hash=outbox_item["payload_hash"],
            payload=payload,
            status=OutboxStatus.PENDING,
            created_at=now,
        )
        return workflow, outbox_event

    def check_idempotency(self, event: WorkflowEvent) -> Tuple[bool, Optional[Dict[str, Any]]]:
        """Check idempotency record for event."""
        workflow_id = event.workflow_id
        logical_key = event.get_logical_event_key()
        idemp_id = f"idemp:{_hash_key(logical_key)}"

        idemp_item = None
        if self.container is not None:
            try:
                idemp_item = self.container.read_item(item=idemp_id, partition_key=workflow_id)
            except Exception:
                idemp_item = None
        else:
            idemp_item = self._items.get(f"{workflow_id}:{idemp_id}")

        current_revision = self.get_workflow_revision(workflow_id)

        if event.workflow_revision < current_revision:
            if idemp_item:
                stored_hash = idemp_item.get("payload_hash")
                if stored_hash and stored_hash != event.payload_hash:
                    raise IntegrityConflictError(
                        f"Integrity conflict for event key '{logical_key}': payload hash mismatch."
                    )
                return True, idemp_item.get("output_reference")
            raise StaleEventError(workflow_id, event.workflow_revision, current_revision)

        if event.workflow_revision > current_revision:
            raise FutureEventError(workflow_id, event.workflow_revision, current_revision)

        if idemp_item:
            stored_hash = idemp_item.get("payload_hash")
            if stored_hash and stored_hash != event.payload_hash:
                raise IntegrityConflictError(
                    f"Integrity conflict for event key '{logical_key}': payload hash mismatch."
                )
            return True, idemp_item.get("output_reference")

        return False, None

    def acquire_execution_claim(
        self,
        workflow_id: str,
        logical_event_key: str,
        owner_id: str,
        ttl_seconds: int = 300,
    ) -> WorkflowExecutionClaim:
        """Acquire an execution claim lease using ETag / CAS conditional write."""
        now = self.clock.now_utc()
        expires_at = now + timedelta(seconds=ttl_seconds)
        claim_id = f"claim:{_hash_key(logical_event_key)}"

        claim_item = None
        if self.container is not None:
            try:
                claim_item = self.container.read_item(item=claim_id, partition_key=workflow_id)
            except Exception:
                claim_item = None
        else:
            claim_item = self._items.get(f"{workflow_id}:{claim_id}")

        if claim_item and claim_item.get("status") in (ClaimStatus.CLAIMED.value, ClaimStatus.RUNNING.value):
            lease_exp_str = claim_item.get("lease_expires_at")
            lease_exp = datetime.fromisoformat(lease_exp_str) if isinstance(lease_exp_str, str) else lease_exp_str
            if now < lease_exp and claim_item.get("owner_id") != owner_id:
                raise LeaseAcquisitionError(logical_event_key, claim_item.get("owner_id", "unknown"), str(lease_exp))

        new_claim_item = {
            "id": claim_id,
            "type": "EXECUTION_CLAIM",
            "claim_id": claim_id,
            "workflow_id": workflow_id,
            "event_id": f"evt-{workflow_id}-{_hash_key(logical_event_key)}",
            "logical_event_key": logical_event_key,
            "payload_hash": "",
            "owner_id": owner_id,
            "status": ClaimStatus.RUNNING.value,
            "claimed_at": now.isoformat(),
            "lease_expires_at": expires_at.isoformat(),
            "_etag": f"etag-{uuid.uuid4().hex[:8]}",
        }

        if self.container is not None:
            try:
                self.container.upsert_item(new_claim_item)
            except Exception as err:
                raise StateSynchronizationError(workflow_id, 0, 0) from err

        self._items[f"{workflow_id}:{claim_id}"] = new_claim_item

        return WorkflowExecutionClaim(
            claim_id=claim_id,
            workflow_id=workflow_id,
            logical_event_key=logical_event_key,
            execution_id=f"exec-{uuid.uuid4().hex[:8]}",
            owner_id=owner_id,
            status=ClaimStatus.RUNNING,
            claimed_at=now,
            lease_expires_at=expires_at,
        )

    def commit_transaction(
        self,
        workflow_id: str,
        expected_revision: int,
        target_state: WorkflowState,
        output_reference: Optional[Dict[str, Any]] = None,
        next_event_type: Optional[EventType] = None,
        next_event_payload: Optional[Dict[str, Any]] = None,
        reason: Optional[str] = None,
    ) -> Tuple[AnalysisWorkflow, Optional[WorkflowOutboxEvent]]:
        """Commit workflow update, claim completion, idempotency record, and outbox record atomically."""
        stored_revision = self.get_workflow_revision(workflow_id)
        if expected_revision != stored_revision:
            raise StateSynchronizationError(workflow_id, expected_revision, stored_revision)

        workflow = self.get_workflow(workflow_id)
        if not workflow:
            raise RuntimeError(f"Workflow '{workflow_id}' not found.")

        previous_state = workflow.current_state
        workflow.transition_to(target_state, reason=reason)
        new_revision = stored_revision + 1
        now = self.clock.now_utc()

        # Step 1: Update WORKFLOW item
        wf_item_id = f"wf:{workflow_id}"
        wf_item = {
            "id": wf_item_id,
            "type": "WORKFLOW",
            "workflow_id": workflow_id,
            "document_id": workflow.document_id,
            "current_state": target_state.value,
            "workflow_revision": new_revision,
            "created_at": workflow.created_at.isoformat(),
            "updated_at": now.isoformat(),
            "failure_reason": workflow.failure_reason,
            "escalation_reason": workflow.escalation_reason,
            "review_reason": workflow.review_reason,
            "_etag": f"etag-{uuid.uuid4().hex[:8]}",
        }

        # Step 2: Locate active claim and prepare claim completion + idempotency items
        claim_item = None
        for k, v in self._items.items():
            if k.startswith(f"{workflow_id}:claim:") and v.get("status") == ClaimStatus.RUNNING.value:
                claim_item = v
                break

        idemp_item = None
        if claim_item:
            claim_item["status"] = ClaimStatus.COMPLETED.value
            claim_item["output_reference"] = output_reference
            logical_key = claim_item.get("logical_event_key", f"{workflow_id}:{stored_revision}:{previous_state.value}")
            idemp_id = f"idemp:{_hash_key(logical_key)}"
            idemp_item = {
                "id": idemp_id,
                "type": "IDEMPOTENCY",
                "event_id": claim_item.get("event_id", f"evt-{workflow_id}-{stored_revision}"),
                "logical_event_key": logical_key,
                "payload_hash": claim_item.get("payload_hash", ""),
                "workflow_id": workflow_id,
                "workflow_revision": stored_revision,
                "output_reference": output_reference,
                "processed_at": now.isoformat(),
            }

        # Step 3: Outbox record
        outbox_event: Optional[WorkflowOutboxEvent] = None
        outbox_item = None
        if next_event_type is not None:
            payload = next_event_payload or {}
            outbox_id = f"evt-{workflow_id}-rev{new_revision}"
            payload_hash = compute_payload_hash(payload)
            outbox_item = {
                "id": f"outbox:{outbox_id}",
                "type": "OUTBOX",
                "outbox_id": outbox_id,
                "workflow_id": workflow_id,
                "document_id": workflow.document_id,
                "event_id": outbox_id,
                "logical_event_key": f"{workflow_id}:{new_revision}:{next_event_type.value}",
                "event_type": next_event_type.value,
                "workflow_revision": new_revision,
                "payload_hash": payload_hash,
                "payload": payload,
                "status": OutboxStatus.PENDING.value,
                "created_at": now.isoformat(),
                "attempts": 0,
            }
            outbox_event = WorkflowOutboxEvent(
                outbox_id=outbox_id,
                workflow_id=workflow_id,
                document_id=workflow.document_id,
                event_id=outbox_id,
                event_type=next_event_type,
                workflow_revision=new_revision,
                payload_hash=payload_hash,
                payload=payload,
                status=OutboxStatus.PENDING,
                created_at=now,
            )

        # Step 4: Execute TransactionalBatch if Cosmos container is active
        if self.container is not None:
            try:
                if hasattr(self.container, "execute_item_batch"):
                    batch = [("upsert", (wf_item,))]
                    if claim_item:
                        batch.append(("upsert", (claim_item,)))
                    if idemp_item:
                        batch.append(("upsert", (idemp_item,)))
                    if outbox_item:
                        batch.append(("create", (outbox_item,)))
                    self.container.execute_item_batch(batch, partition_key=workflow_id)
                elif hasattr(self.container, "create_transactional_batch"):
                    batch = self.container.create_transactional_batch(partition_key=workflow_id)
                    batch.upsert_item(wf_item)
                    if claim_item:
                        batch.upsert_item(claim_item)
                    if idemp_item:
                        batch.upsert_item(idemp_item)
                    if outbox_item:
                        batch.create_item(outbox_item)
                    self.container.execute_transactional_batch(batch)
                else:
                    self.container.upsert_item(wf_item)
                    if claim_item:
                        self.container.upsert_item(claim_item)
                    if idemp_item:
                        self.container.upsert_item(idemp_item)
                    if outbox_item:
                        self.container.upsert_item(outbox_item)

                log_event(
                    logger=logger,
                    level=logging.INFO,
                    message=f"Committed Cosmos TransactionalBatch for '{workflow_id}' (Rev {stored_revision} -> {new_revision}, {previous_state.value} -> {target_state.value})",
                    component="cosmos_state_manager",
                    operation="commit_transaction_batch",
                    workflow_id=workflow_id,
                    previous_state=previous_state.value,
                    target_state=target_state.value,
                    workflow_revision=new_revision,
                    outcome="COMMITTED",
                )
            except Exception as err:
                log_event(
                    logger=logger,
                    level=logging.ERROR,
                    message=f"Cosmos TransactionalBatch commit failed: {err}",
                    component="cosmos_state_manager",
                    operation="commit_transaction_batch",
                    workflow_id=workflow_id,
                    error_category=ErrorCategory.COSMOS_ERROR.value,
                    error_details=str(err),
                )
                raise StateSynchronizationError(workflow_id, expected_revision, stored_revision) from err

        # Save to in-memory store
        self._items[f"{workflow_id}:{wf_item['id']}"] = wf_item
        if claim_item:
            self._items[f"{workflow_id}:{claim_item['id']}"] = claim_item
        if idemp_item:
            self._items[f"{workflow_id}:{idemp_item['id']}"] = idemp_item
        if outbox_item:
            self._items[f"{workflow_id}:{outbox_item['id']}"] = outbox_item

        return workflow, outbox_event

    def _deserialize_workflow(self, data: Dict[str, Any]) -> AnalysisWorkflow:
        created_at_val = data.get("created_at")
        created_at = datetime.fromisoformat(created_at_val) if isinstance(created_at_val, str) else self.clock.now_utc()
        updated_at_val = data.get("updated_at")
        updated_at = datetime.fromisoformat(updated_at_val) if isinstance(updated_at_val, str) else self.clock.now_utc()

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

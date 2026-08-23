import logging
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional
import uuid
from pydantic import BaseModel, Field

from app.events.publisher import BasePublisher
from app.events.schemas import EventType, WorkflowEvent

logger = logging.getLogger(__name__)


class OutboxStatus(str, Enum):
    """Status lifecycle of transactional outbox event records."""

    PENDING = "PENDING"
    PUBLISHED = "PUBLISHED"
    FAILED = "FAILED"
    RETRYING = "RETRYING"


class WorkflowOutboxEvent(BaseModel):
    """Transactional Outbox Record stored in Firestore atomically with state transitions."""

    outbox_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    workflow_id: str
    document_id: str
    event_id: str
    event_type: EventType
    workflow_revision: int
    payload_hash: str
    payload: Dict[str, Any] = Field(default_factory=dict)
    status: OutboxStatus = OutboxStatus.PENDING
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    published_at: Optional[datetime] = None
    attempts: int = 0
    last_error: Optional[str] = None

    def to_workflow_event(self, correlation_id: str = "") -> WorkflowEvent:
        """Convert outbox record into a canonical WorkflowEvent envelope."""
        return WorkflowEvent(
            event_id=self.event_id,
            workflow_id=self.workflow_id,
            document_id=self.document_id,
            event_type=self.event_type,
            current_state="",
            workflow_revision=self.workflow_revision,
            payload_hash=self.payload_hash,
            payload=self.payload,
            event_timestamp=self.created_at,
            correlation_id=correlation_id or self.workflow_id,
            attempt_number=self.attempts + 1,
        )


class OutboxPublisherWorker:
    """Worker responsible for dispatching PENDING transactional outbox events to Pub/Sub."""

    def __init__(self, publisher: BasePublisher, max_retries: int = 3) -> None:
        self.publisher = publisher
        self.max_retries = max_retries
        self._in_memory_outbox: List[WorkflowOutboxEvent] = []

    def add_outbox_event(self, outbox_event: WorkflowOutboxEvent) -> None:
        """Store outbox record (used in local testing / in-memory mode)."""
        self._in_memory_outbox.append(outbox_event)

    def process_pending(self) -> int:
        """Process pending outbox items and publish to Pub/Sub. Return count published."""
        published_count = 0
        for record in self._in_memory_outbox:
            if record.status in (OutboxStatus.PENDING, OutboxStatus.RETRYING):
                try:
                    record.attempts += 1
                    event = record.to_workflow_event()
                    self.publisher.publish(event)
                    record.status = OutboxStatus.PUBLISHED
                    record.published_at = datetime.now(timezone.utc)
                    published_count += 1
                    logger.info(
                        f"[OutboxPublisherWorker] Outbox event {record.outbox_id} "
                        f"published successfully for workflow {record.workflow_id} (Rev {record.workflow_revision})."
                    )
                except Exception as e:
                    record.last_error = str(e)
                    if record.attempts >= self.max_retries:
                        record.status = OutboxStatus.FAILED
                        logger.error(
                            f"[OutboxPublisherWorker] Outbox event {record.outbox_id} failed after {record.attempts} attempts: {e}"
                        )
                    else:
                        record.status = OutboxStatus.RETRYING
                        logger.warning(
                            f"[OutboxPublisherWorker] Outbox event {record.outbox_id} retry attempt {record.attempts}: {e}"
                        )
        return published_count

import json
import logging
from typing import List, Optional
from app.events.schemas import WorkflowEvent

logger = logging.getLogger(__name__)


class BasePublisher:
    """Interface for event publishing."""

    def publish(self, event: WorkflowEvent) -> str:
        raise NotImplementedError

    def publish_batch(self, events: List[WorkflowEvent]) -> List[str]:
        return [self.publish(e) for e in events]


class MockPubSubPublisher(BasePublisher):
    """In-memory mock publisher for testing and local development without GCP credentials."""

    def __init__(self) -> None:
        self.published_events: List[WorkflowEvent] = []

    def publish(self, event: WorkflowEvent) -> str:
        """Record published event in memory."""
        self.published_events.append(event)
        logger.info(
            f"[MockPubSubPublisher] Published event {event.event_id} "
            f"(Type: {event.event_type.value}, Workflow: {event.workflow_id}, Rev: {event.workflow_revision})"
        )
        return event.event_id

    def clear(self) -> None:
        self.published_events.clear()


class PubSubPublisher(BasePublisher):
    """Production GCP Cloud Pub/Sub publisher."""

    def __init__(self, project_id: str, topic_id: str) -> None:
        self.project_id = project_id
        self.topic_id = topic_id
        self._client = None  # Lazily instantiated when GCP credentials available

    def publish(self, event: WorkflowEvent) -> str:
        """Publish WorkflowEvent to GCP Pub/Sub topic."""
        payload_bytes = json.dumps(
            event.model_dump(mode="json"), default=str
        ).encode("utf-8")
        
        # If no client or in dev mode without GCP credentials, log and return event_id
        try:
            from google.cloud import pubsub_v1
            if self._client is None:
                self._client = pubsub_v1.PublisherClient()
            topic_path = self._client.topic_path(self.project_id, self.topic_id)
            future = self._client.publish(
                topic_path,
                data=payload_bytes,
                workflow_id=event.workflow_id,
                event_type=event.event_type.value,
                workflow_revision=str(event.workflow_revision),
            )
            return future.result(timeout=10)
        except Exception as e:
            logger.warning(
                f"[PubSubPublisher] GCP Pub/Sub publish unfulfilled ({e}). Falling back to log record."
            )
            return event.event_id

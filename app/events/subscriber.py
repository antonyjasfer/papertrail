import json
import logging
from typing import Any, Callable, Optional
from app.events.schemas import WorkflowEvent

logger = logging.getLogger(__name__)


class BaseSubscriber:
    """Interface for background event subscribers."""

    def listen(self, callback: Callable[[WorkflowEvent], Any]) -> None:
        raise NotImplementedError


class MockPubSubSubscriber(BaseSubscriber):
    """In-memory mock subscriber for testing."""

    def __init__(self) -> None:
        self._handler: Optional[Callable[[WorkflowEvent], Any]] = None

    def set_handler(self, handler: Callable[[WorkflowEvent], Any]) -> None:
        self._handler = handler

    def listen(self, callback: Callable[[WorkflowEvent], Any]) -> None:
        self._handler = callback

    def simulate_event(self, event: WorkflowEvent) -> Any:
        """Simulate receipt of an incoming event."""
        if self._handler is None:
            raise RuntimeError("Subscriber handler is not registered.")
        logger.info(
            f"[MockPubSubSubscriber] Delivering event {event.event_id} to handler."
        )
        return self._handler(event)


class PubSubSubscriber(BaseSubscriber):
    """Production GCP Cloud Pub/Sub subscriber."""

    def __init__(self, project_id: str, subscription_id: str) -> None:
        self.project_id = project_id
        self.subscription_id = subscription_id

    def process_message(
        self, message_data: bytes, handler: Callable[[WorkflowEvent], Any]
    ) -> bool:
        """Process incoming raw message bytes and dispatch to handler."""
        try:
            data_dict = json.loads(message_data.decode("utf-8"))
            event = WorkflowEvent(**data_dict)
            handler(event)
            return True
        except Exception as e:
            logger.error(
                f"[PubSubSubscriber] Failed to process Pub/Sub message: {e}",
                exc_info=True,
            )
            return False

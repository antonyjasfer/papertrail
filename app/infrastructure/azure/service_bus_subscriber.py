import json
import logging
from typing import Any, Callable, Optional

from app.core.config import settings
from app.events.schemas import WorkflowEvent
from app.events.subscriber import BaseSubscriber
from app.infrastructure.azure.foundation import azure_foundation

logger = logging.getLogger("papertrail.azure.service_bus_subscriber")


class ServiceBusSubscriber(BaseSubscriber):
    """Azure Service Bus Subscription listener implementing BaseSubscriber interface."""

    def __init__(
        self,
        topic_name: Optional[str] = None,
        subscription_name: Optional[str] = None,
        servicebus_client: Optional[Any] = None,
    ) -> None:
        self.topic_name = topic_name or settings.azure_servicebus_topic_workflow_events
        self.subscription_name = subscription_name or settings.azure_servicebus_subscription_orchestrator
        self._servicebus_client = servicebus_client
        self._handler: Optional[Callable[[WorkflowEvent], Any]] = None

    @property
    def client(self) -> Optional[Any]:
        if self._servicebus_client is None:
            self._servicebus_client = azure_foundation.get_servicebus_client()
        return self._servicebus_client

    def listen(self, callback: Callable[[WorkflowEvent], Any]) -> None:
        """Register event processing callback."""
        self._handler = callback

    def process_message(
        self, message_data: bytes, handler: Callable[[WorkflowEvent], Any]
    ) -> bool:
        """Process incoming raw message bytes and dispatch to handler."""
        try:
            data_dict = json.loads(message_data.decode("utf-8"))
            event = WorkflowEvent(**data_dict)
            handler(event)
            return True
        except Exception as err:
            logger.error(
                "[ServiceBusSubscriber] Failed to process Service Bus message: %s",
                err,
                exc_info=True,
            )
            return False

    def simulate_event(self, event: WorkflowEvent) -> Any:
        """Simulate receipt of an incoming event (for testing/mock modes)."""
        if self._handler is None:
            raise RuntimeError("Subscriber handler is not registered.")
        logger.info(
            "[ServiceBusSubscriber] Delivering simulated event '%s' to handler.",
            event.event_id,
        )
        return self._handler(event)

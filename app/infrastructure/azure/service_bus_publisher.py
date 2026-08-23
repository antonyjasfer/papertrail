import json
import logging
from typing import Any, List, Optional

from app.core.config import settings
from app.events.publisher import BasePublisher
from app.events.schemas import WorkflowEvent
from app.infrastructure.azure.foundation import azure_foundation

logger = logging.getLogger("papertrail.azure.service_bus_publisher")


class ServiceBusPublisher(BasePublisher):
    """Azure Service Bus Topic publisher implementing BasePublisher interface."""

    def __init__(
        self,
        topic_name: Optional[str] = None,
        servicebus_client: Optional[Any] = None,
    ) -> None:
        self.topic_name = topic_name or settings.azure_servicebus_topic_workflow_events
        self._servicebus_client = servicebus_client
        self.published_events: List[WorkflowEvent] = []

    @property
    def client(self) -> Optional[Any]:
        if self._servicebus_client is None:
            self._servicebus_client = azure_foundation.get_servicebus_client()
        return self._servicebus_client

    def publish(self, event: WorkflowEvent) -> str:
        """Publish WorkflowEvent to Azure Service Bus Topic."""
        payload_json = json.dumps(event.model_dump(mode="json"), default=str)
        self.published_events.append(event)

        if self.client is not None:
            try:
                from azure.servicebus import ServiceBusMessage
                sender = self.client.get_topic_sender(topic_name=self.topic_name)
                message = ServiceBusMessage(
                    body=payload_json,
                    message_id=event.event_id,
                    content_type="application/json",
                    application_properties={
                        "workflow_id": event.workflow_id,
                        "event_type": event.event_type.value,
                        "workflow_revision": str(event.workflow_revision),
                        "logical_event_key": event.logical_event_key if hasattr(event, "logical_event_key") and event.logical_event_key else event.get_logical_event_key(),
                    },
                )
                with sender:
                    sender.send_messages(message)
                logger.info(
                    "[ServiceBusPublisher] Published event '%s' to topic '%s'",
                    event.event_id,
                    self.topic_name,
                )
                return event.event_id
            except Exception as err:
                logger.warning(
                    "[ServiceBusPublisher] Service Bus publish unfulfilled (%s). Falling back to recorded event.",
                    err,
                )
                return event.event_id

        logger.info(
            "[ServiceBusPublisher (in-memory)] Recorded event '%s' (Type: %s, Workflow: %s)",
            event.event_id,
            event.event_type.value,
            event.workflow_id,
        )
        return event.event_id

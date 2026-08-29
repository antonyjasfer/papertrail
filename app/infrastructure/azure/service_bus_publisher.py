import json
import logging
from typing import Any, List, Optional

from app.core.config import settings
from app.core.errors import ErrorCategory
from app.core.logging import CorrelationContext, log_event
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

        with CorrelationContext(
            workflow_id=event.workflow_id,
            document_id=event.document_id,
            event_type=event.event_type.value,
            workflow_revision=event.workflow_revision,
        ):
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

                    log_event(
                        logger=logger,
                        level=logging.INFO,
                        message=f"Published event '{event.event_id}' ({event.event_type.value}) to Service Bus topic '{self.topic_name}'",
                        component="service_bus_publisher",
                        operation="publish_event",
                        workflow_id=event.workflow_id,
                        document_id=event.document_id,
                        event_type=event.event_type.value,
                        event_id=event.event_id,
                        topic=self.topic_name,
                        outcome="PUBLISHED",
                    )
                    return event.event_id
                except Exception as err:
                    log_event(
                        logger=logger,
                        level=logging.WARNING,
                        message=f"Service Bus publish unfulfilled ({err}). Falling back to recorded event.",
                        component="service_bus_publisher",
                        operation="publish_event_fallback",
                        workflow_id=event.workflow_id,
                        event_id=event.event_id,
                        error_category=ErrorCategory.SERVICE_BUS_ERROR.value,
                        error_details=str(err),
                        outcome="FALLBACK_RECORDED",
                    )
                    return event.event_id

            log_event(
                logger=logger,
                level=logging.INFO,
                message=f"Recorded event '{event.event_id}' in-memory (Type: {event.event_type.value}, Workflow: {event.workflow_id})",
                component="service_bus_publisher",
                operation="publish_in_memory",
                workflow_id=event.workflow_id,
                event_id=event.event_id,
                outcome="IN_MEMORY_RECORDED",
            )
            return event.event_id

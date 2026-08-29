"""PaperTrail AI — Production Background Worker for Event-Driven Workflow Orchestration.

Consumes workflow lifecycle events from Azure Service Bus (or GCP Pub/Sub / in-memory),
executes the Phase 1-13 deterministic orchestration engine, and safely settles messages.
Instrumented with structured logging, correlation propagation, and operational metrics.
"""

import json
import logging
import os
import signal
import sys
import time
from typing import Optional

from app.core.config import settings
from app.core.errors import ErrorCategory, classify_error
from app.core.logging import CorrelationContext, log_event, setup_structured_logging
from app.core.metrics import metrics
from app.events.schemas import WorkflowEvent
from app.infrastructure.azure.foundation import azure_foundation
from app.infrastructure.factory import get_event_publisher, get_state_manager
from app.orchestration.orchestrator import WorkflowOrchestrator

# Initialize structured logging for background worker
setup_structured_logging(level=settings.log_level)
logger = logging.getLogger("papertrail.worker")


class WorkflowWorker:
    """Production worker daemon for processing PaperTrail workflow events."""

    def __init__(self) -> None:
        self.running = True
        self.worker_id = f"worker-{os.getpid()}"
        self.state_manager = get_state_manager()
        self.publisher = get_event_publisher()
        self.orchestrator = WorkflowOrchestrator(
            state_manager=self.state_manager,
            publisher=self.publisher,
            owner_id=self.worker_id,
        )
        self._setup_signals()

    def _setup_signals(self) -> None:
        """Register graceful shutdown signal handlers."""
        def handle_shutdown(signum, frame):
            log_event(
                logger=logger,
                level=logging.INFO,
                message=f"Received signal {signum}. Initiating graceful shutdown...",
                component="worker",
                operation="shutdown_signal_received",
                worker_id=self.worker_id,
                signal=signum,
            )
            self.running = False

        signal.signal(signal.SIGINT, handle_shutdown)
        signal.signal(signal.SIGTERM, handle_shutdown)

    def run_azure(self) -> None:
        """Run Service Bus consumer loop on Azure."""
        topic_name = settings.azure_servicebus_topic_workflow_events
        subscription_name = settings.azure_servicebus_subscription_orchestrator
        fqdn = settings.azure_servicebus_namespace

        log_event(
            logger=logger,
            level=logging.INFO,
            message=f"Starting Azure Service Bus worker on {fqdn} -> {topic_name}/{subscription_name}",
            component="worker",
            operation="worker_startup",
            worker_id=self.worker_id,
            topic=topic_name,
            subscription=subscription_name,
        )

        servicebus_client = azure_foundation.get_servicebus_client()

        with servicebus_client:
            receiver = servicebus_client.get_subscription_receiver(
                topic_name=topic_name,
                subscription_name=subscription_name,
                max_wait_time=5,
            )
            with receiver:
                log_event(
                    logger=logger,
                    level=logging.INFO,
                    message="Service Bus receiver connected and ready for events.",
                    component="worker",
                    operation="receiver_connected",
                    worker_id=self.worker_id,
                )
                while self.running:
                    try:
                        messages = receiver.receive_messages(max_message_count=1, max_wait_time=5)
                        if not messages:
                            # Idle polling - allows scale-to-zero when no messages
                            continue

                        for msg in messages:
                            self._process_azure_message(receiver, msg)

                    except Exception as err:
                        if not self.running:
                            break
                        log_event(
                            logger=logger,
                            level=logging.ERROR,
                            message=f"Error in Service Bus receive loop: {err}",
                            component="worker",
                            operation="receive_loop_error",
                            error_category=classify_error(err).value,
                            error_details=str(err),
                            worker_id=self.worker_id,
                        )
                        time.sleep(2)

        log_event(
            logger=logger,
            level=logging.INFO,
            message="Azure Service Bus worker shutdown cleanly.",
            component="worker",
            operation="worker_shutdown_complete",
            worker_id=self.worker_id,
        )

    def _process_azure_message(self, receiver, msg) -> None:
        """Process an individual Azure Service Bus message."""
        t0 = time.perf_counter()
        msg_id = getattr(msg, "message_id", "unknown-msg")
        delivery_count = getattr(msg, "delivery_count", 1)

        try:
            body_bytes = (
                b"".join(msg.body)
                if hasattr(msg.body, "__iter__") and not isinstance(msg.body, (bytes, bytearray))
                else bytes(msg.body)
            )
            body_str = body_bytes.decode("utf-8")
            data_dict = json.loads(body_str)

            event = WorkflowEvent(**data_dict)
            workflow_id = event.workflow_id
            document_id = event.document_id

            with CorrelationContext(
                workflow_id=workflow_id,
                document_id=document_id,
                message_id=msg_id,
                delivery_count=delivery_count,
            ):
                log_event(
                    logger=logger,
                    level=logging.INFO,
                    message=f"Received event '{event.event_type.value}' for workflow '{workflow_id}' (Delivery: {delivery_count})",
                    component="worker",
                    operation="message_received",
                    workflow_id=workflow_id,
                    document_id=document_id,
                    event_type=event.event_type.value,
                    message_id=msg_id,
                    delivery_count=delivery_count,
                )

                # Dispatch to orchestrator
                workflow, outbox_event = self.orchestrator.dispatch(event)

                # If an outbox event was generated, process it
                if outbox_event:
                    self.orchestrator.outbox_worker.add_outbox_event(outbox_event)
                    self.orchestrator.outbox_worker.process_pending()

                # Settle message on success
                receiver.complete_message(msg)
                duration_ms = (time.perf_counter() - t0) * 1000.0
                metrics.increment("service_bus_messages_processed_total")

                log_event(
                    logger=logger,
                    level=logging.INFO,
                    message=f"Successfully processed and settled message {msg_id} in {duration_ms:.2f}ms",
                    component="worker",
                    operation="message_settled",
                    workflow_id=workflow_id,
                    document_id=document_id,
                    message_id=msg_id,
                    duration_ms=duration_ms,
                    outcome="COMPLETED",
                )

        except json.JSONDecodeError as jde:
            metrics.increment("service_bus_deadletter_total")
            log_event(
                logger=logger,
                level=logging.ERROR,
                message=f"Malformed message body (dead-lettering): {jde}",
                component="worker",
                operation="message_deadlettered",
                message_id=msg_id,
                outcome="DEADLETTERED",
                error_category=ErrorCategory.VALIDATION_ERROR.value,
                error_details=str(jde),
            )
            receiver.dead_letter_message(msg, reason="MalformedJSON", error_description=str(jde))

        except Exception as e:
            duration_ms = (time.perf_counter() - t0) * 1000.0
            err_cat = classify_error(e)
            if delivery_count >= 3:
                metrics.increment("service_bus_deadletter_total")
                log_event(
                    logger=logger,
                    level=logging.WARNING,
                    message=f"Exceeded max retries (dead-lettering message {msg_id}): {e}",
                    component="worker",
                    operation="message_deadlettered",
                    message_id=msg_id,
                    delivery_count=delivery_count,
                    outcome="DEADLETTERED",
                    error_category=err_cat.value,
                    error_details=str(e),
                )
                receiver.dead_letter_message(msg, reason="MaxRetriesExceeded", error_description=str(e))
            else:
                log_event(
                    logger=logger,
                    level=logging.INFO,
                    message=f"Abandoning message {msg_id} for retry (Attempt {delivery_count}): {e}",
                    component="worker",
                    operation="message_abandoned",
                    message_id=msg_id,
                    delivery_count=delivery_count,
                    outcome="ABANDONED_FOR_RETRY",
                    error_category=err_cat.value,
                    error_details=str(e),
                )
                receiver.abandon_message(msg)

    def run(self) -> None:
        """Entrypoint routing based on cloud provider."""
        provider = settings.papertrail_cloud_provider.lower()
        if provider == "azure":
            self.run_azure()
        else:
            log_event(
                logger=logger,
                level=logging.INFO,
                message=f"Running in non-Azure mode ({provider}). Worker idle.",
                component="worker",
                operation="worker_idle",
                worker_id=self.worker_id,
            )
            while self.running:
                time.sleep(1)


def main():
    worker = WorkflowWorker()
    worker.run()


if __name__ == "__main__":
    main()

"""PaperTrail AI — Production Background Worker for Event-Driven Workflow Orchestration.

Consumes workflow lifecycle events from Azure Service Bus (or GCP Pub/Sub / in-memory),
executes the Phase 1-13 deterministic orchestration engine, and safely settles messages.
"""

import json
import logging
import os
import signal
import sys
import time
from typing import Optional

from app.core.config import settings
from app.events.schemas import WorkflowEvent
from app.infrastructure.azure.foundation import azure_foundation
from app.infrastructure.factory import get_event_publisher, get_state_manager
from app.orchestration.orchestrator import WorkflowOrchestrator

logging.basicConfig(
    level=getattr(logging, settings.log_level.upper(), logging.INFO),
    format="%(asctime)s [%(levelname)s] [%(name)s] %(message)s",
)
logger = logging.getLogger("papertrail.worker")


class WorkflowWorker:
    """Production worker daemon for processing PaperTrail workflow events."""

    def __init__(self) -> None:
        self.running = True
        self.state_manager = get_state_manager()
        self.publisher = get_event_publisher()
        self.orchestrator = WorkflowOrchestrator(
            state_manager=self.state_manager,
            publisher=self.publisher,
            owner_id=f"worker-{os.getpid()}",
        )
        self._setup_signals()

    def _setup_signals(self) -> None:
        """Register graceful shutdown signal handlers."""
        def handle_shutdown(signum, frame):
            logger.info(f"[Worker] Received signal {signum}. Initiating graceful shutdown...")
            self.running = False

        signal.signal(signal.SIGINT, handle_shutdown)
        signal.signal(signal.SIGTERM, handle_shutdown)

    def run_azure(self) -> None:
        """Run Service Bus consumer loop on Azure."""
        topic_name = settings.azure_servicebus_topic_workflow_events
        subscription_name = settings.azure_servicebus_subscription_orchestrator
        fqdn = settings.azure_servicebus_namespace

        logger.info(
            f"[Worker] Starting Azure Service Bus worker on {fqdn} -> {topic_name}/{subscription_name}..."
        )

        servicebus_client = azure_foundation.get_servicebus_client()

        with servicebus_client:
            receiver = servicebus_client.get_subscription_receiver(
                topic_name=topic_name,
                subscription_name=subscription_name,
                max_wait_time=5,
            )
            with receiver:
                logger.info("[Worker] Service Bus receiver connected and ready for events.")
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
                        logger.error(f"[Worker] Error in receive loop: {err}", exc_info=True)
                        time.sleep(2)

        logger.info("[Worker] Azure Service Bus worker shutdown cleanly.")

    def _process_azure_message(self, receiver, msg) -> None:
        """Process an individual Azure Service Bus message."""
        try:
            body_bytes = b"".join(msg.body) if hasattr(msg.body, "__iter__") and not isinstance(msg.body, (bytes, bytearray)) else bytes(msg.body)
            body_str = body_bytes.decode("utf-8")
            data_dict = json.loads(body_str)

            event = WorkflowEvent(**data_dict)
            logger.info(
                f"[Worker] Processing event '{event.event_type.value}' for workflow '{event.workflow_id}' (Event ID: {event.event_id})"
            )

            # Dispatch to orchestrator
            workflow, outbox_event = self.orchestrator.dispatch(event)

            # If an outbox event was generated, process it
            if outbox_event:
                self.orchestrator.outbox_worker.add_outbox_event(outbox_event)
                self.orchestrator.outbox_worker.process_pending()

            # Settle message on success
            receiver.complete_message(msg)
            logger.info(f"[Worker] Successfully settled message {msg.message_id}")

        except json.JSONDecodeError as jde:
            logger.error(f"[Worker] Malformed message body (dead-lettering): {jde}")
            receiver.dead_letter_message(msg, reason="MalformedJSON", error_description=str(jde))
        except Exception as e:
            logger.error(f"[Worker] Unhandled error during event dispatch: {e}", exc_info=True)
            if getattr(msg, "delivery_count", 1) >= 3:
                logger.warning(f"[Worker] Exceeded max retries (dead-lettering message {msg.message_id}): {e}")
                receiver.dead_letter_message(msg, reason="MaxRetriesExceeded", error_description=str(e))
            else:
                logger.info(f"[Worker] Abandoning message {msg.message_id} for retry.")
                receiver.abandon_message(msg)

    def run(self) -> None:
        """Entrypoint routing based on cloud provider."""
        provider = settings.papertrail_cloud_provider.lower()
        if provider == "azure":
            self.run_azure()
        else:
            logger.info(f"[Worker] Running in non-Azure mode ({provider}). Worker idle.")
            while self.running:
                time.sleep(1)


def main():
    worker = WorkflowWorker()
    worker.run()


if __name__ == "__main__":
    main()

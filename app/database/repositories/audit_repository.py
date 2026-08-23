import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from app.audit.errors import (
    AuditChainSealedError,
    AuditDuplicateError,
    AuditEventNotFoundError,
    AuditIntegrityError,
    AuditPersistenceError,
    AuditSecurityError,
)
from app.audit.models import AuditEvent, AuditEventType, AuditProvenance
from app.core.gcp import gcp_foundation

logger = logging.getLogger("papertrail.database.audit_repository")


def serialize_audit_event(event: AuditEvent) -> Dict[str, Any]:
    """Serialize AuditEvent model into a Firestore-compatible dictionary."""
    return {
        "event_id": event.event_id,
        "document_id": event.document_id,
        "workflow_id": event.workflow_id,
        "event_type": event.event_type.value,
        "event_timestamp": event.event_timestamp.isoformat(),
        "schema_version": event.schema_version,
        "source_phase": event.source_phase,
        "payload_hash": event.payload_hash,
        "previous_event_hash": event.previous_event_hash,
        "event_hash": event.event_hash,
        "provenance": event.provenance.model_dump(),
        "metadata": event.metadata,
    }


def deserialize_audit_event(data: Dict[str, Any]) -> AuditEvent:
    """Deserialize Firestore document dictionary into an AuditEvent model."""
    try:
        ts_val = data["event_timestamp"]
        if isinstance(ts_val, str):
            event_timestamp = datetime.fromisoformat(ts_val)
        elif isinstance(ts_val, datetime):
            event_timestamp = ts_val
        else:
            event_timestamp = datetime.now(timezone.utc)

        provenance_data = data.get("provenance", {})
        provenance = AuditProvenance(**provenance_data)

        return AuditEvent(
            event_id=data["event_id"],
            document_id=data["document_id"],
            workflow_id=data["workflow_id"],
            event_type=AuditEventType(data["event_type"]),
            event_timestamp=event_timestamp,
            schema_version=data.get("schema_version", "1.0.0"),
            source_phase=data["source_phase"],
            payload_hash=data["payload_hash"],
            previous_event_hash=data["previous_event_hash"],
            event_hash=data["event_hash"],
            provenance=provenance,
            metadata=data.get("metadata", {}),
        )
    except Exception as err:
        raise ValueError(f"Error deserializing audit event payload: {err}") from err


class AuditEventRepository:
    """Repository handling Firestore persistence for AuditEvent instances.
    
    CRITICAL SECURITY CONTRACT:
    Exposes ONLY append and read operations.
    Statically and dynamically prohibits update() and delete() operations.
    """

    COLLECTION_NAME = "audit_events"

    def __init__(self, client: Optional[Any] = None):
        self._client = client

    @property
    def client(self) -> Any:
        """Lazily retrieve or return initialized Firestore client."""
        if self._client is None:
            self._client = gcp_foundation.get_firestore_client()
        if self._client is None:
            raise AuditPersistenceError("connect", "N/A", "Firestore client unavailable.")
        return self._client

    def _get_doc_ref(self, event_id: str) -> Any:
        """Get Firestore document reference for an event_id."""
        return self.client.collection(self.COLLECTION_NAME).document(event_id)

    def append(self, event: AuditEvent) -> AuditEvent:
        """Persist a new AuditEvent instance with idempotency checks.
        
        Rules:
        - If event_id exists with identical payload_hash -> Idempotent success (returns existing).
        - If event_id exists with different payload_hash -> Raises AuditDuplicateError.
        - If logical slot (document_id, workflow_id, event_type) exists with identical payload_hash -> Idempotent success.
        - If logical slot (document_id, workflow_id, event_type) exists with different payload_hash -> Raises AuditIntegrityError.
        - If chain is already sealed (AUDIT_SEALED exists) and new event is not idempotent -> Raises AuditChainSealedError.
        """
        try:
            # Step 1: Check existing event_id
            doc_ref = self._get_doc_ref(event.event_id)
            doc_snapshot = doc_ref.get()
            if doc_snapshot.exists:
                existing = deserialize_audit_event(doc_snapshot.to_dict())
                if existing.payload_hash == event.payload_hash:
                    logger.info("Idempotent append hit for event_id '%s'", event.event_id)
                    return existing
                else:
                    raise AuditDuplicateError(event.event_id, existing.payload_hash, event.payload_hash)

            # Step 2: Check logical slot (document_id, workflow_id, event_type)
            slot_event = self.find_by_event_key(event.document_id, event.workflow_id, event.event_type)
            if slot_event is not None:
                if slot_event.payload_hash == event.payload_hash:
                    logger.info("Idempotent append hit for logical slot (%s, %s, %s)", event.document_id, event.workflow_id, event.event_type.value)
                    return slot_event
                else:
                    raise AuditIntegrityError(
                        f"Logical event slot for phase '{event.event_type.value}' already exists for document "
                        f"'{event.document_id}' with conflicting payload hash '{slot_event.payload_hash}'.",
                        event_id=event.event_id,
                        expected_hash=slot_event.payload_hash,
                        observed_hash=event.payload_hash,
                    )

            # Step 3: Check if chain is already sealed
            sealed_event = self.find_by_event_key(event.document_id, event.workflow_id, AuditEventType.AUDIT_SEALED)
            if sealed_event is not None and event.event_type != AuditEventType.AUDIT_SEALED:
                raise AuditChainSealedError(event.document_id, event.workflow_id)

            # Step 4: Persist event
            payload = serialize_audit_event(event)
            doc_ref.set(payload)
            logger.info("Successfully persisted audit event '%s' (%s)", event.event_id, event.event_type.value)
            return event
        except (AuditDuplicateError, AuditIntegrityError, AuditChainSealedError):
            raise
        except Exception as err:
            raise AuditPersistenceError("append", event.event_id, str(err)) from err

    def get(self, event_id: str) -> AuditEvent:
        """Retrieve AuditEvent by event_id."""
        try:
            doc_ref = self._get_doc_ref(event_id)
            doc_snapshot = doc_ref.get()
            if not doc_snapshot.exists:
                raise AuditEventNotFoundError(event_id)
            return deserialize_audit_event(doc_snapshot.to_dict())
        except AuditEventNotFoundError:
            raise
        except Exception as err:
            raise AuditPersistenceError("get", event_id, str(err)) from err

    def exists(self, event_id: str) -> bool:
        """Check whether an audit event exists in Firestore."""
        try:
            doc_ref = self._get_doc_ref(event_id)
            return doc_ref.get().exists
        except Exception:
            return False

    def get_document_chain(self, document_id: str, workflow_id: str) -> List[AuditEvent]:
        """Retrieve all audit events for a document workflow ordered by creation time."""
        try:
            query = self.client.collection(self.COLLECTION_NAME).where(
                "document_id", "==", document_id
            ).where("workflow_id", "==", workflow_id)
            
            docs = query.stream()
            events = [deserialize_audit_event(d.to_dict()) for d in docs]
            # Return events
            return events
        except Exception as err:
            raise AuditPersistenceError("get_document_chain", document_id, str(err)) from err

    def find_by_event_key(
        self,
        document_id: str,
        workflow_id: str,
        event_type: AuditEventType,
    ) -> Optional[AuditEvent]:
        """Retrieve existing audit event for a logical slot (document_id, workflow_id, event_type)."""
        try:
            query = self.client.collection(self.COLLECTION_NAME).where(
                "document_id", "==", document_id
            ).where(
                "workflow_id", "==", workflow_id
            ).where(
                "event_type", "==", event_type.value
            ).limit(1)

            docs = list(query.stream())
            if docs:
                return deserialize_audit_event(docs[0].to_dict())
            return None
        except Exception as err:
            logger.warning("Error searching for event key (%s, %s, %s): %s", document_id, workflow_id, event_type.value, err)
            return None

    def get_latest_event(self, document_id: str, workflow_id: str) -> Optional[AuditEvent]:
        """Retrieve the latest event in a document workflow chain."""
        events = self.get_document_chain(document_id, workflow_id)
        if not events:
            return None
        # Sort by timestamp
        return sorted(events, key=lambda e: e.event_timestamp)[-1]

    # Explicit Security Prohibitions
    def update(self, *args, **kwargs):
        """Prohibited operation."""
        raise AuditSecurityError("update")

    def delete(self, *args, **kwargs):
        """Prohibited operation."""
        raise AuditSecurityError("delete")

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
from app.core.config import settings
from app.core.contracts.repositories import (
    IAuditEventRepository,
    IDocumentRepository,
    IWorkflowRepository,
)
from app.core.state import AnalysisWorkflow, WorkflowState
from app.database.repositories.document_repository import (
    DocumentAlreadyExistsError,
    DocumentNotFoundError,
    DocumentPersistenceError,
    deserialize_document_metadata,
    serialize_document_metadata,
)
from app.database.repositories.workflow_repository import (
    WorkflowAlreadyExistsError,
    WorkflowNotFoundError,
    WorkflowPersistenceError,
    deserialize_workflow,
    serialize_workflow,
)
from app.infrastructure.azure.foundation import azure_foundation
from app.models.document import DocumentMetadata, DocumentStatus
from app.models.forensics import HistoricalContext

logger = logging.getLogger("papertrail.azure.cosmos_repositories")


class CosmosWorkflowRepository:
    """Cosmos DB repository for AnalysisWorkflow instances.
    
    Implements IWorkflowRepository.
    """
    _shared_items: Dict[str, Dict[str, Any]] = {}

    def __init__(self, container_client: Optional[Any] = None) -> None:
        self._container = container_client
        self._items: Dict[str, Dict[str, Any]] = self._shared_items

    @property
    def container(self) -> Optional[Any]:
        if self._container is None:
            cosmos = azure_foundation.get_cosmos_client()
            if cosmos is not None:
                try:
                    db = cosmos.get_database_client(settings.azure_cosmos_database)
                    self._container = db.get_container_client(settings.azure_cosmos_container_workflow_state)
                except Exception as err:
                    logger.warning("Could not get Cosmos workflow container: %s", err)
        return self._container

    def create(self, workflow: AnalysisWorkflow) -> AnalysisWorkflow:
        if self.exists(workflow.workflow_id):
            raise WorkflowAlreadyExistsError(workflow.workflow_id)

        item = serialize_workflow(workflow)
        item["id"] = f"wf:{workflow.workflow_id}"
        item["type"] = "WORKFLOW"
        item["workflow_revision"] = 1

        if self.container is not None:
            try:
                self.container.create_item(item)
            except Exception as err:
                raise WorkflowPersistenceError("create", workflow.workflow_id, str(err)) from err

        self._items[workflow.workflow_id] = item
        return workflow

    def get(self, workflow_id: str) -> AnalysisWorkflow:
        if self.container is not None:
            try:
                item = self.container.read_item(item=f"wf:{workflow_id}", partition_key=workflow_id)
                return deserialize_workflow(item)
            except Exception as err:
                raise WorkflowNotFoundError(workflow_id) from err

        item = self._items.get(workflow_id)
        if not item:
            raise WorkflowNotFoundError(workflow_id)
        return deserialize_workflow(item)

    def exists(self, workflow_id: str) -> bool:
        if self.container is not None:
            try:
                self.container.read_item(item=f"wf:{workflow_id}", partition_key=workflow_id)
                return True
            except Exception:
                return False
        return workflow_id in self._items

    def update(self, workflow: AnalysisWorkflow) -> AnalysisWorkflow:
        if not self.exists(workflow.workflow_id):
            raise WorkflowNotFoundError(workflow.workflow_id)

        item = serialize_workflow(workflow)
        item["id"] = f"wf:{workflow.workflow_id}"
        item["type"] = "WORKFLOW"

        if self.container is not None:
            try:
                self.container.upsert_item(item)
            except Exception as err:
                raise WorkflowPersistenceError("update", workflow.workflow_id, str(err)) from err

        self._items[workflow.workflow_id] = item
        return workflow

    def save(self, workflow: AnalysisWorkflow) -> AnalysisWorkflow:
        if self.exists(workflow.workflow_id):
            return self.update(workflow)
        return self.create(workflow)

    def delete(self, workflow_id: str) -> bool:
        if not self.exists(workflow_id):
            return False
        if self.container is not None:
            try:
                self.container.delete_item(item=f"wf:{workflow_id}", partition_key=workflow_id)
            except Exception as err:
                raise WorkflowPersistenceError("delete", workflow_id, str(err)) from err
        self._items.pop(workflow_id, None)
        return True


class CosmosDocumentRepository:
    """Cosmos DB repository for DocumentMetadata instances.
    
    Implements IDocumentRepository.
    """
    _shared_items: Dict[str, Dict[str, Any]] = {}

    def __init__(self, container_client: Optional[Any] = None) -> None:
        self._container = container_client
        self._items: Dict[str, Dict[str, Any]] = self._shared_items

    @property
    def container(self) -> Optional[Any]:
        if self._container is None:
            cosmos = azure_foundation.get_cosmos_client()
            if cosmos is not None:
                try:
                    db = cosmos.get_database_client(settings.azure_cosmos_database)
                    self._container = db.get_container_client(settings.azure_cosmos_container_documents)
                except Exception as err:
                    logger.warning("Could not get Cosmos document container: %s", err)
        return self._container

    def create(self, metadata: DocumentMetadata) -> DocumentMetadata:
        if self.exists(metadata.document_id):
            raise DocumentAlreadyExistsError(metadata.document_id)

        item = serialize_document_metadata(metadata)
        item["id"] = f"doc:{metadata.document_id}"
        item["type"] = "DOCUMENT"

        if self.container is not None:
            try:
                self.container.create_item(item)
            except Exception as err:
                raise DocumentPersistenceError("create", metadata.document_id, str(err)) from err

        self._items[metadata.document_id] = item
        return metadata

    def get(self, document_id: str) -> DocumentMetadata:
        if self.container is not None:
            try:
                item = self.container.read_item(item=f"doc:{document_id}", partition_key=document_id)
                return deserialize_document_metadata(item)
            except Exception as err:
                raise DocumentNotFoundError(document_id) from err

        item = self._items.get(document_id)
        if not item:
            raise DocumentNotFoundError(document_id)
        return deserialize_document_metadata(item)

    def exists(self, document_id: str) -> bool:
        if self.container is not None:
            try:
                self.container.read_item(item=f"doc:{document_id}", partition_key=document_id)
                return True
            except Exception:
                return False
        return document_id in self._items

    def update(self, metadata: DocumentMetadata) -> DocumentMetadata:
        if not self.exists(metadata.document_id):
            raise DocumentNotFoundError(metadata.document_id)

        item = serialize_document_metadata(metadata)
        item["id"] = f"doc:{metadata.document_id}"
        item["type"] = "DOCUMENT"

        if self.container is not None:
            try:
                self.container.upsert_item(item)
            except Exception as err:
                raise DocumentPersistenceError("update", metadata.document_id, str(err)) from err

        self._items[metadata.document_id] = item
        return metadata

    def delete(self, document_id: str) -> bool:
        if not self.exists(document_id):
            return False
        if self.container is not None:
            try:
                self.container.delete_item(item=f"doc:{document_id}", partition_key=document_id)
            except Exception as err:
                raise DocumentPersistenceError("delete", document_id, str(err)) from err
        self._items.pop(document_id, None)
        return True

    def get_historical_context(
        self, exclude_document_id: str, exclude_workflow_id: Optional[str] = None
    ) -> HistoricalContext:
        """Query historical document checksums and extracted invoice numbers, strictly excluding current document/workflow."""
        existing_checksums = set()
        existing_invoice_numbers = set()

        if self.container is not None:
            try:
                doc_query = (
                    "SELECT c.checksum FROM c WHERE c.type = 'DOCUMENT' AND c.document_id != @doc_id"
                )
                doc_items = self.container.query_items(
                    query=doc_query,
                    parameters=[{"name": "@doc_id", "value": exclude_document_id}],
                    enable_cross_partition_query=True,
                )
                for item in doc_items:
                    chk = item.get("checksum")
                    if chk:
                        existing_checksums.add(str(chk).strip())
            except Exception as err:
                logger.warning("Error querying historical document checksums from Cosmos: %s", err)

            try:
                cosmos = azure_foundation.get_cosmos_client()
                if cosmos is not None:
                    db = cosmos.get_database_client(settings.azure_cosmos_database)
                    wf_container = db.get_container_client(settings.azure_cosmos_container_workflow_state)
                    wf_query = (
                        "SELECT c.output_reference.extraction.invoice_number AS inv_num, c.workflow_id, c.document_id "
                        "FROM c WHERE c.type = 'EXECUTION_CLAIM' AND IS_DEFINED(c.output_reference.extraction.invoice_number)"
                    )
                    claims = wf_container.query_items(
                        query=wf_query,
                        enable_cross_partition_query=True,
                    )
                    for c in claims:
                        w_id = c.get("workflow_id")
                        d_id = c.get("document_id")
                        inv = c.get("inv_num")
                        if exclude_workflow_id and w_id == exclude_workflow_id:
                            continue
                        if exclude_document_id and d_id == exclude_document_id:
                            continue
                        if inv:
                            existing_invoice_numbers.add(str(inv).strip())
            except Exception as err:
                logger.warning("Error querying historical extraction claims from Cosmos: %s", err)

        # In-memory shared items fallback (for tests/mock)
        for d_id, item in self._items.items():
            if d_id == exclude_document_id:
                continue
            chk = item.get("checksum")
            if chk:
                existing_checksums.add(str(chk).strip())

        return HistoricalContext(
            existing_invoice_numbers=sorted(list(existing_invoice_numbers)),
            existing_checksums=sorted(list(existing_checksums)),
        )


class CosmosAuditEventRepository:
    """Cosmos DB append-only repository for AuditEvent instances.
    
    Implements IAuditEventRepository.
    """
    _shared_items: Dict[str, Dict[str, Any]] = {}

    def __init__(self, container_client: Optional[Any] = None) -> None:
        self._container = container_client
        self._items: Dict[str, Dict[str, Any]] = self._shared_items

    @property
    def container(self) -> Optional[Any]:
        if self._container is None:
            cosmos = azure_foundation.get_cosmos_client()
            if cosmos is not None:
                try:
                    db = cosmos.get_database_client(settings.azure_cosmos_database)
                    self._container = db.get_container_client(settings.azure_cosmos_container_audit_events)
                except Exception as err:
                    logger.warning("Could not get Cosmos audit container: %s", err)
        return self._container

    def append(self, event: AuditEvent) -> AuditEvent:
        # Step 1: Check existing event_id
        if self.exists(event.event_id):
            existing = self.get(event.event_id)
            if existing.payload_hash == event.payload_hash:
                return existing
            raise AuditDuplicateError(event.event_id, existing.payload_hash, event.payload_hash)

        # Step 2: Check logical slot
        slot_event = self.find_by_event_key(event.document_id, event.workflow_id, event.event_type)
        if slot_event is not None:
            if slot_event.payload_hash == event.payload_hash:
                return slot_event
            raise AuditIntegrityError(
                f"Logical event slot for phase '{event.event_type.value}' already exists for document '{event.document_id}'.",
                event_id=event.event_id,
                expected_hash=slot_event.payload_hash,
                observed_hash=event.payload_hash,
            )

        # Step 3: Check if chain is sealed
        sealed_event = self.find_by_event_key(event.document_id, event.workflow_id, AuditEventType.AUDIT_SEALED)
        if sealed_event is not None and event.event_type != AuditEventType.AUDIT_SEALED:
            raise AuditChainSealedError(event.document_id, event.workflow_id)

        item = {
            "id": f"audit:{event.event_id}",
            "type": "AUDIT_EVENT",
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

        if self.container is not None:
            try:
                self.container.create_item(item)
            except Exception as err:
                raise AuditPersistenceError("append", event.event_id, str(err)) from err

        self._items[event.event_id] = item
        return event

    def get(self, event_id: str) -> AuditEvent:
        if self.container is not None:
            try:
                query = f"SELECT * FROM c WHERE c.event_id = '{event_id}'"
                items = list(self.container.query_items(query=query, enable_cross_partition_query=True))
                if items:
                    return self._deserialize(items[0])
                raise AuditEventNotFoundError(event_id)
            except AuditEventNotFoundError:
                raise
            except Exception as err:
                raise AuditPersistenceError("get", event_id, str(err)) from err

        item = self._items.get(event_id)
        if not item:
            raise AuditEventNotFoundError(event_id)
        return self._deserialize(item)

    def exists(self, event_id: str) -> bool:
        try:
            self.get(event_id)
            return True
        except Exception:
            return False

    def get_document_chain(self, document_id: str, workflow_id: str) -> List[AuditEvent]:
        if self.container is not None:
            try:
                query = f"SELECT * FROM c WHERE c.workflow_id = '{workflow_id}' AND c.document_id = '{document_id}'"
                items = list(self.container.query_items(query=query, partition_key=workflow_id))
                events = [self._deserialize(i) for i in items]
                return sorted(events, key=lambda e: e.event_timestamp)
            except Exception as err:
                raise AuditPersistenceError("get_document_chain", document_id, str(err)) from err

        events = [
            self._deserialize(v)
            for v in self._items.values()
            if v.get("workflow_id") == workflow_id and v.get("document_id") == document_id
        ]
        return sorted(events, key=lambda e: e.event_timestamp)

    def find_by_event_key(
        self, document_id: str, workflow_id: str, event_type: AuditEventType
    ) -> Optional[AuditEvent]:
        events = self.get_document_chain(document_id, workflow_id)
        for e in events:
            if e.event_type == event_type:
                return e
        return None

    def get_latest_event(self, document_id: str, workflow_id: str) -> Optional[AuditEvent]:
        events = self.get_document_chain(document_id, workflow_id)
        return events[-1] if events else None

    def update(self, *args: Any, **kwargs: Any) -> None:
        raise AuditSecurityError("update")

    def delete(self, *args: Any, **kwargs: Any) -> None:
        raise AuditSecurityError("delete")

    def _deserialize(self, data: Dict[str, Any]) -> AuditEvent:
        ts_val = data.get("event_timestamp")
        ts = datetime.fromisoformat(ts_val) if isinstance(ts_val, str) else datetime.now(timezone.utc)
        provenance_data = data.get("provenance", {})
        return AuditEvent(
            event_id=data["event_id"],
            document_id=data["document_id"],
            workflow_id=data["workflow_id"],
            event_type=AuditEventType(data["event_type"]),
            event_timestamp=ts,
            schema_version=data.get("schema_version", "1.0.0"),
            source_phase=data.get("source_phase", "azure_audit"),
            payload_hash=data["payload_hash"],
            previous_event_hash=data["previous_event_hash"],
            event_hash=data["event_hash"],
            provenance=AuditProvenance(**provenance_data),
            metadata=data.get("metadata", {}),
        )

from typing import List, Optional, Protocol, runtime_checkable

from app.audit.models import AuditEvent, AuditEventType
from app.core.state import AnalysisWorkflow
from app.models.document import DocumentMetadata
from app.models.forensics import HistoricalContext


@runtime_checkable
class IWorkflowRepository(Protocol):
    """Protocol for workflow persistence repositories."""

    def create(self, workflow: AnalysisWorkflow) -> AnalysisWorkflow: ...

    def get(self, workflow_id: str) -> AnalysisWorkflow: ...

    def exists(self, workflow_id: str) -> bool: ...

    def update(self, workflow: AnalysisWorkflow) -> AnalysisWorkflow: ...

    def save(self, workflow: AnalysisWorkflow) -> AnalysisWorkflow: ...

    def delete(self, workflow_id: str) -> bool: ...


@runtime_checkable
class IDocumentRepository(Protocol):
    """Protocol for document metadata repositories."""

    def create(self, metadata: DocumentMetadata) -> DocumentMetadata: ...

    def get(self, document_id: str) -> DocumentMetadata: ...

    def exists(self, document_id: str) -> bool: ...

    def update(self, metadata: DocumentMetadata) -> DocumentMetadata: ...

    def delete(self, document_id: str) -> bool: ...

    def get_historical_context(
        self, exclude_document_id: str, exclude_workflow_id: Optional[str] = None
    ) -> HistoricalContext: ...


@runtime_checkable
class IAuditEventRepository(Protocol):
    """Protocol for append-only audit event repositories."""

    def append(self, event: AuditEvent) -> AuditEvent: ...

    def get(self, event_id: str) -> AuditEvent: ...

    def exists(self, event_id: str) -> bool: ...

    def get_document_chain(
        self, document_id: str, workflow_id: str
    ) -> List[AuditEvent]: ...

    def find_by_event_key(
        self,
        document_id: str,
        workflow_id: str,
        event_type: AuditEventType,
    ) -> Optional[AuditEvent]: ...

    def get_latest_event(
        self, document_id: str, workflow_id: str
    ) -> Optional[AuditEvent]: ...

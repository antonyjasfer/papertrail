from abc import ABC, abstractmethod
from enum import Enum
from typing import Any, Dict, Optional
from pydantic import BaseModel, Field


class FailureClassification(str, Enum):
    """Failure classifications returned by engine adapters."""

    RETRYABLE = "RETRYABLE"             # Transient network, service, or GCP error
    NON_RETRYABLE = "NON_RETRYABLE"     # Corrupt payload, invalid document, schema violation
    REQUIRES_REVIEW = "REQUIRES_REVIEW"   # Policy ambiguity or high risk score requiring human review


class AdapterResult(BaseModel):
    """Observation contract returned by engine adapters to the orchestrator.
    
    Note: Adapters DO NOT dictate target workflow states. The WorkflowOrchestrator
    evaluates success, failure_classification, and observations against VALID_TRANSITIONS.
    """

    success: bool
    output_reference: Optional[Dict[str, Any]] = None
    failure_classification: Optional[FailureClassification] = None
    failure_reason: Optional[str] = None
    observations: Dict[str, Any] = Field(default_factory=dict)


class BaseEngineAdapter(ABC):
    """Abstract base class for deterministic phase engine adapters."""

    @property
    @abstractmethod
    def adapter_name(self) -> str:
        """Return human-readable adapter identifier."""
        pass

    @abstractmethod
    def execute(
        self,
        workflow_id: str,
        document_id: str,
        payload: Dict[str, Any],
    ) -> AdapterResult:
        """Execute deterministic phase engine logic and return AdapterResult."""
        pass

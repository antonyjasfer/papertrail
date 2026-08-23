"""PaperTrail AI Core Provider Contracts (Structural Protocols).

These protocols define the structural subtyping interfaces for state management,
document and audit persistence, object storage, secret management, and deterministic clocking.
GCP and Azure adapters satisfy these protocols without requiring ABC inheritance.
"""

from app.core.contracts.clock import DeterministicTestClock, IClock, ProductionClock
from app.core.contracts.repositories import (
    IAuditEventRepository,
    IDocumentRepository,
    IWorkflowRepository,
)
from app.core.contracts.secrets import ISecretProvider
from app.core.contracts.state_manager import IWorkflowStateManager
from app.core.contracts.storage import IStorageProvider

__all__ = [
    "IWorkflowStateManager",
    "IWorkflowRepository",
    "IDocumentRepository",
    "IAuditEventRepository",
    "IStorageProvider",
    "ISecretProvider",
    "IClock",
    "ProductionClock",
    "DeterministicTestClock",
]

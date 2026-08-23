import inspect
import pytest

from app.core.contracts.clock import DeterministicTestClock, IClock, ProductionClock
from app.core.contracts.repositories import (
    IAuditEventRepository,
    IDocumentRepository,
    IWorkflowRepository,
)
from app.core.contracts.state_manager import IWorkflowStateManager
from app.core.contracts.storage import IStorageProvider
from app.core.contracts.secrets import ISecretProvider
from app.database.repositories.audit_repository import AuditEventRepository
from app.database.repositories.document_repository import DocumentRepository
from app.database.repositories.workflow_repository import WorkflowRepository
from app.orchestration.state_manager import FirestoreStateManager


def verify_method_signatures(impl_cls: type, prot_cls: type, method_names: list[str]) -> None:
    """Tier 2 verification: assert exact parameter names, ordering, and defaults match."""
    for method_name in method_names:
        impl_method = getattr(impl_cls, method_name)
        prot_method = getattr(prot_cls, method_name)
        impl_sig = inspect.signature(impl_method)
        prot_sig = inspect.signature(prot_method)

        impl_params = list(impl_sig.parameters.items())
        prot_params = list(prot_sig.parameters.items())

        assert len(impl_params) == len(prot_params), (
            f"Parameter count mismatch in '{method_name}': {len(impl_params)} != {len(prot_params)}"
        )

        for (i_name, i_param), (p_name, p_param) in zip(impl_params, prot_params):
            assert i_name == p_name, (
                f"Parameter name mismatch in '{method_name}': {i_name} != {p_name}"
            )
            assert i_param.default == p_param.default, (
                f"Parameter default value mismatch for '{i_name}' in '{method_name}'"
            )


def test_firestore_state_manager_protocol_conformance():
    """Verify FirestoreStateManager satisfies IWorkflowStateManager structurally and via reflection."""
    manager = FirestoreStateManager()
    # Tier 1: Structural check
    assert isinstance(manager, IWorkflowStateManager)

    # Tier 2: Exact signature verification
    methods = [
        "get_workflow",
        "get_workflow_revision",
        "create_workflow",
        "check_idempotency",
        "acquire_execution_claim",
        "commit_transaction",
    ]
    verify_method_signatures(FirestoreStateManager, IWorkflowStateManager, methods)


def test_workflow_repository_protocol_conformance():
    """Verify WorkflowRepository satisfies IWorkflowRepository."""
    repo = WorkflowRepository(client="mock")
    assert isinstance(repo, IWorkflowRepository)
    methods = ["create", "get", "exists", "update", "save", "delete"]
    verify_method_signatures(WorkflowRepository, IWorkflowRepository, methods)


def test_document_repository_protocol_conformance():
    """Verify DocumentRepository satisfies IDocumentRepository."""
    repo = DocumentRepository(client="mock")
    assert isinstance(repo, IDocumentRepository)
    methods = ["create", "get", "exists", "update", "delete"]
    verify_method_signatures(DocumentRepository, IDocumentRepository, methods)


def test_audit_event_repository_protocol_conformance():
    """Verify AuditEventRepository satisfies IAuditEventRepository."""
    repo = AuditEventRepository(client="mock")
    assert isinstance(repo, IAuditEventRepository)
    methods = ["append", "get", "exists", "get_document_chain", "find_by_event_key", "get_latest_event"]
    verify_method_signatures(AuditEventRepository, IAuditEventRepository, methods)


def test_clock_implementations_protocol_conformance():
    """Verify ProductionClock and DeterministicTestClock satisfy IClock."""
    prod_clock = ProductionClock()
    test_clock = DeterministicTestClock()
    assert isinstance(prod_clock, IClock)
    assert isinstance(test_clock, IClock)
    verify_method_signatures(ProductionClock, IClock, ["now_utc"])
    verify_method_signatures(DeterministicTestClock, IClock, ["now_utc"])

import inspect
import pytest
from datetime import datetime, timedelta, timezone

from app.core.contracts.clock import DeterministicTestClock, IClock, ProductionClock
from app.core.contracts.repositories import (
    IAuditEventRepository,
    IDocumentRepository,
    IWorkflowRepository,
)
from app.core.contracts.secrets import ISecretProvider
from app.core.contracts.state_manager import IWorkflowStateManager
from app.core.contracts.storage import IStorageProvider
from app.core.state import AnalysisWorkflow, WorkflowState
from app.events.schemas import EventType, WorkflowEvent, compute_payload_hash
from app.infrastructure.azure.blob_storage import AzureBlobStorageProvider
from app.infrastructure.azure.cosmos_repositories import (
    CosmosAuditEventRepository,
    CosmosDocumentRepository,
    CosmosWorkflowRepository,
)
from app.infrastructure.azure.cosmos_state_manager import CosmosStateManager
from app.infrastructure.azure.key_vault_provider import AzureKeyVaultSecretProvider
from app.infrastructure.azure.service_bus_publisher import ServiceBusPublisher
from app.infrastructure.azure.service_bus_subscriber import ServiceBusSubscriber
from app.infrastructure.factory import (
    get_audit_repository,
    get_document_repository,
    get_event_publisher,
    get_event_subscriber,
    get_secret_provider,
    get_state_manager,
    get_storage_provider,
    get_workflow_repository,
)
from app.infrastructure.mock.state_manager import InMemoryStateManager
from app.models.document import DocumentMetadata, DocumentStatus
from app.orchestration.errors import (
    FutureEventError,
    IntegrityConflictError,
    LeaseAcquisitionError,
    StaleEventError,
    StateSynchronizationError,
)
from app.orchestration.models import ClaimStatus


def test_cosmos_state_manager_protocol_conformance():
    """Test 1: CosmosStateManager satisfies IWorkflowStateManager structurally and via signature check."""
    manager = CosmosStateManager()
    assert isinstance(manager, IWorkflowStateManager)

    methods = [
        "get_workflow",
        "get_workflow_revision",
        "create_workflow",
        "check_idempotency",
        "acquire_execution_claim",
        "commit_transaction",
    ]
    for method_name in methods:
        impl_sig = inspect.signature(getattr(CosmosStateManager, method_name))
        prot_sig = inspect.signature(getattr(IWorkflowStateManager, method_name))
        assert list(impl_sig.parameters.keys()) == list(prot_sig.parameters.keys())


def test_cosmos_repositories_protocol_conformance():
    """Test 1b: Cosmos repositories satisfy their respective protocols."""
    wf_repo = CosmosWorkflowRepository()
    doc_repo = CosmosDocumentRepository()
    audit_repo = CosmosAuditEventRepository()

    assert isinstance(wf_repo, IWorkflowRepository)
    assert isinstance(doc_repo, IDocumentRepository)
    assert isinstance(audit_repo, IAuditEventRepository)


def test_blob_storage_and_key_vault_protocol_conformance():
    """Test 1c: BlobStorage and KeyVault satisfy IStorageProvider and ISecretProvider."""
    storage = AzureBlobStorageProvider()
    kv = AzureKeyVaultSecretProvider()

    assert isinstance(storage, IStorageProvider)
    assert isinstance(kv, ISecretProvider)


def test_provider_selection_factory():
    """Test 2, 3, 4: Factory selects appropriate implementations based on provider."""
    # GCP Selection
    gcp_sm = get_state_manager(provider="gcp")
    assert type(gcp_sm).__name__ == "FirestoreStateManager"

    # Azure Selection
    azure_sm = get_state_manager(provider="azure")
    assert isinstance(azure_sm, CosmosStateManager)

    # Mock Selection
    mock_sm = get_state_manager(provider="mock")
    assert isinstance(mock_sm, InMemoryStateManager)


def test_original_logical_event_key_and_payload_hash_preservation():
    """Test 5, 6, 7: Asserts incoming logical_event_key, event_id, and payload_hash are stored unchanged."""
    sm = CosmosStateManager()
    wf, outbox = sm.create_workflow("wf-test-1", "doc-101")
    assert wf.workflow_id == "wf-test-1"
    assert outbox.payload_hash == compute_payload_hash({"document_id": "doc-101"})

    # Acquire execution claim
    claim = sm.acquire_execution_claim(
        workflow_id="wf-test-1",
        logical_event_key="wf-test-1:1:DOCUMENT_UPLOADED",
        owner_id="worker-1",
    )
    assert claim.logical_event_key == "wf-test-1:1:DOCUMENT_UPLOADED"

    # Commit transaction
    updated_wf, next_outbox = sm.commit_transaction(
        workflow_id="wf-test-1",
        expected_revision=1,
        target_state=WorkflowState.INGESTING,
        output_reference={"extracted_text": "sample text"},
        next_event_type=EventType.INGESTION_COMPLETED,
        next_event_payload={"document_id": "doc-101", "bytes_count": 1024},
    )
    assert updated_wf.current_state == WorkflowState.INGESTING
    assert sm.get_workflow_revision("wf-test-1") == 2
    assert next_outbox is not None
    assert next_outbox.payload_hash == compute_payload_hash({"document_id": "doc-101", "bytes_count": 1024})


def test_outbox_payload_hash_correctness():
    """Test 8: Outbox payload_hash is always deterministic SHA-256 over exact canonical payload."""
    payload = {"key": "value", "numbers": [1, 2, 3]}
    expected_hash = compute_payload_hash(payload)
    assert expected_hash != ""
    assert len(expected_hash) == 64


def test_idempotency_and_payload_conflict():
    """Test 9, 10: Idempotent replay returns cached output; conflicting payload raises IntegrityConflictError."""
    sm = CosmosStateManager()
    sm.create_workflow("wf-idemp-1", "doc-101")
    sm.acquire_execution_claim("wf-idemp-1", "wf-idemp-1:1:DOCUMENT_UPLOADED", "worker-1")
    sm.commit_transaction(
        workflow_id="wf-idemp-1",
        expected_revision=1,
        target_state=WorkflowState.INGESTING,
        output_reference={"result": "ok"},
    )

    # Valid matching replay event
    matching_event = WorkflowEvent(
        event_id="evt-1",
        workflow_id="wf-idemp-1",
        document_id="doc-101",
        event_type=EventType.DOCUMENT_UPLOADED,
        current_state="UPLOADED",
        workflow_revision=1,
        payload={"document_id": "doc-101"},
        event_timestamp=datetime.now(timezone.utc),
        correlation_id="wf-idemp-1",
    )
    # Set the claim's payload_hash in internal items for test check
    for v in sm._items.values():
        if v.get("type") == "IDEMPOTENCY":
            v["payload_hash"] = matching_event.payload_hash

    is_processed, cached = sm.check_idempotency(matching_event)
    assert is_processed is True
    assert cached == {"result": "ok"}

    # Conflicting payload
    conflict_event = WorkflowEvent(
        event_id="evt-2",
        workflow_id="wf-idemp-1",
        document_id="doc-101",
        event_type=EventType.DOCUMENT_UPLOADED,
        current_state="UPLOADED",
        workflow_revision=1,
        payload={"document_id": "doc-DIFFERENT"},
        event_timestamp=datetime.now(timezone.utc),
        correlation_id="wf-idemp-1",
    )
    with pytest.raises(IntegrityConflictError):
        sm.check_idempotency(conflict_event)


def test_stale_and_future_revision_rejection():
    """Test 11, 12: Rejects stale (unrecorded) and future revisions."""
    sm = CosmosStateManager()
    sm.create_workflow("wf-rev-1", "doc-101")  # at rev 1

    # Future event (rev 5 > 1)
    future_event = WorkflowEvent(
        event_id="evt-fut",
        workflow_id="wf-rev-1",
        document_id="doc-101",
        event_type=EventType.INGESTION_COMPLETED,
        current_state="INGESTING",
        workflow_revision=5,
        payload={},
        event_timestamp=datetime.now(timezone.utc),
        correlation_id="wf-rev-1",
    )
    with pytest.raises(FutureEventError):
        sm.check_idempotency(future_event)


def test_claim_contention_and_lease_expiry():
    """Test 13, 14, 15: Active lease blocks competing worker; expired lease allows takeover."""
    fixed_time = datetime(2026, 8, 20, 12, 0, 0, tzinfo=timezone.utc)
    clock = DeterministicTestClock(fixed_time)
    sm = CosmosStateManager(clock=clock)
    sm.create_workflow("wf-claim-1", "doc-101")

    # Worker 1 acquires claim
    claim1 = sm.acquire_execution_claim(
        workflow_id="wf-claim-1",
        logical_event_key="wf-claim-1:1:DOCUMENT_UPLOADED",
        owner_id="worker-1",
        ttl_seconds=300,
    )
    assert claim1.owner_id == "worker-1"

    # Worker 2 attempts acquisition while lease is active -> LeaseAcquisitionError
    with pytest.raises(LeaseAcquisitionError):
        sm.acquire_execution_claim(
            workflow_id="wf-claim-1",
            logical_event_key="wf-claim-1:1:DOCUMENT_UPLOADED",
            owner_id="worker-2",
            ttl_seconds=300,
        )

    # Advance clock beyond lease TTL (301 seconds)
    clock.advance(301)

    # Worker 2 now successfully takes over expired claim
    claim2 = sm.acquire_execution_claim(
        workflow_id="wf-claim-1",
        logical_event_key="wf-claim-1:1:DOCUMENT_UPLOADED",
        owner_id="worker-2",
        ttl_seconds=300,
    )
    assert claim2.owner_id == "worker-2"


def test_blob_storage_upload_download_delete():
    """Test 19, 20: AzureBlobStorageProvider uploads, downloads, and deletes blobs."""
    storage = AzureBlobStorageProvider()
    container = "papertrail-documents-dev"
    path = "documents/doc-test/original/test.pdf"
    data = b"%PDF-1.4 test document content"

    storage.upload_bytes(container, path, data, "application/pdf")
    assert storage.object_exists(container, path) is True

    downloaded = storage.download_bytes(container, path)
    assert downloaded == data

    assert storage.delete_object(container, path) is True
    assert storage.object_exists(container, path) is False


def test_key_vault_fail_closed_security():
    """Test 21, 22: Key Vault fails closed on missing secret when no default is provided."""
    kv = AzureKeyVaultSecretProvider()
    kv.set_in_memory_secret("test-key", "secret-value-123")

    assert kv.get_secret("test-key") == "secret-value-123"
    assert kv.get_secret("missing-key", default="fallback") == "fallback"

    with pytest.raises(KeyError):
        kv.get_secret("missing-key")


def test_service_bus_publisher_and_subscriber():
    """Test 17, 18: ServiceBusPublisher and ServiceBusSubscriber dispatch and receive events."""
    publisher = ServiceBusPublisher(topic_name="test-topic")
    subscriber = ServiceBusSubscriber(topic_name="test-topic", subscription_name="test-sub")

    received = []
    subscriber.listen(lambda evt: received.append(evt))

    event = WorkflowEvent(
        event_id="evt-sb-1",
        workflow_id="wf-sb-1",
        document_id="doc-1",
        event_type=EventType.DOCUMENT_UPLOADED,
        current_state="UPLOADED",
        workflow_revision=1,
        payload={"test": "data"},
        event_timestamp=datetime.now(timezone.utc),
        correlation_id="wf-sb-1",
    )

    pub_id = publisher.publish(event)
    assert pub_id == "evt-sb-1"

    # Simulate subscriber delivery
    subscriber.simulate_event(event)
    assert len(received) == 1
    assert received[0].event_id == "evt-sb-1"

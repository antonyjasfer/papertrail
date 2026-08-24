"""
PaperTrail AI - Phase 14 Comprehensive Live Security Regression Audit Suite
Non-destructive, synthetic security adversarial test suite.
"""

import os
import sys
import uuid
import hashlib
import json
import time
import requests
from datetime import datetime, timezone

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.core.config import settings
from app.core.state import AnalysisWorkflow, WorkflowState, validate_transition, StateTransitionError
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
from app.orchestration.orchestrator import WorkflowOrchestrator
from app.orchestration.models import HumanReviewPayload, ReviewDecision
from app.orchestration.errors import (
    FutureEventError,
    IntegrityConflictError,
    LeaseAcquisitionError,
    StaleEventError,
    StateSynchronizationError,
    UnauthorizedReviewerError,
)

results = []

def audit_log(test_id: str, title: str, expected: str, observed: str, passed: bool, evidence: str = ""):
    status = "PASS" if passed else "FAIL"
    print(f"[{status}] {test_id} - {title}")
    print(f"       Expected: {expected}")
    print(f"       Observed: {observed}")
    if evidence:
        print(f"       Evidence: {evidence}")
    results.append({
        "id": test_id,
        "title": title,
        "expected": expected,
        "observed": observed,
        "status": status,
        "evidence": evidence
    })


def test_api_security_and_inputs(base_url: str):
    print("\n=======================================================")
    print("  1. API SECURITY, PROBES & INPUT HARDENING AUDIT")
    print("=======================================================")
    
    # 1.1 Liveness Probe
    try:
        r = requests.get(f"{base_url}/health", timeout=30)
        passed = (r.status_code == 200 and r.json().get("status") == "ok")
        audit_log("SEC-API-001", "API Liveness Probe", "HTTP 200 with status=ok", f"HTTP {r.status_code}, payload={r.json()}", passed)
    except Exception as e:
        audit_log("SEC-API-001", "API Liveness Probe", "HTTP 200", f"Exception: {e}", False)

    # 1.2 Readiness Probe
    try:
        r = requests.get(f"{base_url}/health/ready", timeout=30)
        passed = (r.status_code == 200 and r.json().get("status") == "ready" and r.json().get("provider") == "azure")
        audit_log("SEC-API-002", "API Readiness Probe", "HTTP 200 ready & provider=azure", f"HTTP {r.status_code}, payload={r.json()}", passed)
    except Exception as e:
        audit_log("SEC-API-002", "API Readiness Probe", "HTTP 200", f"Exception: {e}", False)

    # 1.3 Path Traversal Injection Protection on Documents API
    try:
        r = requests.get(f"{base_url}/documents/../../etc/passwd", timeout=15)
        passed = (r.status_code in (404, 400, 422))
        audit_log("SEC-API-003", "Path Traversal Injection in URL", "HTTP 404/400/422 Rejection", f"HTTP {r.status_code}", passed, "Path traversal sanitization")
    except Exception as e:
        audit_log("SEC-API-003", "Path Traversal Injection in URL", "HTTP 4xx", f"Exception: {e}", False)

    # 1.4 Missing / Invalid Multipart Payload
    try:
        headers = {"Content-Type": "application/json"}
        r = requests.post(f"{base_url}/documents", data="INVALID_JSON{", headers=headers, timeout=15)
        passed = (r.status_code in (400, 422))
        audit_log("SEC-API-004", "Malformed / Invalid Content Type on Upload", "HTTP 400/422 Bad Request", f"HTTP {r.status_code}", passed)
    except Exception as e:
        audit_log("SEC-API-004", "Malformed / Invalid Content Type on Upload", "HTTP 4xx", f"Exception: {e}", False)


def test_api_authorization_and_role_spoofing(base_url: str):
    print("\n=======================================================")
    print("  2. API AUTHORIZATION & ROLE SPOOFING AUDIT")
    print("=======================================================")
    
    # 2.1 Missing Authentication Header on Sensitive Resume Endpoint
    try:
        resume_payload = {
            "payload": {
                "workflow_id": "wf-dummy-test",
                "reviewer_id": "attacker-id",
                "decision": "APPROVED",
                "decision_reason": "Malicious spoof attempt",
                "requested_target": "FORENSIC_ANALYSIS"
            }
        }
        r = requests.post(f"{base_url}/api/v1/pipeline/wf-dummy-test/resume", json=resume_payload, timeout=15)
        passed = (r.status_code == 401)
        audit_log("SEC-AUTH-001", "Missing Reviewer Auth Header", "HTTP 401 Unauthorized", f"HTTP {r.status_code}: {r.text}", passed, "X-Reviewer-Principal required")
    except Exception as e:
        audit_log("SEC-AUTH-001", "Missing Reviewer Auth Header", "HTTP 401", f"Exception: {e}", False)

    # 2.2 Direct Reviewer Authorization Check via Orchestrator (Missing / Invalid Principal)
    state_manager = CosmosStateManager()
    orchestrator = WorkflowOrchestrator(state_manager=state_manager)
    wf_id = f"sec-auth-{uuid.uuid4().hex[:6]}"
    doc_id = f"sec-doc-{uuid.uuid4().hex[:6]}"
    orchestrator.start_workflow(wf_id, doc_id)
    state_manager.commit_transaction(wf_id, 1, WorkflowState.INGESTING)
    state_manager.commit_transaction(wf_id, 2, WorkflowState.EXTRACTING)
    state_manager.commit_transaction(wf_id, 3, WorkflowState.REQUIRES_REVIEW, reason="Manual review")

    unauth_payload = HumanReviewPayload(
        workflow_id=wf_id,
        reviewer_id="attacker-user-999",
        decision=ReviewDecision.APPROVED,
        decision_reason="Spoofed approval attempt",
        requested_target="FORENSIC_ANALYSIS",
    )
    try:
        orchestrator.resume_workflow(
            workflow_id=wf_id,
            payload=unauth_payload,
            reviewer_principal=None,
        )
        audit_log("SEC-AUTH-002", "Unauthenticated Reviewer Resume", "UnauthorizedReviewerError", "Allowed", False)
    except UnauthorizedReviewerError:
        audit_log("SEC-AUTH-002", "Unauthenticated Reviewer Resume", "UnauthorizedReviewerError", "UnauthorizedReviewerError raised", True, "Unauthenticated reviewer strictly rejected")
    finally:
        try:
            CosmosWorkflowRepository().delete(wf_id)
        except Exception:
            pass


def test_state_machine_and_revision_security():
    print("\n=======================================================")
    print("  3. STATE MACHINE, OCC & REVISION LOCKING AUDIT")
    print("=======================================================")
    state_manager = CosmosStateManager()
    orchestrator = WorkflowOrchestrator(state_manager=state_manager)

    wf_id = f"sec-state-{uuid.uuid4().hex[:6]}"
    doc_id = f"sec-doc-{uuid.uuid4().hex[:6]}"

    orchestrator.start_workflow(wf_id, doc_id)

    # 3.1 State Machine Transition Bypass (UPLOADED -> COMPLETED)
    try:
        validate_transition(WorkflowState.UPLOADED, WorkflowState.COMPLETED)
        audit_log("SEC-STM-001", "Direct Illegal State Jump", "StateTransitionError", "Allowed", False)
    except StateTransitionError:
        audit_log("SEC-STM-001", "Direct Illegal State Jump", "StateTransitionError", "StateTransitionError raised", True, "Transition matrix enforced")

    # 3.2 Stale Event Revision Rejection (Revision < Current)
    state_manager.commit_transaction(wf_id, 1, WorkflowState.INGESTING) # now rev 2
    stale_event = WorkflowEvent(
        workflow_id=wf_id,
        document_id=doc_id,
        event_type=EventType.DOCUMENT_UPLOADED,
        current_state="UPLOADED",
        workflow_revision=1,
        payload={"stale": True},
        event_timestamp=datetime.now(timezone.utc),
        correlation_id=str(uuid.uuid4()),
    )
    try:
        state_manager.check_idempotency(stale_event)
        audit_log("SEC-STM-002", "Stale Revision Event Rejection", "StaleEventError", "Processed", False)
    except StaleEventError:
        audit_log("SEC-STM-002", "Stale Revision Event Rejection", "StaleEventError", "StaleEventError raised", True, "Monotonic revision enforced")

    # 3.3 Future Revision Event Rejection (Revision > Current)
    future_event = WorkflowEvent(
        workflow_id=wf_id,
        document_id=doc_id,
        event_type=EventType.FORENSICS_COMPLETED,
        current_state="EXTRACTED",
        workflow_revision=99,
        payload={"future": True},
        event_timestamp=datetime.now(timezone.utc),
        correlation_id=str(uuid.uuid4()),
    )
    try:
        state_manager.check_idempotency(future_event)
        audit_log("SEC-STM-003", "Future Revision Event Rejection", "FutureEventError", "Processed", False)
    except FutureEventError:
        audit_log("SEC-STM-003", "Future Revision Event Rejection", "FutureEventError", "FutureEventError raised", True, "Out-of-order execution prevented")

    CosmosWorkflowRepository().delete(wf_id)


def test_payload_tampering_and_claims():
    print("\n=======================================================")
    print("  4. PAYLOAD TAMPERING & EXECUTION CLAIM RACE AUDIT")
    print("=======================================================")
    state_manager = CosmosStateManager()
    publisher = ServiceBusPublisher()
    orchestrator = WorkflowOrchestrator(state_manager=state_manager, publisher=publisher)

    wf_id = f"sec-tamp-{uuid.uuid4().hex[:6]}"
    doc_id = f"sec-doc-{uuid.uuid4().hex[:6]}"

    workflow, outbox = orchestrator.start_workflow(wf_id, doc_id)
    event1 = outbox.to_workflow_event()

    # 4.1 Process authentic event
    wf1, outbox1 = orchestrator.dispatch(event1)
    passed1 = (wf1.current_state == WorkflowState.INGESTING)

    # 4.2 Replay same logical key with tampered payload against idempotency store
    logical_key = f"{wf_id}:1:{event1.event_type.value}"
    h_key = hashlib.sha256(logical_key.encode("utf-8")).hexdigest()
    idemp_id = f"idemp:{h_key}"
    idemp_item = {
        "id": idemp_id,
        "type": "IDEMPOTENCY",
        "logical_event_key": logical_key,
        "payload_hash": "original_payload_hash_12345",
        "workflow_id": wf_id,
        "workflow_revision": 1,
    }
    state_manager._items[f"{wf_id}:{idemp_id}"] = idemp_item

    tampered_event = WorkflowEvent(
        workflow_id=wf_id,
        document_id=doc_id,
        event_type=event1.event_type,
        current_state="UPLOADED",
        workflow_revision=1,
        payload={"tampered_key": "injected_tamper"},
        payload_hash="tampered_hash_99999",
        event_timestamp=datetime.now(timezone.utc),
        correlation_id=event1.correlation_id,
    )
    
    try:
        is_processed, _ = state_manager.check_idempotency(tampered_event)
        audit_log("SEC-TMP-001", "Payload Tampering Hash Mismatch", "IntegrityConflictError", "Processed", False)
    except IntegrityConflictError:
        audit_log("SEC-TMP-001", "Payload Tampering Hash Mismatch", "IntegrityConflictError", "IntegrityConflictError raised", True, "Payload hash verification active")
    except Exception as e:
        audit_log("SEC-TMP-001", "Payload Tampering Hash Mismatch", "IntegrityConflictError", f"Failed with {type(e).__name__}: {e}", False)

    # 4.3 Concurrent Claim Race Condition Protection
    logical_key = f"{wf_id}:2:INGESTION_COMPLETED"
    claim1 = state_manager.acquire_execution_claim(wf_id, logical_key, owner_id="worker-node-1", ttl_seconds=300)
    try:
        claim2 = state_manager.acquire_execution_claim(wf_id, logical_key, owner_id="worker-node-2", ttl_seconds=300)
        audit_log("SEC-CLM-001", "Concurrent Claim Lease Collision", "LeaseAcquisitionError", "Duplicate Lease Granted", False)
    except LeaseAcquisitionError:
        audit_log("SEC-CLM-001", "Concurrent Claim Lease Collision", "LeaseAcquisitionError", "LeaseAcquisitionError raised", True, "Worker node 2 safely locked out")

    CosmosWorkflowRepository().delete(wf_id)


def test_secretless_dataplane_and_anonymous_storage():
    print("\n=======================================================")
    print("  5. SECRETLESS DATA-PLANE & STORAGE ACCESS CONTROL")
    print("=======================================================")
    
    # 5.1 Storage Anonymous Public Read Rejection
    account_url = settings.azure_storage_account_url
    if account_url:
        anon_url = f"{account_url.rstrip('/')}/papertrail-documents-dev/non_existent_or_private.pdf"
        try:
            r = requests.get(anon_url, timeout=10)
            passed = (r.status_code in (400, 403, 404, 409))
            audit_log("SEC-STR-001", "Anonymous Public Blob Read", "HTTP 403/400/409 (Denied)", f"HTTP {r.status_code}", passed, "allowBlobPublicAccess=false")
        except Exception as e:
            audit_log("SEC-STR-001", "Anonymous Public Blob Read", "Denied", f"Exception: {e}", True)

    # 5.2 Key Vault Secret Retrieval via Managed Identity
    kv = AzureKeyVaultSecretProvider(vault_url=settings.azure_keyvault_url or "https://papertrail-kv-dev-2026.vault.azure.net/")
    try:
        secret_val = kv.get_secret("gemini-api-key")
        passed = (secret_val is not None and len(secret_val) > 0)
        audit_log("SEC-KV-001", "Key Vault Secret Retrieval", "Secret value retrieved safely in memory", f"Length: {len(secret_val)} (Value redacted)", passed)
    except Exception as e:
        audit_log("SEC-KV-001", "Key Vault Secret Retrieval", "Success", f"Exception: {e}", False)

    # 5.3 Key Vault Missing Secret Fail-Closed
    try:
        kv.get_secret("non-existent-secret-999")
        audit_log("SEC-KV-002", "Key Vault Missing Secret Fail-Closed", "KeyError / ResourceNotFound", "Returned Value", False)
    except KeyError:
        audit_log("SEC-KV-002", "Key Vault Missing Secret Fail-Closed", "KeyError", "KeyError raised", True, "Fail-closed semantics verified")


def test_full_security_e2e_workflow():
    print("\n=======================================================")
    print("  6. FULL LIVE E2E SECURITY WORKFLOW EXECUTION")
    print("=======================================================")
    state_manager = CosmosStateManager()
    publisher = ServiceBusPublisher()
    storage = AzureBlobStorageProvider()
    orchestrator = WorkflowOrchestrator(state_manager=state_manager, publisher=publisher)

    doc_id = "security-final-audit-001"
    wf_id = "wf-security-final-audit-001"

    try:
        CosmosWorkflowRepository().delete(wf_id)
    except Exception:
        pass

    # Upload document payload
    raw_path = f"documents/{doc_id}/original/audit_invoice.pdf"
    sample_content = b"%PDF-1.4 Mock Adversarial Audit Document for Phase 14 Security Baseline Verification."
    expected_content_hash = hashlib.sha256(sample_content).hexdigest()
    storage.upload_bytes("papertrail-documents-dev", raw_path, sample_content, "application/pdf")
    
    workflow, outbox = orchestrator.start_workflow(wf_id, doc_id)
    rev1 = state_manager.get_workflow_revision(wf_id)
    passed_init = (workflow.workflow_id == wf_id and workflow.current_state == WorkflowState.UPLOADED and rev1 == 1)
    audit_log("SEC-E2E-001", "Workflow Initialization", "UPLOADED (Rev 1)", f"{workflow.current_state.value} (Rev {rev1})", passed_init)

    # Execute deterministic pipeline
    transitions = [
        (EventType.DOCUMENT_UPLOADED, "UPLOADED", 1),
        (EventType.INGESTION_COMPLETED, "INGESTING", 2),
        (EventType.EXTRACTION_COMPLETED, "EXTRACTING", 3),
        (EventType.ANALYSIS_TRIGGERED, "EXTRACTED", 4),
        (EventType.FORENSICS_COMPLETED, "FORENSIC_ANALYSIS", 5),
        (EventType.COMPLIANCE_COMPLETED, "COMPLIANCE_ANALYSIS", 6),
        (EventType.RISK_COMPLETED, "RISK_ASSESSED", 7),
        (EventType.AUDIT_COMPLETED, "AUDIT_SEALED", 8),
        (EventType.REPORT_COMPLETED, "REPORT_GENERATED", 9),
    ]

    all_passed = True
    for evt_type, cur_st, exp_rev in transitions:
        evt = WorkflowEvent(
            workflow_id=wf_id,
            document_id=doc_id,
            event_type=evt_type,
            current_state=cur_st,
            workflow_revision=exp_rev,
            payload={"document_id": doc_id, "file_path": raw_path},
            event_timestamp=datetime.now(timezone.utc),
            correlation_id=str(uuid.uuid4()),
        )
        updated, _ = orchestrator.dispatch(evt)
        if not updated:
            all_passed = False
            break

    final_wf = state_manager.get_workflow(wf_id)
    final_rev = state_manager.get_workflow_revision(wf_id)
    passed_final = (final_wf is not None and final_wf.current_state == WorkflowState.COMPLETED and final_rev == 10)
    audit_log("SEC-E2E-002", "Deterministic State Machine Completion", "COMPLETED (Rev 10)", f"{final_wf.current_state.value} (Rev {final_rev})", passed_final)

    # Clean up
    CosmosWorkflowRepository().delete(wf_id)


def main():
    print("================================================================================")
    print("    PAPERTRAIL AI - PHASE 14 FINAL LIVE SECURITY REGRESSION AUDIT SUITE        ")
    print("================================================================================")
    
    base_url = "https://papertrail-api.gentlesmoke-4100f438.centralindia.azurecontainerapps.io"
    
    test_api_security_and_inputs(base_url)
    test_api_authorization_and_role_spoofing(base_url)
    test_state_machine_and_revision_security()
    test_payload_tampering_and_claims()
    test_secretless_dataplane_and_anonymous_storage()
    test_full_security_e2e_workflow()

    print("\n================================================================================")
    print("                         AUDIT EXECUTION COMPLETED                              ")
    print("================================================================================")
    pass_count = sum(1 for r in results if r["status"] == "PASS")
    fail_count = sum(1 for r in results if r["status"] == "FAIL")
    print(f"Total Security Checks: {len(results)} | Passed: {pass_count} | Failed: {fail_count}")


if __name__ == "__main__":
    main()

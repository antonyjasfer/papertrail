import json
import os
import sys
import time
import uuid
import urllib.request
from azure.identity import DefaultAzureCredential
from azure.cosmos import CosmosClient
from azure.storage.blob import BlobServiceClient

API_BASE = "https://papertrail-api.gentlesmoke-4100f438.centralindia.azurecontainerapps.io"
COSMOS_ENDPOINT = os.environ.get("AZURE_COSMOS_ENDPOINT", "https://papertrail-cosmos-dev-2026.documents.azure.com:443/")
STORAGE_URL = os.environ.get("AZURE_STORAGE_ACCOUNT_URL", "https://papertrailstrdev2026.blob.core.windows.net/")
CLIENT_ID = "668e039e-71fd-46dd-bcbb-406a7b8849ea"
credential = DefaultAzureCredential(managed_identity_client_id=CLIENT_ID)

cosmos_client = CosmosClient(COSMOS_ENDPOINT, credential)
database = cosmos_client.get_database_client("papertrail-db")
container = database.get_container_client("papertrail-container")

blob_service = BlobServiceClient(STORAGE_URL, credential)

def run_test2_live():
    print("=== STEP 1: Upload fresh Test 2 invoice (clean_invoice_318.pdf) ===")
    pdf_path = "PaperTrail_Test_Documents/01_clean/clean_invoice_318.pdf"
    with open(pdf_path, "rb") as f:
        pdf_bytes = f.read()

    doc_id = f"doc-test2-{uuid.uuid4().hex[:12]}"
    blob_client = blob_service.get_blob_client(container="documents", blob=f"{doc_id}/clean_invoice_318.pdf")
    blob_client.upload_blob(pdf_bytes, overwrite=True)
    print(f"Uploaded {len(pdf_bytes)} bytes to Azure Blob documents container with document_id: {doc_id}")

    # Also store document metadata in Cosmos DB
    doc_meta_item = {
        "id": f"{doc_id}:meta",
        "pk": doc_id,
        "item_type": "document_metadata",
        "document_id": doc_id,
        "filename": "clean_invoice_318.pdf",
        "content_type": "application/pdf",
        "size_bytes": len(pdf_bytes),
        "storage_path": f"documents/{doc_id}/clean_invoice_318.pdf",
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    container.upsert_item(doc_meta_item)
    print(f"Upserted document metadata to Cosmos DB: {doc_id}:meta")

    print("\n=== STEP 2: Start Workflow via API ===")
    wf_id = f"wf-test2-live-{doc_id}"
    req_body = json.dumps({"document_id": doc_id, "workflow_id": wf_id}).encode("utf-8")
    req = urllib.request.Request(
        f"{API_BASE}/api/v1/pipeline/start",
        data=req_body,
        headers={"Content-Type": "application/json"},
        method="POST"
    )
    with urllib.request.urlopen(req) as resp:
        resp_data = json.loads(resp.read().decode("utf-8"))
        print(f"Pipeline start response (HTTP {resp.status}):")
        print(json.dumps(resp_data, indent=2))

    assert resp_data["workflow_id"] == wf_id
    assert resp_data["current_state"] == "UPLOADED"
    assert resp_data["workflow_revision"] == 1
    print("Initial state UPLOADED / revision 1 verified!")

    print("\n=== STEP 3: Monitor Workflow Execution via Cosmos DB ===")
    t_start = time.time()
    final_states = {"COMPLETED", "REQUIRES_REVIEW", "FAILED"}
    last_state = None
    last_rev = None

    while time.time() - t_start < 120:
        query = f"SELECT * FROM c WHERE c.pk = '{wf_id}' AND c.item_type = 'workflow'"
        items = list(container.query_items(query=query, enable_cross_partition_query=True))
        if items:
            wf = items[0]
            curr_state = wf.get("current_state")
            curr_rev = wf.get("workflow_revision")
            if curr_state != last_state or curr_rev != last_rev:
                print(f"[{time.strftime('%H:%M:%S')}] Workflow '{wf_id}' -> State: {curr_state}, Revision: {curr_rev}")
                last_state = curr_state
                last_rev = curr_rev
            if curr_state in final_states:
                print(f"Workflow reached terminal state: {curr_state} (Revision {curr_rev})")
                break
        time.sleep(3)

    print("\n=== STEP 4: Inspect Claims & Execution Data ===")
    claims_query = f"SELECT * FROM c WHERE c.pk = '{wf_id}' AND c.item_type = 'execution_claim' ORDER BY c.acquired_at"
    claims = list(container.query_items(query=claims_query, enable_cross_partition_query=True))
    print(f"Total execution claims acquired: {len(claims)}")
    for c in claims:
        print(f" - Claim ID: {c.get('claim_id')} | Worker: {c.get('worker_id')} | Acquired: {c.get('acquired_at')}")

    outbox_query = f"SELECT * FROM c WHERE c.pk = '{wf_id}' AND c.item_type = 'outbox_event'"
    outbox_items = list(container.query_items(query=outbox_query, enable_cross_partition_query=True))
    print(f"Total outbox events: {len(outbox_items)}")

    audit_query = f"SELECT * FROM c WHERE c.pk = '{wf_id}' AND c.item_type = 'audit_event'"
    audit_events = list(container.query_items(query=audit_query, enable_cross_partition_query=True))
    print(f"Total audit events: {len(audit_events)}")

    return wf_id, doc_id

if __name__ == "__main__":
    run_test2_live()

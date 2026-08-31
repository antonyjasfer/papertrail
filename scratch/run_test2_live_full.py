import os
import sys
import time
import json
import requests
import hashlib

os.environ["ENVIRONMENT"] = "development"
os.environ["PAPERTRAIL_CLOUD_PROVIDER"] = "azure"
os.environ["AZURE_COSMOS_ENDPOINT"] = "https://papertrailcosmosdev2026.documents.azure.com:443/"
os.environ["AZURE_STORAGE_ACCOUNT_URL"] = "https://papertrailstoragedev2026.blob.core.windows.net/"
os.environ["AZURE_SERVICEBUS_NAMESPACE"] = "papertrail-sb-dev-2026.servicebus.windows.net"
os.environ["AZURE_KEYVAULT_URL"] = "https://papertrail-kv-dev-2026.vault.azure.net/"

sys.path.insert(0, ".")

from app.infrastructure.azure.cosmos_state_manager import CosmosStateManager

API_BASE = "https://papertrail-api.gentlesmoke-4100f438.centralindia.azurecontainerapps.io"
PDF_PATH = "PaperTrail_Test_Documents/01_clean/clean_invoice_318.pdf"

print("================================================================================")
print("1. PROBE /health and /health/ready")
r_health = requests.get(f"{API_BASE}/health", timeout=10)
print(f"Health: {r_health.status_code}, {r_health.text}")
assert r_health.status_code == 200

r_ready = requests.get(f"{API_BASE}/health/ready", timeout=10)
print(f"Ready: {r_ready.status_code}, {r_ready.text}")
assert r_ready.status_code == 200

print("\n================================================================================")
print("2. UPLOAD FRESH TEST 2 INVOICE: clean_invoice_318.pdf")
with open(PDF_PATH, "rb") as f:
    pdf_bytes = f.read()

sha256_hash = hashlib.sha256(pdf_bytes).hexdigest()
print(f"File size: {len(pdf_bytes)} bytes | SHA-256: {sha256_hash}")

files = {"file": ("clean_invoice_318.pdf", pdf_bytes, "application/pdf")}
r_upload = requests.post(f"{API_BASE}/documents", files=files, timeout=30)
print(f"Upload Status: {r_upload.status_code}, Body: {r_upload.text}")
assert r_upload.status_code == 201, "Upload failed"
doc_data = r_upload.json()
doc_id = doc_data["document_id"]
print(f"Uploaded Document ID: {doc_id}")

print("\n================================================================================")
print("3. START PIPELINE WORKFLOW (NEW WORKFLOW ID)")
wf_id = f"wf-test2-live-{doc_id}"
r_start = requests.post(
    f"{API_BASE}/api/v1/pipeline/start",
    json={"document_id": doc_id, "workflow_id": wf_id},
    timeout=30
)
print(f"Start Status: {r_start.status_code}, Body: {r_start.text}")
assert r_start.status_code in (200, 201, 202), "Start pipeline failed"
start_data = r_start.json()
print(f"Initial State: {start_data.get('current_state')} | Revision: {start_data.get('workflow_revision')}")
assert start_data.get("current_state") == "UPLOADED"
assert start_data.get("workflow_revision") == 1

print("\n================================================================================")
print(f"4. MONITOR WORKFLOW EXECUTION: {wf_id}")
max_wait = 120
start_time = time.time()
final_status = None
last_state = None
last_rev = None

while time.time() - start_time < max_wait:
    time.sleep(3)
    r_status = requests.get(f"{API_BASE}/api/v1/pipeline/{wf_id}/status", timeout=10)
    if r_status.status_code == 200:
        st_data = r_status.json()
        current_state = st_data.get("current_state")
        current_rev = st_data.get("workflow_revision")
        if current_state != last_state or current_rev != last_rev:
            print(f"[{time.strftime('%H:%M:%S')}] Workflow '{wf_id}' -> State: {current_state}, Revision: {current_rev}")
            last_state = current_state
            last_rev = current_rev
        if current_state in ("COMPLETED", "REQUIRES_REVIEW", "FAILED"):
            final_status = st_data
            print(f"Workflow reached terminal state: {current_state} (Revision {current_rev})")
            break

print("\n================================================================================")
print("5. QUERY COSMOS DB FOR ALL WORKFLOW ITEMS & CLAIMS")
state_mgr = CosmosStateManager()
container = state_mgr.container

items = list(container.query_items(
    query="SELECT * FROM c WHERE c.workflow_id = @wf_id",
    parameters=[{"name": "@wf_id", "value": wf_id}],
    enable_cross_partition_query=False,
    partition_key=wf_id
))

print(f"Total Cosmos DB items found for partition '{wf_id}': {len(items)}")

item_types = {}
for it in items:
    itype = it.get("item_type", "unknown")
    item_types[itype] = item_types.get(itype, 0) + 1
print(f"Item types breakdown: {json.dumps(item_types, indent=2)}")

# Save full Cosmos dump to file for detailed inspection
with open("scratch/test2_live_cosmos_dump.json", "w") as f:
    json.dump(items, f, indent=2)
print("Saved full Cosmos dump to scratch/test2_live_cosmos_dump.json")

print("\n================================================================================")
print("6. EXTRACT KEY RESULTS FROM CLAIMS")
claims = [it for it in items if it.get("item_type") == "execution_claim"]
claims_sorted = sorted(claims, key=lambda x: x.get("workflow_revision", 0))
print(f"Found {len(claims_sorted)} execution claims:")
for c in claims_sorted:
    print(f"Claim rev {c.get('workflow_revision')}: event_type={c.get('event_type')}, worker={c.get('worker_id')}")

outbox_items = [it for it in items if it.get("item_type") == "outbox_event"]
print(f"Found {len(outbox_items)} outbox events.")

audit_items = [it for it in items if it.get("item_type") == "audit_event"]
print(f"Found {len(audit_items)} audit events.")


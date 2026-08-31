import os
import sys
import json

os.environ["ENVIRONMENT"] = "development"
os.environ["PAPERTRAIL_CLOUD_PROVIDER"] = "azure"
os.environ["AZURE_COSMOS_ENDPOINT"] = "https://papertrailcosmosdev2026.documents.azure.com:443/"
os.environ["AZURE_STORAGE_ACCOUNT_URL"] = "https://papertrailstoragedev2026.blob.core.windows.net/"
os.environ["AZURE_SERVICEBUS_NAMESPACE"] = "papertrail-sb-dev-2026.servicebus.windows.net"
os.environ["AZURE_KEYVAULT_URL"] = "https://papertrail-kv-dev-2026.vault.azure.net/"

sys.path.insert(0, ".")

from app.infrastructure.azure.cosmos_state_manager import CosmosStateManager
from app.infrastructure.azure.blob_storage import AzureBlobStorageProvider

wf_id = "wf-test3-dup-doc-802dabf7f61b"
doc_id = "doc-802dabf7f61b"

state_mgr = CosmosStateManager()
container = state_mgr.container

print(f"=== QUERYING COSMOS DB FOR WORKFLOW {wf_id} ===")
items = list(container.query_items(
    query="SELECT * FROM c WHERE c.workflow_id = @wf_id",
    parameters=[{"name": "@wf_id", "value": wf_id}],
    enable_cross_partition_query=False,
    partition_key=wf_id
))

print(f"Found {len(items)} items for partition {wf_id}")

workflow_item = next((i for i in items if i.get("type") == "WORKFLOW"), None)
if workflow_item:
    print("\n--- WORKFLOW RECORD ---")
    print(json.dumps(workflow_item, indent=2, default=str))

claims = [i for i in items if i.get("type") == "EXECUTION_CLAIM"]
claims_sorted = sorted(claims, key=lambda x: x.get("logical_event_key", ""))

for c in claims_sorted:
    print(f"\n==================== CLAIM: {c.get('logical_event_key')} ====================")
    print(f"Claim ID: {c.get('claim_id')}")
    print(f"Status: {c.get('status')}")
    print("OUTPUT REFERENCE:")
    print(json.dumps(c.get("output_reference"), indent=2, default=str))

# Also query cross-partition for document metadata and audit records
print(f"\n=== QUERYING DOCUMENT RECORD FOR {doc_id} ===")
doc_items = list(container.query_items(
    query="SELECT * FROM c WHERE c.id = @doc_item_id OR c.document_id = @doc_id",
    parameters=[{"name": "@doc_item_id", "value": f"doc:{doc_id}"}, {"name": "@doc_id", "value": doc_id}],
    enable_cross_partition_query=True
))
for d in doc_items:
    if d.get("type") == "DOCUMENT":
        print(f"Document Metadata Item: {json.dumps(d, indent=2, default=str)}")

print(f"\n=== QUERYING AUDIT EVENTS FOR WORKFLOW {wf_id} ===")
audit_items = list(container.query_items(
    query="SELECT * FROM c WHERE c.workflow_id = @wf_id AND c.type = 'AUDIT_EVENT'",
    parameters=[{"name": "@wf_id", "value": wf_id}],
    enable_cross_partition_query=True
))
print(f"Found {len(audit_items)} audit events:")
for a in sorted(audit_items, key=lambda x: x.get("sequence_number", 0)):
    print(f" - Event #{a.get('sequence_number')}: {a.get('event_type')} | Stage: {a.get('stage')} | Outcome: {a.get('outcome')}")
    if a.get("event_type") in ("ANALYSIS_ANOMALIES_DETECTED", "COMPLIANCE_FAILED", "REVIEW_ESCALATED", "WORKFLOW_ROUTED_TO_REVIEW"):
        print(f"   Payload: {json.dumps(a.get('payload'), indent=2, default=str)}")


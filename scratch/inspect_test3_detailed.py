import os
import sys
import json
from azure.identity import AzureCliCredential
from azure.cosmos import CosmosClient

COSMOS_ENDPOINT = "https://papertrailcosmosdev2026.documents.azure.com:443/"
DATABASE_NAME = "papertrail-db"
CONTAINER_NAME = "papertrail-container"

wf_id = "wf-test3-dup-doc-802dabf7f61b"
doc_id = "doc-802dabf7f61b"

cred = AzureCliCredential()
client = CosmosClient(COSMOS_ENDPOINT, credential=cred)
database = client.get_database_client(DATABASE_NAME)
container = database.get_container_client(CONTAINER_NAME)

print("=" * 80)
print(f"1. WORKFLOW STATE RECORD FOR {wf_id}")
wf_items = list(container.query_items(
    query="SELECT * FROM c WHERE c.workflow_id = @wf_id",
    parameters=[{"name": "@wf_id", "value": wf_id}],
    enable_cross_partition_query=False,
    partition_key=wf_id
))
print(f"Total partition items: {len(wf_items)}")
for it in wf_items:
    if it.get("type") == "WORKFLOW":
        print(json.dumps(it, indent=2, default=str))

print("\n" + "=" * 80)
print("2. EXECUTION CLAIMS FOR ALL STAGES")
claims = [i for i in wf_items if i.get("type") == "EXECUTION_CLAIM"]
claims_sorted = sorted(claims, key=lambda x: x.get("logical_event_key", ""))
for c in claims_sorted:
    print(f"\n>>> CLAIM: {c.get('logical_event_key')} (Status: {c.get('status')})")
    out_ref = c.get("output_reference", {})
    print(json.dumps(out_ref, indent=2, default=str))

print("\n" + "=" * 80)
print(f"3. DOCUMENT METADATA RECORDS FOR {doc_id} AND ORIGINAL doc-ad023107c485")
doc_items = list(container.query_items(
    query="SELECT * FROM c WHERE c.type = 'DOCUMENT' AND (c.document_id = @doc_id OR c.document_id = 'doc-ad023107c485')",
    parameters=[{"name": "@doc_id", "value": doc_id}],
    enable_cross_partition_query=True
))
for d in doc_items:
    print(f"\nDocument ID: {d.get('document_id')}")
    print(f"Filename: {d.get('filename')}")
    print(f"Checksum (SHA-256): {d.get('checksum')}")
    print(f"Status: {d.get('document_status')}")
    print(f"Size: {d.get('size_bytes')} bytes")
    print(f"Storage Object: {d.get('storage_object')}")

print("\n" + "=" * 80)
print(f"4. AUDIT EVENTS FOR WORKFLOW {wf_id}")
audit_items = list(container.query_items(
    query="SELECT * FROM c WHERE c.workflow_id = @wf_id AND c.type = 'AUDIT_EVENT'",
    parameters=[{"name": "@wf_id", "value": wf_id}],
    enable_cross_partition_query=True
))
audit_sorted = sorted(audit_items, key=lambda x: x.get("sequence_number", 0))
for a in audit_sorted:
    print(f"Seq #{a.get('sequence_number')}: EventType={a.get('event_type')}, Stage={a.get('stage')}, Hash={a.get('event_hash', '')[:16]}..., PrevHash={a.get('previous_event_hash', '')[:16]}...")
    if a.get("stage") in ("FORENSICS", "COMPLIANCE", "RISK", "FINAL_SEAL") or "FINDING" in a.get("event_type", ""):
        print(f"   Payload: {json.dumps(a.get('payload'), indent=2, default=str)}")


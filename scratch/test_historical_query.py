import os
import sys
import json
from azure.identity import AzureCliCredential
from azure.cosmos import CosmosClient

COSMOS_ENDPOINT = "https://papertrailcosmosdev2026.documents.azure.com:443/"
DATABASE_NAME = "papertrail-db"

cred = AzureCliCredential()
client = CosmosClient(COSMOS_ENDPOINT, credential=cred)
database = client.get_database_client(DATABASE_NAME)
doc_container = database.get_container_client("documents")
wf_container = database.get_container_client("workflow_state")

current_doc_id = "doc-802dabf7f61b"

print("=== 1. QUERY EXISTING CHECKSUMS (EXCLUDING CURRENT DOC) ===")
checksum_query = "SELECT c.checksum, c.document_id FROM c WHERE c.type = 'DOCUMENT' AND c.document_id != @doc_id"
docs = list(doc_container.query_items(
    query=checksum_query,
    parameters=[{"name": "@doc_id", "value": current_doc_id}],
    enable_cross_partition_query=True
))
print(f"Found {len(docs)} other documents:")
existing_checksums = [d["checksum"] for d in docs if d.get("checksum")]
for d in docs:
    print(f"  - doc_id: {d.get('document_id')}, checksum: {d.get('checksum')}")

print(f"\nCollected {len(existing_checksums)} existing checksums: {existing_checksums}")

print("\n=== 2. QUERY EXISTING INVOICE NUMBERS ACROSS WORKFLOW CLAIMS ===")
inv_query = "SELECT c.output_reference.extraction.invoice_number, c.document_id, c.workflow_id FROM c WHERE c.type = 'EXECUTION_CLAIM' AND IS_DEFINED(c.output_reference.extraction.invoice_number) AND c.document_id != @doc_id"
inv_items = list(wf_container.query_items(
    query=inv_query,
    parameters=[{"name": "@doc_id", "value": current_doc_id}],
    enable_cross_partition_query=True
))
print(f"Found {len(inv_items)} extraction claims for other documents:")
existing_inv_nums = []
for it in inv_items:
    inv = it.get("invoice_number")
    if inv and inv not in existing_inv_nums:
        existing_inv_nums.append(inv)
    print(f"  - wf: {it.get('workflow_id')}, doc: {it.get('document_id')}, invoice_number: {inv}")

print(f"\nCollected existing invoice numbers: {existing_inv_nums}")

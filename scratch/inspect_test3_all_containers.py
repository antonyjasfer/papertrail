import os
import sys
import json
from azure.identity import AzureCliCredential
from azure.cosmos import CosmosClient

COSMOS_ENDPOINT = "https://papertrailcosmosdev2026.documents.azure.com:443/"
DATABASE_NAME = "papertrail-db"

wf_id = "wf-test3-dup-doc-802dabf7f61b"
doc_id = "doc-802dabf7f61b"

cred = AzureCliCredential()
client = CosmosClient(COSMOS_ENDPOINT, credential=cred)
database = client.get_database_client(DATABASE_NAME)

containers = list(database.list_containers())
print(f"Available Cosmos Containers: {[c['id'] for c in containers]}")

for cont_info in containers:
    cid = cont_info['id']
    c_client = database.get_container_client(cid)
    items = list(c_client.query_items(
        query="SELECT * FROM c WHERE c.workflow_id = @wf_id OR c.document_id = @doc_id OR c.id = @doc_id OR c.id = @doc_item_id",
        parameters=[
            {"name": "@wf_id", "value": wf_id},
            {"name": "@doc_id", "value": doc_id},
            {"name": "@doc_item_id", "value": f"doc:{doc_id}"}
        ],
        enable_cross_partition_query=True
    ))
    print(f"\n================ CONTAINER: {cid} (Matched {len(items)} items) ================")
    for it in items:
        t = it.get("type") or it.get("id")
        print(f"--- Item ID: {it.get('id')} | Type: {t} ---")
        print(json.dumps(it, indent=2, default=str))


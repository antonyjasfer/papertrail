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
wf_container = database.get_container_client("workflow_state")

items = list(wf_container.query_items(
    query="SELECT c.id, c.workflow_id, c.output_reference FROM c WHERE c.type = 'EXECUTION_CLAIM'",
    enable_cross_partition_query=True
))

print(f"Total execution claims: {len(items)}")
for it in items:
    out = it.get("output_reference")
    if out and isinstance(out, dict) and "extraction" in out:
        print(f"Found extraction in claim {it['id']}: invoice_number = {out['extraction'].get('invoice_number')}")
    elif out and isinstance(out, dict) and "forensic_result" in out:
        pass

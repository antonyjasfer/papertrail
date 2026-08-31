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

from azure.identity import AzureCliCredential
from azure.cosmos import CosmosClient
from app.models.forensics import HistoricalContext

COSMOS_ENDPOINT = "https://papertrailcosmosdev2026.documents.azure.com:443/"
DATABASE_NAME = "papertrail-db"

cred = AzureCliCredential()
client = CosmosClient(COSMOS_ENDPOINT, credential=cred)
db = client.get_database_client(DATABASE_NAME)
doc_container = db.get_container_client("documents")
wf_container = db.get_container_client("workflow_state")

def get_historical_context_test(exclude_doc_id: str, exclude_wf_id: str = None) -> HistoricalContext:
    existing_checksums = set()
    existing_inv_nums = set()

    # 1. Query documents container for checksums
    try:
        doc_query = "SELECT c.checksum FROM c WHERE c.type = 'DOCUMENT' AND c.document_id != @doc_id"
        doc_items = doc_container.query_items(
            query=doc_query,
            parameters=[{"name": "@doc_id", "value": exclude_doc_id}],
            enable_cross_partition_query=True
        )
        for item in doc_items:
            chk = item.get("checksum")
            if chk:
                existing_checksums.add(chk)
    except Exception as e:
        print(f"Error querying doc checksums: {e}")

    # 2. Query workflow_state for invoice numbers
    try:
        wf_query = (
            "SELECT c.output_reference.extraction.invoice_number AS inv_num, c.workflow_id, c.document_id "
            "FROM c WHERE c.type = 'EXECUTION_CLAIM' AND IS_DEFINED(c.output_reference.extraction.invoice_number)"
        )
        claims = wf_container.query_items(
            query=wf_query,
            enable_cross_partition_query=True
        )
        for c in claims:
            w_id = c.get("workflow_id")
            d_id = c.get("document_id")
            inv = c.get("inv_num")
            if exclude_wf_id and w_id == exclude_wf_id:
                continue
            if exclude_doc_id and d_id == exclude_doc_id:
                continue
            if inv:
                existing_inv_nums.add(str(inv).strip())
    except Exception as e:
        print(f"Error querying claim invoice numbers: {e}")

    return HistoricalContext(
        existing_invoice_numbers=sorted(list(existing_inv_nums)),
        existing_checksums=sorted(list(existing_checksums)),
    )

# Test with duplicate document
dup_doc_id = "doc-802dabf7f61b"
dup_wf_id = "wf-test3-dup-doc-802dabf7f61b"

ctx = get_historical_context_test(dup_doc_id, dup_wf_id)
print(f"Historical Checksums count: {len(ctx.existing_checksums)}")
print(f"Historical Invoice Numbers count: {len(ctx.existing_invoice_numbers)}")
print(f"Sample Invoice Numbers: {ctx.existing_invoice_numbers[:10]}")

# Check if target values match
target_chk = "ea0e878b2b4d949a947b7ed11ecb213d9718446f5e4a774c7646270d2f200e6e"
target_inv = "36259"

print(f"\nTarget Checksum '{target_chk}' in historical context: {target_chk in ctx.existing_checksums}")
print(f"Target Invoice #{target_inv} in historical context: {target_inv in ctx.existing_invoice_numbers}")


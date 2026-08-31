import os
import sys
import json

sys.path.insert(0, os.path.abspath("."))
sys.path.insert(0, os.path.abspath("scratch/dns_fix"))
import sitecustomize

os.environ["ENVIRONMENT"] = "development"
os.environ["PAPERTRAIL_CLOUD_PROVIDER"] = "azure"
os.environ["AZURE_COSMOS_ENDPOINT"] = "https://papertrailcosmosdev2026.documents.azure.com:443/"
os.environ["AZURE_STORAGE_ACCOUNT_URL"] = "https://papertrailstoragedev2026.blob.core.windows.net/"
os.environ["AZURE_SERVICEBUS_NAMESPACE"] = "papertrail-sb-dev-2026.servicebus.windows.net"
os.environ["AZURE_KEYVAULT_URL"] = "https://papertrail-kv-dev-2026.vault.azure.net/"

from app.infrastructure.azure.cosmos_repositories import CosmosAuditEventRepository

wf_id = "wf-test3-live-dup-doc-a6e2e466a941"
doc_id = "doc-a6e2e466a941"

def main():
    audit_repo = CosmosAuditEventRepository()
    if audit_repo.container is not None:
        items = list(audit_repo.container.query_items(
            query="SELECT * FROM c WHERE c.workflow_id = @wf_id OR c.document_id = @doc_id",
            parameters=[{"name": "@wf_id", "value": wf_id}, {"name": "@doc_id", "value": doc_id}],
            enable_cross_partition_query=True
        ))
        print(f"Total audit items found: {len(items)}")
        for a in items:
            print(f"ID: {a.get('id')}, Type: {a.get('type')}, Seq: {a.get('sequence_number')}, EventType: {a.get('event_type')}, Hash: {a.get('event_hash')}")
            print(json.dumps(a, indent=2, default=str))

if __name__ == "__main__":
    main()

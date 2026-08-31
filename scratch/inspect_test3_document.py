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

from app.infrastructure.azure.cosmos_repositories import CosmosDocumentRepository

doc_id = "doc-a6e2e466a941"

def main():
    doc_repo = CosmosDocumentRepository()
    if doc_repo.container is not None:
        items = list(doc_repo.container.query_items(
            query="SELECT * FROM c WHERE c.document_id = @doc_id",
            parameters=[{"name": "@doc_id", "value": doc_id}],
            enable_cross_partition_query=True
        ))
        print(f"Document items found: {len(items)}")
        for d in items:
            print(json.dumps(d, indent=2, default=str))

if __name__ == "__main__":
    main()

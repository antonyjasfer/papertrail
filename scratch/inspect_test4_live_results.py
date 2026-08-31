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

from app.infrastructure.azure.cosmos_state_manager import CosmosStateManager
from app.infrastructure.azure.cosmos_repositories import CosmosAuditEventRepository, CosmosDocumentRepository

wf_id = "wf-test4-doc-fa33d76d28ce"
doc_id = "doc-fa33d76d28ce"

def main():
    state_mgr = CosmosStateManager()
    container = state_mgr.container
    if container is None:
        print("Error: Cosmos container is None")
        return

    # 1. Query workflow state document & claims
    items = list(container.query_items(
        query="SELECT * FROM c WHERE c.workflow_id = @wf_id",
        parameters=[{"name": "@wf_id", "value": wf_id}],
        enable_cross_partition_query=False,
        partition_key=wf_id
    ))

    state_doc = next((i for i in items if i.get("type") == "WORKFLOW" or i.get("type") == "WORKFLOW_STATE" or i.get("id") == f"wf:{wf_id}"), None)
    claims = [i for i in items if i.get("type") == "EXECUTION_CLAIM"]
    claims_sorted = sorted(claims, key=lambda x: x.get("logical_event_key", ""))

    print("=================================================================")
    print(f"LIVE COSMOS WORKFLOW STATE: {wf_id}")
    print("=================================================================")
    if state_doc:
        print(json.dumps(state_doc, indent=2, default=str))
    else:
        print("Workflow state document not found!")

    print("\n=================================================================")
    print(f"TOTAL EXECUTION CLAIMS: {len(claims_sorted)}")
    print("=================================================================")
    for c in claims_sorted:
        event_key = c.get("logical_event_key")
        claim_id = c.get("claim_id")
        status = c.get("status")
        rev = c.get("revision")
        print(f"\n==================== CLAIM: {event_key} (ID: {claim_id}, Status: {status}, Rev: {rev}) ====================")
        print("OUTPUT REFERENCE:")
        print(json.dumps(c.get("output_reference"), indent=2, default=str))

    # 2. Query Document Record
    doc_repo = CosmosDocumentRepository()
    if doc_repo.container is not None:
        doc_items = list(doc_repo.container.query_items(
            query="SELECT * FROM c WHERE c.document_id = @doc_id",
            parameters=[{"name": "@doc_id", "value": doc_id}],
            enable_cross_partition_query=True
        ))
        print("\n=================================================================")
        print(f"DOCUMENT RECORD ({len(doc_items)} found)")
        print("=================================================================")
        for d in doc_items:
            print(json.dumps(d, indent=2, default=str))

    # 3. Query Audit Events
    audit_repo = CosmosAuditEventRepository()
    if audit_repo.container is not None:
        audit_items = list(audit_repo.container.query_items(
            query="SELECT * FROM c WHERE c.workflow_id = @wf_id OR c.document_id = @doc_id",
            parameters=[{"name": "@wf_id", "value": wf_id}, {"name": "@doc_id", "value": doc_id}],
            enable_cross_partition_query=True
        ))
        print("\n=================================================================")
        print(f"AUDIT TRAIL ({len(audit_items)} events)")
        print("=================================================================")
        for a in audit_items:
            print(json.dumps(a, indent=2, default=str))

if __name__ == "__main__":
    main()

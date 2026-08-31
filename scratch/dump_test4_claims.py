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

wf_id = "wf-test4-doc-fa33d76d28ce"

def main():
    state_mgr = CosmosStateManager()
    container = state_mgr.container
    
    items = list(container.query_items(
        query="SELECT * FROM c WHERE c.workflow_id = @wf_id",
        parameters=[{"name": "@wf_id", "value": wf_id}],
        enable_cross_partition_query=False,
        partition_key=wf_id
    ))

    claims = [i for i in items if i.get("type") == "EXECUTION_CLAIM"]
    claims_sorted = sorted(claims, key=lambda x: x.get("logical_event_key", ""))

    for c in claims_sorted:
        print(f"\n==================== CLAIM: {c.get('logical_event_key')} ====================")
        print(f"Claim ID: {c.get('claim_id')}")
        print(f"Status: {c.get('status')}")
        print(f"Event Type: {c.get('event_type')}")
        print("OUTPUT REFERENCE:")
        print(json.dumps(c.get("output_reference"), indent=2, default=str))

if __name__ == "__main__":
    main()

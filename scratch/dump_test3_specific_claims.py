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
wf_container = database.get_container_client("workflow_state")
audit_container = database.get_container_client("audit_events")
doc_container = database.get_container_client("documents")

print("=" * 80)
print(f"=== 1. WORKFLOW RECORD ({wf_id}) ===")
wf_item = wf_container.read_item(item=f"wf:{wf_id}", partition_key=wf_id)
print(f"Current State: {wf_item.get('current_state')}")
print(f"Revision: {wf_item.get('workflow_revision')}")
print(f"Failure Reason: {wf_item.get('failure_reason')}")
print(f"Review Reason: {wf_item.get('review_reason')}")

print("\n" + "=" * 80)
print("=== 2. STAGE EXECUTION CLAIMS ===")
claims = list(wf_container.query_items(
    query="SELECT * FROM c WHERE c.workflow_id = @wf_id AND c.type = 'EXECUTION_CLAIM'",
    parameters=[{"name": "@wf_id", "value": wf_id}],
    enable_cross_partition_query=False,
    partition_key=wf_id
))
claims_sorted = sorted(claims, key=lambda x: x.get("logical_event_key", ""))

for c in claims_sorted:
    k = c.get("logical_event_key", "")
    out_ref = c.get("output_reference", {})
    print(f"\n--------------------------------------------------------------------------------")
    print(f"CLAIM KEY: {k}")
    
    # Check extraction (Stage 2)
    if ":2:" in k:
        ext = out_ref.get("extraction", {})
        print(f"EXTRACTION OUTPUT:")
        print(f"  Invoice Number: {ext.get('invoice_number')}")
        print(f"  Vendor: {ext.get('vendor')}")
        print(f"  Customer: {ext.get('customer')}")
        print(f"  Dates: {ext.get('dates')}")
        print(f"  Amounts: {ext.get('amounts')}")
        print(f"  Line Items Count: {len(ext.get('line_items', []))}")
        for li in ext.get('line_items', []):
            print(f"    - {li}")
        print(f"  Confidence: {ext.get('extraction_confidence')}")
        print(f"  Raw Text Sample: {ext.get('raw_text', '')[:100]}")

    # Check forensics (Stage 5)
    elif ":5:" in k:
        f_res = out_ref.get("forensic_result", {})
        print(f"FORENSIC RESULT:")
        print(f"  Finding Count: {f_res.get('finding_count')}")
        print(f"  Findings: {json.dumps(f_res.get('findings'), indent=2)}")
        print(f"  Deterministic Checks Run: {f_res.get('deterministic_checks_run')}")
        print(f"  Checks Skipped: {json.dumps(f_res.get('checks_skipped'), indent=2)}")
        print(f"  Evidence Summary: {f_res.get('evidence_summary')}")

    # Check compliance (Stage 6)
    elif ":6:" in k:
        cmp_res = out_ref.get("compliance_result", {})
        print(f"COMPLIANCE RESULT:")
        print(f"  Overall Status: {cmp_res.get('status')}")
        print(f"  Findings Count: {cmp_res.get('finding_count')}")
        print(f"  Findings:")
        for f in cmp_res.get("findings", []):
            print(f"    - Rule: {f.get('rule_id')} | Control: {f.get('control_id')} | Status: {f.get('status')} | Desc: {f.get('description')}")
            print(f"      Evidence: {json.dumps(f.get('evidence'), indent=2)}")

    # Check risk (Stage 7)
    elif ":7:" in k:
        risk_res = out_ref.get("risk_assessment", {})
        print(f"RISK ASSESSMENT:")
        print(f"  Composite Score: {risk_res.get('composite_score')}")
        print(f"  Risk Level: {risk_res.get('risk_level')}")
        print(f"  Review Recommended: {risk_res.get('review_recommended')}")
        print(f"  Summary: {risk_res.get('assessment_summary')}")
        print(f"  Dimension Scores:")
        for d in risk_res.get("dimensions", []):
            print(f"    - {d.get('dimension_id')} ({d.get('dimension_name')}): Score={d.get('score')}, Weight={d.get('weight')}, WeightedContrib={d.get('weighted_contribution')}")
            print(f"      Factors: {d.get('evidence', {}).get('contributing_factors')}")

    # Check report (Stage 9)
    elif ":9:" in k:
        print(f"REPORT OUTPUT:")
        print(json.dumps(out_ref, indent=2))

print("\n" + "=" * 80)
print(f"=== 3. AUDIT TRAIL ({len(claims)} stage claims verified) ===")
audit_items = list(audit_container.query_items(
    query="SELECT * FROM c WHERE c.workflow_id = @wf_id",
    parameters=[{"name": "@wf_id", "value": wf_id}],
    enable_cross_partition_query=True
))
audit_sorted = sorted(audit_items, key=lambda x: x.get("sequence_number", 0))
for a in audit_sorted:
    print(f"Seq #{a.get('sequence_number')}: {a.get('event_type')} | Stage: {a.get('stage')} | Outcome: {a.get('outcome')}")


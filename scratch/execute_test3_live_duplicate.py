import os
import sys
import time
import json
import hashlib

sys.path.insert(0, os.path.abspath("."))
sys.path.insert(0, os.path.abspath("scratch/dns_fix"))
import sitecustomize

import requests
from azure.cosmos import CosmosClient
from app.infrastructure.azure.foundation import azure_foundation

API_URL = "https://papertrail-api.gentlesmoke-4100f438.centralindia.azurecontainerapps.io"
PDF_PATH = r"c:\Users\anton\OneDrive\Desktop\papertrail\PaperTrail_Test_Documents\01_clean\clean_invoice_02.pdf"

def main():
    # 1. Verify local file and calculate checksum
    with open(PDF_PATH, "rb") as f:
        pdf_bytes = f.read()
    local_sha = hashlib.sha256(pdf_bytes).hexdigest()
    print(f"Local file: clean_invoice_02.pdf ({len(pdf_bytes)} bytes)")
    print(f"Local SHA-256: {local_sha}")
    assert local_sha == "ea0e878b2b4d949a947b7ed11ecb213d9718446f5e4a774c7646270d2f200e6e"

    # 2. Upload document to Azure API
    print("\n--- 1. Uploading Document to Azure API ---")
    files = {"file": ("clean_invoice_02.pdf", pdf_bytes, "application/pdf")}
    resp = requests.post(f"{API_URL}/documents", files=files, timeout=60)
    print("Upload Status:", resp.status_code)
    upload_data = resp.json()
    print("Upload Response:", json.dumps(upload_data, indent=2))
    
    doc_id = upload_data.get("document_id")
    assert doc_id, "Missing document_id"
    uploaded_sha = upload_data.get("checksum")
    print(f"Fresh Document ID: {doc_id}")
    print(f"Uploaded Checksum: {uploaded_sha}")
    assert uploaded_sha == local_sha

    # 3. Start Workflow
    wf_id = f"wf-test3-live-dup-{doc_id}"
    print(f"\n--- 2. Starting Fresh Duplicate Workflow: {wf_id} ---")
    start_payload = {
        "workflow_id": wf_id,
        "document_id": doc_id,
        "document_type": "invoice",
    }
    resp = requests.post(f"{API_URL}/api/v1/pipeline/start", json=start_payload, timeout=30)
    print("Start Status:", resp.status_code)
    start_data = resp.json()
    print("Start Response:", json.dumps(start_data, indent=2))

    # 4. Monitor workflow in Cosmos DB
    print("\n--- 3. Monitoring Workflow Execution in Cosmos DB ---")
    cosmos = azure_foundation.get_cosmos_client()
    db = cosmos.get_database_client("papertrail-db")
    wf_container = db.get_container_client("workflow_state")
    audit_container = db.get_container_client("audit_events")

    final_state = None
    final_rev = None
    for i in range(60):
        time.sleep(2)
        query = f"SELECT * FROM c WHERE c.workflow_id = '{wf_id}'"
        items = list(wf_container.query_items(query=query, enable_cross_partition_query=True))
        
        state_doc = next((it for it in items if it.get("type") == "WORKFLOW_STATE" or it.get("id") == f"wf:{wf_id}"), None)
        claims = [it for it in items if it.get("type") == "EXECUTION_CLAIM"]
        
        if state_doc:
            status = state_doc.get("status")
            rev = state_doc.get("revision") or state_doc.get("workflow_revision")
            current_stage = state_doc.get("current_stage")
            print(f"[{i*2}s] Status: {status} | Revision: {rev} | Stage: {current_stage} | Claims count: {len(claims)}")
            
            if status in ("REQUIRES_REVIEW", "COMPLETED", "FAILED", "SUSPENDED"):
                final_state = status
                final_rev = rev
                print(f"\nWorkflow reached terminal state: {final_state} at Revision {final_rev}!")
                break
        else:
            print(f"[{i*2}s] Waiting for workflow state record... (Claims: {len(claims)})")

    # 5. Fetch all claims and inspect findings
    print("\n--- 4. Inspecting All Stage Claims and Findings ---")
    query = f"SELECT * FROM c WHERE c.workflow_id = '{wf_id}' ORDER BY c.claim_sequence ASC"
    items = list(wf_container.query_items(query=query, enable_cross_partition_query=True))
    
    for item in items:
        if item.get("type") == "EXECUTION_CLAIM":
            stage = item.get("stage_name")
            seq = item.get("claim_sequence")
            rev = item.get("workflow_revision")
            res_type = item.get("result_type")
            status = item.get("claim_status")
            print(f"\n=== CLAIM #{seq} | Stage: {stage} | Result: {res_type} | Revision: {rev} | Status: {status} ===")
            out_ref = item.get("output_reference", {})
            
            if stage == "EXTRACTION":
                ext = out_ref.get("extraction", {})
                print(f"  Vendor: {ext.get('vendor')}")
                print(f"  Customer: {ext.get('customer')}")
                print(f"  Invoice Number: {ext.get('invoice_number')}")
                print(f"  Invoice Date: {ext.get('dates')}")
                print(f"  Total: {ext.get('amounts')}")
                print(f"  Gemini Confidence: {ext.get('extraction_confidence')}")
                
            elif stage == "FORENSIC":
                f_res = out_ref.get("forensic_result", {})
                findings = f_res.get("findings", [])
                print(f"  Forensic Findings Count: {len(findings)}")
                for f in findings:
                    print(f"    -> Code: {f.get('finding_code')} | Rule: {f.get('rule_id')} | Severity: {f.get('severity')} | Title: {f.get('title')}")
                    print(f"       Description: {f.get('description')}")
                    print(f"       Evidence: {f.get('evidence')}")
                    
            elif stage == "COMPLIANCE":
                c_res = out_ref.get("compliance_result", {})
                findings = c_res.get("findings", [])
                print(f"  Compliance Findings Count: {len(findings)}")
                for f in findings:
                    print(f"    -> Control: {f.get('control_id')} | Rule: {f.get('rule_id')} | Status: {f.get('status')} | Severity: {f.get('severity')}")
                    print(f"       Description: {f.get('description')}")
                    
            elif stage == "RISK":
                r_res = out_ref.get("risk_result", {})
                print(f"  Composite Risk Score: {r_res.get('composite_score')}")
                print(f"  Risk Level: {r_res.get('risk_level')}")
                print(f"  Review Recommended: {r_res.get('review_recommended')}")
                print(f"  Contributing Factors: {r_res.get('contributing_factors')}")

    # 6. Audit Trail Check
    print("\n--- 5. Checking Audit Trail ---")
    audit_query = f"SELECT * FROM c WHERE c.workflow_id = '{wf_id}' ORDER BY c.sequence_number ASC"
    audit_events = list(audit_container.query_items(query=audit_query, enable_cross_partition_query=True))
    print(f"Audit events recorded: {len(audit_events)}")
    for ev in audit_events:
        print(f"  Seq {ev.get('sequence_number')} | Event: {ev.get('event_type')} | Stage: {ev.get('stage')} | State: {ev.get('state_transition')}")

    print("\n========================================================")
    print(f"TEST 3 EXECUTION SUMMARY:")
    print(f"Document ID: {doc_id}")
    print(f"Workflow ID: {wf_id}")
    print(f"Final State: {final_state} (Revision {final_rev})")
    print("========================================================")

if __name__ == "__main__":
    main()

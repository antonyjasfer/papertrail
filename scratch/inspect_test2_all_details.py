import json

with open("scratch/test2_live_cosmos_dump.json", "r") as f:
    items = json.load(f)

print("================================================================================")
print("1. REAL GEMINI EXTRACTION (Claim #2 / #3 Output)")
extract_claim = next(it for it in items if it.get("id") == "claim:36d1ded4a1c062df")
ext = extract_claim["output_reference"]["extraction"]
print("Extraction Payload:")
print(json.dumps(ext, indent=2))

print("\n================================================================================")
print("2. FORENSIC RESULTS (Claim #5 Output)")
forensic_claim = next(it for it in items if it.get("id") == "claim:41709bc266c52f42")
forensic = forensic_claim["output_reference"]["forensic_result"]
print("Forensic Result:")
print(json.dumps(forensic, indent=2))

print("\n================================================================================")
print("3. COMPLIANCE RESULTS (Claim #6 Output)")
comp_claim = next(it for it in items if it.get("id") == "claim:c9251f19d0349f10")
comp = comp_claim["output_reference"]["compliance_result"]
print("Compliance Result:")
print(json.dumps(comp, indent=2))

print("\n================================================================================")
print("4. RISK ASSESSMENT RESULTS (Claim #7 Output)")
risk_claim = next(it for it in items if it.get("id") == "claim:0c757dc1d3c48c3c")
risk = risk_claim["output_reference"]["risk_result"]
print("Risk Result:")
print(json.dumps(risk, indent=2))

print("\n================================================================================")
print("5. OUTBOX EVENTS & CLAIMS SUMMARY")
claims = [it for it in items if it.get("type") == "EXECUTION_CLAIM"]
idemp = [it for it in items if it.get("type") == "IDEMPOTENCY"]
outbox = [it for it in items if it.get("type") == "OUTBOX"]
print(f"Total Execution Claims: {len(claims)}")
print(f"Total Idempotency Records: {len(idemp)}")
print(f"Total Outbox Events: {len(outbox)}")
for o in outbox:
    print(f"Outbox: {o.get('id')} | EventType: {o.get('event_type')} | Rev: {o.get('workflow_revision')} | Published: {o.get('published')}")


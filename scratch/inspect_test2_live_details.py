import json

with open("scratch/test2_live_cosmos_dump.json", "r") as f:
    items = json.load(f)

print(f"Loaded {len(items)} items from Cosmos dump.")

# Sort items by id or timestamp
for i, it in enumerate(items):
    item_id = it.get("id")
    entity_type = it.get("entity_type") or it.get("type") or ("claim" if "claim_id" in it else ("outbox" if "event_id" in it and "status" in it else ("audit" if "event_id" in it and "event_hash" in it else "workflow")))
    print(f"Item #{i+1}: ID={item_id} | Type={entity_type} | Keys={list(it.keys())[:6]}")

# Find workflow item
wf_items = [it for it in items if it.get("id") == "wf-test2-live-doc-4068cf2507d5" or ("current_state" in it and "workflow_revision" in it)]
print("\n================ WORKFLOW ITEM ================")
for w in wf_items:
    print(json.dumps(w, indent=2))

# Find claims
claims = [it for it in items if "claim_id" in it or "claimed_by" in it or "worker_id" in it]
print(f"\n================ CLAIMS ({len(claims)}) ================")
for c in claims:
    print(f"Claim: id={c.get('id')} rev={c.get('workflow_revision')} worker={c.get('worker_id') or c.get('claimed_by')} stage={c.get('stage') or c.get('event_type')}")
    if "output_reference" in c or "output" in c:
        print("  Output keys:", list((c.get("output_reference") or c.get("output") or {}).keys()))

# Dump all claims and outbox
with open("scratch/claims_and_outputs.json", "w") as f:
    json.dump(claims, f, indent=2)


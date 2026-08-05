"""Test single conversation to capture AI raw output vs fallback."""
import requests
import json
import time

BACKEND = "http://127.0.0.1:8000"

# Snapshot with actual data (internato with claims)
snapshot = {
    "snapshot_id": "snap_test_001",
    "schema_version": "6",
    "intent": "PERSON_LOOKUP",
    "target": {
        "display_name": "ABBATTISTA ATTILIO",
        "target_id": "internati_1",
        "conflict": "WWII",
    },
    "origin": {
        "presence": "PRESENT_LOCAL",
        "provenance": "UNVERIFIED",
        "source_id": "internati_1",
    },
    "identity_resolution": "PARTIAL",
    "external_corroboration": "NONE",
    "manifest_hash": "test_hash_001",
    "asserted_claims": [
        {"claim_id": "c_by", "subject_id": "internati_1", "predicate": "birth_year", "value_normalized": "1910", "source": "origin_record"},
        {"claim_id": "c_bp", "subject_id": "internati_1", "predicate": "birth_place", "value_normalized": "Torino", "source": "origin_record"},
        {"claim_id": "c_rk", "subject_id": "internati_1", "predicate": "rank", "value_normalized": "soldato", "source": "origin_record"},
        {"claim_id": "c_ip", "subject_id": "internati_1", "predicate": "internment_place", "value_normalized": "Campo 85", "source": "origin_record"},
    ],
    "accepted_claims": [],
    "accepted_evidence": [],
    "conditional_gaps": [
        {"gap_id": "gap_service_number", "field_name": "service_number", "reason": "Field service_number not supported", "blocking": False},
    ],
    "next_steps": [],
    "limitations": [],
}

# Create conversation
r = requests.post(f"{BACKEND}/research/reports/test_ai_raw/conversations", json={"snapshot": snapshot})
d = r.json()
cid = d["conversation_id"]
print(f"Conversation: {cid}")
print(f"Provider: {d.get('provider')}, Model: {d.get('model')}")

# Send question
questions = [
    "Chi era ABBATTISTA ATTILIO?",
    "Quali sono i dati certi su ABBATTISTA ATTILIO?",
    "Quali fonti posso consultare per ABBATTISTA ATTILIO?",
]

for q in questions:
    print(f"\n{'='*60}")
    print(f"Q: {q}")
    r2 = requests.post(
        f"{BACKEND}/research/conversations/{cid}/messages",
        json={"message": q, "snapshot": snapshot},
        timeout=90,
    )
    d2 = r2.json()
    print(f"Validation: {d2.get('validation_state', 'N/A')}")
    print(f"Provider: {d2.get('provider_class', 'N/A')}")
    print(f"Model: {d2.get('provider', 'N/A')}")
    print(f"Answer:\n{d2.get('content', 'N/A')}")
    if d2.get("validation_details"):
        print(f"Validation details: {json.dumps(d2['validation_details'], ensure_ascii=False, indent=2)}")

# Check stderr log
print(f"\n{'='*60}")
print("Checking backend stderr for AI raw output...")
time.sleep(1)
try:
    with open("_backend_stderr.log", encoding="utf-8", errors="replace") as f:
        lines = f.readlines()[-50:]
    for line in lines:
        if "AI raw" in line or "Validation failed" in line:
            print(line.strip())
except FileNotFoundError:
    print("No stderr log found")

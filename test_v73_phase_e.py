"""V7.3 Phase E Tests — adapters, feature flags, quarantine filtering."""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from adapters_v73 import (
    is_feature_enabled, get_feature_status, FEATURE_FLAGS,
    get_dossier, get_dossier_legacy, get_dossier_canonical,
    get_graph, get_graph_legacy, get_graph_canonical,
    get_map_events, get_map_events_legacy, get_map_events_canonical,
    search, search_legacy, search_canonical,
    filter_quarantined_links,
    get_event_links_canonical, get_record_links_canonical,
    get_endpoint_info,
)

passed = 0
failed = 0
errors = []


def test(name, condition, detail=""):
    global passed, failed
    if condition:
        passed += 1
        print(f"  PASS: {name}")
    else:
        failed += 1
        errors.append(f"{name}: {detail}")
        print(f"  FAIL: {name} — {detail}")


# ─── 1. Feature flags ───────────────────────────────────────────────────────

print("\n=== 1. Feature Flags ===")

# All flags default OFF
for flag in FEATURE_FLAGS:
    os.environ.pop(flag, None)
test(f"{flag} defaults to OFF", not is_feature_enabled(flag))

# Enable a flag
os.environ["V73_CANONICAL_DOSSIER"] = "true"
test("V73_CANONICAL_DOSSIER ON when env set", is_feature_enabled("V73_CANONICAL_DOSSIER"))
os.environ.pop("V73_CANONICAL_DOSSIER", None)
test("V73_CANONICAL_DOSSIER OFF when env removed", not is_feature_enabled("V73_CANONICAL_DOSSIER"))

# Feature status
status = get_feature_status()
test("get_feature_status returns all flags", len(status) == len(FEATURE_FLAGS))
test("All flags OFF by default", all(not v for v in status.values()))


# ─── 2. Dossier adapter ─────────────────────────────────────────────────────

print("\n=== 2. Dossier Adapter ===")

# Legacy dossier (flag OFF) — use first available ID
os.environ.pop("V73_CANONICAL_DOSSIER", None)
dossier = get_dossier(2344)
test("Legacy dossier returns data", "error" not in dossier, f"got {dossier.get('error', 'none')}")
test("Legacy dossier source = legacy", dossier.get("source") == "legacy", f"got {dossier.get('source')}")

# Canonical dossier (flag ON)
os.environ["V73_CANONICAL_DOSSIER"] = "true"
dossier_canon = get_dossier(2344)
test("Canonical dossier returns data", "error" not in dossier_canon, f"got {dossier_canon.get('error', 'none')}")
test("Canonical dossier source = canonical_v73", dossier_canon.get("source") == "canonical_v73", f"got {dossier_canon.get('source')}")
test("Canonical dossier has canonical_claims", "canonical_claims" in dossier_canon)
test("Canonical dossier has canonical_relations", "canonical_relations" in dossier_canon)
os.environ.pop("V73_CANONICAL_DOSSIER", None)

# Non-existent ID
dossier_missing = get_dossier(999999)
test("Missing dossier returns error", "error" in dossier_missing)


# ─── 3. Graph adapter ───────────────────────────────────────────────────────

print("\n=== 3. Graph Adapter ===")

# Legacy graph (flag OFF)
os.environ.pop("V73_CANONICAL_GRAPH", None)
graph = get_graph("2344")
test("Legacy graph returns data", "edges" in graph)
test("Legacy graph source = legacy", graph.get("source") == "legacy")

# Canonical graph (flag ON)
os.environ["V73_CANONICAL_GRAPH"] = "true"
graph_canon = get_graph("test-entity-id")
test("Canonical graph returns data", "edges" in graph_canon)
test("Canonical graph source = canonical_v73", graph_canon.get("source") == "canonical_v73")
test("Canonical graph has nodes", "nodes" in graph_canon)
os.environ.pop("V73_CANONICAL_GRAPH", None)


# ─── 4. Map adapter ─────────────────────────────────────────────────────────

print("\n=== 4. Map Adapter ===")

# Legacy map (flag OFF)
os.environ.pop("V73_CANONICAL_MAP", None)
events_legacy = get_map_events()
test("Legacy map events is a list", isinstance(events_legacy, list))

# Canonical map (flag ON)
os.environ["V73_CANONICAL_MAP"] = "true"
events_canon = get_map_events()
test("Canonical map events is a list", isinstance(events_canon, list))
test("Canonical map events non-empty", len(events_canon) > 0, f"got {len(events_canon)}")
if events_canon:
    test("Canonical map event has stable_id", "stable_id" in events_canon[0])
    test("Canonical map event has war", "war" in events_canon[0])
os.environ.pop("V73_CANONICAL_MAP", None)


# ─── 5. Search adapter ──────────────────────────────────────────────────────

print("\n=== 5. Search Adapter ===")

# Legacy search (flag OFF)
os.environ.pop("V73_CANONICAL_SEARCH", None)
results = search("Rossi")
test("Legacy search returns data", isinstance(results, (list, dict)))

# Canonical search (flag ON)
os.environ["V73_CANONICAL_SEARCH"] = "true"
results_canon = search("Rossi")
test("Canonical search returns list", isinstance(results_canon, list))
os.environ.pop("V73_CANONICAL_SEARCH", None)


# ─── 6. Quarantine filtering ────────────────────────────────────────────────

print("\n=== 6. Quarantine Filtering ===")

# Filter quarantined links
mixed_links = [
    {"id": 1, "usable_as_evidence": 1, "status": "VERIFIED"},
    {"id": 2, "usable_as_evidence": 0, "status": "CANDIDATE"},
    {"id": 3, "usable_as_evidence": 0, "status": "CANDIDATE"},
    {"id": 4, "usable_as_evidence": 1, "status": "PROBABLE"},
]
usable, quarantined = filter_quarantined_links(mixed_links)
test("Usable links filtered", len(usable) == 2, f"got {len(usable)}")
test("Quarantined links filtered", len(quarantined) == 2, f"got {len(quarantined)}")

# Event links with quarantine
event_links = get_event_links_canonical(17)  # Battaglie dell'Isonzo
test("Event links has usable_links", "usable_links" in event_links)
test("Event links has quarantined_links", "quarantined_links" in event_links)
test("Event links total > 0", event_links["total"] > 0, f"got {event_links['total']}")
test("Event links all quarantined (no usable)", event_links["usable_count"] == 0, f"got usable={event_links['usable_count']}")

# Record links with quarantine
record_links = get_record_links_canonical(1)
test("Record links has usable_links", "usable_links" in record_links)
test("Record links has quarantined_links", "quarantined_links" in record_links)


# ─── 7. Endpoint info ───────────────────────────────────────────────────────

print("\n=== 7. Endpoint Info ===")

info = get_endpoint_info()
test("Endpoint info has feature_flags", "feature_flags" in info)
test("Endpoint info has endpoints", "endpoints" in info)
test("Endpoint info has quarantine_status", "quarantine_status" in info)
test("Endpoint info lists 4 endpoints", len(info["endpoints"]) == 4, f"got {len(info['endpoints'])}")
test("Quarantine status shows event_links", "event_links" in info["quarantine_status"])
test("Quarantine status shows record_links", "record_links" in info["quarantine_status"])


# ─── Summary ────────────────────────────────────────────────────────────────

print(f"\n{'='*80}")
print(f"V7.3 Phase E Tests: {passed} PASS, {failed} FAIL")
print(f"{'='*80}")

if errors:
    print("\nFailures:")
    for e in errors:
        print(f"  - {e}")

sys.exit(0 if failed == 0 else 1)

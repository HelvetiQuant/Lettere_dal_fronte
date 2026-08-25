"""_test_ussme_viewpoints.py — Test viewpoints v2 with USSME sources."""
import json
import time
import urllib.request

PORT = 8020
EVENT_ID = 16

def main():
    # Wait for server
    for i in range(15):
        try:
            req = urllib.request.Request(
                f"http://127.0.0.1:{PORT}/docs",
                method="GET"
            )
            urllib.request.urlopen(req, timeout=2)
            print("Server ready!")
            break
        except Exception:
            time.sleep(1)
    else:
        print("Server not ready, trying anyway...")

    # Call viewpoints v2
    payload = json.dumps({"event_id": str(EVENT_ID), "use_ai": False}).encode()
    req = urllib.request.Request(
        f"http://127.0.0.1:{PORT}/api/viewpoints/v2/create",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST"
    )

    try:
        resp = urllib.request.urlopen(req, timeout=60)
        data = json.loads(resp.read())
    except Exception as e:
        print(f"ERROR: {e}")
        return

    # Print key metrics
    print("=" * 70)
    print(f"VIEWPOINTS V2 — Event {EVENT_ID} (Caporetto) with USSME sources")
    print("=" * 70)

    perspectives = data.get("perspectives", [])
    print(f"\nPerspectives: {len(perspectives)}")
    for p in perspectives:
        faction = p.get("alignment", "?")
        n_sources = len(p.get("sources", []))
        n_claims = len(p.get("claims", []))
        narrative_len = len(p.get("narrative", ""))
        print(f"  {faction}: {n_sources} sources, {n_claims} claims, narrative={narrative_len} chars")

    # Show source providers per faction
    for p in perspectives:
        faction = p.get("alignment", "?")
        sources = p.get("sources", [])
        providers = {}
        for s in sources:
            prov = s.get("metadata", {}).get("provider", "?")
            providers[prov] = providers.get(prov, 0) + 1
        print(f"\n  {faction} providers: {dict(sorted(providers.items(), key=lambda x: -x[1]))}")

    # Common ground
    cg = data.get("common_ground", {})
    cg_claims = cg.get("claims", []) if isinstance(cg, dict) else []
    cg_narrative = data.get("common_ground_narrative", "")
    print(f"\nCommon Ground: {len(cg_claims)} claims")
    print(f"Common Ground Narrative: {len(cg_narrative)} chars")
    if cg_narrative:
        print(f"  Preview: {cg_narrative[:200]}...")

    # Divergence
    div = data.get("divergences", [])
    div_narrative = data.get("divergence_narrative", "")
    print(f"\nDivergences: {len(div)}")
    print(f"Divergence Narrative: {len(div_narrative)} chars")
    if div_narrative:
        print(f"  Preview: {div_narrative[:200]}...")

    # Omissions
    omissions = data.get("omissions", [])
    om_narrative = data.get("omission_narrative", "")
    print(f"\nOmissions: {len(omissions)}")
    print(f"Omission Narrative: {len(om_narrative)} chars")
    if om_narrative:
        print(f"  Preview: {om_narrative[:200]}...")

    # Show first few claims from each perspective
    for p in perspectives:
        faction = p.get("alignment", "?")
        claims = p.get("claims", [])
        print(f"\n--- {faction} claims (first 5) ---")
        for c in claims[:5]:
            pred = c.get("predicate", "?")
            val = str(c.get("value", "?"))[:60]
            conf = c.get("confidence", 0)
            print(f"  {pred} = {val} (conf={conf})")

    print("\n" + "=" * 70)
    print("DONE")
    print("=" * 70)

if __name__ == "__main__":
    main()

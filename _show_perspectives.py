"""_show_perspectives.py — Print each perspective narrative separately."""
import json
import urllib.request

PORT = 8020

def main():
    payload = json.dumps({"event_id": "16", "use_ai": False}).encode()
    req = urllib.request.Request(
        f"http://127.0.0.1:{PORT}/api/viewpoints/v2/create",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST"
    )
    resp = urllib.request.urlopen(req, timeout=60)
    data = json.loads(resp.read())

    for p in data.get("perspectives", []):
        faction = p.get("alignment", "?")
        n_sources = len(p.get("sources", []))
        n_claims = len(p.get("claims", []))
        print(f"\n{'=' * 70}")
        print(f"PROSPETTIVA: {faction} | {n_sources} fonti | {n_claims} claim")
        print(f"{'=' * 70}")
        print(p.get("narrative", ""))

        # Show all claims
        claims = p.get("claims", [])
        print(f"\n--- CLAIM ({len(claims)}) ---")
        for i, c in enumerate(claims):
            pred = c.get("predicate", "?")
            val = str(c.get("value", "?"))[:80]
            conf = c.get("confidence", 0)
            sources = c.get("source_ids", c.get("sources", []))
            n_src = len(sources) if isinstance(sources, list) else "?"
            print(f"  [{i+1}] {pred} = {val} (conf={conf}, src={n_src})")

        # Show source providers
        sources = p.get("sources", [])
        providers = {}
        for s in sources:
            prov = s.get("metadata", {}).get("provider", "?")
            providers[prov] = providers.get(prov, 0) + 1
        print(f"\n--- PROVIDERS ---")
        for prov, count in sorted(providers.items(), key=lambda x: -x[1]):
            print(f"  {prov}: {count}")

if __name__ == "__main__":
    main()

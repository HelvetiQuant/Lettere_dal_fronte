"""_show_narratives_only.py — Print only narrative text from each perspective."""
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
        print(f">>> PROSPETTIVA {faction} ({n_sources} fonti, {n_claims} claim)")
        print(f"{'=' * 70}")
        print(p.get("narrative", ""))
        print()

    print(f"\n{'=' * 70}")
    print(">>> RICOSTRUZIONE COMUNE")
    print(f"{'=' * 70}")
    print(data.get("common_ground_narrative", ""))

    print(f"\n{'=' * 70}")
    print(">>> DIVERGENZE")
    print(f"{'=' * 70}")
    print(data.get("divergence_narrative", ""))

    print(f"\n{'=' * 70}")
    print(">>> OMISSIONI (primi 3000 char)")
    print(f"{'=' * 70}")
    om = data.get("omission_narrative", "")
    print(om[:3000])
    if len(om) > 3000:
        print(f"\n...[troncato, {len(om)} char totali]")

if __name__ == "__main__":
    main()

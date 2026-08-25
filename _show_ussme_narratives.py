"""_show_ussme_narratives.py — Print full narratives from viewpoints v2."""
import json
import time
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

    print("=" * 80)
    print("CAPARETTO (event_id=16) — NARRATIVE COMPLETE GENERATE DAL BACKEND")
    print("=" * 80)

    # Perspectives
    for p in data.get("perspectives", []):
        faction = p.get("alignment", "?")
        n_sources = len(p.get("sources", []))
        n_claims = len(p.get("claims", []))
        print(f"\n{'#' * 80}")
        print(f"# PROSPETTIVA: {faction} ({n_sources} fonti, {n_claims} claim)")
        print(f"{'#' * 80}")
        narrative = p.get("narrative", "")
        print(narrative)

    # Common Ground
    print(f"\n{'#' * 80}")
    print(f"# RICOSTRUZIONE COMUNE")
    print(f"{'#' * 80}")
    cg = data.get("common_ground_narrative", "")
    print(cg)

    # Divergences
    print(f"\n{'#' * 80}")
    print(f"# DIVERGENZE")
    print(f"{'#' * 80}")
    div = data.get("divergence_narrative", "")
    print(div)

    # Omissions (truncated if too long)
    print(f"\n{'#' * 80}")
    print(f"# OMISSIONI (primi 5000 caratteri)")
    print(f"{'#' * 80}")
    om = data.get("omission_narrative", "")
    if len(om) > 5000:
        print(om[:5000])
        print(f"\n... [TRONCATO — {len(om)} caratteri totali]")
    else:
        print(om)

    print(f"\n{'=' * 80}")
    print("FINE OUTPUT")
    print(f"{'=' * 80}")

if __name__ == "__main__":
    main()

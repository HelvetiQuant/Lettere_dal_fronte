"""_debug_ussme.py — Debug faction alignment in viewpoints v2 response."""
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

    perspectives = data.get("perspectives", [])
    print(f"Perspectives: {len(perspectives)}")
    for i, p in enumerate(perspectives):
        print(f"\n--- Perspective {i} ---")
        print(f"  Keys: {list(p.keys())}")
        # Print all non-list, non-dict fields
        for k, v in p.items():
            if isinstance(v, (str, int, float, bool)):
                print(f"  {k}: {v}")
            elif isinstance(v, list):
                print(f"  {k}: list[{len(v)}]")
            elif isinstance(v, dict):
                print(f"  {k}: dict[{len(v)}]")
        # Show first source
        sources = p.get("sources", [])
        if sources:
            print(f"  First source keys: {list(sources[0].keys())}")
            print(f"  First source metadata: {sources[0].get('metadata', {}).get('provider', 'NONE')}")
            print(f"  First source label: {sources[0].get('label', 'NONE')}")

if __name__ == "__main__":
    main()

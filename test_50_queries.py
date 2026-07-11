"""Test di funzionamento su 50 query casuali partendo da dati reali nel DB.

Testa:
1. /api/search (search_all locale)
2. /api/soldiers/{id}/dashboard (dashboard investigativa)
3. /api/source/search (ricerca federata)
4. /api/providers (lista provider)
5. /api/source/stats (statistiche federation)

Non scarica documenti. Verifica solo che gli endpoint rispondano correttamente.
"""

import json
import random
import sqlite3
import time
import requests
from pathlib import Path

DB_PATH = Path(__file__).parent / "imi_internati.db"
BASE_URL = "http://127.0.0.1:8000"

def get_random_soldiers(n=50):
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        "SELECT id, cognome, nome, luogo_nascita, luogo_internamento, sorte "
        "FROM internati ORDER BY RANDOM() LIMIT ?", (n,)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]

def test_endpoint(method, path, json_body=None, params=None, timeout=15):
    try:
        url = f"{BASE_URL}{path}"
        if method == "GET":
            r = requests.get(url, params=params, timeout=timeout)
        else:
            r = requests.post(url, json=json_body, timeout=timeout)
        if r.status_code == 200:
            return True, r.json(), r.elapsed.total_seconds()
        else:
            return False, {"status": r.status_code, "body": r.text[:200]}, r.elapsed.total_seconds()
    except requests.exceptions.ConnectionError:
        return False, {"error": "server non raggiungibile"}, 0
    except Exception as e:
        return False, {"error": str(e)}, 0

def run_tests():
    soldiers = get_random_soldiers(50)
    if not soldiers:
        print("ERRORE: nessun soldato nel DB")
        return

    print(f"=== TEST 50 QUERY CASUALI SU DATI REALI ===\n")
    print(f"Server: {BASE_URL}")
    print(f"Soldati estratti: {len(soldiers)}\n")

    # Test 0: verifica server attivo
    ok, _, t = test_endpoint("GET", "/api/status")
    if not ok:
        print("SERVER NON ATTIVO — avvia con: uvicorn app:app --reload")
        return
    print(f"Server attivo (risposta in {t:.3f}s)\n")

    results = {
        "search_local": {"ok": 0, "fail": 0, "times": [], "errors": []},
        "dashboard": {"ok": 0, "fail": 0, "times": [], "errors": []},
        "federated": {"ok": 0, "fail": 0, "times": [], "errors": []},
        "providers": {"ok": 0, "fail": 0, "times": [], "errors": []},
        "source_stats": {"ok": 0, "fail": 0, "times": [], "errors": []},
    }

    # Test statici (1 volta)
    print("--- Endpoint statici ---")
    ok, data, t = test_endpoint("GET", "/api/providers")
    results["providers"]["ok" if ok else "fail"] += 1
    results["providers"]["times"].append(t)
    if ok:
        print(f"  /api/providers: OK ({t:.3f}s) — {data.get('count', '?')} provider")
    else:
        print(f"  /api/providers: FAIL — {data}")
        results["providers"]["errors"].append(str(data))

    ok, data, t = test_endpoint("GET", "/api/source/stats")
    results["source_stats"]["ok" if ok else "fail"] += 1
    results["source_stats"]["times"].append(t)
    if ok:
        print(f"  /api/source/stats: OK ({t:.3f}s) — {data.get('total_sources', 0)} fonti, {data.get('providers', 0)} provider")
    else:
        print(f"  /api/source/stats: FAIL — {data}")
        results["source_stats"]["errors"].append(str(data))

    print()

    # Test dinamici (50 query)
    print("--- 50 query dinamiche ---")
    for i, s in enumerate(soldiers):
        query = f"{s['cognome']} {s['nome'] or ''}".strip()
        sid = s["id"]

        # 1. search_all locale
        ok, data, t = test_endpoint("GET", "/api/search", params={"q": query, "limit": 5})
        if ok:
            results["search_local"]["ok"] += 1
            results["search_local"]["times"].append(t)
            n_int = len(data.get("internati", []))
            n_menz = len(data.get("menzioni", []))
            n_dec = len(data.get("decorati", []))
            if i < 5 or not ok:
                print(f"  [{i+1:02d}] search '{query}': OK ({t:.3f}s) — internati={n_int} menzioni={n_menz} decorati={n_dec}")
        else:
            results["search_local"]["fail"] += 1
            results["search_local"]["errors"].append(f"{query}: {data}")
            print(f"  [{i+1:02d}] search '{query}': FAIL — {data}")

        # 2. dashboard soldato
        ok, data, t = test_endpoint("GET", f"/api/soldiers/{sid}/dashboard", timeout=30)
        if ok:
            results["dashboard"]["ok"] += 1
            results["dashboard"]["times"].append(t)
            summ = data.get("summary", {})
            if i < 5 or not ok:
                print(f"       dashboard id={sid}: OK ({t:.3f}s) — local={summ.get('local_count',0)} ext={summ.get('external_count',0)} facts={summ.get('facts_count',0)}")
        else:
            results["dashboard"]["fail"] += 1
            results["dashboard"]["errors"].append(f"id={sid}: {data}")
            print(f"       dashboard id={sid}: FAIL — {data}")

        # 3. ricerca federata (solo prime 10 per non sovraccaricare)
        if i < 10:
            ok, data, t = test_endpoint("POST", "/api/source/search",
                                        json_body={"query": query, "providers": ["nara", "cwgc"]},
                                        timeout=20)
            if ok:
                results["federated"]["ok"] += 1
                results["federated"]["times"].append(t)
                n_res = data.get("count", 0)
                print(f"       federated '{query}': OK ({t:.3f}s) — {n_res} risultati")
            else:
                results["federated"]["fail"] += 1
                results["federated"]["errors"].append(f"{query}: {data}")
                print(f"       federated '{query}': FAIL — {data}")

    # Riepilogo
    print("\n=== RIEPILOGO TEST ===\n")
    print(f"{'Endpoint':<25} {'OK':>5} {'FAIL':>5} {'Avg time':>10} {'Max time':>10}")
    print("-" * 60)
    for name, stats in results.items():
        n_ok = stats["ok"]
        n_fail = stats["fail"]
        times = stats["times"]
        avg = sum(times) / len(times) if times else 0
        mx = max(times) if times else 0
        status = "OK" if n_fail == 0 else "WARN"
        print(f"{name:<25} {n_ok:>5} {n_fail:>5} {avg:>9.3f}s {mx:>9.3f}s  {status}")
        if stats["errors"]:
            for e in stats["errors"][:3]:
                print(f"  ! {e[:120]}")

    total_ok = sum(s["ok"] for s in results.values())
    total_fail = sum(s["fail"] for s in results.values())
    total = total_ok + total_fail
    print(f"\nTOTALE: {total_ok}/{total} passati ({total_ok/total*100:.1f}%)")

    if total_fail > 0:
        print(f"\n{total_fail} fallimenti — vedi errori sopra")

if __name__ == "__main__":
    run_tests()

"""Test diretto (senza server) dei moduli soldier_dashboard e federation."""
import sys
import random
import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).parent / "imi_internati.db"

def get_random_soldiers(n=50):
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        "SELECT id, cognome, nome, luogo_nascita, luogo_internamento, sorte "
        "FROM internati ORDER BY RANDOM() LIMIT ?", (n,)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]

def main():
    print("=== TEST DIRETTO 50 QUERY (senza server HTTP) ===\n")

    # Test 1: federation stats
    print("--- Federation stats ---")
    try:
        from source_providers.federation import get_federation_stats, list_providers
        stats = get_federation_stats()
        providers = list_providers()
        print(f"  Provider registrati: {len(providers)}")
        print(f"  Fonti indicizzate: {stats.get('total_sources', 0)}")
        print(f"  Cache count: {stats.get('cache_count', 0)}")
        print(f"  OK")
    except Exception as e:
        print(f"  FAIL: {e}")
        import traceback; traceback.print_exc()
        return

    # Test 2: soldier dashboard su 50 soldati casuali
    print("\n--- Soldier Dashboard (50 soldati casuali) ---")
    soldiers = get_random_soldiers(50)
    if not soldiers:
        print("  Nessun soldato nel DB")
        return

    from soldier_dashboard import get_soldier_dashboard

    ok_count = 0
    fail_count = 0
    errors = []
    times = []

    import time as tmod

    for i, s in enumerate(soldiers):
        sid = s["id"]
        query = f"{s['cognome']} {s['nome'] or ''}".strip()
        t0 = tmod.time()
        try:
            result = get_soldier_dashboard(sid)
            elapsed = tmod.time() - t0
            times.append(elapsed)
            if result.get("ok"):
                ok_count += 1
                summ = result.get("summary", {})
                if i < 5:
                    print(f"  [{i+1:02d}] id={sid} '{query}': OK ({elapsed:.3f}s) "
                          f"facts={summ.get('facts_count',0)} "
                          f"local={summ.get('local_count',0)} "
                          f"ext={summ.get('external_count',0)} "
                          f"timeline={summ.get('timeline_count',0)} "
                          f"entities={summ.get('entities_count',0)}")
            else:
                fail_count += 1
                errors.append(f"id={sid}: {result.get('error', '?')}")
                if i < 5:
                    print(f"  [{i+1:02d}] id={sid} '{query}': FAIL — {result.get('error')}")
        except Exception as e:
            elapsed = tmod.time() - t0
            fail_count += 1
            errors.append(f"id={sid}: {e}")
            if i < 5:
                print(f"  [{i+1:02d}] id={sid} '{query}': EXCEPTION — {e}")

    avg_t = sum(times) / len(times) if times else 0
    max_t = max(times) if times else 0
    print(f"\n  Dashboard: {ok_count} OK, {fail_count} FAIL, avg={avg_t:.3f}s, max={max_t:.3f}s")
    if errors:
        print(f"  Prime 3 errori:")
        for e in errors[:3]:
            print(f"    ! {e}")

    # Test 3: federated search su 10 query
    print("\n--- Federated Search (10 query, provider nara+cwgc) ---")
    from source_providers.federation import federated_search

    fed_ok = 0
    fed_fail = 0
    fed_errors = []
    fed_times = []

    for i, s in enumerate(soldiers[:10]):
        query = f"{s['cognome']} {s['nome'] or ''}".strip()
        cues = {}
        if s.get("cognome"):
            cues["persona"] = query
        if s.get("luogo_nascita"):
            cues["luogo"] = s["luogo_nascita"]
        t0 = tmod.time()
        try:
            results = federated_search(query, cues=cues, providers=["nara", "cwgc"])
            elapsed = tmod.time() - t0
            fed_times.append(elapsed)
            fed_ok += 1
            n_res = len(results)
            n_err = sum(1 for r in results if "error" in r)
            print(f"  [{i+1:02d}] '{query}': OK ({elapsed:.3f}s) — {n_res} risultati ({n_err} errori provider)")
        except Exception as e:
            elapsed = tmod.time() - t0
            fed_fail += 1
            fed_errors.append(f"{query}: {e}")
            print(f"  [{i+1:02d}] '{query}': EXCEPTION — {e}")

    if fed_times:
        print(f"\n  Federated: {fed_ok} OK, {fed_fail} FAIL, avg={sum(fed_times)/len(fed_times):.3f}s, max={max(fed_times):.3f}s")

    # Test 4: search_all locale (reference)
    print("\n--- Search locale (50 query, reference) ---")
    from database import search_all
    loc_ok = 0
    loc_fail = 0
    for s in soldiers:
        query = f"{s['cognome']} {s['nome'] or ''}".strip()
        try:
            res = search_all(query, limit=5)
            loc_ok += 1
        except Exception as e:
            loc_fail += 1
    print(f"  search_all: {loc_ok} OK, {loc_fail} FAIL")

    # Riepilogo finale
    print("\n=== RIEPILOGO FINALE ===\n")
    print(f"  Federation stats:     OK")
    print(f"  Soldier dashboard:    {ok_count}/50 OK ({ok_count/50*100:.0f}%)")
    print(f"  Federated search:     {fed_ok}/10 OK ({fed_ok/10*100:.0f}%)")
    print(f"  Search locale:        {loc_ok}/50 OK ({loc_ok/50*100:.0f}%)")
    total = 1 + ok_count + fed_ok + loc_ok
    total_fail = fail_count + fed_fail + loc_fail
    print(f"\n  TOTALE: {total}/{total+total_fail} ({total/(total+total_fail)*100:.1f}%)")

if __name__ == "__main__":
    main()

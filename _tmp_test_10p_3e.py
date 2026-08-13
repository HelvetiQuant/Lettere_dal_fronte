"""Test 10 nomi casuali + 3 eventi su pipeline V7."""
import sqlite3, json, time, warnings, logging, random
warnings.filterwarnings("ignore")
logging.disable(logging.WARNING)

DB = "imi_internati.db"
conn = sqlite3.connect(DB)
conn.row_factory = sqlite3.Row

# Pick 2 random names from each of 5 tables
picks = []

tables = [
    ("internati", "SELECT id, cognome, nome FROM internati WHERE cognome IS NOT NULL AND nome IS NOT NULL ORDER BY RANDOM() LIMIT 2"),
    ("lebi_records", "SELECT lebi_id as id, cognome, nome FROM lebi_records WHERE cognome IS NOT NULL AND nome IS NOT NULL ORDER BY RANDOM() LIMIT 2"),
    ("caduti_ministero", "SELECT id, cognome, nome FROM caduti_ministero WHERE cognome IS NOT NULL AND nome IS NOT NULL ORDER BY RANDOM() LIMIT 2"),
    ("decorati_nastroazzurro", "SELECT id, cognome, nome FROM decorati_nastroazzurro WHERE cognome IS NOT NULL AND nome IS NOT NULL ORDER BY RANDOM() LIMIT 2"),
    ("caduti_albooro", "SELECT id, nominativo FROM caduti_albooro WHERE nominativo IS NOT NULL AND nominativo != '' ORDER BY RANDOM() LIMIT 2"),
]

for tbl, query in tables:
    for row in conn.execute(query).fetchall():
        if "nominativo" in row.keys():
            name = row["nominativo"]
        else:
            name = f"{row['cognome']} {row['nome']}"
        picks.append((tbl, row["id"], name))

conn.close()

print("=== 10 NOMI CASUALI ===")
for tbl, rid, name in picks:
    print(f"  [{tbl}] id={rid}: {name}")

# ─── PERSON PIPELINE ───
from unified_orchestrator_v7 import UnifiedResearchOrchestratorV7
orch = UnifiedResearchOrchestratorV7()

out = []
person_results = []

for tbl, rid, name in picks:
    header = f"\n{'#'*100}\n# [{tbl}] {name} (id={rid})\n{'#'*100}\n"
    print(header)
    out.append(header)
    
    t0 = time.time()
    try:
        result = orch.execute(name, intent="PERSON_LOOKUP")
        elapsed = time.time() - t0
        
        errors = result.get("errors", [])
        snapshot = result.get("snapshot")
        report = result.get("report", "")
        obs_count = result.get("observation_count", 0)
        semantic = result.get("semantic_counts", {})
        
        identity = snapshot.get("identity_status", "N/A") if snapshot else "N/A"
        corroboration = snapshot.get("corroboration_status", "N/A") if snapshot else "N/A"
        person_claims = snapshot.get("person_claims", []) if snapshot else []
        war_period = snapshot.get("war_period", "N/A") if snapshot else "N/A"
        cross_war = semantic.get("cross_war_contamination", False)
        
        status = "OK" if len(errors) == 0 else "ERRORS"
        
        summary = f"Status: {status} | Time: {elapsed:.1f}s | Obs: {obs_count} | Identity: {identity} | Corroboration: {corroboration} | Claims: {len(person_claims)} | Cross-war: {cross_war} | Errors: {len(errors)}\n"
        print(summary)
        out.append(summary)
        
        if errors:
            err_text = "\n--- ERRORS ---\n" + "\n".join(f"  {e}" for e in errors[:5]) + "\n"
            print(err_text)
            out.append(err_text)
        
        if report:
            rep_header = f"\n--- REPORT ({len(report)} chars) ---\n"
            print(rep_header + report)
            out.append(rep_header + report)
        
        person_results.append({
            "table": tbl, "name": name, "time": round(elapsed, 1),
            "obs": obs_count, "identity": identity, "claims": len(person_claims),
            "errors": len(errors), "cross_war": cross_war
        })
        
    except Exception as e:
        elapsed = time.time() - t0
        err = f"EXCEPTION: {e}\nTime: {elapsed:.1f}s\n"
        print(err)
        import traceback; traceback.print_exc()
        out.append(err)
        person_results.append({"table": tbl, "name": name, "time": round(elapsed,1), "obs": 0, "identity": "EXCEPTION", "claims": 0, "errors": 1, "cross_war": False})
    
    sep = f"\n{'='*100}\n"
    print(sep)
    out.append(sep)

# ─── EVENT PIPELINE ───
from event_research_engine import research_event

test_events = ["Caporetto", "Isonzo", "Asiago"]
event_results = []

for ev_name in test_events:
    header = f"\n{'#'*100}\n# EVENTO: {ev_name}\n{'#'*100}\n"
    print(header)
    out.append(header)
    
    t0 = time.time()
    try:
        result = research_event(ev_name, mode="specialist")
        elapsed = time.time() - t0
        
        if result.get("ok"):
            provider = result.get("provider", "N/A")
            canonical = result.get("canonical", "N/A")
            sources = result.get("sources", [])
            scheda = result.get("risposta", "")
            jd = result.get("json", {})
            disputed = jd.get("disputed_data", [])
            unverified = jd.get("unverified_claims", [])
            confidence = jd.get("research_status", {}).get("overall_confidence", "N/A")
            
            summary = f"Status: OK | Provider: {provider} | Canonical: {canonical} | Time: {elapsed:.1f}s | Sources: {len(sources)} | Confidence: {confidence} | Disputed: {len(disputed)} | Unverified: {len(unverified)}\n"
            print(summary)
            out.append(summary)
            
            if scheda:
                rep_header = f"\n--- SCHEDA ({len(scheda)} chars) ---\n"
                print(rep_header + scheda)
                out.append(rep_header + scheda)
            
            event_results.append({
                "event": ev_name, "provider": provider, "time": round(elapsed,1),
                "sources": len(sources), "confidence": confidence,
                "disputed": len(disputed), "unverified": len(unverified)
            })
        else:
            err = f"FAILED: {result.get('error', 'Unknown')}\n"
            print(err)
            out.append(err)
            event_results.append({"event": ev_name, "provider": "N/A", "time": round(elapsed,1), "sources": 0, "confidence": "FAIL", "disputed": 0, "unverified": 0})
    except Exception as e:
        elapsed = time.time() - t0
        err = f"EXCEPTION: {e}\n"
        print(err)
        out.append(err)
        event_results.append({"event": ev_name, "provider": "N/A", "time": round(elapsed,1), "sources": 0, "confidence": "EXC", "disputed": 0, "unverified": 0})
    
    sep = f"\n{'='*100}\n"
    print(sep)
    out.append(sep)

# ─── SUMMARY ───
summary_text = f"\n{'='*100}\nSUMMARY — 10 PERSONS\n{'='*100}\n"
summary_text += f"{'#':<3} {'Table':<25} {'Name':<30} {'Time':>6} {'Obs':>5} {'Identity':<20} {'Claims':>7} {'Err':>4} {'XWar':>5}\n"
summary_text += "-"*100 + "\n"
for i, r in enumerate(person_results, 1):
    summary_text += f"{i:<3} {r['table']:<25} {r['name'][:30]:<30} {r['time']:>5.1f}s {r['obs']:>5} {r['identity']:<20} {r['claims']:>7} {r['errors']:>4} {str(r['cross_war']):>5}\n"

ok_persons = sum(1 for r in person_results if r["errors"] == 0)
xwar_persons = sum(1 for r in person_results if r["cross_war"])
summary_text += f"\nPersons OK: {ok_persons}/10 | Cross-war contamination: {xwar_persons}/10\n"

summary_text += f"\n{'='*100}\nSUMMARY — 3 EVENTS\n{'='*100}\n"
summary_text += f"{'Event':<15} {'Provider':<10} {'Time':>6} {'Sources':>8} {'Confidence':<30} {'Disputed':>9} {'Unverified':>11}\n"
summary_text += "-"*100 + "\n"
for r in event_results:
    summary_text += f"{r['event']:<15} {r['provider']:<10} {r['time']:>5.1f}s {r['sources']:>8} {r['confidence'][:30]:<30} {r['disputed']:>9} {r['unverified']:>11}\n"

ok_events = sum(1 for r in event_results if r["confidence"] not in ("FAIL", "EXC"))
summary_text += f"\nEvents OK: {ok_events}/3\n"

print(summary_text)
out.append(summary_text)

with open("_tmp_test13_output.md", "w", encoding="utf-8") as f:
    f.write("\n".join(out))
print(f"\nOutput saved to _tmp_test13_output.md")

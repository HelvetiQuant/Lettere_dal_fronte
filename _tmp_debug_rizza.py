"""Debug RIZZA GIOVANNI — check raw DB data and pipeline claims."""
import sqlite3, json, time
from unified_orchestrator_v7 import UnifiedResearchOrchestratorV7

db = sqlite3.connect('imi_internati.db')
db.row_factory = sqlite3.Row

print("=== decorati_nastroazzurro ===")
rows = db.execute("SELECT * FROM decorati_nastroazzurro WHERE cognome LIKE 'RIZZA%' AND nome LIKE 'GIOVANNI%'").fetchall()
for r in rows:
    print(dict(r))

print("\n=== lebi_records ===")
rows = db.execute("SELECT * FROM lebi_records WHERE cognome LIKE 'RIZZA%' AND nome LIKE 'GIOVANNI%'").fetchall()
for r in rows:
    print(dict(r))

print("\n=== internati ===")
rows = db.execute("SELECT * FROM internati WHERE cognome LIKE 'RIZZA%' AND nome LIKE 'GIOVANNI%'").fetchall()
for r in rows:
    d = dict(r)
    # Print only key fields
    for k in ['cognome','nome','paternita','data_nascita','luogo_nascita','grado','reparto','destinazione','data_decesso','luogo_decesso','causa_decesso','provincia','comune','note']:
        if k in d and d[k]:
            print(f"  {k}: {d[k]}")

print("\n=== caduti_ministero ===")
rows = db.execute("SELECT * FROM caduti_ministero WHERE cognome LIKE 'RIZZA%' AND nome LIKE 'GIOVANNI%'").fetchall()
for r in rows:
    d = dict(r)
    for k in ['cognome','nome','paternita','data_n','luogo_n','provincia_n','grado','corpo','data_d','luogo_d','causa_d','provincia_d']:
        if k in d and d[k]:
            print(f"  {k}: {d[k]}")
    print()

db.close()

print("\n\n=== PIPELINE RUN ===")
orch = UnifiedResearchOrchestratorV7()
t0 = time.time()
result = orch.execute("RIZZA GIOVANNI", intent="PERSON_LOOKUP")
elapsed = time.time() - t0

# Extract snapshot
if hasattr(result, 'evidence_snapshot'):
    snap = result.evidence_snapshot
elif isinstance(result, dict):
    snap = result.get('evidence_snapshot')

if snap:
    print(f"\nIdentity Status: {snap.identity_status}")
    print(f"Corroboration: {snap.corroboration_status}")
    print(f"Person Claims: {len(snap.person_claims)}")
    print(f"Context Claims: {len(snap.context_claims)}")
    print(f"\n=== PERSON CLAIMS (first 20) ===")
    for i, c in enumerate(snap.person_claims[:20]):
        if hasattr(c, '__dict__'):
            print(f"  [{i}] {c.__dict__}")
        else:
            print(f"  [{i}] {c}")

    print(f"\n=== CONTEXT CLAIMS ===")
    for i, c in enumerate(snap.context_claims):
        if hasattr(c, '__dict__'):
            print(f"  [{i}] {c.__dict__}")
        else:
            print(f"  [{i}] {c}")

# Extract narration
if hasattr(result, 'narration_result'):
    nr = result.narration_result
elif isinstance(result, dict):
    nr = result.get('narration_result')

if nr:
    if hasattr(nr, 'answer_markdown'):
        answer = nr.answer_markdown
    else:
        answer = nr.get('answer_markdown', '')
    print(f"\n=== ANSWER ===")
    print(answer)
    print(f"\nElapsed: {elapsed:.1f}s")

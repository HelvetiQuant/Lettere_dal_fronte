"""Technical analysis data gathering."""
import sqlite3
import json

conn = sqlite3.connect("imi_internati.db")
conn.row_factory = sqlite3.Row

# Table counts
tables_info = []
for t, col in [("internati","cognome"),("caduti_albooro","nominativo"),
               ("decorati_nastroazzurro","cognome"),("caduti_cwgc","cognome"),
               ("caduti_ministero","cognome")]:
    try:
        total = conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
        nonempty = conn.execute(f"SELECT COUNT(*) FROM {t} WHERE {col} IS NOT NULL AND {col} != ''").fetchone()[0]
        cols = [d[1] for d in conn.execute(f"PRAGMA table_info({t})").fetchall()]
        tables_info.append({"table": t, "total": total, "nonempty": nonempty, "columns": cols})
    except Exception as e:
        tables_info.append({"table": t, "error": str(e)})

# Check which tables have structured fields
for ti in tables_info:
    if "error" in ti:
        print(f"ERROR: {ti['table']}: {ti['error']}")
        continue
    print(f"\n{ti['table']}: {ti['total']} total, {ti['nonempty']} with name")
    print(f"  Columns: {ti['columns']}")

# Check the 6 zero-claim cases
print("\n\n=== ZERO-CLAIM ANALYSIS ===")
zero_cases = ["GIACOLLO COSIMO", "MURNANE HUGH", "BADELLINO GIACINTO",
              "BARBARINI ANGELO DI PIETRO", "WENSING THEODOOR", "BOVERI GIUSEPPE DI GIOVANNI"]

for name in zero_cases:
    parts = name.split()
    cognome = parts[0]
    nome = " ".join(parts[1:]) if len(parts) > 1 else ""
    print(f"\n--- {name} ---")
    for t in ["internati", "caduti_albooro", "decorati_nastroazzurro", "caduti_cwgc", "caduti_ministero"]:
        try:
            if t == "caduti_albooro":
                r = conn.execute(f"SELECT * FROM {t} WHERE nominativo = ? LIMIT 1", (name,)).fetchone()
            else:
                if nome:
                    r = conn.execute(f"SELECT * FROM {t} WHERE cognome = ? AND nome = ? LIMIT 1", (cognome, nome)).fetchone()
                else:
                    r = conn.execute(f"SELECT * FROM {t} WHERE cognome = ? LIMIT 1", (cognome,)).fetchone()
            if r:
                d = dict(r)
                nonempty = {k: v for k, v in d.items() if v is not None and str(v).strip() and str(v).strip() != "-"}
                print(f"  {t}: found (id={d.get('id')}) fields={list(nonempty.keys())}")
            else:
                # Try surname-only
                if t != "caduti_albooro":
                    r2 = conn.execute(f"SELECT * FROM {t} WHERE cognome = ? LIMIT 1", (cognome,)).fetchone()
                    if r2:
                        d = dict(r2)
                        print(f"  {t}: surname-only match (nome={d.get('nome','')})")
                    else:
                        print(f"  {t}: no match")
                else:
                    print(f"  {t}: no match")
        except Exception as e:
            print(f"  {t}: error {e}")

# Claim extraction filter check
print("\n\n=== _stage_extract_person_claims TABLE FILTER ===")
print("Currently filtered tables: internati, caduti_albooro, decorati_nastroazzurro, caduti_cwgc")
print("NOT filtered: caduti_ministero")

# Check caduti_ministero columns
try:
    cols = [d[1] for d in conn.execute("PRAGMA table_info(caduti_ministero)").fetchall()]
    print(f"\ncaduti_ministero columns: {cols}")
except:
    print("\ncaduti_ministero: table not found")

# Check caduti_cwgc columns
try:
    cols = [d[1] for d in conn.execute("PRAGMA table_info(caduti_cwgc)").fetchall()]
    print(f"caduti_cwgc columns: {cols}")
except:
    print("caduti_cwgc: table not found")

# Check decorati_nastroazzurro columns
try:
    cols = [d[1] for d in conn.execute("PRAGMA table_info(decorati_nastroazzurro)").fetchall()]
    print(f"decorati_nastroazzurro columns: {cols}")
except:
    print("decorati_nastroazzurro: table not found")

# Check caduti_albooro columns
try:
    cols = [d[1] for d in conn.execute("PRAGMA table_info(caduti_albooro)").fetchall()]
    print(f"caduti_albooro columns: {cols}")
except:
    print("caduti_albooro: table not found")

conn.close()

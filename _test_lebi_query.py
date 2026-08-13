"""Quick check: are LeBI records being queried by the pipeline?"""
import sqlite3

conn = sqlite3.connect("imi_internati.db")
conn.row_factory = sqlite3.Row

# Check a few names
names = [("FERRARI", "PIETRO"), ("MILANI", "LELIO FRANCESCO"), ("POGGIALI", "ROBERTO"),
         ("PIETRAFESA", "GERARDO"), ("FOLGORI", "ANDREA")]

for cognome, nome in names:
    exact = conn.execute(
        "SELECT COUNT(*) as c FROM lebi_records WHERE cognome = ? AND nome = ?",
        (cognome, nome)
    ).fetchone()["c"]
    surname = conn.execute(
        "SELECT COUNT(*) as c FROM lebi_records WHERE cognome = ?",
        (cognome,)
    ).fetchone()["c"]
    sample = conn.execute(
        "SELECT cognome, nome, grado, sorte FROM lebi_records WHERE cognome = ? LIMIT 3",
        (cognome,)
    ).fetchall()
    print(f"\n{cognome} {nome}: exact={exact}, surname_only={surname}")
    for s in sample:
        print(f"  {s['cognome']} {s['nome']} | {s['grado']} | {s['sorte']}")

conn.close()

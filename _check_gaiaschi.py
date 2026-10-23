"""Diagnostic: check Gaiaschi record — import-safe, read-only.

All work is inside main(). Importing this module has zero side effects.
"""
import sqlite3, json
import os

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "imi_internati.db")


def main():
    conn = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row

    print("=== RECORD GAIASCHI ===")
    rows = conn.execute("SELECT * FROM internati WHERE cognome LIKE '%Gaiaschi%'").fetchall()
    for r in rows:
        print(json.dumps(dict(r), indent=2, default=str, ensure_ascii=False))

    print("\n=== TIMELINE/DASHBOARD DATA ===")
    tables = [r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()]
    print("Tables:", [t for t in tables if 'time' in t.lower() or 'dash' in t.lower() or 'dossier' in t.lower() or 'soldier' in t.lower()])

    if 'record_links' in tables:
        for r in rows:
            links = conn.execute("SELECT * FROM record_links WHERE from_table='internati' AND from_id=?", (r['id'],)).fetchall()
            print(f"\nrecord_links for internati id={r['id']}:")
            for l in links:
                print(f"  {dict(l)}")

    if 'entita' in tables:
        for r in rows:
            ents = conn.execute("SELECT * FROM entita WHERE fonte_tabella='internati' AND fonte_id=?", (r['id'],)).fetchall()
            print(f"\nentita for internati id={r['id']}:")
            for e in ents:
                print(f"  {dict(e)}")

    conn.close()


if __name__ == "__main__":
    main()

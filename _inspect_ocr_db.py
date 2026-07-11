import sqlite3
conn = sqlite3.connect('import_ocr_lettere/ocr_lettere.db')
tables = conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
for t in tables:
    print(f"TABLE: {t[0]}")
    for c in conn.execute(f"PRAGMA table_info({t[0]})").fetchall():
        print(f"  {c[1]} {c[2]}")
    print()
conn.close()

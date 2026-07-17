import sqlite3
conn = sqlite3.connect("imi_internati.db")
conn.row_factory = sqlite3.Row
print("=== SCHEMI TABELLE ===")
for tab in ["caduti_albooro", "decorati_nastroazzurro", "archivio_documenti", "collegamenti", "entita", "fonti_indice"]:
    print(f"\n--- {tab} ---")
    for r in conn.execute(f"PRAGMA table_info({tab})").fetchall():
        print(f"  {r['name']:30s} {r['type']}")
    print(f"  Rows: {conn.execute(f'SELECT COUNT(*) FROM {tab}').fetchone()[0]}")
conn.close()

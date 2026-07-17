import sqlite3
conn = sqlite3.connect("imi_internati.db")
print("=== STATO DB ===")
print(f"fonti_indice:      {conn.execute('SELECT COUNT(*) FROM fonti_indice').fetchone()[0]}")
print(f"collegamenti:      {conn.execute('SELECT COUNT(*) FROM collegamenti').fetchone()[0]}")
print(f"archivio_documenti: {conn.execute('SELECT COUNT(*) FROM archivio_documenti').fetchone()[0]}")
print()
print("--- archivio_documenti per provider ---")
for r in conn.execute("SELECT provider, COUNT(*) FROM archivio_documenti GROUP BY provider ORDER BY 2 DESC").fetchall():
    print(f"  {r[0]:30s} {r[1]:>6}")
print()
print("--- archivio_documenti per tipo ---")
for r in conn.execute("SELECT doc_type, COUNT(*) FROM archivio_documenti GROUP BY doc_type ORDER BY 2 DESC").fetchall():
    print(f"  {r[0] or '(null)':15s} {r[1]:>6}")
print()
print("--- fonti_indice per archivio (top 20) ---")
for r in conn.execute("SELECT archivio, COUNT(*) as n FROM fonti_indice GROUP BY archivio ORDER BY n DESC LIMIT 20").fetchall():
    print(f"  {r[0] or '(null)':50s} {r[1]:>6}")
print()
# Tabelle dati 1GM
for tab in ["caduti_albooro", "decorati_nastroazzurro", "caduti_cwgc"]:
    try:
        n = conn.execute(f"SELECT COUNT(*) FROM {tab}").fetchone()[0]
        print(f"{tab}: {n}")
    except:
        print(f"{tab}: N/A")
print()
# Collegamenti per tabella
print("--- collegamenti per tabella (top 10) ---")
for r in conn.execute("SELECT tabella_origine, COUNT(*) as n FROM collegamenti GROUP BY tabella_origine ORDER BY n DESC LIMIT 10").fetchall():
    print(f"  {r[0]:25s} {r[1]:>10}")
conn.close()

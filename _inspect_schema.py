import sqlite3, json

DB = "imi_internati.db"
conn = sqlite3.connect(DB)
conn.row_factory = sqlite3.Row

tables = [r[0] for r in conn.execute(
    "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
).fetchall()]

for t in tables:
    cols = conn.execute(f"PRAGMA table_info({t})").fetchall()
    cnt = conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
    print(f"\n--- {t} ({cnt} rows) ---")
    for c in cols:
        print(f"  {c['name']:30s} {c['type']:15s}")

print("\n=== caduti_albooro sample ===")
for r in conn.execute("SELECT * FROM caduti_albooro LIMIT 2").fetchall():
    print(json.dumps(dict(r), ensure_ascii=False, indent=2))

print("\n=== archivio_documenti columns ===")
cols = [c['name'] for c in conn.execute("PRAGMA table_info(archivio_documenti)").fetchall()]
print(cols)

print("\n=== archivio_documenti sample ===")
for r in conn.execute("SELECT * FROM archivio_documenti LIMIT 3").fetchall():
    print(json.dumps(dict(r), ensure_ascii=False, indent=2))

print("\n=== decorati_nastroazzurro columns ===")
cols = [c['name'] for c in conn.execute("PRAGMA table_info(decorati_nastroazzurro)").fetchall()]
print(cols)

print("\n=== decorati sample ===")
for r in conn.execute("SELECT * FROM decorati_nastroazzurro LIMIT 2").fetchall():
    print(json.dumps(dict(r), ensure_ascii=False, indent=2))

print("\n=== Top 30 luoghi morte ===")
for r in conn.execute(
    "SELECT luogo_morte, COUNT(*) as n FROM caduti_albooro "
    "WHERE luogo_morte IS NOT NULL AND luogo_morte != '' AND luogo_morte != '-' "
    "GROUP BY luogo_morte ORDER BY n DESC LIMIT 30"
).fetchall():
    print(f"  {r['luogo_morte']:40s} {r['n']:>6}")

print("\n=== archivio_documenti: distinct providers ===")
for r in conn.execute(
    "SELECT provider, doc_type, COUNT(*) as n FROM archivio_documenti GROUP BY provider, doc_type ORDER BY n DESC LIMIT 20"
).fetchall():
    print(f"  [{r['provider']:30s}] {r['doc_type']:20s} n={r['n']}")

print("\n=== fonti_indice: distinct archivi ===")
for r in conn.execute(
    "SELECT archivio, tipo_fonte, COUNT(*) as n FROM fonti_indice GROUP BY archivio, tipo_fonte ORDER BY n DESC LIMIT 20"
).fetchall():
    print(f"  [{r['archivio']:15s}] {r['tipo_fonte']:25s} n={r['n']}")

print("\n=== Search 'Caporetto' in caduti ===")
cnt = conn.execute("SELECT COUNT(*) FROM caduti_albooro WHERE luogo_morte LIKE '%Caporetto%' OR luogo_morte LIKE '%caporetto%'").fetchone()[0]
print(f"  caduti with luogo_morte containing Caporetto: {cnt}")

print("\n=== Search 'Isonzo' in caduti ===")
cnt = conn.execute("SELECT COUNT(*) FROM caduti_albooro WHERE luogo_morte LIKE '%Isonzo%'").fetchone()[0]
print(f"  caduti with Isonzo: {cnt}")

print("\n=== Search 'Caporetto' in archivio_documenti ===")
for col in ['title', 'titolo', 'description', 'subject', 'name', 'text']:
    try:
        cnt = conn.execute(f"SELECT COUNT(*) FROM archivio_documenti WHERE {col} LIKE '%Caporetto%'").fetchone()[0]
        if cnt > 0:
            print(f"  archivio_documenti.{col} with Caporetto: {cnt}")
    except:
        pass

print("\n=== Search 'Caporetto' in fonti_indice ===")
for col in ['titolo', 'soggetti_collegati', 'luogo', 'note']:
    try:
        cnt = conn.execute(f"SELECT COUNT(*) FROM fonti_indice WHERE {col} LIKE '%Caporetto%'").fetchone()[0]
        if cnt > 0:
            print(f"  fonti_indice.{col} with Caporetto: {cnt}")
    except:
        pass

conn.close()

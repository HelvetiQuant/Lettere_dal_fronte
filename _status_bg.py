from database import get_conn
conn = get_conn()

print("=== STATUS ACQUISIZIONE DATI IN BACKGROUND ===\n")

# CWGC
n_cwgc = conn.execute("SELECT COUNT(*) FROM caduti_cwgc").fetchone()[0]
last_cwgc = conn.execute("SELECT elaborato_il FROM caduti_cwgc ORDER BY elaborato_il DESC LIMIT 1").fetchone()
ultimo_cwgc = last_cwgc[0] if last_cwgc else "N/A"
print(f"CWGC WW2: {n_cwgc:,} record (target ~1.76M)")
by_nat = conn.execute("SELECT nationality, COUNT(*) as n FROM caduti_cwgc GROUP BY nationality ORDER BY n DESC LIMIT 10").fetchall()
for r in by_nat:
    print(f"  {r[0]}: {r[1]:,}")
print(f"  ultimo inserimento: {ultimo_cwgc}")

# NARA Catalog
n_nara = conn.execute("SELECT COUNT(*) FROM documenti_nara_catalog").fetchone()[0]
last_nara = conn.execute("SELECT elaborato_il FROM documenti_nara_catalog ORDER BY elaborato_il DESC LIMIT 1").fetchone()
ultimo_nara = last_nara[0] if last_nara else "N/A"
print(f"\nNARA Catalog AAR Italy: {n_nara:,} record")
print(f"  ultimo inserimento: {ultimo_nara}")
types = conn.execute("SELECT document_type, COUNT(*) FROM documenti_nara_catalog GROUP BY document_type ORDER BY 2 DESC").fetchall()
for r in types:
    print(f"  {r[0]}: {r[1]}")

# NARA T315
n_t315 = conn.execute("SELECT COUNT(*) FROM documenti_nara_t315").fetchone()[0]
print(f"\nNARA T315 OCR: {n_t315:,} frame (completato)")

# Archivio fonti
n_af = conn.execute("SELECT COUNT(*) FROM archivio_fonti").fetchone()[0]
ocr_dist = conn.execute("SELECT ocr_status, COUNT(*) FROM archivio_fonti GROUP BY ocr_status").fetchall()
print(f"\nArchivio fonti: {n_af:,} documenti")
for r in ocr_dist:
    print(f"  {r[0]}: {r[1]}")

# Entita e collegamenti (linker)
ne = conn.execute("SELECT COUNT(*) FROM entita").fetchone()[0]
nc = conn.execute("SELECT COUNT(*) FROM collegamenti").fetchone()[0]
print(f"\nLinker: entita={ne:,}  collegamenti={nc:,}")

# Memory trace
try:
    n_trace = conn.execute("SELECT COUNT(*) FROM memory_trace").fetchone()[0]
    n_cloud = conn.execute("SELECT COUNT(*) FROM memory_trace WHERE used_cloud_ai=1").fetchone()[0]
    print(f"\nMemory Router: {n_trace} query tracciate, {n_cloud} con Perplexity")
except Exception:
    pass

# Progress log
print("\nProgress PDF extractor (ultimi 12):")
rows = conn.execute(
    "SELECT lettera, total_pages, processed_pages, status, started_at FROM progress ORDER BY started_at DESC LIMIT 12"
).fetchall()
for r in rows:
    tot = str(r[1]) if r[1] else "?"
    ts = str(r[4])[:19] if r[4] else "?"
    print(f"  [{ts}] lettera={r[0]}: {r[2]}/{tot} pagine ({r[3]})")

conn.close()

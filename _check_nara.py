"""Analisi frame NARA: confronta immagini vs DB"""
from pathlib import Path
from database import get_conn

IMAGES_DIR = Path(r"C:\Users\eryma\Downloads\T315_R1299_extracted\T315 R1299")
SKIP_FRAMES = {1, 2, 3}

images = sorted(IMAGES_DIR.glob("*.jpg"))
all_frames = {int(p.stem) for p in images if int(p.stem) not in SKIP_FRAMES}
print(f"Immagini totali: {len(images)}, da processare (skip 1-3): {len(all_frames)}")

conn = get_conn()
db_frames = {r[0] for r in conn.execute("SELECT frame FROM documenti_nara_t315").fetchall()}
print(f"Frame nel DB: {len(db_frames)}")

missing = sorted(all_frames - db_frames)
print(f"Frame MANCANTI: {len(missing)}")
if missing:
    print(f"  Primi 20: {missing[:20]}")
    print(f"  Ultimi 20: {missing[-20:]}")

extra = sorted(db_frames - all_frames)
print(f"Frame nel DB ma non nelle immagini: {len(extra)}")
if extra:
    print(f"  {extra[:10]}")

# Analisi qualità: frame con errore parsing
err_frames = conn.execute(
    "SELECT frame, note FROM documenti_nara_t315 WHERE note LIKE '%Errore parsing%'"
).fetchall()
print(f"\nFrame con 'Errore parsing JSON': {len(err_frames)}")
for f in err_frames[:10]:
    print(f"  frame {f[0]}: {f[1][:80]}")

# Distribuzione per tipo
print("\nDistribuzione per tipo_documento:")
for r in conn.execute("SELECT tipo_documento, COUNT(*) as n FROM documenti_nara_t315 GROUP BY tipo_documento ORDER BY n DESC").fetchall():
    print(f"  {r[0] or '(null)'}: {r[1]}")

conn.close()

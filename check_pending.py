import sqlite3
conn = sqlite3.connect('imi_internati.db')
c = conn.cursor()

# Progress entries not done
c.execute("SELECT * FROM progress WHERE status != 'done' ORDER BY lettera")
rows = c.fetchall()
print("=== Progress non completati ===")
for r in rows:
    print(f"  {r[0]}: {r[3]} (pag {r[2]}/{r[1]})")

# Check fondi in DB vs progress
c.execute("SELECT codice, file_pdf, schede, menzioni FROM fondi_archivistici ORDER BY codice")
fondi = c.fetchall()
print(f"\n=== Fondi in DB: {len(fondi)} ===")

# Get all fondo progress keys
c.execute("SELECT lettera FROM progress WHERE lettera LIKE 'FONDO:%'")
done_fondi = set(r[0].replace('FONDO:', '') for r in c.fetchall())
print(f"Fondi con progress: {len(done_fondi)}")

# Check which fondi PDFs exist on disk but not in progress
import os
pdf_dir = "pdf_fondi"
if os.path.isdir(pdf_dir):
    pdfs = [f for f in os.listdir(pdf_dir) if f.endswith('.pdf')]
    print(f"\nPDF fondi su disco: {len(pdfs)}")
    for p in sorted(pdfs):
        key = f"FONDO:{p}"
        c.execute("SELECT status FROM progress WHERE lettera=?", (key,))
        r = c.fetchone()
        status = r[0] if r else "NON INIZIATO"
        print(f"  {p}: {status}")

# Check CWGC target
c.execute("SELECT COUNT(*) FROM caduti_cwgc")
cwgc = c.fetchone()[0]
print(f"\nCWGC: {cwgc:,} (target ~1.76M)")

# Check NARA
c.execute("SELECT COUNT(*) FROM documenti_nara_t315")
nara_t = c.fetchone()[0]
c.execute("SELECT COUNT(*) FROM documenti_nara_catalog")
nara_c = c.fetchone()[0]
print(f"NARA T315: {nara_t:,}, Catalog: {nara_c:,}")

conn.close()

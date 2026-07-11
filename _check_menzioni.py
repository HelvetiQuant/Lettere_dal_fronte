import sqlite3
conn = sqlite3.connect('imi_internati.db')
c = conn.cursor()

# Menzioni per file PDF
c.execute("SELECT file_pdf, COUNT(*) as n FROM menzioni GROUP BY file_pdf ORDER BY n DESC LIMIT 20")
print("=== Menzioni per PDF (top 20) ===")
for r in c.fetchall():
    print(f"  {r[0]}: {r[1]} menzioni")

# Totale menzioni
c.execute("SELECT COUNT(*) FROM menzioni")
print(f"\nTotale menzioni: {c.fetchone()[0]:,}")

# Fondi con 0 menzioni
c.execute("""
    SELECT f.file_pdf, f.pagina, SUBSTR(f.raw_text, 1, 200) as txt
    FROM fondi_archivistici f
    WHERE f.file_pdf = 'G33.pdf'
    LIMIT 3
""")
print("\n=== G33.pdf - testo estratto (prime 3 pagine) ===")
for r in c.fetchall():
    print(f"  Pag {r[1]}: {r[2][:150]}...")

# Conta fondi per G33
c.execute("SELECT COUNT(*) FROM fondi_archivistici WHERE file_pdf='G33.pdf'")
print(f"\nG33.pdf: {c.fetchone()[0]} schede/fondi estratti")

# Conta menzioni per G33
c.execute("SELECT COUNT(*) FROM menzioni WHERE file_pdf='G33.pdf'")
print(f"G33.pdf: {c.fetchone()[0]} menzioni")

conn.close()

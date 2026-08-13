"""Analyze internati raw_text to extract missing structured fields."""
import sqlite3, re, warnings, logging
from collections import Counter
warnings.filterwarnings("ignore")
logging.disable(logging.WARNING)

db = sqlite3.connect('imi_internati.db')
db.row_factory = sqlite3.Row

# Check raw_text coverage
total = db.execute("SELECT COUNT(*) as c FROM internati").fetchone()['c']
has_raw = db.execute("SELECT COUNT(*) as c FROM internati WHERE raw_text IS NOT NULL AND raw_text != ''").fetchone()['c']
print(f"Total internati: {total}")
print(f"With raw_text: {has_raw} ({has_raw*100//total}%)")

# Sample raw_text to understand structure
print("\n=== SAMPLE RAW_TEXT (5 records) ===")
for r in db.execute("SELECT id, cognome, nome, raw_text FROM internati WHERE raw_text IS NOT NULL AND raw_text != '' LIMIT 5").fetchall():
    print(f"\n--- id={r['id']}: {r['cognome']} {r['nome']} ---")
    print(r['raw_text'][:500])

# Check what structured fields are missing but might be in raw_text
print("\n\n=== FIELD COVERAGE ANALYSIS ===")
fields = ['data_nascita', 'luogo_nascita', 'grado', 'reparto', 'arma', 
          'luogo_cattura', 'data_cattura', 'matricola', 'arbeitskommando', 'mansione']
for f in fields:
    has = db.execute(f"SELECT COUNT(*) as c FROM internati WHERE {f} IS NOT NULL AND {f} != ''").fetchone()['c']
    print(f"  {f}: {has}/{total} ({has*100//total}%)")

# Check if raw_text contains grado patterns
print("\n=== GRADO PATTERNS IN RAW_TEXT ===")
grado_patterns = [
    r'(Soldato|Sold\.|Sld\.)',
    r'(Caporale|Cap\.|Cpl\.)',
    r'(Sergente|Serg\.|Sgt\.)',
    r'(Tenente|Ten\.)',
    r'(Sottotenente|Sottoten\.)',
    r'(Capitano|Cap\.)',
    r'(Maggiore|Magg\.)',
    r'(Colonnello|Col\.)',
    r'(Aviere|Av\.)',
    r'(Marò|Marinaio)',
    r'(Artigliere|Art\.)',
    r'(Bersagliere|Bers\.)',
    r'(Alpino|Alp\.)',
    r'(Fanteria|Ftr\.)',
    r'(Genio|Gen\.)',
]

# Sample 1000 records with raw_text but no grado
sample = db.execute("""
    SELECT id, raw_text FROM internati 
    WHERE (grado IS NULL OR grado = '') AND raw_text IS NOT NULL AND raw_text != ''
    LIMIT 1000
""").fetchall()

grado_found = Counter()
for r in sample:
    text = r['raw_text']
    for pattern in grado_patterns:
        m = re.search(pattern, text, re.IGNORECASE)
        if m:
            grado_found[m.group(1)] += 1
            break

print(f"  Sample size: {len(sample)}")
print(f"  Grado found in raw_text: {sum(grado_found.values())}")
for g, c in grado_found.most_common():
    print(f"    {g}: {c}")

# Check for date patterns (birth dates)
print("\n=== DATE PATTERNS IN RAW_TEXT ===")
date_patterns = [
    (r'nato\s+(?:il\s+)?(\d{1,2}[-/]\d{1,2}[-/]\d{4})', 'nato_il'),
    (r'nato\s+a\s+(\w+)', 'nato_a'),
    (r'(\d{1,2}[-/]\d{1,2}[-/]\d{4})', 'any_date'),
    (r'catturato\s+(?:il\s+)?(\d{1,2}[-/]\d{1,2}[-/]\d{4})', 'catturato'),
]

for pattern, name in date_patterns:
    found = 0
    for r in sample:
        if re.search(pattern, r['raw_text'], re.IGNORECASE):
            found += 1
    print(f"  {name}: {found}/{len(sample)}")

# Check for reparto patterns
print("\n=== REPARTO PATTERNS IN RAW_TEXT ===")
reparto_patterns = [
    r'(\d+\s*Rgt\.\s*\w+)',
    r'(\d+\s*Reggimento\s*\w+)',
    r'(\d+\s*Battaglione\s*\w+)',
    r'(\d+\s*Compagnia\s*\w+)',
    r'(Dep\.\s*\d+\s*Rgt\.)',
]
reparto_found = 0
for r in sample:
    for p in reparto_patterns:
        if re.search(p, r['raw_text'], re.IGNORECASE):
            reparto_found += 1
            break
print(f"  Reparto found: {reparto_found}/{len(sample)}")

db.close()

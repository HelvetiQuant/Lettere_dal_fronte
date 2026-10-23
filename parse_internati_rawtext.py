"""Parse internati raw_text (OCR pages) to extract per-record structured fields.

The raw_text is a full OCR page shared by all records on that page.
Each record starts with "COGNOME Nome" followed by lines with details.
We parse: birth_place, death_date, death_cause, burial_place, residence, capture info.
"""
import sqlite3, re, time, warnings, logging
from collections import defaultdict
warnings.filterwarnings("ignore")
logging.disable(logging.WARNING)

db = sqlite3.connect('imi_internati.db')
db.row_factory = sqlite3.Row
db.execute("PRAGMA journal_mode=WAL")

# ─── Step 1: Group records by raw_text (page) ───────────────────────────────
print("=== STEP 1: Group records by page ===")
t0 = time.time()

rows = db.execute("""
    SELECT id, cognome, nome, raw_text, data_nascita, luogo_nascita, 
           grado, reparto, arma, luogo_internamento, sorte, residenza,
           luogo_cattura, data_cattura
    FROM internati 
    WHERE raw_text IS NOT NULL AND raw_text != ''
""").fetchall()

# Group by raw_text hash (page)
pages = defaultdict(list)
for r in rows:
    pages[r['raw_text']].append(r)

print(f"  Records with raw_text: {len(rows)}")
print(f"  Unique pages: {len(pages)}")
print(f"  Avg records/page: {len(rows)/len(pages):.1f}")
print(f"  Time: {time.time()-t0:.1f}s")

# ─── Step 2: Parse each page to extract per-record data ─────────────────────
print("\n=== STEP 2: Parse pages for per-record fields ===")
t0 = time.time()

def parse_page(raw_text):
    """Parse a page of OCR text and return list of (name, details_text)."""
    # Split into lines
    lines = raw_text.split('\n')
    
    # Find record boundaries: lines that look like "COGNOME Nome" (all caps cognome)
    records = []
    current_name = None
    current_lines = []
    
    for i, line in enumerate(lines):
        line_stripped = line.strip()
        if not line_stripped:
            continue
        
        # Check if this line is a name (starts with uppercase, no special chars except spaces)
        # Names are like "ALTA Antonio" or "AMEDEO Agostino" or "ARMUNISCO Vincenzo"
        # They don't start with +, (, #, digits, or lowercase
        if (line_stripped[0].isupper() and 
            not line_stripped.startswith('+') and 
            not line_stripped.startswith('(') and
            not line_stripped.startswith('#') and
            not line_stripped[0].isdigit() and
            not line_stripped.startswith('Bolzano') and
            not line_stripped.startswith('F.') and
            not line_stripped.startswith('F.n') and
            len(line_stripped) > 3 and
            not line_stripped.endswith('.') and
            ',' not in line_stripped.split()[0]  # First word has no comma
            ):
            # Save previous record
            if current_name:
                records.append((current_name, '\n'.join(current_lines)))
            current_name = line_stripped
            current_lines = []
        else:
            if current_name:
                current_lines.append(line_stripped)
    
    # Save last record
    if current_name:
        records.append((current_name, '\n'.join(current_lines)))
    
    return records

def extract_fields(details_text):
    """Extract structured fields from the details text following a name."""
    fields = {}
    text = details_text.replace('\n', ' ').replace('- ', '').strip()
    
    # Birth place: pattern "+City, ..." or "+City (note) ..."
    m = re.match(r'\+([^,\-.]+?)(?:[,\-.](?:\s|$))', text)
    if m:
        birth_place = m.group(1).strip()
        if len(birth_place) > 2 and len(birth_place) < 50:
            fields['birth_place'] = birth_place
    
    # Death date: "Morto il DD-MM-YYYY" or "Morto il DD-M-YYYY"
    m = re.search(r'[Mm]orto\s+(?:il\s+)?(\d{1,2}[-/]\d{1,2}[-/]\d{4})', text)
    if m:
        fields['death_date'] = m.group(1).replace('/', '-')
    
    # Death cause: "per X" or "di X" after death
    m = re.search(r'[Mm]orto\s+(?:il\s+)?(?:\d{1,2}[-/]\d{1,2}[-/]\d{4})?\s*(?:per|di)\s+([^.]+?)(?:\.|,|al|nel|sepolto|$)', text)
    if m:
        cause = m.group(1).strip().rstrip('.,')
        if len(cause) > 2 and len(cause) < 80:
            fields['death_cause'] = cause
    
    # Death place: "al X" or "nel X" after death
    m = re.search(r'(?:al|nel)\s+([a-zA-Z][^.]+?)(?:\.|,|sepolto|$)', text)
    if m:
        place = m.group(1).strip().rstrip('.,')
        if len(place) > 2 and len(place) < 80 and 'sepolto' not in place.lower():
            fields['death_place'] = place
    
    # Burial place: "sepolto nel cimitero di X" or "sepolto a X"
    m = re.search(r'sepolto\s+(?:nel\s+cimitero\s+di\s+|a\s+|nel\s+)([^.\-]+?)(?:\.|-|$)', text)
    if m:
        burial = m.group(1).strip().rstrip('.,')
        if len(burial) > 2 and len(burial) < 80:
            fields['burial_place'] = burial
    
    # Residence: pattern in parentheses "(Name, City, address)"
    m = re.search(r'\(([^)]+,\s*[^)]+)\)', text)
    if m:
        residence = m.group(1).strip()
        if len(residence) > 5 and len(residence) < 100:
            fields['residence'] = residence
    
    # Capture: "catturato il DD-MM-YYYY" or "catturato a X"
    m = re.search(r'catturato\s+(?:il\s+)?(\d{1,2}[-/]\d{1,2}[-/]\d{4})', text, re.IGNORECASE)
    if m:
        fields['capture_date'] = m.group(1).replace('/', '-')
    
    m = re.search(r'catturato\s+a\s+([^.\-]+?)(?:\.|-|il|$)', text, re.IGNORECASE)
    if m:
        cap_place = m.group(1).strip().rstrip('.,')
        if len(cap_place) > 2 and len(cap_place) < 50:
            fields['capture_place'] = cap_place
    
    # Grado: look for military rank
    grado_patterns = [
        (r'\b(Soldato|Sld\.?)\b', 'Soldato'),
        (r'\b(Caporale|Cpl\.?|Cap\.)\b', 'Caporale'),
        (r'\b(Sergente|Serg\.?)\b', 'Sergente'),
        (r'\b(Tenente|Ten\.?)\b', 'Tenente'),
        (r'\b(Sottotenente|Sottoten\.?)\b', 'Sottotenente'),
        (r'\b(Capitano|Cap\.)\b', 'Capitano'),
        (r'\b(Maggiore|Magg\.?)\b', 'Maggiore'),
        (r'\b(Colon(n)?ello|Col\.?)\b', 'Colonnello'),
        (r'\b(Aviere|Av\.?)\b', 'Aviere'),
    ]
    for pattern, rank in grado_patterns:
        if re.search(pattern, text):
            fields['grado'] = rank
            break
    
    return fields

# Parse all pages and match to records
updates = []  # (id, field, value)
stats = defaultdict(int)
total_records_parsed = 0

for page_text, page_records in pages.items():
    parsed = parse_page(page_text)
    
    # Build index of parsed records by normalized name
    parsed_index = {}
    for name, details in parsed:
        # Normalize: uppercase, remove extra spaces
        norm = ' '.join(name.upper().split())
        parsed_index[norm] = details
    
    # Match each internati record to parsed record
    for r in page_records:
        rname = f"{r['cognome']} {r['nome']}".strip().upper()
        rname_clean = ' '.join(rname.split())
        
        # Try exact match
        details = parsed_index.get(rname_clean)
        
        # Try with just cognome + first nome
        if not details and r['nome']:
            rname_short = f"{r['cognome']} {r['nome'].split()[0]}".strip().upper()
            rname_short = ' '.join(rname_short.split())
            details = parsed_index.get(rname_short)
        
        if not details:
            # Try fuzzy: find parsed name that starts with cognome
            for pname in parsed_index:
                if pname.startswith(r['cognome'].upper() + ' '):
                    details = parsed_index[pname]
                    break
        
        if not details:
            stats['no_match'] += 1
            continue
        
        stats['matched'] += 1
        total_records_parsed += 1
        fields = extract_fields(details)
        
        # Only update fields that are currently empty
        for field, value in fields.items():
            current = r[field] if field in r.keys() else None
            if not current or current.strip() == '':
                col_map = {
                    'birth_place': 'luogo_nascita',
                    'death_date': 'data_decesso',
                    'death_cause': 'causa_morte',
                    'death_place': 'luogo_morte',
                    'burial_place': 'luogo_sepoltura',
                    'residence': 'residenza',
                    'capture_date': 'data_cattura',
                    'capture_place': 'luogo_cattura',
                    'grado': 'grado',
                }
                col = col_map.get(field)
                if col:
                    updates.append((col, value, r['id']))
                    stats[f'extracted_{field}'] += 1

print(f"  Pages parsed: {len(pages)}")
print(f"  Records matched: {stats['matched']}")
print(f"  No match: {stats['no_match']}")
print(f"  Total field extractions: {len(updates)}")
print(f"  Time: {time.time()-t0:.1f}s")

print(f"\n  Field extraction breakdown:")
for k, v in sorted(stats.items()):
    if k.startswith('extracted_'):
        print(f"    {k}: {v}")

# ─── Step 3: Apply updates ──────────────────────────────────────────────────
print(f"\n=== STEP 3: Apply {len(updates)} updates ===")
t0 = time.time()

# Check which columns exist
cursor = db.execute("PRAGMA table_info(internati)")
existing_cols = {row['name'] for row in cursor.fetchall()}

# Add missing columns
new_cols = ['data_decesso', 'causa_morte', 'luogo_morte', 'luogo_sepoltura']
for col in new_cols:
    if col not in existing_cols:
        db.execute(f"ALTER TABLE internati ADD COLUMN {col} TEXT")
        print(f"  Added column: {col}")
        existing_cols.add(col)

# Apply updates in batches
batch = []
applied = 0
for col, value, rid in updates:
    if col in existing_cols:
        batch.append((value, rid))
        if len(batch) >= 500:
            db.executemany(f"UPDATE internati SET {col}=? WHERE id=?", batch)
            db.commit()
            applied += len(batch)
            batch = []

if batch:
    db.executemany(f"UPDATE internati SET {col}=? WHERE id=?", batch)
    db.commit()
    applied += len(batch)

print(f"  Applied: {applied} updates")
print(f"  Time: {time.time()-t0:.1f}s")

# ─── Step 4: Verify results ─────────────────────────────────────────────────
print(f"\n=== STEP 4: Updated field coverage ===")
fields_check = ['data_nascita', 'luogo_nascita', 'grado', 'reparto', 'arma',
                'luogo_cattura', 'data_cattura', 'residenza', 
                'data_decesso', 'causa_morte', 'luogo_morte', 'luogo_sepoltura']
for f in fields_check:
    if f in existing_cols:
        has = db.execute(f"SELECT COUNT(*) as c FROM internati WHERE {f} IS NOT NULL AND {f} != ''").fetchone()['c']
        print(f"  {f}: {has}/20465 ({has*100//20465}%)")

# Sample
print(f"\n  Sample enriched records:")
for r in db.execute("""
    SELECT cognome, nome, luogo_nascita, data_decesso, causa_morte, luogo_morte, luogo_sepoltura
    FROM internati WHERE data_decesso IS NOT NULL AND data_decesso != '' LIMIT 5
""").fetchall():
    print(f"    {r['cognome']} {r['nome']} | nasc={r['luogo_nascita']} | morte={r['data_decesso']} causa={r['causa_morte']} luogo={r['luogo_morte']} sepolt={r['luogo_sepoltura']}")

db.close()
print(f"\nDone. Total time: {time.time()-t0:.1f}s")

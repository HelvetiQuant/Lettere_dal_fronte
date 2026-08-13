"""Re-apply extracted fields that didn't persist due to column creation timing."""
import sqlite3, re, time, warnings, logging
from collections import defaultdict
warnings.filterwarnings("ignore")
logging.disable(logging.WARNING)

db = sqlite3.connect('imi_internati.db')
db.row_factory = sqlite3.Row
db.execute("PRAGMA journal_mode=WAL")

# ─── Parse pages and re-apply ───────────────────────────────────────────────
print("=== Re-parsing and applying all fields ===")
t0 = time.time()

rows = db.execute("""
    SELECT id, cognome, nome, raw_text, data_nascita, luogo_nascita,
           grado, reparto, arma, luogo_internamento, sorte, residenza,
           luogo_cattura, data_cattura
    FROM internati 
    WHERE raw_text IS NOT NULL AND raw_text != ''
""").fetchall()

pages = defaultdict(list)
for r in rows:
    pages[r['raw_text']].append(r)

def parse_page(raw_text):
    lines = raw_text.split('\n')
    records = []
    current_name = None
    current_lines = []
    for line in lines:
        line_stripped = line.strip()
        if not line_stripped:
            continue
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
            ',' not in line_stripped.split()[0]
            ):
            if current_name:
                records.append((current_name, '\n'.join(current_lines)))
            current_name = line_stripped
            current_lines = []
        else:
            if current_name:
                current_lines.append(line_stripped)
    if current_name:
        records.append((current_name, '\n'.join(current_lines)))
    return records

def extract_fields(details_text):
    fields = {}
    text = details_text.replace('\n', ' ').replace('- ', '').strip()
    
    # Birth place
    m = re.match(r'\+([^,\-.]+?)(?:[,\-.](?:\s|$))', text)
    if m:
        bp = m.group(1).strip()
        if 2 < len(bp) < 50:
            fields['luogo_nascita'] = bp
    
    # Death date
    m = re.search(r'[Mm]orto\s+(?:il\s+)?(\d{1,2}[-/]\d{1,2}[-/]\d{4})', text)
    if m:
        fields['data_decesso'] = m.group(1).replace('/', '-')
    
    # Death cause
    m = re.search(r'[Mm]orto\s+(?:il\s+)?(?:\d{1,2}[-/]\d{1,2}[-/]\d{4})?\s*(?:per|di)\s+([^.]+?)(?:\.|,|al|nel|sepolto|$)', text)
    if m:
        cause = m.group(1).strip().rstrip('.,')
        if 2 < len(cause) < 80:
            fields['causa_morte'] = cause
    
    # Death place
    m = re.search(r'(?:al|nel)\s+([a-zA-Z][^.]+?)(?:\.|,|sepolto|$)', text)
    if m:
        place = m.group(1).strip().rstrip('.,')
        if 2 < len(place) < 80 and 'sepolto' not in place.lower():
            fields['luogo_morte'] = place
    
    # Burial place
    m = re.search(r'sepolto\s+(?:nel\s+cimitero\s+di\s+|a\s+|nel\s+)([^.\-]+?)(?:\.|-|$)', text)
    if m:
        burial = m.group(1).strip().rstrip('.,')
        if 2 < len(burial) < 80:
            fields['luogo_sepoltura'] = burial
    
    # Residence
    m = re.search(r'\(([^)]+,\s*[^)]+)\)', text)
    if m:
        residence = m.group(1).strip()
        if 5 < len(residence) < 100:
            fields['residenza'] = residence
    
    # Grado
    for pattern, rank in [
        (r'\b(Soldato|Sld\.?)\b', 'Soldato'),
        (r'\b(Caporale|Cpl\.?|Cap\.)\b', 'Caporale'),
        (r'\b(Sergente|Serg\.?)\b', 'Sergente'),
        (r'\b(Tenente|Ten\.?)\b', 'Tenente'),
        (r'\b(Sottotenente|Sottoten\.?)\b', 'Sottotenente'),
        (r'\b(Capitano|Cap\.)\b', 'Capitano'),
        (r'\b(Maggiore|Magg\.?)\b', 'Maggiore'),
        (r'\b(Colon(n)?ello|Col\.?)\b', 'Colonnello'),
        (r'\b(Aviere|Av\.?)\b', 'Aviere'),
    ]:
        if re.search(pattern, text):
            fields['grado'] = rank
            break
    
    return fields

# Build all updates per column
col_updates = defaultdict(list)  # col -> [(value, id), ...]
matched = 0
no_match = 0

for page_text, page_records in pages.items():
    parsed = parse_page(page_text)
    parsed_index = {}
    for name, details in parsed:
        norm = ' '.join(name.upper().split())
        parsed_index[norm] = details
    
    for r in page_records:
        rname = f"{r['cognome']} {r['nome']}".strip().upper()
        rname_clean = ' '.join(rname.split())
        
        details = parsed_index.get(rname_clean)
        if not details and r['nome']:
            rname_short = f"{r['cognome']} {r['nome'].split()[0]}".strip().upper()
            rname_short = ' '.join(rname_short.split())
            details = parsed_index.get(rname_short)
        if not details:
            for pname in parsed_index:
                if pname.startswith(r['cognome'].upper() + ' '):
                    details = parsed_index[pname]
                    break
        
        if not details:
            no_match += 1
            continue
        
        matched += 1
        fields = extract_fields(details)
        
        for field, value in fields.items():
            current = r[field] if field in r.keys() else None
            if not current or str(current).strip() == '':
                col_updates[field].append((value, r['id']))

print(f"  Matched: {matched}, No match: {no_match}")
print(f"  Updates by column:")
for col, updates in sorted(col_updates.items()):
    print(f"    {col}: {len(updates)}")

# Apply per-column
for col, updates in col_updates.items():
    if col in ['data_decesso', 'causa_morte', 'luogo_morte', 'luogo_sepoltura']:
        # These columns already exist from previous run
        db.executemany(f"UPDATE internati SET {col}=? WHERE id=?", updates)
        db.commit()
        print(f"  Applied {len(updates)} updates to {col}")

# Verify
print(f"\n=== FINAL FIELD COVERAGE ===")
for f in ['data_nascita', 'luogo_nascita', 'grado', 'reparto', 'arma',
          'luogo_cattura', 'data_cattura', 'residenza',
          'data_decesso', 'causa_morte', 'luogo_morte', 'luogo_sepoltura']:
    has = db.execute(f"SELECT COUNT(*) as c FROM internati WHERE {f} IS NOT NULL AND {f} != ''").fetchone()['c']
    print(f"  {f}: {has}/20465 ({has*100//20465}%)")

# Sample
print(f"\n  Sample with death info:")
for r in db.execute("""
    SELECT cognome, nome, luogo_nascita, data_decesso, causa_morte, luogo_morte, luogo_sepoltura
    FROM internati WHERE data_decesso != '' AND data_decesso IS NOT NULL LIMIT 5
""").fetchall():
    print(f"    {r['cognome']} {r['nome']} | nasc={r['luogo_nascita']} | morte={r['data_decesso']} causa={r['causa_morte']} luogo={r['luogo_morte']} sepolt={r['luogo_sepoltura']}")

print(f"\n  Sample with burial info:")
for r in db.execute("""
    SELECT cognome, nome, luogo_sepoltura
    FROM internati WHERE luogo_sepoltura != '' AND luogo_sepoltura IS NOT NULL LIMIT 5
""").fetchall():
    print(f"    {r['cognome']} {r['nome']} | sepoltura={r['luogo_sepoltura']}")

db.close()
print(f"\nDone. Time: {time.time()-t0:.1f}s")

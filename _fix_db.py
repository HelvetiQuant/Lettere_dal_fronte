"""Scan all databases for place name errors, OCR character issues, and wrong provinces."""
import sqlite3
import re
from pathlib import Path
from collections import Counter, defaultdict

ROOT = Path(__file__).resolve().parent
OCR_ROOT = ROOT.parent / "ocr_lettere"
DBS = {
    "imi_internati": ROOT / "imi_internati.db",
    "eventi_1gm": ROOT / "eventi_1gm.db",
    "archivio_fonti": ROOT / "archivio_fonti.db",
    "fonti_risorse": ROOT / "fonti_risorse.db",
    "albo_oro": ROOT / "albo_oro.db",
    "imi_data": ROOT / "imi_data.db",
    "validazioni_ai": ROOT / "validazioni_ai.db",
    "ocr_lettere": OCR_ROOT / "ocr_lettere.db",
}

PLACE_COLS = {"luogo", "luogo_nascita", "comune_nascita", "luogo_morte", "luogo_cattura", "luogo_internamento", "residenza", "place", "luogo_sepoltura", "cimitero", "paese_cimitero", "provincia_nascita", "comune"}

# Known OCR/encoding errors in Italian place names
OCR_CHAR_FIXES = {
    "ñ": "n",  # Nibbiaño → Nibbiano
    "à´": "ò",
    "â€™": "'",
    "Ã¨": "è",
    "Ã©": "é",
    "Ã¬": "ì",
    "Ã²": "ò",
    "Ã¹": "ù",
    "Ã ": "à",
}

# Known wrong province associations (place → correct province)
# Built from verified online research
PLACE_PROVINCE_FIXES = {
    "nibbiano": ("Piacenza", "Bergamo"),  # Nibbiano is in PC, not BG
}

def connect(path):
    conn = sqlite3.connect(path, timeout=10)
    conn.row_factory = sqlite3.Row
    return conn

def table_names(conn):
    return [r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")]

def table_columns(conn, table):
    return [r[1] for r in conn.execute(f'PRAGMA table_info("{table}")')]

print("=" * 80)
print("  SCAN DATABASE PER ERRORI TOPONIMI E CARATTERI OCR")
print("=" * 80)

# 1. Find all place columns with suspicious characters or wrong provinces
suspicious_chars = Counter()
place_province_issues = []
ocr_fixes_needed = []

for db_name, path in DBS.items():
    if not path.exists():
        continue
    with connect(path) as conn:
        for table in table_names(conn):
            cols = table_columns(conn, table)
            place_cols = [c for c in cols if c.lower() in PLACE_COLS]
            if not place_cols:
                continue
            for col in place_cols:
                try:
                    rows = conn.execute(f'SELECT rowid, "{col}" FROM "{table}" WHERE "{col}" IS NOT NULL').fetchall()
                except Exception:
                    continue
                for row in rows:
                    val = str(row[col]).strip()
                    if not val:
                        continue
                    # Check for OCR character issues
                    for bad_char, good_char in OCR_CHAR_FIXES.items():
                        if bad_char in val:
                            suspicious_chars[bad_char] += 1
                            ocr_fixes_needed.append({
                                "db": db_name, "table": table, "col": col,
                                "rowid": row[0], "old": val,
                                "char": bad_char
                            })
                    # Check for wrong province associations
                    val_lower = val.lower().strip()
                    for place, (correct_prov, wrong_prov) in PLACE_PROVINCE_FIXES.items():
                        if place in val_lower and wrong_prov.lower() in val_lower:
                            place_province_issues.append({
                                "db": db_name, "table": table, "col": col,
                                "rowid": row[0], "old": val,
                                "place": place, "correct_prov": correct_prov,
                                "wrong_prov": wrong_prov
                            })

print()
print("--- CARATTERI OCR ERRATI ---")
print(f"  Totale record con caratteri sospetti: {len(ocr_fixes_needed)}")
for char, count in suspicious_chars.most_common():
    print(f"  '{char}' → '{OCR_CHAR_FIXES[char]}': {count} occorrenze")

print()
print("--- PROVINCE ERRATE ---")
print(f"  Totale record con provincia errata: {len(place_province_issues)}")
for issue in place_province_issues[:20]:
    print(f"  [{issue['db']}:{issue['table']}] row={issue['rowid']} col={issue['col']}")
    print(f"    '{issue['old']}' → '{issue['correct_prov']}' (non '{issue['wrong_prov']}')")
if len(place_province_issues) > 20:
    print(f"  ... e altri {len(place_province_issues) - 20}")

# 2. Scan for other suspicious patterns in place names
print()
print("--- PATTERN SOSPETTI NEI TOPONIMI ---")
suspicious_patterns = []
for db_name, path in DBS.items():
    if not path.exists():
        continue
    with connect(path) as conn:
        for table in table_names(conn):
            cols = table_columns(conn, table)
            place_cols = [c for c in cols if c.lower() in PLACE_COLS]
            if not place_cols:
                continue
            for col in place_cols:
                try:
                    rows = conn.execute(f'SELECT rowid, "{col}" FROM "{table}" WHERE "{col}" IS NOT NULL LIMIT 200000').fetchall()
                except Exception:
                    continue
                for row in rows:
                    val = str(row[col]).strip()
                    if not val:
                        continue
                    # Check for non-Italian characters that shouldn't be in Italian place names
                    if re.search(r'[ñüïçðþßæœ]', val, re.IGNORECASE):
                        suspicious_patterns.append({"db": db_name, "table": table, "col": col, "rowid": row[0], "val": val})
                    # Check for double encoding artifacts
                    if "Ã" in val or "â€" in val:
                        suspicious_patterns.append({"db": db_name, "table": table, "col": col, "rowid": row[0], "val": val})

print(f"  Record con caratteri non italiani o artefatti encoding: {len(suspicious_patterns)}")
for s in suspicious_patterns[:30]:
    print(f"  [{s['db']}:{s['table']}] row={s['rowid']} col={s['col']}: '{s['val']}'")
if len(suspicious_patterns) > 30:
    print(f"  ... e altri {len(suspicious_patterns) - 30}")

# 3. Show unique place names with province in parentheses for review
print()
print("--- TOPONIMI CON PROVINCIA TRA PARENTESI (campione) ---")
places_with_prov = defaultdict(Counter)
for db_name, path in DBS.items():
    if not path.exists():
        continue
    with connect(path) as conn:
        for table in table_names(conn):
            cols = table_columns(conn, table)
            place_cols = [c for c in cols if c.lower() in {"luogo_nascita", "comune_nascita", "luogo"}]
            if not place_cols:
                continue
            for col in place_cols:
                try:
                    rows = conn.execute(f'SELECT "{col}" FROM "{table}" WHERE "{col}" IS NOT NULL LIMIT 200000').fetchall()
                except Exception:
                    continue
                for row in rows:
                    val = str(row[0]).strip()
                    m = re.match(r'^(.+?)\s*\((\w+)\)$', val)
                    if m:
                        place = m.group(1).strip()
                        prov = m.group(2).strip()
                        places_with_prov[place.lower()][prov] += 1

# Show places that appear with multiple different provinces
conflicting = {p: provs for p, provs in places_with_prov.items() if len(provs) > 1}
print(f"  Toponimi con province multiple/diverse: {len(conflicting)}")
for place, provs in sorted(conflicting.items())[:30]:
    print(f"  '{place}': {dict(provs)}")
if len(conflicting) > 30:
    print(f"  ... e altri {len(conflicting) - 30}")

print()
print("=" * 80)

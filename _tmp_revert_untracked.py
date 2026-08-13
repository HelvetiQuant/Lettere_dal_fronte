"""Manual revert of the untracked populate_internati_v2.py changes.

The first cross-linking run (populate_internati_v2.py) applied data without 
audit tracking. This script:
1. Records current state as 'UNTRACKED_CROSS_LINK' in audit table
2. Clears all cross-linked fields (those that were empty before the run)
3. Then we can run --audit to record clean baseline, then --run for safe version

Strategy: we know which fields were populated by cross-linking because the 
first run only updated fields that were empty. We can't know the original 
empty state for sure, but we CAN identify suspicious data by checking:
- Fields that don't match the original internati OCR structure
- Data from lebi_records (has campi_internamento in JSON format)
- Data from decorati (decorazione field didn't exist before)
"""
import sqlite3, re, time, warnings, logging
from datetime import datetime
warnings.filterwarnings("ignore")
logging.disable(logging.WARNING)

db = sqlite3.connect('imi_internati.db')
db.row_factory = sqlite3.Row
db.execute("PRAGMA journal_mode=WAL")

# Ensure audit table
db.execute("""
    CREATE TABLE IF NOT EXISTS cross_link_audit (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        internati_id INTEGER NOT NULL,
        column_name TEXT NOT NULL,
        old_value TEXT,
        new_value TEXT,
        source_table TEXT NOT NULL,
        source_record_id INTEGER,
        match_method TEXT NOT NULL,
        match_score INTEGER,
        reverted INTEGER DEFAULT 0,
        reverted_at TEXT,
        created_at TEXT NOT NULL,
        FOREIGN KEY (internati_id) REFERENCES internati(id)
    )
""")
db.execute("CREATE INDEX IF NOT EXISTS idx_audit_internati_id ON cross_link_audit(internati_id)")
db.execute("CREATE INDEX IF NOT EXISTS idx_audit_method ON cross_link_audit(match_method)")
db.execute("CREATE INDEX IF NOT EXISTS idx_audit_reverted ON cross_link_audit(reverted)")
db.commit()

now = datetime.now().isoformat()

# Fields that were added/populated by cross-linking runs
# These columns either didn't exist before or were populated by the scripts
CROSS_LINKED_FIELDS = {
    # New columns added by cross-linking scripts
    'data_decesso': 'NEW_COLUMN',      # Added by parse_internati_rawtext.py / lebi
    'causa_morte': 'NEW_COLUMN',       # Added by parse_internati_rawtext.py / lebi
    'luogo_morte': 'NEW_COLUMN',       # Added by parse_internati_rawtext.py / lebi
    'luogo_sepoltura': 'NEW_COLUMN',   # Added by parse_internati_rawtext.py / lebi
    'campi_internamento': 'NEW_COLUMN', # Added by populate_internati_v2.py
    'fronte_cattura': 'NEW_COLUMN',    # Added by populate_internati_v2.py
    'data_rientro': 'NEW_COLUMN',      # Added by populate_internati_v2.py
    'decorazione': 'NEW_COLUMN',       # Added by populate_internati_v2.py
    'anno_decorazione': 'NEW_COLUMN',  # Added by populate_internati_v2.py
    'anno_morte': 'NEW_COLUMN',        # Added by populate_internati_v2.py
    # Existing columns that were populated by cross-linking (were partially empty before)
    'data_nascita': 'EXISTING_COLUMN',
    'luogo_nascita': 'EXISTING_COLUMN',
    'grado': 'EXISTING_COLUMN',
    'reparto': 'EXISTING_COLUMN',
    'arma': 'EXISTING_COLUMN',
    'luogo_cattura': 'EXISTING_COLUMN',
    'data_cattura': 'EXISTING_COLUMN',
}

# For NEW_COLUMN fields: all non-empty values were from cross-linking → clear all
# For EXISTING_COLUMN fields: we need to identify which values came from cross-linking
# Strategy: check if the value format matches lebi_records format
# - lebi data_nascita: "DD-MM-YYYY" or "YYYY-MM-DD" format
# - original internati data_nascita: was only 4% coverage, mostly from OCR

# Step 1: Record current state in audit table
print("=== STEP 1: Record current state in audit table ===")
recorded = 0
for r in db.execute("SELECT * FROM internati").fetchall():
    for col, col_type in CROSS_LINKED_FIELDS.items():
        val = r[col] if col in r.keys() else None
        if val is not None and str(val).strip() != '':
            db.execute("""
                INSERT INTO cross_link_audit 
                (internati_id, column_name, old_value, new_value, source_table, 
                 match_method, match_score, created_at)
                VALUES (?, ?, NULL, ?, 'UNTRACKED', 'UNTRACKED_CROSS_LINK', 0, ?)
            """, (r['id'], col, str(val), now))
            recorded += 1

db.commit()
print(f"  Recorded {recorded} current values as UNTRACKED_CROSS_LINK")

# Step 2: For NEW_COLUMN fields, clear all (they didn't exist before)
print("\n=== STEP 2: Clear NEW_COLUMN fields (revert to pre-cross-link state) ===")
new_cols = [col for col, typ in CROSS_LINKED_FIELDS.items() if typ == 'NEW_COLUMN']
for col in new_cols:
    has = db.execute(f"SELECT COUNT(*) as c FROM internati WHERE {col} IS NOT NULL AND {col} != ''").fetchone()['c']
    db.execute(f"UPDATE internati SET {col}=NULL")
    db.commit()
    print(f"  Cleared {col}: {has} values reset to NULL")

# Step 3: For EXISTING_COLUMN fields, we need to be more careful
# The original internati data had very low coverage:
#   data_nascita: 4% (876), luogo_nascita: 1% (277), grado: 28% (5932), 
#   reparto: 26% (5367), arma: 28% (5731), luogo_cattura: 1% (385), data_cattura: 0% (197)
# Cross-linking added:
#   data_nascita: +4705 from lebi, luogo_nascita: +4490 from lebi, etc.
# 
# We can identify cross-linked values by checking if the SAME value exists in lebi_records
# But that's complex. Simpler: use the audit table to restore.
# Since we don't have the pre-cross-link baseline, we'll use a heuristic:
# - For data_nascita: if format is "DD-MM-YYYY" and year is 1895-1928, it's likely from lebi
#   (original internati dates were in various formats from OCR)
# - For luogo_nascita: if it matches a lebi_records.luogo_nascita, it's likely from lebi
# - For grado/reparto/arma: harder to tell, but we know cross-linking only added to empty fields

# Actually, the safest approach: we know the ORIGINAL coverage numbers.
# data_nascita: 876 original, now 6236 → 5360 were added
# luogo_nascita: 277 original, now 7095 → 6818 were added
# grado: 5932 original, now 6545 → 613 were added
# reparto: 5367 original, now 5990 → 623 were added
# arma: 5731 original, now 8122 → 2391 were added
# luogo_cattura: 385 original, now 1779 → 1394 were added
# data_cattura: 197 original, now 2141 → 1944 were added

# For grado, reparto: the cross-linking only added 241 each from lebi
# But we can't easily distinguish which 241 were added vs original

# BEST APPROACH: Check if the value in internati matches the value in lebi_records
# for the same person. If it does, it was cross-linked. If not, it was original.

print("\n=== STEP 3: Identify and revert cross-linked EXISTING_COLUMN fields ===")

# Build lebi index for matching
lebi_by_name = {}
for lr in db.execute("""
    SELECT id, cognome, nome, data_nascita, luogo_nascita, grado, reparto, arma,
           luogo_cattura, data_cattura
    FROM lebi_records
""").fetchall():
    key = f"{(lr['cognome'] or '').upper().strip()}|{(lr['nome'] or '').upper().strip()}"
    if key not in lebi_by_name:
        lebi_by_name[key] = lr

# Also build caduti_ministero index
cm_by_name = {}
for cr in db.execute("""
    SELECT id, cognome, nome, data_nascita, comune_nascita, grado, reparto
    FROM caduti_ministero
    WHERE cognome IS NOT NULL AND cognome != ''
""").fetchall():
    key = f"{(cr['cognome'] or '').upper().strip()}|{(cr['nome'] or '').upper().strip()}"
    if key not in cm_by_name:
        cm_by_name[key] = cr

existing_cols_to_check = [col for col, typ in CROSS_LINKED_FIELDS.items() if typ == 'EXISTING_COLUMN']

reverted_count = 0
for r in db.execute("SELECT * FROM internati").fetchall():
    key = f"{(r['cognome'] or '').upper().strip()}|{(r['nome'] or '').upper().strip()}"
    
    lr = lebi_by_name.get(key)
    cr = cm_by_name.get(key)
    
    for col in existing_cols_to_check:
        val = r[col] if col in r.keys() else None
        if not val or str(val).strip() == '':
            continue
        
        # Check if this value matches lebi or caduti_ministero
        is_cross_linked = False
        
        if lr:
            lebi_col_map = {
                'data_nascita': 'data_nascita',
                'luogo_nascita': 'luogo_nascita',
                'grado': 'grado',
                'reparto': 'reparto',
                'arma': 'arma',
                'luogo_cattura': 'luogo_cattura',
                'data_cattura': 'data_cattura',
            }
            lebi_col = lebi_col_map.get(col)
            if lebi_col and lebi_col in lr.keys():
                lebi_val = lr[lebi_col]
                if lebi_val and str(lebi_val).strip() == str(val).strip():
                    is_cross_linked = True
        
        if not is_cross_linked and cr:
            cm_col_map = {
                'data_nascita': 'data_nascita',
                'luogo_nascita': 'comune_nascita',
                'grado': 'grado',
                'reparto': 'reparto',
            }
            cm_col = cm_col_map.get(col)
            if cm_col and cm_col in cr.keys():
                cm_val = cr[cm_col]
                if cm_val and str(cm_val).strip() == str(val).strip():
                    is_cross_linked = True
        
        if is_cross_linked:
            # Record in audit and clear
            db.execute("""
                INSERT INTO cross_link_audit 
                (internati_id, column_name, old_value, new_value, source_table, 
                 match_method, match_score, created_at)
                VALUES (?, ?, ?, NULL, 'UNTRACKED', 'UNTRACKED_CROSS_LINK_REVERT', 0, ?)
            """, (r['id'], col, str(val), now))
            db.execute(f"UPDATE internati SET {col}=NULL WHERE id=?", (r['id'],))
            reverted_count += 1

db.commit()
print(f"  Reverted {reverted_count} cross-linked values in existing columns")

# Also clear decorati-sourced data (decorazione, anno_decorazione already cleared as NEW_COLUMN)
# But arma from decorati needs checking
print("\n=== STEP 4: Check arma from decorati ===")
dec_arma_reverted = 0
for r in db.execute("SELECT id, cognome, nome, arma FROM internati WHERE arma IS NOT NULL AND arma != ''").fetchall():
    key = f"{(r['cognome'] or '').upper().strip()}|{(r['nome'] or '').upper().strip()}"
    # Check if this arma matches a decorati record
    for dr in db.execute("""
        SELECT arma FROM decorati_nastroazzurro 
        WHERE cognome=? AND nome=?
    """, (r['cognome'], r['nome'])).fetchall():
        if dr['arma'] and str(dr['arma']).strip() == str(r['arma']).strip():
            # Check if lebi also has this arma — if so, it could be from lebi (keep)
            lr = lebi_by_name.get(key)
            if lr and lr['arma'] and str(lr['arma']).strip() == str(r['arma']).strip():
                break  # lebi also has it, keep
            # Only from decorati — revert
            db.execute("""
                INSERT INTO cross_link_audit 
                (internati_id, column_name, old_value, new_value, source_table, 
                 match_method, match_score, created_at)
                VALUES (?, ?, ?, NULL, 'decorati_nastroazzurro', 'UNTRACKED_CROSS_LINK_REVERT', 0, ?)
            """, (r['id'], 'arma', str(r['arma']), now))
            db.execute("UPDATE internati SET arma=NULL WHERE id=?", (r['id'],))
            dec_arma_reverted += 1
            break

db.commit()
print(f"  Reverted {dec_arma_reverted} arma values from decorati")

# Final coverage
print("\n=== POST-REVERT FIELD COVERAGE ===")
TOTAL = db.execute("SELECT COUNT(*) as c FROM internati").fetchone()['c']
for col in sorted(list(CROSS_LINKED_FIELDS.keys()) + ['luogo_internamento', 'sorte', 'residenza']):
    has = db.execute(f"SELECT COUNT(*) as c FROM internati WHERE {col} IS NOT NULL AND {col} != ''").fetchone()['c']
    pct = has * 100 // TOTAL
    print(f"  {col}: {has}/{TOTAL} ({pct}%)")

db.close()
print(f"\nDone. All changes tracked in cross_link_audit table.")

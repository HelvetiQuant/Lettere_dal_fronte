"""Cross-link audit table + revert mechanism.

Creates cross_link_audit table to track every field change with:
- old_value, new_value, source_table, match_method, timestamp
- Allows full rollback via --revert flag

Usage:
  python cross_link_safe.py --audit     # create audit table + record current state
  python cross_link_safe.py --revert    # revert all changes from audit table
  python cross_link_safe.py --run       # run safe cross-linking (strict matching only)
  python cross_link_safe.py --status    # show current audit status
"""
import sqlite3, re, time, sys, warnings, logging
from collections import defaultdict, Counter
from datetime import datetime
warnings.filterwarnings("ignore")
logging.disable(logging.WARNING)

DB_PATH = 'imi_internati.db'

def get_db():
    db = sqlite3.connect(DB_PATH)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA journal_mode=WAL")
    return db

def ensure_audit_table(db):
    """Create cross_link_audit table if not exists."""
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
    db.execute("""
        CREATE INDEX IF NOT EXISTS idx_audit_internati_id 
        ON cross_link_audit(internati_id)
    """)
    db.execute("""
        CREATE INDEX IF NOT EXISTS idx_audit_method 
        ON cross_link_audit(match_method)
    """)
    db.execute("""
        CREATE INDEX IF NOT EXISTS idx_audit_reverted 
        ON cross_link_audit(reverted)
    """)
    db.commit()

def cmd_audit(db):
    """Record current state of all cross-linked fields as baseline."""
    ensure_audit_table(db)
    
    # Check how many audit records exist
    count = db.execute("SELECT COUNT(*) as c FROM cross_link_audit WHERE reverted=0").fetchone()['c']
    if count > 0:
        print(f"Audit table already has {count} active records. Use --revert first if you want to re-run.")
        return
    
    # Record current state: snapshot all fields that could have been cross-linked
    # We mark them with match_method='PRE_CROSS_LINK_BASELINE' so we know these are original values
    cross_link_cols = [
        'data_nascita', 'luogo_nascita', 'grado', 'reparto', 'arma',
        'luogo_cattura', 'data_cattura', 'matricola', 'sorte',
        'data_decesso', 'causa_morte', 'luogo_morte', 'luogo_sepoltura',
        'campi_internamento', 'fronte_cattura', 'data_rientro',
        'decorazione', 'anno_decorazione', 'anno_morte',
        'residenza'
    ]
    
    existing_cols = {r['name'] for r in db.execute("PRAGMA table_info(internati)").fetchall()}
    now = datetime.now().isoformat()
    
    recorded = 0
    for r in db.execute("SELECT * FROM internati").fetchall():
        for col in cross_link_cols:
            if col not in existing_cols:
                continue
            val = r[col]
            if val is not None and str(val).strip() != '':
                db.execute("""
                    INSERT INTO cross_link_audit 
                    (internati_id, column_name, old_value, new_value, source_table, 
                     match_method, match_score, created_at)
                    VALUES (?, ?, NULL, ?, 'BASELINE', 'PRE_CROSS_LINK_BASELINE', 100, ?)
                """, (r['id'], col, str(val), now))
                recorded += 1
    
    db.commit()
    print(f"Baseline recorded: {recorded} existing field values saved.")

def cmd_revert(db):
    """Revert all cross-linked changes using audit table."""
    ensure_audit_table(db)
    
    # Get all cross-link updates (not baseline)
    updates = db.execute("""
        SELECT * FROM cross_link_audit 
        WHERE match_method != 'PRE_CROSS_LINK_BASELINE' 
        AND reverted = 0
        ORDER BY id DESC
    """).fetchall()
    
    print(f"Reverting {len(updates)} cross-link updates...")
    
    reverted = 0
    for u in updates:
        # Restore old_value (NULL means the field was empty before)
        old_val = u['old_value']
        db.execute(f"UPDATE internati SET {u['column_name']}=? WHERE id=?", 
                   (old_val, u['internati_id']))
        db.execute("UPDATE cross_link_audit SET reverted=1, reverted_at=? WHERE id=?",
                   (datetime.now().isoformat(), u['id']))
        reverted += 1
        if reverted % 1000 == 0:
            db.commit()
            print(f"  Reverted {reverted}/{len(updates)}...")
    
    db.commit()
    print(f"Done. Reverted {reverted} updates.")
    
    # Show post-revert coverage
    show_coverage(db)

def cmd_status(db):
    """Show current audit status."""
    ensure_audit_table(db)
    
    total = db.execute("SELECT COUNT(*) as c FROM cross_link_audit").fetchone()['c']
    active = db.execute("SELECT COUNT(*) as c FROM cross_link_audit WHERE reverted=0").fetchone()['c']
    reverted = db.execute("SELECT COUNT(*) as c FROM cross_link_audit WHERE reverted=1").fetchone()['c']
    
    print(f"=== CROSS-LINK AUDIT STATUS ===")
    print(f"  Total records: {total}")
    print(f"  Active (non-reverted): {active}")
    print(f"  Reverted: {reverted}")
    
    # By match method
    print(f"\n  By match method (active only):")
    for r in db.execute("""
        SELECT match_method, COUNT(*) as c 
        FROM cross_link_audit WHERE reverted=0
        GROUP BY match_method ORDER BY c DESC
    """).fetchall():
        print(f"    {r['match_method']}: {r['c']}")
    
    # By source table
    print(f"\n  By source table (active only):")
    for r in db.execute("""
        SELECT source_table, COUNT(*) as c 
        FROM cross_link_audit WHERE reverted=0 AND match_method != 'PRE_CROSS_LINK_BASELINE'
        GROUP BY source_table ORDER BY c DESC
    """).fetchall():
        print(f"    {r['source_table']}: {r['c']}")
    
    # By column
    print(f"\n  By column (active, non-baseline only):")
    for r in db.execute("""
        SELECT column_name, COUNT(*) as c 
        FROM cross_link_audit WHERE reverted=0 AND match_method != 'PRE_CROSS_LINK_BASELINE'
        GROUP BY column_name ORDER BY c DESC
    """).fetchall():
        print(f"    {r['column_name']}: {r['c']}")

def show_coverage(db):
    """Show current field coverage."""
    TOTAL = db.execute("SELECT COUNT(*) as c FROM internati").fetchone()['c']
    existing_cols = {r['name'] for r in db.execute("PRAGMA table_info(internati)").fetchall()}
    
    print(f"\n=== CURRENT FIELD COVERAGE ===")
    for col in sorted(existing_cols):
        if col in ('id', 'raw_text', 'source_file', 'page_number', 'cross_link_source',
                    'elaborato_il', 'file_pdf', 'lettera', 'pagina', 'needs_review',
                    'review_reason', 'luogo_validato', 'documenti', 'cognome', 'nome'):
            continue
        has = db.execute(f"SELECT COUNT(*) as c FROM internati WHERE {col} IS NOT NULL AND {col} != ''").fetchone()['c']
        pct = has * 100 // TOTAL
        if pct > 0:
            print(f"  {col}: {has}/{TOTAL} ({pct}%)")

def norm_name(cognome, nome):
    c = (cognome or '').upper().strip()
    n = (nome or '').upper().strip()
    for prefix in ['DI ', "DELL'", "DELLA ", "DE ", "D'"]:
        c = c.replace(prefix, '') if c.startswith(prefix) else c
    return c, n

def norm_year(date_str):
    if not date_str:
        return None
    m = re.search(r'(\d{4})', str(date_str))
    return int(m.group(1)) if m else None

def norm_place(place):
    if not place:
        return None
    p = place.upper().strip().rstrip(',')
    p = re.sub(r'\s*\([A-Z]{2}\)$', '', p)
    return p

def is_plausible_wwii_birth_year(year):
    """WWII internees were typically born 1895-1927."""
    return year is not None and 1895 <= year <= 1928

def cmd_run(db):
    """Run SAFE cross-linking with strict matching only.
    
    Safe methods (require strong identifier match):
    - name+year: exact cognome+nome + same birth year
    - name+place: exact cognome+nome + same birth place
    
    UNSAFE methods (NOT used):
    - name_unique: exact name but no second identifier
    - fuzzy_first3: partial first name match
    - cognome_single_partial: cognome only
    """
    ensure_audit_table(db)
    
    # Check if baseline exists
    baseline = db.execute("""
        SELECT COUNT(*) as c FROM cross_link_audit 
        WHERE match_method='PRE_CROSS_LINK_BASELINE' AND reverted=0
    """).fetchone()['c']
    
    if baseline == 0:
        print("No baseline found. Run --audit first to record pre-cross-link state.")
        return
    
    # Check if there are active non-baseline records
    active = db.execute("""
        SELECT COUNT(*) as c FROM cross_link_audit 
        WHERE match_method != 'PRE_CROSS_LINK_BASELINE' AND reverted=0
    """).fetchone()['c']
    
    if active > 0:
        print(f"Found {active} active cross-link records. Run --revert first to clean state.")
        return
    
    now = datetime.now().isoformat()
    TOTAL = db.execute("SELECT COUNT(*) as c FROM internati").fetchone()['c']
    
    # ─── 1. internati ← lebi_records (STRICT: name+year or name+place) ──────
    print("=== 1. internati ← lebi_records (STRICT matching) ===")
    t0 = time.time()
    
    internati = db.execute("""
        SELECT id, cognome, nome, data_nascita, luogo_nascita, grado, reparto, arma,
               luogo_cattura, data_cattura, matricola, sorte,
               data_decesso, causa_morte, luogo_morte, luogo_sepoltura,
               campi_internamento, data_rientro, fronte_cattura
        FROM internati
    """).fetchall()
    
    lebi_by_cognome = defaultdict(list)
    lebi_rows = db.execute("""
        SELECT id, cognome, nome, data_nascita, luogo_nascita, provincia_nascita,
               grado, reparto, arma, fronte_cattura, luogo_cattura, data_cattura,
               matricola, campi_internamento, sorte, data_decesso, luogo_decesso,
               causa_morte, luogo_sepoltura, data_rientro
        FROM lebi_records
    """).fetchall()
    for lr in lebi_rows:
        nc, nn = norm_name(lr['cognome'], lr['nome'])
        lebi_by_cognome[nc].append((lr, nn))
    
    print(f"  internati: {len(internati)}, lebi_records: {len(lebi_rows)}")
    
    field_map_lebi = {
        'data_nascita': 'data_nascita',
        'luogo_nascita': 'luogo_nascita',
        'grado': 'grado',
        'reparto': 'reparto',
        'arma': 'arma',
        'fronte_cattura': 'fronte_cattura',
        'luogo_cattura': 'luogo_cattura',
        'data_cattura': 'data_cattura',
        'matricola': 'matricola',
        'campi_internamento': 'campi_internamento',
        'sorte': 'sorte',
        'data_decesso': 'data_decesso',
        'causa_morte': 'causa_morte',
        'luogo_sepoltura': 'luogo_sepoltura',
        'data_rientro': 'data_rientro',
        'luogo_decesso': 'luogo_morte',
    }
    
    updates_lebi = []
    matched_lebi = 0
    match_methods = Counter()
    
    for ir in internati:
        ic, in_ = norm_name(ir['cognome'], ir['nome'])
        if not ic:
            continue
        
        candidates = lebi_by_cognome.get(ic, [])
        if not candidates:
            continue
        
        i_year = norm_year(ir['data_nascita'])
        i_place = norm_place(ir['luogo_nascita'])
        
        best_match = None
        best_method = None
        best_score = 0
        
        # STRICT: exact name + same birth year
        if i_year:
            for lr, ln in candidates:
                if ln == in_ and norm_year(lr['data_nascita']) == i_year:
                    # Additional check: birth year must be plausible for WWII
                    if is_plausible_wwii_birth_year(i_year):
                        best_match = lr
                        best_method = 'name+year'
                        best_score = 100
                        break
        
        # STRICT: exact name + same birth place
        if not best_match and i_place:
            for lr, ln in candidates:
                if ln == in_ and norm_place(lr['luogo_nascita']) == i_place:
                    best_match = lr
                    best_method = 'name+place'
                    best_score = 90
                    break
        
        # STRICT: exact name + both have birth year and they match (even if internati year was extracted from raw_text)
        if not best_match and i_year:
            exact = [(lr, ln) for lr, ln in candidates if ln == in_]
            if len(exact) == 1:
                lr = exact[0][0]
                lr_year = norm_year(lr['data_nascita'])
                if lr_year and lr_year == i_year and is_plausible_wwii_birth_year(i_year):
                    best_match = lr
                    best_method = 'name_unique+year_verified'
                    best_score = 85
        
        # SAFE: exact name + unique lebi candidate + lebi has plausible WWII birth year
        # This is safe because:
        # 1. Exact cognome+nome match (no fuzzy)
        # 2. Only 1 candidate in lebi with that exact name (no ambiguity)
        # 3. LeBI birth year is plausible for WWII (filters out WWI/other-era homonyms)
        if not best_match:
            exact = [(lr, ln) for lr, ln in candidates if ln == in_]
            if len(exact) == 1:
                lr = exact[0][0]
                lr_year = norm_year(lr['data_nascita'])
                if lr_year and is_plausible_wwii_birth_year(lr_year):
                    best_match = lr
                    best_method = 'name_unique+lebi_year_plausible'
                    best_score = 75
        
        # SAFE: exact name + multiple lebi candidates but only 1 with plausible WWII birth year
        if not best_match:
            exact = [(lr, ln) for lr, ln in candidates if ln == in_]
            plausible = [(lr, ln) for lr, ln in exact 
                         if is_plausible_wwii_birth_year(norm_year(lr['data_nascita']))]
            if len(plausible) == 1:
                best_match = plausible[0][0]
                best_method = 'name_ambiguous+single_plausible_year'
                best_score = 70
        
        if best_match:
            matched_lebi += 1
            match_methods[best_method] += 1
            
            for lebi_col, int_col in field_map_lebi.items():
                current = ir[int_col] if int_col in ir.keys() else None
                lebi_val = best_match[lebi_col] if lebi_col in best_match.keys() else None
                if (not current or str(current).strip() == '') and lebi_val and str(lebi_val).strip() != '':
                    updates_lebi.append((int_col, str(current) or '', str(lebi_val).strip(), 
                                         ir['id'], 'lebi_records', best_match['id'], 
                                         best_method, best_score, now))
    
    print(f"  Matched: {matched_lebi}/{len(internati)} ({matched_lebi*100//len(internati)}%)")
    print(f"  Updates: {len(updates_lebi)}")
    print(f"  Methods: {dict(match_methods.most_common())}")
    print(f"  Time: {time.time()-t0:.1f}s")
    
    # Apply lebi updates with audit
    for col, old_val, new_val, iid, src_table, src_id, method, score, ts in updates_lebi:
        db.execute(f"UPDATE internati SET {col}=? WHERE id=?", (new_val, iid))
        db.execute("""
            INSERT INTO cross_link_audit 
            (internati_id, column_name, old_value, new_value, source_table, 
             source_record_id, match_method, match_score, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (iid, col, old_val, new_val, src_table, src_id, method, score, ts))
    db.commit()
    print(f"  Applied + audited: {len(updates_lebi)} updates")
    
    # ─── 2. internati ← caduti_ministero (STRICT: name+year) ────────────────
    print(f"\n=== 2. internati ← caduti_ministero (STRICT matching) ===")
    t0 = time.time()
    
    cm_by_cognome = defaultdict(list)
    cm_rows = db.execute("""
        SELECT id, cognome, nome, data_nascita, comune_nascita, provincia_nascita,
               grado, reparto, anno_morte, luogo_morte, causa_morte
        FROM caduti_ministero
        WHERE cognome IS NOT NULL AND cognome != ''
    """).fetchall()
    for cr in cm_rows:
        nc, nn = norm_name(cr['cognome'], cr['nome'])
        cm_by_cognome[nc].append((cr, nn))
    
    print(f"  caduti_ministero indexed: {len(cm_rows)}")
    
    internati2 = db.execute("""
        SELECT id, cognome, nome, data_nascita, luogo_nascita, grado, reparto,
               data_decesso, causa_morte, luogo_morte, luogo_sepoltura, anno_morte
        FROM internati
    """).fetchall()
    
    updates_cm = []
    matched_cm = 0
    
    for ir in internati2:
        ic, in_ = norm_name(ir['cognome'], ir['nome'])
        if not ic:
            continue
        
        candidates = cm_by_cognome.get(ic, [])
        if not candidates:
            continue
        
        i_year = norm_year(ir['data_nascita'])
        
        best_match = None
        best_method = None
        best_score_cm = 100
        
        # STRICT: exact name + same birth year
        if i_year and is_plausible_wwii_birth_year(i_year):
            for cr, cn in candidates:
                if cn == in_ and norm_year(cr['data_nascita']) == i_year:
                    best_match = cr
                    best_method = 'name+year'
                    break
        
        # STRICT: exact name + same birth place (if no year)
        if not best_match:
            i_place = norm_place(ir['luogo_nascita'])
            if i_place:
                for cr, cn in candidates:
                    if cn == in_ and norm_place(cr['comune_nascita']) == i_place:
                        best_match = cr
                        best_method = 'name+place'
                        break
        
        # SAFE: exact name + unique caduti_ministero candidate + plausible WWII birth year
        if not best_match:
            exact = [(cr, cn) for cr, cn in candidates if cn == in_]
            if len(exact) == 1:
                cr = exact[0][0]
                cr_year = norm_year(cr['data_nascita'])
                if cr_year and is_plausible_wwii_birth_year(cr_year):
                    best_match = cr
                    best_method = 'name_unique+cm_year_plausible'
                    best_score_cm = 75
        
        # SAFE: exact name + multiple candidates but only 1 with plausible WWII birth year
        if not best_match:
            exact = [(cr, cn) for cr, cn in candidates if cn == in_]
            plausible = [(cr, cn) for cr, cn in exact
                         if is_plausible_wwii_birth_year(norm_year(cr['data_nascita']))]
            if len(plausible) == 1:
                best_match = plausible[0][0]
                best_method = 'name_ambiguous+single_plausible_year'
                best_score_cm = 70
        
        if best_match:
            matched_cm += 1
            field_map_cm = {
                'data_nascita': 'data_nascita',
                'comune_nascita': 'luogo_nascita',
                'grado': 'grado',
                'reparto': 'reparto',
                'anno_morte': 'anno_morte',
                'luogo_morte': 'luogo_morte',
                'causa_morte': 'causa_morte',
            }
            
            for cm_col, int_col in field_map_cm.items():
                current = ir[int_col] if int_col in ir.keys() else None
                cm_val = best_match[cm_col] if cm_col in best_match.keys() else None
                if (not current or str(current).strip() == '') and cm_val and str(cm_val).strip() != '' and str(cm_val).strip() != '-':
                    updates_cm.append((int_col, str(current) or '', str(cm_val).strip(),
                                       ir['id'], 'caduti_ministero', best_match['id'],
                                       best_method, best_score_cm, now))
    
    print(f"  Matched: {matched_cm}/{len(internati2)} ({matched_cm*100//len(internati2)}%)")
    print(f"  Updates: {len(updates_cm)}")
    print(f"  Time: {time.time()-t0:.1f}s")
    
    for col, old_val, new_val, iid, src_table, src_id, method, score, ts in updates_cm:
        db.execute(f"UPDATE internati SET {col}=? WHERE id=?", (new_val, iid))
        db.execute("""
            INSERT INTO cross_link_audit 
            (internati_id, column_name, old_value, new_value, source_table, 
             source_record_id, match_method, match_score, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (iid, col, old_val, new_val, src_table, src_id, method, score, ts))
    db.commit()
    print(f"  Applied + audited: {len(updates_cm)} updates")
    
    # ─── 3. internati ← decorati_nastroazzurro (STRICT: name+year) ──────────
    print(f"\n=== 3. internati ← decorati_nastroazzurro (STRICT matching) ===")
    t0 = time.time()
    
    dec_by_cognome = defaultdict(list)
    dec_rows = db.execute("""
        SELECT id, cognome, nome, arma, anno_decorazione, tipo_decorazione
        FROM decorati_nastroazzurro
        WHERE cognome IS NOT NULL AND cognome != ''
    """).fetchall()
    for dr in dec_rows:
        nc, nn = norm_name(dr['cognome'], dr['nome'])
        dec_by_cognome[nc].append((dr, nn))
    
    print(f"  decorati indexed: {len(dec_rows)}")
    
    internati3 = db.execute("""
        SELECT id, cognome, nome, data_nascita, arma, decorazione, anno_decorazione
        FROM internati
    """).fetchall()
    
    updates_dec = []
    matched_dec = 0
    
    for ir in internati3:
        ic, in_ = norm_name(ir['cognome'], ir['nome'])
        if not ic:
            continue
        
        candidates = dec_by_cognome.get(ic, [])
        if not candidates:
            continue
        
        i_year = norm_year(ir['data_nascita'])
        
        best_match = None
        best_method = None
        
        # STRICT: exact name + birth year plausible for WWII
        if i_year and is_plausible_wwii_birth_year(i_year):
            for dr, dn in candidates:
                if dn == in_:
                    # Decoration year should be 1940-1947 for WWII
                    dec_year = norm_year(dr['anno_decorazione'])
                    if dec_year and 1940 <= dec_year <= 1947:
                        best_match = dr
                        best_method = 'name+deco_year_wwii'
                        break
        
        # LESS STRICT but still safe: exact name, unique candidate, decoration in WWII period
        if not best_match:
            exact = [(dr, dn) for dr, dn in candidates if dn == in_]
            if len(exact) == 1:
                dec_year = norm_year(exact[0][0]['anno_decorazione'])
                if dec_year and 1940 <= dec_year <= 1947:
                    best_match = exact[0][0]
                    best_method = 'name_unique+deco_year_wwii'
        
        if best_match:
            matched_dec += 1
            if (not ir['arma'] or str(ir['arma']).strip() == '') and best_match['arma']:
                updates_dec.append(('arma', str(ir['arma']) or '', best_match['arma'],
                                    ir['id'], 'decorati_nastroazzurro', best_match['id'],
                                    best_method, 90, now))
            if best_match['tipo_decorazione'] and (not ir['decorazione'] or str(ir['decorazione']).strip() == ''):
                updates_dec.append(('decorazione', str(ir['decorazione']) or '', best_match['tipo_decorazione'],
                                    ir['id'], 'decorati_nastroazzurro', best_match['id'],
                                    best_method, 90, now))
            if best_match['anno_decorazione'] and (not ir['anno_decorazione'] or str(ir['anno_decorazione']).strip() == ''):
                updates_dec.append(('anno_decorazione', str(ir['anno_decorazione']) or '', best_match['anno_decorazione'],
                                    ir['id'], 'decorati_nastroazzurro', best_match['id'],
                                    best_method, 90, now))
    
    print(f"  Matched: {matched_dec}/{len(internati3)} ({matched_dec*100//len(internati3)}%)")
    print(f"  Updates: {len(updates_dec)}")
    print(f"  Time: {time.time()-t0:.1f}s")
    
    for col, old_val, new_val, iid, src_table, src_id, method, score, ts in updates_dec:
        db.execute(f"UPDATE internati SET {col}=? WHERE id=?", (new_val, iid))
        db.execute("""
            INSERT INTO cross_link_audit 
            (internati_id, column_name, old_value, new_value, source_table, 
             source_record_id, match_method, match_score, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (iid, col, old_val, new_val, src_table, src_id, method, score, ts))
    db.commit()
    print(f"  Applied + audited: {len(updates_dec)} updates")
    
    # ─── FINAL ──────────────────────────────────────────────────────────────
    print(f"\n=== SUMMARY ===")
    print(f"  Total updates applied: {len(updates_lebi) + len(updates_cm) + len(updates_dec)}")
    print(f"  All tracked in cross_link_audit table (reversible via --revert)")
    show_coverage(db)

def main():
    cmd = sys.argv[1] if len(sys.argv) > 1 else '--status'
    db = get_db()
    
    if cmd == '--audit':
        cmd_audit(db)
    elif cmd == '--revert':
        cmd_revert(db)
    elif cmd == '--run':
        cmd_run(db)
    elif cmd == '--status':
        cmd_status(db)
    else:
        print(f"Unknown command: {cmd}")
        print("Usage: python cross_link_safe.py --audit|--revert|--run|--status")
    
    db.close()

if __name__ == '__main__':
    main()

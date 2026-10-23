"""Cross-link LeBI v2 — matricola di cattura + impiego + matricola militare.

Estende il cross-link internati <- lebi_records con le nuove colonne LeBI
(create 2026-10-04):
  - lebi.matricola_cattura  -> internati.matricola  (STESSO dominio: numero prigioniero)
  - lebi.impiego            -> internati.arbeitskommando
  - lebi.matricola_militare -> internati.matricola_militare (nuova colonna)

ATTENZIONE dominio: internati.matricola e' il numero di PRIGIONIERO (scheda ASBZ),
NON la matricola militare. Verificato empiricamente: match puramente numerico
genera falsi positivi (AMICI 79795 -> FIORENTE). Il match via matricola richiede
SEMPRE anche cognome+nome uguali.

Ogni update e' registrato in cross_link_audit (revert possibile).

Usage:
  python cross_link_lebi_v2.py --dry    # solo conteggi, nessuna scrittura
  python cross_link_lebi_v2.py --run    # esegue + audit
"""
import sqlite3, sys, time
from collections import defaultdict
from datetime import datetime

DB_PATH = 'imi_internati.db'
METHOD_MAT = 'matricola_cattura+name'
METHOD_ENRICH = 'lebi_enrichment_v2'


def norm(s):
    return ' '.join(str(s or '').upper().replace("'", ' ').replace('.', ' ').split())


def cat_tokens(v):
    """matricola_cattura puo' contenere '113541; 0565' -> set di token."""
    return {t.strip() for t in str(v or '').split(';') if t.strip()}


def main():
    dry = '--dry' in sys.argv
    db = sqlite3.connect(DB_PATH)
    db.row_factory = sqlite3.Row
    now = datetime.now().isoformat()

    # nuova colonna matricola_militare
    cols = [c[1] for c in db.execute('PRAGMA table_info(internati)')]
    if 'matricola_militare' not in cols:
        if not dry:
            db.execute('ALTER TABLE internati ADD COLUMN matricola_militare TEXT')
            db.commit()
        print('Colonna internati.matricola_militare: aggiunta' if not dry else 'Colonna matricola_militare da aggiungere')

    # indici lebi
    lebi_rows = db.execute("""
        SELECT id, lebi_id, cognome, nome, data_nascita, luogo_nascita, grado, reparto, arma,
               fronte_cattura, luogo_cattura, data_cattura, matricola_militare, matricola_cattura,
               impiego, campi_internamento, sorte, data_decesso, luogo_decesso, causa_morte,
               luogo_sepoltura, data_rientro
        FROM lebi_records
    """).fetchall()

    lebi_by_id = {}
    lebi_by_cat = defaultdict(list)   # token matricola_cattura -> lebi rows
    lebi_by_mil = defaultdict(list)   # matricola_militare -> lebi rows
    for lr in lebi_rows:
        lebi_by_id[lr['id']] = lr
        for t in cat_tokens(lr['matricola_cattura']):
            lebi_by_cat[t].append(lr)
        mm = str(lr['matricola_militare'] or '').strip()
        if mm:
            lebi_by_mil[mm].append(lr)

    # coppie gia' linkate via name-match precedente (audit)
    known_pairs = {}  # internati_id -> lebi row id
    for iid, lid in db.execute("""
        SELECT DISTINCT internati_id, source_record_id FROM cross_link_audit
        WHERE source_table='lebi_records' AND reverted=0 AND source_record_id IS NOT NULL
    """):
        known_pairs[iid] = lid
    print(f'Coppie gia note (name match): {len(known_pairs)}')

    internati = db.execute("""
        SELECT * FROM internati
    """).fetchall()

    updates = []   # (col, old, new, iid, src_id, method, score)
    new_links = 0
    enriched = 0

    FIELDS = [
        ('matricola_cattura', 'matricola'),          # stesso dominio (prigioniero)
        ('matricola_militare', 'matricola_militare'),
        ('impiego', 'arbeitskommando'),
        ('campi_internamento', 'campi_internamento'),
        ('fronte_cattura', 'fronte_cattura'),
        ('luogo_cattura', 'luogo_cattura'),
        ('data_cattura', 'data_cattura'),
        ('data_nascita', 'data_nascita'),
        ('luogo_nascita', 'luogo_nascita'),
        ('grado', 'grado'),
        ('reparto', 'reparto'),
        ('arma', 'arma'),
        ('sorte', 'sorte'),
        ('data_decesso', 'data_decesso'),
        ('luogo_decesso', 'luogo_morte'),
        ('causa_morte', 'causa_morte'),
        ('luogo_sepoltura', 'luogo_sepoltura'),
        ('data_rientro', 'data_rientro'),
    ]

    def fill(ir, lr, method, score):
        """Accoda update per campi vuoti di internati dalla riga lebi."""
        n = 0
        for lebi_col, int_col in FIELDS:
            if int_col not in ir.keys():
                continue
            cur = ir[int_col]
            val = lr[lebi_col]
            if (cur is None or str(cur).strip() == '') and val and str(val).strip():
                updates.append((int_col, '', str(val).strip(), ir['id'], lr['id'], method, score))
                n += 1
        return n

    t0 = time.time()
    for ir in internati:
        iid = ir['id']
        lr = None
        method = METHOD_ENRICH
        score = 0

        if iid in known_pairs:
            lr = lebi_by_id.get(known_pairs[iid])
            score = 80
        else:
            # match via matricola (cattura o militare) + cognome E nome identici
            m = str(ir['matricola'] or '').strip()
            if m:
                cands = [c for c in lebi_by_cat.get(m, []) + lebi_by_mil.get(m, [])]
                ic, inome = norm(ir['cognome']), norm(ir['nome'])
                exact = [c for c in cands if norm(c['cognome']) == ic and norm(c['nome']) == inome]
                if len(exact) == 1:
                    lr = exact[0]
                    method = METHOD_MAT
                    score = 95
        if lr:
            n = fill(ir, lr, method, score)
            if method == METHOD_MAT:
                new_links += 1
                if (not ir['cross_link_source'] or not str(ir['cross_link_source']).strip()):
                    updates.append(('cross_link_source', '', f"lebi_records:{lr['lebi_id']}", iid, lr['id'], METHOD_MAT, 95))
            if n:
                enriched += 1

    print(f'Nuovi link via matricola+nome: {new_links}')
    print(f'Internati arricchiti: {enriched}')
    print(f'Update campi totali: {len(updates)}')
    from collections import Counter
    print('Per colonna:', dict(Counter(u[0] for u in updates).most_common()))
    print(f'Time: {time.time()-t0:.1f}s')

    if dry:
        print('DRY RUN — nessuna scrittura')
        return

    for col, old, new, iid, src_id, method, score in updates:
        db.execute(f"UPDATE internati SET {col}=? WHERE id=?", (new, iid))
        db.execute("""
            INSERT INTO cross_link_audit
            (internati_id, column_name, old_value, new_value, source_table,
             source_record_id, match_method, match_score, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (iid, col, old, new, 'lebi_records', src_id, method, score, now))
    db.commit()
    print(f'Applicate + auditate: {len(updates)} modifiche')


if __name__ == '__main__':
    main()

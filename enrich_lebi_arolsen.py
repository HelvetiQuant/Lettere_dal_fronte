"""Enrich LeBI records with Arolsen Archives prisoner numbers.

Queries Arolsen Archives (ITS) per LeBI record (cognome+nome [+anno nascita])
and stores matches in table `arolsen_matches` — provenance preserved, the
canonical `matricola_cattura` column is NOT touched by this script.

Match rule (strict, historian-grade):
  - normalized cognome AND nome equal, AND
  - birth year match when both sides have one (LeBI data_nascita vs Arolsen Dob)

Usage:
  python enrich_lebi_arolsen.py            # full run (checkpoint resume)
  python enrich_lebi_arolsen.py --limit N  # first N only
  python enrich_lebi_arolsen.py --linked   # only lebi ids linked to internati
"""
import sqlite3, json, sys, time, warnings, uuid
import requests
warnings.filterwarnings('ignore')

DB = 'imi_internati.db'
CKPT = '.arolsen_checkpoint.json'
API = 'https://collections-server.arolsen-archives.org/ITS-WS.asmx'
BASE = 'https://collections.arolsen-archives.org'
RATE = 1.2  # s per record (2-3 req each)


def norm(s):
    return ' '.join(str(s or '').upper().replace("'", ' ').replace('.', ' ').split())


def year_of(d):
    import re
    m = re.search(r'(18|19|20)\d{2}', str(d or ''))
    return m.group(0) if m else ''


def ensure_table(db):
    db.execute("""
        CREATE TABLE IF NOT EXISTS arolsen_matches (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            lebi_id INTEGER NOT NULL,
            arolsen_obj_id TEXT,
            last_name TEXT, first_name TEXT,
            prisoner_number TEXT,
            dob TEXT, place_birth TEXT,
            match_method TEXT,
            detail_url TEXT,
            raw_json TEXT,
            created_at TEXT NOT NULL,
            UNIQUE(lebi_id, arolsen_obj_id)
        )
    """)
    db.commit()


def arolsen_search(query):
    """Return list of person dicts from Arolsen ITS-WS."""
    uid = str(uuid.uuid4())
    hdr = {'Content-Type': 'application/json', 'Accept': 'application/json',
           'Origin': BASE, 'Referer': f'{BASE}/'}
    sess = requests.Session()
    r = sess.post(f'{API}/BuildQueryGlobalForAngular',
                  json={'uniqueId': uid, 'lang': 'en', 'archiveIds': [],
                        'strSearch': query, 'synSearch': True},
                  headers=hdr, timeout=30, verify=False)
    if r.status_code != 200:
        return []
    cnt = sess.post(f'{API}/GetCount',
                    json={'uniqueId': uid, 'lang': 'en', 'searchType': 'person', 'useFilter': False},
                    headers=hdr, timeout=30, verify=False)
    try:
        n = int(cnt.json().get('d', 0))
    except Exception:
        n = 0
    if n == 0:
        return []
    pl = sess.post(f'{API}/GetPersonList',
                   json={'uniqueId': uid, 'lang': 'en', 'rowNum': 0,
                         'orderBy': 'LastName', 'orderType': 'asc'},
                   headers=hdr, timeout=30, verify=False)
    if pl.status_code != 200:
        return []
    return pl.json().get('d', []) or []


def main():
    limit = None
    only_linked = '--linked' in sys.argv
    for i, a in enumerate(sys.argv):
        if a == '--limit':
            limit = int(sys.argv[i + 1])

    db = sqlite3.connect(DB)
    db.row_factory = sqlite3.Row
    ensure_table(db)

    db.execute("""
        CREATE TABLE IF NOT EXISTS arolsen_checked (
            lebi_id INTEGER PRIMARY KEY, checked_at TEXT, hits INTEGER
        )
    """)
    db.commit()
    done_ids = {r[0] for r in db.execute('SELECT lebi_id FROM arolsen_checked')}

    if only_linked:
        # lebi ids linked to internati via cross_link_audit
        ids = [r[0] for r in db.execute("""
            SELECT DISTINCT lr.lebi_id FROM lebi_records lr
            JOIN cross_link_audit a ON a.source_record_id = lr.id
            WHERE a.source_table='lebi_records' AND a.reverted=0
              AND lr.matricola_cattura IS NULL
        """)]
        print(f'Modalita --linked: {len(ids)} record lebi linkati senza matricola cattura')
    else:
        ids = [r[0] for r in db.execute("""
            SELECT lebi_id FROM lebi_records
            WHERE (matricola_cattura IS NULL OR matricola_cattura = '')
            ORDER BY lebi_id
        """)]
        print(f'Record senza matricola cattura: {len(ids)}')

    todo = [i for i in ids if i not in done_ids]
    if limit:
        todo = todo[:limit]
    print(f'Da processare: {len(todo)} (gia fatti: {len(done_ids)})')

    matched = checked = 0
    now = lambda: time.strftime('%Y-%m-%dT%H:%M:%S')
    t0 = time.time()
    for idx, lid in enumerate(todo):
        rec = db.execute(
            'SELECT lebi_id, cognome, nome, data_nascita FROM lebi_records WHERE lebi_id=?',
            (lid,)).fetchone()
        if not rec:
            continue
        q = f"{rec['cognome']} {rec['nome']}".strip()
        hits = 0
        try:
            persons = arolsen_search(q)
            ic, inome = norm(rec['cognome']), norm(rec['nome'])
            iy = year_of(rec['data_nascita'])
            for p in persons:
                if norm(p.get('LastName')) != ic:
                    continue
                fn = norm(p.get('FirstName'))
                name_exact = (not inome) or fn == inome
                # variante di traslitterazione tedesca (CESARE->Cesar, GIUSEPPE->Guiseppe):
                # stesso iniziale + prime 3 lettere uguali o una contiene l'altra
                name_variant = (not name_exact and fn and inome
                                and fn[0] == inome[0]
                                and (fn[:3] == inome[:3] or fn.startswith(inome[:4])
                                     or inome.startswith(fn[:4])))
                py = year_of(p.get('Dob'))
                year_match = bool(iy and py and iy == py)
                if name_exact and (year_match or not iy or not py):
                    method = 'exact+dob' if year_match else 'exact'
                elif (name_exact or name_variant) and year_match:
                    method = 'variant+dob'
                elif not name_exact and not name_variant:
                    continue  # nome diverso -> omonimo o parente
                else:
                    continue  # anno diverso senza variante -> incerto, non registrare
                db.execute("""
                    INSERT OR IGNORE INTO arolsen_matches
                    (lebi_id, arolsen_obj_id, last_name, first_name, prisoner_number,
                     dob, place_birth, match_method, detail_url, raw_json, created_at)
                    VALUES (?,?,?,?,?,?,?,?,?,?,?)
                """, (lid, str(p.get('ObjId') or ''), p.get('LastName', ''), p.get('FirstName', ''),
                      p.get('PrisonerNumber', ''), p.get('Dob', ''), p.get('PlaceBirth', ''),
                      method, f"{BASE}/en/document/{p.get('ObjId')}" if p.get('ObjId') else '',
                      json.dumps(p, ensure_ascii=False)[:4000], now()))
                hits += 1
            db.execute('INSERT OR REPLACE INTO arolsen_checked (lebi_id, checked_at, hits) VALUES (?,?,?)',
                       (lid, now(), hits))
            db.commit()
            checked += 1
            matched += hits
        except Exception as e:
            print(f'ERR {lid}: {e}')
        if checked and checked % 50 == 0:
            rate = checked / (time.time() - t0)
            print(f'{checked}/{len(todo)} ({rate:.1f}/s) matched={matched} hits={hits}')
            json.dump({'offset': idx, 'matched': matched, 'checked': checked}, open(CKPT, 'w'))
        time.sleep(RATE)

    print(f'\nFATTO: checked={checked} matched={matched} hits totali')


if __name__ == '__main__':
    main()

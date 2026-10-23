#!/usr/bin/env python3
"""
DEPRECATED — Legacy event-centric linking pipeline.

V7.3-FIX: Word-boundary matching, temporal barriers (WWI/WWII), no skip-if-exists,
CLI with --dry-run/--execute. Multi-event matching (no break on first).

Known remaining issues (documented, not fixed here — use linking v2):
- O(N×M) scan of records × events
- No provenance, no algorithm version, no evidence
- Confidence values are not calibrated

Use the new linking v2 pipeline instead:
    python -m linking.cli generate --dry-run

To run this script in audit-only mode:
    LEGACY_JOB_LEGACY_EVENT_LINKS=true python _gen_event_links.py --dry-run

To execute with DB writes:
    LEGACY_JOB_LEGACY_EVENT_LINKS=true python _gen_event_links.py --execute
"""
import sys
import os
import argparse
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from linking.kill_switch import LegacyJob, assert_frozen

assert_frozen(LegacyJob.EVENT_LINKS, "_gen_event_links.py is deprecated")

import sqlite3, json, re
from datetime import datetime
from pathlib import Path

# V7.3-FIX: War period classification for events
def _event_war_period(ev):
    """Classify event as WWI, WWII, or BOTH based on dates."""
    di = ev.get("data_inizio", "")
    if not di:
        return "UNKNOWN"
    year = int(di[:4])
    if year >= 1939:
        return "WWII"
    elif year >= 1914:
        return "WWI"
    return "UNKNOWN"

# V7.3-FIX: Word-boundary matcher
def _word_boundary_match(keyword, text):
    """Match keyword as a whole word in text (case-insensitive).

    'Lana' does NOT match 'Castellana'.
    'Roma' does NOT match 'Romania'.
    'Nero' does NOT match 'Pinero'.
    """
    if not keyword or not text:
        return False
    pattern = r'\b' + re.escape(keyword.upper()) + r'\b'
    return bool(re.search(pattern, text.upper()))

DB = Path(__file__).parent / "imi_internati.db"
EDB = Path(__file__).parent / "eventi_1gm.db"

# ─── Eventi canonici 1GM ───────────────────────────────────────────────────
# Ogni evento ha: nome, data_inizio, data_fine, luogo, aliases (varianti nome),
# keywords per ricerca in documenti/fonti, descrizione
EVENTI_1GM = [
    {
        "nome": "Battaglia di Caporetto",
        "data_inizio": "1917-10-24",
        "data_fine": "1917-11-12",
        "luogo": "Isonzo, settore Tolmino-Caporetto",
        "aliases": ["Caporetto", "Kobarid", "Settore Di Tolmino", "Ripiegamento al Piave"],
        "keywords": ["Caporetto", "Kobarid", "Tolmino", "ritirata", "ripiegamento", "Karfreit"],
        "descrizione": "Sconfitta italiana 24 ott - 12 nov 1917. Rottura del fronte Isonzo, ritirata al Piave.",
    },
    {
        "nome": "Battaglie dell'Isonzo",
        "data_inizio": "1915-06-23",
        "data_fine": "1917-09-12",
        "luogo": "Fronte Isonzo, Carso",
        "aliases": ["Isonzo", "Medio Isonzo", "Basso Isonzo", "Alto Isonzo", "Soča"],
        "keywords": ["Isonzo", "Soča", "Gorizia", "Carso", "Sabotino", "San Michele", "Doberdò"],
        "descrizione": "12 offensive italiane sul fiume Isonzo giun-1915 / set-1917.",
    },
    {
        "nome": "Battaglia del Carso",
        "data_inizio": "1915-06-23",
        "data_fine": "1917-11-12",
        "luogo": "Altopiano del Carso",
        "aliases": ["Carso", "Monte San Michele", "Monte San Gabriele", "Doberdò", "Monte Ermada"],
        "keywords": ["Carso", "Karst", "San Michele", "San Gabriele", "Doberdò", "Ermada", "Castagnevizza"],
        "descrizione": "Combattimenti sul Carso durante tutte le battaglie dell'Isonzo.",
    },
    {
        "nome": "Battaglia del Piave",
        "data_inizio": "1918-06-15",
        "data_fine": "1918-06-23",
        "luogo": "Fiume Piave",
        "aliases": ["Piave", "Ripiegamento al Piave", "Monte Grappa", "Monte Solarolo"],
        "keywords": ["Piave", "Grappa", "Solarolo", "Montello", "Nervesa", "Monte Tomba"],
        "descrizione": "Offensiva austro-tedesca fermata sul Piave giu-1918.",
    },
    {
        "nome": "Battaglia di Vittorio Veneto",
        "data_inizio": "1918-10-24",
        "data_fine": "1918-11-04",
        "luogo": "Veneto, Piave-Grappa",
        "aliases": ["Vittorio Veneto", "Monte Grappa", "Monte Pertica"],
        "keywords": ["Vittorio Veneto", "Grappa", "Pertica", "Tombea", "Valsugana", "offensiva finale"],
        "descrizione": "Offensiva finale italiana ott-nov 1918, sfondamento del fronte.",
    },
    {
        "nome": "Altopiano di Asiago",
        "data_inizio": "1916-05-15",
        "data_fine": "1918-11-04",
        "luogo": "Altopiano dei Sette Comuni",
        "aliases": ["Altopiano Di Asiago", "Altipiano Di Asiago", "Asiago", "Monte Ortigara", "Monte Zebio", "Monte Cengio"],
        "keywords": ["Asiago", "Ortigara", "Zebio", "Cengio", "Sette Comuni", "Cima Dieci", "Fiorentina"],
        "descrizione": "Offensiva austriaca (Strafexpedition) mag-1916 e battaglie successive.",
    },
    {
        "nome": "Monte Grappa",
        "data_inizio": "1917-11-13",
        "data_fine": "1918-11-04",
        "luogo": "Massiccio del Grappa",
        "aliases": ["Monte Grappa", "Grappa", "Monte Asolone", "Monte Solarolo"],
        "keywords": ["Grappa", "Asolone", "Solarolo", "Pertica", "Tombea", "Valderoa"],
        "descrizione": "Difesa del Grappa dopo Caporetto, linea di resistenza nov-1917 / nov-1918.",
    },
    {
        "nome": "Monte Pasubio",
        "data_inizio": "1916-05-15",
        "data_fine": "1918-11-04",
        "luogo": "Monte Pasubio, Prealpi Venete",
        "aliases": ["Monte Pasubio", "Pasubio", "Monte Corno", "Dente Italiano", "Dente Austriaco"],
        "keywords": ["Pasubio", "Corno", "Dente", "Porte di Pasubio", "Strada delle Gallerie"],
        "descrizione": "Combattimenti sul Pasubio 1916-1918, settore prealpino.",
    },
    {
        "nome": "Monte San Michele",
        "data_inizio": "1915-06-23",
        "data_fine": "1917-09-12",
        "luogo": "Carso, Monte San Michele",
        "aliases": ["Monte San Michele", "San Michele", "Santo Michele"],
        "keywords": ["San Michele", "Monte San Michele", "Debelpet", "Peuma"],
        "descrizione": "Posizione chiave del Carso, conquistata nella 6a battaglia dell'Isonzo ago-1916.",
    },
    {
        "nome": "Prigionia",
        "data_inizio": "1915-05-24",
        "data_fine": "1918-11-04",
        "luogo": "Campi di prigionia (Austria-Ungheria, Germania)",
        "aliases": ["Prigionia", "Campo", "Prigioniero", "Lager"],
        "keywords": ["Prigionia", "prigioniero", "campo", "Lager", "Cattura", "Captured"],
        "descrizione": "Soldati italiani catturati e internati in campi di prigionia.",
    },
    {
        "nome": "Fronte Macedone",
        "data_inizio": "1915-10-14",
        "data_fine": "1918-09-30",
        "luogo": "Macedonia, Salonicco",
        "aliases": ["Macedonia", "Salonicco", "Fronte Orientale"],
        "keywords": ["Macedonia", "Salonicco", "Salonika", "Thessaloniki", "Vardar"],
        "descrizione": "Fronte macedone con truppe italiane 35a Divisione.",
    },
    {
        "nome": "Fronte Albanese",
        "data_inizio": "1915-12-03",
        "data_fine": "1918-09-30",
        "luogo": "Albania",
        "aliases": ["Albania", "Valona", "Durazzo"],
        "keywords": ["Albania", "Valona", "Vlorë", "Durazzo", "Durrës"],
        "descrizione": "Occupazione italiana dell'Albania, settore Valona.",
    },
    {
        "nome": "Monte Col di Lana",
        "data_inizio": "1915-06-23",
        "data_fine": "1917-11-12",
        "luogo": "Dolomiti, Col di Lana",
        "aliases": ["Monte Col Di Lana", "Col Di Lana", "Col di Lana", "Lana"],
        "keywords": ["Col di Lana", "Col di Lana", "Lana", "Dolomiti", "Mine"],
        "descrizione": "Conquista del Col di Lana con mina apr-1916.",
    },
    {
        "nome": "Monte Nero",
        "data_inizio": "1915-06-23",
        "data_fine": "1917-09-12",
        "luogo": "Isonzo, Monte Nero",
        "aliases": ["Monte Nero", "Nero", "Krn"],
        "keywords": ["Monte Nero", "Krn", "Mte Nero"],
        "descrizione": "Conquista del Monte Nero giun-1915, prima operazione offensiva italiana.",
    },
    {
        "nome": "Settore di Tolmino",
        "data_inizio": "1915-06-23",
        "data_fine": "1917-10-24",
        "luogo": "Isonzo, Tolmino",
        "aliases": ["Settore Di Tolmino", "Tolmino", "Tolmin"],
        "keywords": ["Tolmino", "Tolmin", "Tolmein", "Kobarid"],
        "descrizione": "Settore del fronte Isonzo presso Tolmino, punto di rottura di Caporetto.",
    },
    # ─── Eventi WW2 ────────────────────────────────────────────────────────
    {
        "nome": "Operazione Achse",
        "data_inizio": "1943-09-08",
        "data_fine": "1945-05-08",
        "luogo": "Italia, Germania",
        "aliases": ["Achse", "Operazione Achse", "Armistizio", "8 settembre", "Disarmo"],
        "keywords": ["Achse", "armistizio", "8 settembre", "internati militari", "IMI", "disarmo"],
        "descrizione": "Disarmo delle forze armate italiane e deportazione nel Terzo Reich dopo l'8 settembre 1943.",
    },
    {
        "nome": "Eccidio di Cefalonia",
        "data_inizio": "1943-09-08",
        "data_fine": "1943-09-24",
        "luogo": "Cefalonia, Grecia",
        "aliases": ["Cefalonia", "Cephalonia", "Divisione Acqui", "Corfu", "Corfù"],
        "keywords": ["Cefalonia", "Cephalonia", "Acqui", "Corfu", "Corfù", "eccidio"],
        "descrizione": "Scontri e rappresaglia tedesca contro la Divisione Acqui a Cefalonia, settembre 1943.",
    },
    {
        "nome": "Campagna di Russia (ARMIR)",
        "data_inizio": "1941-07-01",
        "data_fine": "1943-03-31",
        "luogo": "Fronte orientale, Russia",
        "aliases": ["ARMIR", "Russia", "Fronte Orientale", "Don", "Stalingrado"],
        "keywords": ["Russia", "ARMIR", "Stalingrado", "Don", "Ucraina", "Renci", "Taganrog"],
        "descrizione": "Operazioni dell'ARMIR sul fronte orientale e ritirata invernale 1942-43.",
    },
    {
        "nome": "Battaglia di Tobruk",
        "data_inizio": "1941-01-01",
        "data_fine": "1942-06-21",
        "luogo": "Libia, Tobruk",
        "aliases": ["Tobruk", "Tobruch", "Tripoli", "Africa Settentrionale"],
        "keywords": ["Tobruk", "Tobruch", "Tripoli", "El Alamein", "Africa", "Libia"],
        "descrizione": "Caduta di Tobruk e cattura di migliaia di soldati italiani in Nord Africa.",
    },
    {
        "nome": "Mauthausen e Gusen",
        "data_inizio": "1943-09-08",
        "data_fine": "1945-05-05",
        "luogo": "Austria, Mauthausen",
        "aliases": ["Mauthausen", "Gusen", "Linz", "Campo di concentramento"],
        "keywords": ["Mauthausen", "Gusen", "Linz", "KZ", "concentramento"],
        "descrizione": "Internamento, lavoro forzato e morte nei campi del sistema Mauthausen-Gusen.",
    },
    {
        "nome": "Lavoro forzato nel Reich",
        "data_inizio": "1943-09-08",
        "data_fine": "1945-05-08",
        "luogo": "Germania, Terzo Reich",
        "aliases": ["Lavoro forzato", "Arbeitskommando", "Forzato", "Reich"],
        "keywords": ["lavoro forzato", "arbeitskommando", "forzato", "Berlino", "Amburgo", "Hannover", "Essen", "Dresda"],
        "descrizione": "Impiego di Internati Militari Italiani come manodopera coatta in Germania.",
    },
    {
        "nome": "Battaglia di Cassino",
        "data_inizio": "1944-01-17",
        "data_fine": "1944-05-19",
        "luogo": "Monte Cassino, Lazio",
        "aliases": ["Cassino", "Monte Cassino", "Gustav", "Linea Gustav"],
        "keywords": ["Cassino", "Gustav", "Montecassino", "Rapido", "Garigliano"],
        "descrizione": "Quattro battaglie per lo sfondamento della Linea Gustav, gen-mag 1944.",
    },
]


def main():
    parser = argparse.ArgumentParser(description="Legacy event linking (deprecated)")
    parser.add_argument("--dry-run", action="store_true", default=True,
                        help="Audit only, no DB writes (default)")
    parser.add_argument("--execute", action="store_true", default=False,
                        help="Execute with DB writes")
    args = parser.parse_args()

    if args.execute:
        args.dry_run = False
        print("WARNING: --execute mode. DB will be modified.")
        confirm = input("Type 'yes' to continue: ")
        if confirm.strip().lower() != "yes":
            print("Aborted.")
            return
    else:
        print("[DRY-RUN] No DB writes. Use --execute to apply.")

    # Read-only connection to main DB
    conn_ro = sqlite3.connect(str(DB), timeout=30)
    conn_ro.row_factory = sqlite3.Row
    conn_ro.execute("PRAGMA journal_mode=WAL")
    conn_ro.execute("PRAGMA query_only=ON")

    # Writable connection to event DB
    conn = sqlite3.connect(str(EDB))
    conn.row_factory = sqlite3.Row

    now = datetime.now().isoformat()

    # V7.3-FIX: Pre-load events with war period classification
    all_events = []
    for ev in EVENTI_1GM:
        ev_copy = dict(ev)
        ev_copy["war_period"] = _event_war_period(ev)
        all_events.append(ev_copy)
    wwi_events = [e for e in all_events if e["war_period"] == "WWI"]
    wwii_events = [e for e in all_events if e["war_period"] == "WWII"]

    # Check if already populated
    existing_events = 0
    existing_links = 0
    existing_caduti = 0
    existing_decorati = 0
    existing_doc = 0
    existing_fonti = 0
    try:
        existing_events = conn.execute("SELECT COUNT(*) FROM eventi_1gm").fetchone()[0]
        existing_links = conn.execute("SELECT COUNT(*) FROM event_links").fetchone()[0]
        existing_caduti = conn.execute("SELECT COUNT(*) FROM event_links WHERE link_type='soldato_caduto'").fetchone()[0]
        existing_decorati = conn.execute("SELECT COUNT(*) FROM event_links WHERE link_type='soldato_decorato'").fetchone()[0]
        existing_doc = conn.execute("SELECT COUNT(*) FROM event_links WHERE link_type='documento'").fetchone()[0]
        existing_fonti = conn.execute("SELECT COUNT(*) FROM event_links WHERE link_type='fonte_archivistica'").fetchone()[0]
    except sqlite3.OperationalError:
        pass

    # ─── 1. Crea tabella eventi_1gm (se non esiste) ────────────────────────
    if existing_events == 0:
        conn.execute("""CREATE TABLE IF NOT EXISTS eventi_1gm (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nome TEXT NOT NULL UNIQUE,
            data_inizio TEXT,
            data_fine TEXT,
            luogo TEXT,
            aliases TEXT,
            keywords TEXT,
            descrizione TEXT,
            created_at TEXT
        )""")
        for ev in EVENTI_1GM:
            conn.execute(
                "INSERT INTO eventi_1gm (nome, data_inizio, data_fine, luogo, aliases, keywords, descrizione, created_at) "
                "VALUES (?,?,?,?,?,?,?,?)",
                (ev["nome"], ev["data_inizio"], ev["data_fine"], ev["luogo"],
                 json.dumps(ev["aliases"], ensure_ascii=False),
                 json.dumps(ev["keywords"], ensure_ascii=False),
                 ev["descrizione"], now)
            )
        conn.commit()
        print(f"[eventi_1gm] {len(EVENTI_1GM)} eventi creati")
    else:
        print(f"[eventi_1gm] {existing_events} eventi gia esistenti, skip creazione")

    # ─── 2. Crea tabella event_links (se non esiste) ───────────────────────
    conn.execute("""CREATE TABLE IF NOT EXISTS event_links (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        evento_id INTEGER NOT NULL,
        target_table TEXT NOT NULL,
        target_id INTEGER NOT NULL,
        link_type TEXT NOT NULL,
        match_field TEXT,
        match_value TEXT,
        confidence REAL DEFAULT 0.5,
        created_at TEXT,
        FOREIGN KEY (evento_id) REFERENCES eventi_1gm(id)
    )""")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_event_links_evento ON event_links(evento_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_event_links_target ON event_links(target_table, target_id)")
    # V7.3-FIX: Add quarantine columns (additive, idempotent)
    for col, default in [("usable_as_evidence", 1), ("quarantined_at", None), ("quarantine_reason", None), ("war_period", None)]:
        try:
            if default is not None:
                conn.execute(f"ALTER TABLE event_links ADD COLUMN {col} INTEGER DEFAULT {default}")
            else:
                conn.execute(f"ALTER TABLE event_links ADD COLUMN {col} TEXT")
        except sqlite3.OperationalError:
            pass
    conn.commit()

    # V7.3-FIX: Load existing link keys to avoid duplicates (incremental, not skip-if-exists)
    existing_link_keys = set()
    try:
        for r in conn.execute("SELECT evento_id, target_table, target_id, link_type FROM event_links").fetchall():
            existing_link_keys.add((r["evento_id"], r["target_table"], r["target_id"], r["link_type"]))
    except sqlite3.OperationalError:
        pass
    print(f"[PRE] event_links esistenti: {len(existing_link_keys)}")

    # ─── 3. Collega caduti_albooro a eventi ────────────────────────────────
    # V7.3-FIX: Word-boundary match, temporal barrier (WWI only), incremental (no skip-if-exists)
    print("\n[1/5] Linking caduti_albooro -> eventi (luogo_morte)...")
    caduti = conn_ro.execute("SELECT id, luogo_morte, anno_morte FROM caduti_albooro").fetchall()
    print(f"  {len(caduti)} caduti da processare")
    linked = 0
    batch = []

    for c in caduti:
        lm = (c["luogo_morte"] or "").strip()
        if not lm or lm == "-":
            continue

        # V7.3-FIX: caduti_albooro is WWII — only match WWII events
        for ev in wwii_events:
            aliases = ev["aliases"]
            matched = False
            match_alias = None

            for alias in aliases:
                if len(alias) >= 4 and _word_boundary_match(alias, lm):
                    matched = True
                    match_alias = alias
                    break

            if matched:
                key = (None, "caduti_albooro", c["id"], "soldato_caduto")  # evento_id filled below
                # V7.3-FIX: No break — allow multi-event matching
                # But avoid duplicate links
                dup_key = (ev["nome"], "caduti_albooro", c["id"], "soldato_caduto")
                # Check against existing by event name → need event ID
                # We'll check via the batch + existing set
                batch.append((
                    ev["nome"], "caduti_albooro", c["id"], "soldato_caduto",
                    "luogo_morte", lm, 0.9, now, "WWII"
                ))
                linked += 1

    # V7.3-FIX: Resolve event names to IDs and filter duplicates
    event_name_to_id = {ev["nome"]: i+1 for i, ev in enumerate(EVENTI_1GM)}  # 1-based IDs
    filtered_batch = []
    for row in batch:
        ev_name = row[0]
        ev_id = event_name_to_id.get(ev_name)
        if not ev_id:
            continue
        key = (ev_id, row[1], row[2], row[3])
        if key in existing_link_keys:
            continue
        existing_link_keys.add(key)
        filtered_batch.append((ev_id, row[1], row[2], row[3], row[4], row[5], row[6], row[7], row[8]))

    if filtered_batch and not args.dry_run:
        conn.executemany(
            "INSERT INTO event_links (evento_id, target_table, target_id, link_type, match_field, match_value, confidence, created_at, war_period) "
            "VALUES (?,?,?,?,?,?,?,?,?)", filtered_batch
        )
        conn.commit()
    print(f"  {len(filtered_batch)} caduti collegati a eventi (WWII only, word-boundary)")

    # ─── 4. Collega decorati_nastroazzurro a eventi (per anno) ─────────────
    # V7.3-FIX: Temporal barrier — decorati is WWII, only match WWII events
    print("\n[2/5] Linking decorati_nastroazzurro -> eventi (anno_decorazione)...")
    decorati = conn_ro.execute("SELECT id, anno_decorazione FROM decorati_nastroazzurro").fetchall()
    print(f"  {len(decorati)} decorati da processare")
    linked_dec = 0
    batch_dec = []

    for d in decorati:
        anno = (d["anno_decorazione"] or "").strip()
        if not anno or not re.match(r"^19[0-9]{2}$", anno):
            continue
        anno_int = int(anno)

        for ev in wwii_events:
            di = ev["data_inizio"][:4] if ev["data_inizio"] else ""
            df = ev["data_fine"][:4] if ev["data_fine"] else ""
            if di and df:
                try:
                    if int(di) <= anno_int <= int(df):
                        span = int(df) - int(di)
                        if span <= 1:
                            conf = 0.6
                        elif span == 2:
                            conf = 0.4
                        else:
                            conf = 0.3
                        batch_dec.append((
                            ev["nome"], "decorati_nastroazzurro", d["id"], "soldato_decorato",
                            "anno_decorazione", anno, conf, now, "WWII"
                        ))
                        linked_dec += 1
                except ValueError:
                    pass

    filtered_dec = []
    for row in batch_dec:
        ev_id = event_name_to_id.get(row[0])
        if not ev_id:
            continue
        key = (ev_id, row[1], row[2], row[3])
        if key in existing_link_keys:
            continue
        existing_link_keys.add(key)
        filtered_dec.append((ev_id, row[1], row[2], row[3], row[4], row[5], row[6], row[7], row[8]))

    if filtered_dec and not args.dry_run:
        conn.executemany(
            "INSERT INTO event_links (evento_id, target_table, target_id, link_type, match_field, match_value, confidence, created_at, war_period) "
            "VALUES (?,?,?,?,?,?,?,?,?)", filtered_dec
        )
        conn.commit()
    print(f"  {len(filtered_dec)} decorati collegati a eventi (WWII only, match per anno)")

    # ─── 5. Collega archivio_documenti a eventi (title/description/place/creator/date_text) ──
    # V7.3-FIX: Word-boundary match, temporal barrier by doc year, incremental
    print("\n[3/5] Linking archivio_documenti -> eventi (text-match esteso)...")
    docs = conn_ro.execute(
        "SELECT rowid as id, title, description, provider, doc_type, source_url, "
        "thumbnail_url, creator, date_text, place, provider_collection "
        "FROM archivio_documenti"
    ).fetchall()
    print(f"  {len(docs)} documenti da processare")
    linked_doc = 0
    batch_doc = []

    for d in docs:
        text = " ".join(filter(None, [
            d["title"], d["description"], d["place"],
            d["creator"], d["date_text"], d["provider_collection"]
        ]))
        if not text.strip():
            continue

        # V7.3-FIX: Determine war period from date_text or year_start
        doc_year = None
        dt = (d["date_text"] or "").strip()
        year_match = re.search(r"(19[0-9]{2})", dt)
        if year_match:
            doc_year = int(year_match.group(1))

        for ev in all_events:
            # V7.3-FIX: Temporal barrier — skip events from wrong war period
            if doc_year:
                if ev["war_period"] == "WWI" and doc_year >= 1939:
                    continue
                if ev["war_period"] == "WWII" and doc_year < 1939:
                    continue

            keywords = ev["keywords"]
            aliases = ev["aliases"]
            matched = False
            match_kw = None
            confidence = 0.8

            for kw in keywords:
                if _word_boundary_match(kw, text):
                    matched = True
                    match_kw = kw
                    if _word_boundary_match(kw, d["title"] or ""):
                        confidence = 0.9
                    break

            if not matched:
                for alias in aliases:
                    if len(alias) >= 4 and _word_boundary_match(alias, text):
                        matched = True
                        match_kw = alias
                        confidence = 0.7
                        break

            if matched:
                batch_doc.append((
                    ev["nome"], "archivio_documenti", d["id"], "documento",
                    "text_match", match_kw, confidence, now, ev["war_period"]
                ))
                linked_doc += 1

    filtered_doc = []
    for row in batch_doc:
        ev_id = event_name_to_id.get(row[0])
        if not ev_id:
            continue
        key = (ev_id, row[1], row[2], row[3])
        if key in existing_link_keys:
            continue
        existing_link_keys.add(key)
        filtered_doc.append((ev_id, row[1], row[2], row[3], row[4], row[5], row[6], row[7], row[8]))

    if filtered_doc and not args.dry_run:
        conn.executemany(
            "INSERT INTO event_links (evento_id, target_table, target_id, link_type, match_field, match_value, confidence, created_at, war_period) "
            "VALUES (?,?,?,?,?,?,?,?,?)", filtered_doc
        )
        conn.commit()
    print(f"  {len(filtered_doc)} documenti collegati a eventi (word-boundary, temporal barrier)")

    # ─── 6. Collega fonti_indice a eventi (titolo/luogo/soggetti) ───────────
    # V7.3-FIX: Word-boundary match, no break on first, incremental
    print("\n[4/5] Linking fonti_indice -> eventi (titolo/luogo/soggetti_collegati)...")
    fonti = conn_ro.execute("SELECT id, titolo, luogo, soggetti_collegati, url_catalogo, url_file, archivio FROM fonti_indice").fetchall()
    print(f"  {len(fonti)} fonti da processare")
    linked_fon = 0
    batch_fon = []

    for f in fonti:
        text = " ".join(filter(None, [f["titolo"], f["luogo"], f["soggetti_collegati"]]))
        if not text.strip():
            continue

        for ev in all_events:
            keywords = ev["keywords"]
            aliases = ev["aliases"]
            matched = False
            match_kw = None

            for kw in keywords:
                if _word_boundary_match(kw, text):
                    matched = True
                    match_kw = kw
                    break

            if not matched:
                for alias in aliases:
                    if len(alias) >= 4 and _word_boundary_match(alias, text):
                        matched = True
                        match_kw = alias
                        break

            if matched:
                batch_fon.append((
                    ev["nome"], "fonti_indice", f["id"], "fonte_archivistica",
                    "titolo_luogo_soggetti", match_kw, 0.7, now, ev["war_period"]
                ))
                linked_fon += 1
                # V7.3-FIX: No break — allow multi-event matching

    filtered_fon = []
    for row in batch_fon:
        ev_id = event_name_to_id.get(row[0])
        if not ev_id:
            continue
        key = (ev_id, row[1], row[2], row[3])
        if key in existing_link_keys:
            continue
        existing_link_keys.add(key)
        filtered_fon.append((ev_id, row[1], row[2], row[3], row[4], row[5], row[6], row[7], row[8]))

    if filtered_fon and not args.dry_run:
        conn.executemany(
            "INSERT INTO event_links (evento_id, target_table, target_id, link_type, match_field, match_value, confidence, created_at, war_period) "
            "VALUES (?,?,?,?,?,?,?,?,?)", filtered_fon
        )
        conn.commit()
    print(f"  {len(filtered_fon)} fonti collegate a eventi (word-boundary, multi-event)")

    # ─── 7. Collega caduti_cwgc WW1 a eventi (cimitero ↔ alias) ──────────
    # V7.3-FIX: Word-boundary match, WWI events only, incremental
    print("\n[5/8] Linking caduti_cwgc WW1 -> eventi (cimitero)...")
    cwgc = conn_ro.execute(
        "SELECT id, cimitero, paese_cimitero FROM caduti_cwgc WHERE guerra = 'World War 1'"
    ).fetchall()
    print(f"  {len(cwgc)} caduti CWGC WW1 da processare")
    linked_cwgc = 0
    batch_cwgc = []

    for c in cwgc:
        cim = (c["cimitero"] or "").strip()
        paese = (c["paese_cimitero"] or "").strip()
        text = cim + " " + paese
        if not text.strip():
            continue

        # V7.3-FIX: CWGC WW1 → only WWI events
        for ev in wwi_events:
            aliases = ev["aliases"]
            matched = False
            match_alias = None

            for alias in aliases:
                if len(alias) >= 4 and _word_boundary_match(alias, text):
                    matched = True
                    match_alias = alias
                    break

            if matched:
                batch_cwgc.append((
                    ev["nome"], "caduti_cwgc", c["id"], "soldato_caduto_cwgc",
                    "cimitero", cim, 0.7, now, "WWI"
                ))
                linked_cwgc += 1
                # V7.3-FIX: No break — allow multi-event

    filtered_cwgc = []
    for row in batch_cwgc:
        ev_id = event_name_to_id.get(row[0])
        if not ev_id:
            continue
        key = (ev_id, row[1], row[2], row[3])
        if key in existing_link_keys:
            continue
        existing_link_keys.add(key)
        filtered_cwgc.append((ev_id, row[1], row[2], row[3], row[4], row[5], row[6], row[7], row[8]))

    if filtered_cwgc and not args.dry_run:
        conn.executemany(
            "INSERT INTO event_links (evento_id, target_table, target_id, link_type, match_field, match_value, confidence, created_at, war_period) "
            "VALUES (?,?,?,?,?,?,?,?,?)", filtered_cwgc
        )
        conn.commit()
    print(f"  {len(filtered_cwgc)} caduti CWGC WW1 collegati a eventi (word-boundary, WWI only)")

    # ─── 8. Collega caduti_ministero a eventi (luogo_sepoltura/nazione_decesso) ──
    # V7.3-FIX: Word-boundary match, WWII events only, incremental
    print("\n[6/8] Linking caduti_ministero -> eventi (luogo_sepoltura/nazione_decesso)...")
    minist = conn_ro.execute(
        "SELECT id, luogo_sepoltura, nazione_decesso, data_decesso FROM caduti_ministero"
    ).fetchall()
    print(f"  {len(minist)} caduti ministero da processare")
    linked_min = 0
    batch_min = []

    for c in minist:
        sep = (c["luogo_sepoltura"] or "").strip()
        naz = (c["nazione_decesso"] or "").strip()
        text = sep + " " + naz
        if not text.strip():
            continue

        # V7.3-FIX: caduti_ministero is WWII — only match WWII events
        for ev in wwii_events:
            aliases = ev["aliases"]
            matched = False
            match_alias = None

            for alias in aliases:
                if len(alias) >= 4 and _word_boundary_match(alias, text):
                    matched = True
                    match_alias = alias
                    break

            if matched:
                batch_min.append((
                    ev["nome"], "caduti_ministero", c["id"], "soldato_caduto_ministero",
                    "luogo_sepoltura", sep or naz, 0.6, now, "WWII"
                ))
                linked_min += 1

    filtered_min = []
    for row in batch_min:
        ev_id = event_name_to_id.get(row[0])
        if not ev_id:
            continue
        key = (ev_id, row[1], row[2], row[3])
        if key in existing_link_keys:
            continue
        existing_link_keys.add(key)
        filtered_min.append((ev_id, row[1], row[2], row[3], row[4], row[5], row[6], row[7], row[8]))

    if filtered_min and not args.dry_run:
        conn.executemany(
            "INSERT INTO event_links (evento_id, target_table, target_id, link_type, match_field, match_value, confidence, created_at, war_period) "
            "VALUES (?,?,?,?,?,?,?,?,?)", filtered_min
        )
        conn.commit()
    print(f"  {len(filtered_min)} caduti ministero collegati a eventi (word-boundary, WWII only)")

    # ─── 9. Collega internati WW2 a eventi (luogo_cattura/luogo_internamento) ──
    # V7.3-FIX: Word-boundary match, WWII events only, incremental
    print("\n[7/8] Linking internati -> eventi WW2 (luogo_cattura/internamento)...")
    internati = conn_ro.execute(
        "SELECT id, luogo_cattura, luogo_internamento, arbeitskommando, sorte, raw_text FROM internati"
    ).fetchall()
    print(f"  {len(internati)} internati da processare")
    linked_int = 0
    batch_int = []

    for i in internati:
        text = " ".join(filter(None, [
            i["luogo_cattura"], i["luogo_internamento"],
            i["arbeitskommando"], i["sorte"], i["raw_text"]
        ]))
        if not text.strip():
            continue

        # V7.3-FIX: internati is WWII — only match WWII events
        for ev in wwii_events:
            keywords = ev["keywords"]
            aliases = ev["aliases"]
            matched = False
            match_kw = None

            for kw in keywords:
                if len(kw) >= 4 and _word_boundary_match(kw, text):
                    matched = True
                    match_kw = kw
                    break

            if not matched:
                for alias in aliases:
                    if len(alias) >= 4 and _word_boundary_match(alias, text):
                        matched = True
                        match_kw = alias
                        break

            if matched:
                batch_int.append((
                    ev["nome"], "internati", i["id"], "internato_ww2",
                    "luogo_text", match_kw, 0.7, now, "WWII"
                ))
                linked_int += 1
                # V7.3-FIX: No break — allow multi-event

    filtered_int = []
    for row in batch_int:
        ev_id = event_name_to_id.get(row[0])
        if not ev_id:
            continue
        key = (ev_id, row[1], row[2], row[3])
        if key in existing_link_keys:
            continue
        existing_link_keys.add(key)
        filtered_int.append((ev_id, row[1], row[2], row[3], row[4], row[5], row[6], row[7], row[8]))

    if filtered_int and not args.dry_run:
        conn.executemany(
            "INSERT INTO event_links (evento_id, target_table, target_id, link_type, match_field, match_value, confidence, created_at, war_period) "
            "VALUES (?,?,?,?,?,?,?,?,?)", filtered_int
        )
        conn.commit()
    print(f"  {len(filtered_int)} internati collegati a eventi (word-boundary, WWII only)")

    # ─── 10. Statistiche finali ────────────────────────────────────────────
    print("\n[8/8] Statistiche finali")
    print("=" * 60)

    total = conn.execute("SELECT COUNT(*) FROM event_links").fetchone()[0]
    print(f"Totale event_links: {total}")

    print("\nPer evento:")
    for r in conn.execute(
        "SELECT e.nome, COUNT(el.id) as n, "
        "SUM(CASE WHEN el.link_type='soldato_caduto' THEN 1 ELSE 0 END) as caduti, "
        "SUM(CASE WHEN el.link_type='soldato_decorato' THEN 1 ELSE 0 END) as decorati, "
        "SUM(CASE WHEN el.link_type='soldato_caduto_cwgc' THEN 1 ELSE 0 END) as cwgc, "
        "SUM(CASE WHEN el.link_type='soldato_caduto_ministero' THEN 1 ELSE 0 END) as minist, "
        "SUM(CASE WHEN el.link_type='documento' THEN 1 ELSE 0 END) as documenti, "
        "SUM(CASE WHEN el.link_type='fonte_archivistica' THEN 1 ELSE 0 END) as fonti, "
        "SUM(CASE WHEN el.link_type='internato_ww2' THEN 1 ELSE 0 END) as internati "
        "FROM eventi_1gm e LEFT JOIN event_links el ON e.id=el.evento_id "
        "GROUP BY e.id ORDER BY n DESC"
    ).fetchall():
        print(f"  {r['nome']:30s}  total={r['n']:>6}  caduti={r['caduti'] or 0:>5}  dec={r['decorati'] or 0:>5}  cwgc={r['cwgc'] or 0:>4}  min={r['minist'] or 0:>4}  doc={r['documenti'] or 0:>3}  fon={r['fonti'] or 0:>3}  int={r['internati'] or 0:>3}")

    print("\nPer link_type:")
    for r in conn.execute(
        "SELECT link_type, COUNT(*) as n FROM event_links GROUP BY link_type ORDER BY n DESC"
    ).fetchall():
        print(f"  {r['link_type']:30s}  n={r['n']:>6}")

    conn.close()
    conn_ro.close()
    print("\nDONE")


if __name__ == "__main__":
    main()

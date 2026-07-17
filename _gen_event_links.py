#!/usr/bin/env python3
"""
Pipeline event-centric per 1GM.
Crea:
1. Tabella eventi_1gm con battaglie/eventi canonici
2. Tabella event_links che collega eventi a soldati, documenti, fonti, diari, immagini
3. Query engine che dato un evento aggrega tutti i dati e risale alle fonti esterne
"""
import sqlite3, json, re, os
from datetime import datetime
from pathlib import Path

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
    # Read-only connection to main DB
    conn_ro = sqlite3.connect(str(DB), timeout=30)
    conn_ro.row_factory = sqlite3.Row
    conn_ro.execute("PRAGMA journal_mode=WAL")
    conn_ro.execute("PRAGMA query_only=ON")

    # Writable connection to event DB
    conn = sqlite3.connect(str(EDB))
    conn.row_factory = sqlite3.Row

    now = datetime.now().isoformat()

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
    if existing_links == 0:
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

    # ─── 3. Collega caduti_albooro a eventi ────────────────────────────────
    if existing_caduti == 0:
        print("\n[1/5] Linking caduti_albooro -> eventi (luogo_morte)...")
        caduti = conn_ro.execute("SELECT id, luogo_morte, anno_morte FROM caduti_albooro").fetchall()
        print(f"  {len(caduti)} caduti da processare")
        linked = 0
        batch = []

        for c in caduti:
            lm = (c["luogo_morte"] or "").strip()
            if not lm or lm == "-":
                continue
            lm_up = lm.upper()

            for ev in conn.execute("SELECT id, aliases, keywords FROM eventi_1gm").fetchall():
                aliases = json.loads(ev["aliases"])
                matched = False
                match_alias = None

                for alias in aliases:
                    if alias.upper() in lm_up or lm_up in alias.upper():
                        if len(alias) >= 4:
                            matched = True
                            match_alias = alias
                            break

                if matched:
                    batch.append((
                        ev["id"], "caduti_albooro", c["id"], "soldato_caduto",
                        "luogo_morte", lm, 0.9, now
                    ))
                    linked += 1
                    break

        if batch:
            conn.executemany(
                "INSERT INTO event_links (evento_id, target_table, target_id, link_type, match_field, match_value, confidence, created_at) "
                "VALUES (?,?,?,?,?,?,?,?)", batch
            )
            conn.commit()
        print(f"  {linked} caduti collegati a eventi")
    else:
        print(f"\n[1/5] caduti_albooro: {existing_caduti} link gia esistenti, skip")

    # ─── 4. Collega decorati_nastroazzurro a eventi (per anno) ─────────────
    if existing_decorati == 0:
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

            for ev in conn.execute("SELECT id, data_inizio, data_fine FROM eventi_1gm").fetchall():
                di = ev["data_inizio"][:4] if ev["data_inizio"] else ""
                df = ev["data_fine"][:4] if ev["data_fine"] else ""
                if di and df:
                    try:
                        if int(di) <= anno_int <= int(df):
                            # Variable confidence: shorter event span = higher confidence
                            span = int(df) - int(di)
                            if span <= 1:
                                conf = 0.6
                            elif span == 2:
                                conf = 0.4
                            else:
                                conf = 0.3
                            batch_dec.append((
                                ev["id"], "decorati_nastroazzurro", d["id"], "soldato_decorato",
                                "anno_decorazione", anno, conf, now
                            ))
                            linked_dec += 1
                    except ValueError:
                        pass

        if batch_dec:
            conn.executemany(
                "INSERT INTO event_links (evento_id, target_table, target_id, link_type, match_field, match_value, confidence, created_at) "
                "VALUES (?,?,?,?,?,?,?,?)", batch_dec
            )
            conn.commit()
        print(f"  {linked_dec} decorati collegati a eventi (match per anno, confidence bassa)")
    else:
        print(f"\n[2/5] decorati_nastroazzurro: {existing_decorati} link gia esistenti, skip")

    # ─── 5. Collega archivio_documenti a eventi (title/description/place/creator/date_text) ──
    if existing_doc == 0:
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
            # Combina tutti i campi testuali per il match
            text = " ".join(filter(None, [
                d["title"], d["description"], d["place"],
                d["creator"], d["date_text"], d["provider_collection"]
            ])).upper()
            if not text.strip():
                continue

            for ev in conn.execute("SELECT id, keywords, aliases, nome FROM eventi_1gm").fetchall():
                keywords = json.loads(ev["keywords"])
                aliases = json.loads(ev["aliases"])
                matched = False
                match_kw = None
                confidence = 0.8

                for kw in keywords:
                    kw_up = kw.upper()
                    if kw_up in text:
                        matched = True
                        match_kw = kw
                        # Higher confidence if match in title
                        if kw_up in (d["title"] or "").upper():
                            confidence = 0.9
                        break

                if not matched:
                    for alias in aliases:
                        if len(alias) >= 4 and alias.upper() in text:
                            matched = True
                            match_kw = alias
                            confidence = 0.7
                            break

                if matched:
                    batch_doc.append((
                        ev["id"], "archivio_documenti", d["id"], "documento",
                        "text_match", match_kw, confidence, now
                    ))
                    linked_doc += 1
                    # Non fare break: un documento può matchare più eventi

        if batch_doc:
            conn.executemany(
                "INSERT INTO event_links (evento_id, target_table, target_id, link_type, match_field, match_value, confidence, created_at) "
                "VALUES (?,?,?,?,?,?,?,?)", batch_doc
            )
            conn.commit()
        print(f"  {linked_doc} documenti collegati a eventi (match multi-evento)")
    else:
        print(f"\n[3/5] archivio_documenti: {existing_doc} link gia esistenti, skip")

    # ─── 6. Collega fonti_indice a eventi (titolo/luogo/soggetti) ───────────
    if existing_fonti == 0:
        print("\n[4/5] Linking fonti_indice -> eventi (titolo/luogo/soggetti_collegati)...")
        fonti = conn_ro.execute("SELECT id, titolo, luogo, soggetti_collegati, url_catalogo, url_file, archivio FROM fonti_indice").fetchall()
        print(f"  {len(fonti)} fonti da processare")
        linked_fon = 0
        batch_fon = []

        for f in fonti:
            text = " ".join(filter(None, [f["titolo"], f["luogo"], f["soggetti_collegati"]])).upper()
            if not text.strip():
                continue

            for ev in conn.execute("SELECT id, keywords, aliases, nome FROM eventi_1gm").fetchall():
                keywords = json.loads(ev["keywords"])
                aliases = json.loads(ev["aliases"])
                matched = False
                match_kw = None

                for kw in keywords:
                    if kw.upper() in text:
                        matched = True
                        match_kw = kw
                        break

                if not matched:
                    for alias in aliases:
                        if len(alias) >= 4 and alias.upper() in text:
                            matched = True
                            match_kw = alias
                            break

                if matched:
                    batch_fon.append((
                        ev["id"], "fonti_indice", f["id"], "fonte_archivistica",
                        "titolo_luogo_soggetti", match_kw, 0.7, now
                    ))
                    linked_fon += 1
                    break

        if batch_fon:
            conn.executemany(
                "INSERT INTO event_links (evento_id, target_table, target_id, link_type, match_field, match_value, confidence, created_at) "
                "VALUES (?,?,?,?,?,?,?,?)", batch_fon
            )
            conn.commit()
        print(f"  {linked_fon} fonti collegate a eventi")
    else:
        print(f"\n[4/5] fonti_indice: {existing_fonti} link gia esistenti, skip")

    # ─── 7. Collega caduti_cwgc WW1 a eventi (cimitero ↔ aliases) ──────────
    existing_cwgc = 0
    try:
        existing_cwgc = conn.execute("SELECT COUNT(*) FROM event_links WHERE link_type='soldato_caduto_cwgc'").fetchone()[0]
    except sqlite3.OperationalError:
        pass

    if existing_cwgc == 0:
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
            text = (cim + " " + paese).upper()
            if not text.strip():
                continue

            for ev in conn.execute("SELECT id, aliases, keywords FROM eventi_1gm").fetchall():
                aliases = json.loads(ev["aliases"])
                matched = False
                match_alias = None

                for alias in aliases:
                    if len(alias) >= 4 and (alias.upper() in text or text in alias.upper()):
                        matched = True
                        match_alias = alias
                        break

                if matched:
                    batch_cwgc.append((
                        ev["id"], "caduti_cwgc", c["id"], "soldato_caduto_cwgc",
                        "cimitero", cim, 0.7, now
                    ))
                    linked_cwgc += 1
                    break

        if batch_cwgc:
            conn.executemany(
                "INSERT INTO event_links (evento_id, target_table, target_id, link_type, match_field, match_value, confidence, created_at) "
                "VALUES (?,?,?,?,?,?,?,?)", batch_cwgc
            )
            conn.commit()
        print(f"  {linked_cwgc} caduti CWGC WW1 collegati a eventi")
    else:
        print(f"\n[5/8] caduti_cwgc WW1: {existing_cwgc} link gia esistenti, skip")

    # ─── 8. Collega caduti_ministero a eventi (luogo_sepoltura/nazione_decesso) ──
    existing_min = 0
    try:
        existing_min = conn.execute("SELECT COUNT(*) FROM event_links WHERE link_type='soldato_caduto_ministero'").fetchone()[0]
    except sqlite3.OperationalError:
        pass

    if existing_min == 0:
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
            text = (sep + " " + naz).upper()
            if not text.strip():
                continue

            for ev in conn.execute("SELECT id, aliases, keywords FROM eventi_1gm").fetchall():
                aliases = json.loads(ev["aliases"])
                matched = False
                match_alias = None

                for alias in aliases:
                    if len(alias) >= 4 and alias.upper() in text:
                        matched = True
                        match_alias = alias
                        break

                if matched:
                    batch_min.append((
                        ev["id"], "caduti_ministero", c["id"], "soldato_caduto_ministero",
                        "luogo_sepoltura", sep or naz, 0.6, now
                    ))
                    linked_min += 1
                    break

        if batch_min:
            conn.executemany(
                "INSERT INTO event_links (evento_id, target_table, target_id, link_type, match_field, match_value, confidence, created_at) "
                "VALUES (?,?,?,?,?,?,?,?)", batch_min
            )
            conn.commit()
        print(f"  {linked_min} caduti ministero collegati a eventi")
    else:
        print(f"\n[6/8] caduti_ministero: {existing_min} link gia esistenti, skip")

    # ─── 9. Collega internati WW2 a eventi (luogo_cattura/luogo_internamento) ──
    existing_int = 0
    try:
        existing_int = conn.execute("SELECT COUNT(*) FROM event_links WHERE link_type='internato_ww2'").fetchone()[0]
    except sqlite3.OperationalError:
        pass

    if existing_int == 0:
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
            ])).upper()
            if not text.strip():
                continue

            for ev in conn.execute("SELECT id, keywords, aliases, nome FROM eventi_1gm").fetchall():
                keywords = json.loads(ev["keywords"])
                aliases = json.loads(ev["aliases"])
                matched = False
                match_kw = None

                for kw in keywords:
                    if len(kw) >= 4 and kw.upper() in text:
                        matched = True
                        match_kw = kw
                        break

                if not matched:
                    for alias in aliases:
                        if len(alias) >= 4 and alias.upper() in text:
                            matched = True
                            match_kw = alias
                            break

                if matched:
                    batch_int.append((
                        ev["id"], "internati", i["id"], "internato_ww2",
                        "luogo_text", match_kw, 0.7, now
                    ))
                    linked_int += 1
                    break

        if batch_int:
            conn.executemany(
                "INSERT INTO event_links (evento_id, target_table, target_id, link_type, match_field, match_value, confidence, created_at) "
                "VALUES (?,?,?,?,?,?,?,?)", batch_int
            )
            conn.commit()
        print(f"  {linked_int} internati collegati a eventi")
    else:
        print(f"\n[7/8] internati: {existing_int} link gia esistenti, skip")

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

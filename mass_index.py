"""Pipeline di indicizzazione massiva multi-archivio.

Modalità di esecuzione:
    python mass_index.py soldati   -- cerca fonti per ogni soldato IMI
    python mass_index.py reparti   -- cerca fonti per unità militari
    python mass_index.py eventi    -- cerca fonti per eventi/battaglie + giornali
    python mass_index.py luoghi    -- cerca fonti per luoghi/movimentazioni
    python mass_index.py all       -- tutte le pipeline in sequenza

Per ogni query:
  1. federated_search su tutti i provider reali
  2. Salva metadati + URL diretto in fonti_indice (upsert)
  3. Collega via collegamenti (soggetto ↔ fonte)
  4. Log progresso in mass_index.log

Parallelismo: usa ThreadPoolExecutor con max_workers=4 per non
  sovraccaricare i provider (rispetta rate limit).
"""

import argparse
import logging
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path

from database import get_conn
from source_providers.federation import federated_search, get_registry

LOG_FILE = Path(__file__).parent / "mass_index.log"
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(LOG_FILE, encoding="utf-8"),
        logging.StreamHandler(sys.stdout),
    ],
)
log = logging.getLogger("mass_index")

MAX_WORKERS    = 4     # thread paralleli verso provider esterni
BATCH_SLEEP    = 0.3   # secondi tra batch per rispettare rate limit
MIN_SCORE      = 0.25  # scarta risultati con score troppo basso
MAX_PER_QUERY  = 15    # risultati massimi da salvare per query


# ─── Helper validazione URL ────────────────────────────────────────────────────

import re

# Pattern URL che sono form/pagine di ricerca, non record specifici.
_SEARCH_URL_PATTERNS = [
    # Arolsen
    "collections.arolsen-archives.org/en/search/",
    "collections.arolsen-archives.org/de/search/",
    # TNA discovery results
    "discovery.nationalarchives.gov.uk/results",
    # LAC
    "bac-lac.gc.ca/eng/search/",
    # SHD
    "memoiredeshommes.sga.defense.gouv.fr/fr/search",
    # Archivportal-D
    "archivportal-d.de/search/",
    # DDB
    "deutsche-digitale-bibliothek.de/search/",
    # Europeana search
    "europeana.eu/it/search",
    "europeana.eu/en/search",
    "europeana.eu/api/v2/search.json",
    # Internet Archive search
    "archive.org/search",
    # Gallica search portals
    "gallica.bnf.fr/services/engine/solr/suggest",
    "gallica.bnf.fr/html/und/fr/s/inventaire",
    # HathiTrust search
    "catalog.hathitrust.org/Search/Home",
    "catalog.hathitrust.org/api/volumes",
    # Antenati
    "antenati.cultura.gov.it/search/",
    # CWGC search
    "cwgc.org/find-records/search/",
    # AWM
    "awm.gov.au/search",
    # ABMC
    "abmc.gov/search",
    # IWM Lives
    "livesofthefirstworldwar.iwm.org.uk/search",
    # Grand Memorial
    "memorial-genweb.org/intern/_search",
]

# Pattern generici di URL di ricerca (regex).
_GENERIC_SEARCH_RE = re.compile(
    r"(/search[/?]|/search\.aspx|/search\.php|/results\?|/search\?|search\?query=|q=[^&]+&search=|s=[^&]+&search=)",
    re.IGNORECASE,
)

# Pattern che indicano un record/documento diretto.
_DIRECT_RECORD_RE = re.compile(
    r"(/document/|/record/|/item/|/details/|/archive/|/person/|/unit/|/reference/|/permalink/|/ark:/|/download/|/view/|\.pdf\b|\.jpg\b|\.png\b)",
    re.IGNORECASE,
)


def _is_search_page_url(url: str) -> bool:
    """True se l'URL punta a una pagina/form di ricerca, non a un record specifico."""
    if not url:
        return False
    u = url.lower()
    for pat in _SEARCH_URL_PATTERNS:
        if pat in u:
            return True
    if _GENERIC_SEARCH_RE.search(u):
        return True
    return False


def _is_direct_record_url(url: str) -> bool:
    """True se l'URL sembra puntare a un record/documento specifico."""
    if not url:
        return False
    return bool(_DIRECT_RECORD_RE.search(url.lower()))


def _matches_entity(meta: dict, cues: dict) -> bool:
    """Verifica che la fonte faccia riferimento all'entità cercata.

    Per persone richiede che il cognome (o nome) compaia nel titolo,
    descrizione o URL, a meno che l'URL non sia un record diretto.
    """
    cues = cues or {}
    persona = cues.get("persona") or ""
    if not persona:
        return True
    url = (meta.get("url_catalogo") or "") + " " + (meta.get("url_file") or "")
    if _is_direct_record_url(url):
        return True
    tokens = persona.upper().split()
    haystack = " ".join([
        (meta.get("titolo") or ""),
        (meta.get("note") or ""),
        (meta.get("segnatura") or ""),
        url,
    ]).upper()
    # Richiedi almeno il match di cognome o nome se persona è "COGNOME NOME"
    for token in tokens:
        if len(token) >= 2 and token in haystack:
            return True
    return False


# ─── Helper DB ─────────────────────────────────────────────────────────────────

def _upsert_fonte(meta: dict) -> int:
    """Inserisce o aggiorna una fonte in fonti_indice. Ritorna id."""
    conn = get_conn()
    now  = datetime.now().isoformat(timespec="seconds")
    row  = conn.execute(
        "SELECT id FROM fonti_indice WHERE archivio IS ? AND segnatura IS ? AND titolo IS ?",
        (meta.get("archivio"), meta.get("segnatura",""), meta.get("titolo",""))
    ).fetchone()
    if row:
        fid = row[0]
        conn.execute(
            "UPDATE fonti_indice SET url_catalogo=?, url_file=?, access_type=?, "
            "confidence=?, note=?, last_checked_at=? WHERE id=?",
            (meta.get("url_catalogo",""), meta.get("url_file",""),
             meta.get("access_type","online"), meta.get("confidence", 0.5),
             meta.get("note","")[:500], now, fid)
        )
    else:
        conn.execute(
            "INSERT OR IGNORE INTO fonti_indice "
            "(archivio, segnatura, titolo, tipo_fonte, url_catalogo, url_file, "
            "access_type, confidence, note, created_at) VALUES (?,?,?,?,?,?,?,?,?,?)",
            (meta.get("archivio",""), meta.get("segnatura",""), meta.get("titolo","")[:200],
             meta.get("tipo_fonte",""), meta.get("url_catalogo",""), meta.get("url_file",""),
             meta.get("access_type","online"), meta.get("confidence", 0.5),
             meta.get("note","")[:500], now)
        )
        fid = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
    conn.commit()
    conn.close()
    return fid


def _collegamento_exists(sogg_tab: str, sogg_id: int, fonte_id: int) -> bool:
    conn = get_conn()
    r = conn.execute(
        "SELECT 1 FROM collegamenti WHERE tabella_origine=? AND record_id=? AND "
        "entita_id=? LIMIT 1",
        (sogg_tab, sogg_id, fonte_id)
    ).fetchone()
    conn.close()
    return r is not None


def _add_collegamento(sogg_tab: str, sogg_id: int, fonte_id: int, tipo: str = "fonte"):
    if _collegamento_exists(sogg_tab, sogg_id, fonte_id):
        return
    conn = get_conn()
    try:
        now = datetime.now().isoformat(timespec='seconds')
        conn.execute(
            "INSERT OR IGNORE INTO collegamenti (tabella_origine, record_id, entita_id, tipo_collegamento, elaborato_il) "
            "VALUES (?,?,?,?,?)",
            (sogg_tab, sogg_id, fonte_id, tipo, now)
        )
        conn.commit()
    except Exception:
        pass
    finally:
        conn.close()


# ─── Indicizzazione singola query ──────────────────────────────────────────────

def index_query(query: str, cues: dict, sogg_tab: str, sogg_id: int,
                providers_filter: list = None) -> int:
    """Cerca su tutti i provider, salva risultati, ritorna n fonti nuove."""
    try:
        results = federated_search(
            query,
            cues=cues,
            providers=providers_filter,
            filters={"page_size": 20},
        )
    except Exception as e:
        log.warning("federated_search error per '%s': %s", query, e)
        return 0

    saved = 0
    for r in results:
        if r.get("error"):
            continue
        score = r.get("score", 0.0)
        if score < MIN_SCORE:
            continue
        url  = r.get("direct_url") or r.get("catalog_url") or ""
        if not url or _is_search_page_url(url):
            continue

        meta = {
            "archivio":    r.get("archivio") or r.get("provider", ""),
            "segnatura":   r.get("provider_record_id") or "",
            "titolo":      (r.get("titolo") or r.get("title") or query)[:200],
            "tipo_fonte":  r.get("source_type") or "",
            "url_catalogo": url,
            "url_file":    r.get("direct_url") or "",
            "access_type": r.get("access_type") or "online",
            "confidence":  round(score, 3),
            "note":        (r.get("description") or "")[:400],
        }
        if not _matches_entity(meta, cues):
            continue
        try:
            fid = _upsert_fonte(meta)
            if sogg_id:
                _add_collegamento(sogg_tab, sogg_id, fid)
            saved += 1
        except Exception as e:
            log.debug("upsert error: %s — %s", query, e)

        if saved >= MAX_PER_QUERY:
            break

    return saved


# ─── Pipeline SOLDATI ──────────────────────────────────────────────────────────

def pipeline_soldati(limit: int = None, offset: int = 0):
    """Cerca fonti per ogni soldato IMI per cognome+nome su tutti i provider.

    Priorità: Arolsen (ITS), Bundesarchiv, NARA, Onorcaduti, CWGC, Europeana,
              Gallica, Internet Archive, HathiTrust, TNA, AWM, Antenati.
    """
    log.info("=== PIPELINE SOLDATI (offset=%d, limit=%s) ===", offset, limit)
    conn = get_conn()
    conn.row_factory = lambda c, r: dict(zip([col[0] for col in c.description], r))
    q = "SELECT id, cognome, nome FROM internati WHERE cognome IS NOT NULL AND cognome != '' ORDER BY id"
    if limit:
        q += f" LIMIT {limit} OFFSET {offset}"
    rows = conn.execute(q).fetchall()
    conn.close()
    log.info("Soldati da processare: %d", len(rows))

    total_saved = 0
    done = 0

    # Provider più rilevanti per soldati IMI — esclude provider solo UK/AUS/FR
    SOLDATI_PROVIDERS = [
        "arolsen", "bundesarchiv", "nara", "cwgc", "europeana",
        "internet_archive", "hathitrust", "gallica", "tna", "awm",
        "antenati", "wikitree", "iwm_lives",
    ]

    def process(row):
        cognome = (row["cognome"] or "").strip().upper()
        nome    = (row["nome"]    or "").strip()
        query   = f"{cognome} {nome}".strip()
        if len(query) < 3:
            return 0
        cues = {"persona": query, "cognome": cognome, "nome": nome,
                "nazione": "Italia", "periodo": "1943-1945"}
        saved = index_query(query, cues, "internati", row["id"], SOLDATI_PROVIDERS)
        return saved

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as ex:
        futures = {ex.submit(process, row): row for row in rows}
        for fut in as_completed(futures):
            done += 1
            try:
                n = fut.result()
                total_saved += n
            except Exception as e:
                log.warning("Errore soldato: %s", e)
            if done % 100 == 0:
                log.info("Soldati: %d/%d — fonti salvate: %d", done, len(rows), total_saved)
                time.sleep(BATCH_SLEEP)

    log.info("SOLDATI completato: %d soldati, %d fonti salvate", done, total_saved)
    return total_saved


# ─── Pipeline REPARTI ──────────────────────────────────────────────────────────

def pipeline_reparti():
    """Cerca fonti per unità militari dal DB entita (tipo='unita').

    Include: diari di guerra, ordini del giorno, rapporti, fotografie.
    Archivi target: USSME, NARA T-315 (diari div. tedesche), TNA, Bundesarchiv,
                    Internet Archive, Europeana, HathiTrust.
    """
    log.info("=== PIPELINE REPARTI ===")
    conn = get_conn()
    conn.row_factory = lambda c, r: dict(zip([col[0] for col in c.description], r))
    rows = conn.execute(
        "SELECT id, valore, contesto FROM entita WHERE tipo='unita' ORDER BY id"
    ).fetchall()
    conn.close()
    log.info("Unità da processare: %d", len(rows))

    REPARTI_PROVIDERS = [
        "nara", "bundesarchiv", "tna", "ussme", "internet_archive",
        "europeana", "hathitrust", "ddb", "archivportal_d",
    ]

    total_saved = 0
    done = 0

    def process(row):
        valore = (row["valore"] or "").strip()
        if len(valore) < 4:
            return 0
        # Cerca sia il nome originale che varianti tedesche/inglesi
        queries = [valore]
        # Aggiungi "war diary" per trovare diari su TNA/AWM
        if any(k in valore.lower() for k in ["divisione", "reggimento", "battaglione", "brigata"]):
            queries.append(f"{valore} war diary")
            queries.append(f"{valore} Kriegstagebuch")
        saved = 0
        for q in queries:
            cues = {"unita": valore, "periodo": "1943-1945", "nazione": "Italia"}
            saved += index_query(q, cues, "entita", row["id"], REPARTI_PROVIDERS)
        return saved

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as ex:
        futures = {ex.submit(process, row): row for row in rows}
        for fut in as_completed(futures):
            done += 1
            try:
                total_saved += fut.result()
            except Exception as e:
                log.warning("Errore reparto: %s", e)
            if done % 50 == 0:
                log.info("Reparti: %d/%d — fonti: %d", done, len(rows), total_saved)
                time.sleep(BATCH_SLEEP)

    log.info("REPARTI completato: %d unità, %d fonti", done, total_saved)
    return total_saved


# ─── Pipeline EVENTI ───────────────────────────────────────────────────────────

def pipeline_eventi():
    """Cerca fonti per eventi storici: battaglie, operazioni, capitolazioni.

    Include articoli di giornali d'epoca (Europeana Press, IA Newspapers,
    Gallica/BnF, HathiTrust, Google Books).
    Query estese: nome evento + "1943"/"1944"/"1945" + sinonimi IT/DE/EN.
    """
    log.info("=== PIPELINE EVENTI ===")

    # Eventi manurati ad alto valore storico (complementano DB entita)
    EVENTI_FISSI = [
        "Armistizio 8 settembre 1943",
        "Operazione Achse 1943",
        "Battaglia di El Alamein",
        "Campagna d'Africa 1942 1943",
        "Battaglia di Cassino 1944",
        "Liberazione di Roma 1944",
        "Battaglia di Anzio 1944",
        "Invasione della Sicilia 1943 Operazione Husky",
        "Fronte russo italiano ARMIR 1942",
        "Battaglia di Stalingrado italiani",
        "Resistenza italiana 1943 1945",
        "Lager nazisti italiani prigionieri",
        "IMI internati militari italiani Germania",
        "Divisione Acqui Cefalonia 1943 eccidio",
        "Divisione Julia Russia 1943",
        "Corpo d'Armata Alpino 1943",
    ]

    # Prende anche eventi dal DB entita (tipo='evento') — filtra solo quelli storici
    conn = get_conn()
    conn.row_factory = lambda c, r: dict(zip([col[0] for col in c.description], r))
    db_eventi = conn.execute(
        "SELECT id, valore FROM entita WHERE tipo='evento' "
        "AND (valore LIKE '%battag%' OR valore LIKE '%operazion%' OR "
        "     valore LIKE '%assedio%' OR valore LIKE '%offensiv%' OR "
        "     valore LIKE '%campagna%') "
        "ORDER BY id LIMIT 500"
    ).fetchall()
    conn.close()
    log.info("Eventi DB: %d + %d fissi = %d totali",
             len(db_eventi), len(EVENTI_FISSI), len(db_eventi) + len(EVENTI_FISSI))

    # Provider ottimali per eventi: archivi di giornali + biblioteche + archivi militari
    EVENTI_PROVIDERS = [
        "europeana", "internet_archive", "gallica", "hathitrust",
        "google_books", "nara", "tna", "bundesarchiv", "ddb",
        "memoire_des_hommes", "wikitree",
    ]

    total_saved = 0
    done = 0
    all_queries = [(e, None) for e in EVENTI_FISSI] + \
                  [(r["valore"], r["id"]) for r in db_eventi]

    def process(item):
        valore, eid = item
        if len((valore or "").strip()) < 5:
            return 0
        cues = {"evento": valore, "periodo": "1940-1945", "nazione": "Italia",
                "tipo": "articolo giornale documento storico"}
        saved = index_query(valore, cues, "entita", eid or 0, EVENTI_PROVIDERS)
        # Cerca anche in inglese per archivi angloamericani
        query_en = valore.replace("Battaglia di", "Battle of") \
                         .replace("Operazione", "Operation") \
                         .replace("Campagna", "Campaign")
        if query_en != valore:
            saved += index_query(query_en, cues, "entita", eid or 0, ["tna","nara","awm","europeana"])
        return saved

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as ex:
        futures = {ex.submit(process, item): item for item in all_queries}
        for fut in as_completed(futures):
            done += 1
            try:
                total_saved += fut.result()
            except Exception as e:
                log.warning("Errore evento: %s", e)
            if done % 20 == 0:
                log.info("Eventi: %d/%d — fonti: %d", done, len(all_queries), total_saved)
                time.sleep(BATCH_SLEEP)

    log.info("EVENTI completato: %d query, %d fonti", done, total_saved)
    return total_saved


# ─── Pipeline LUOGHI ───────────────────────────────────────────────────────────

def pipeline_luoghi():
    """Cerca fonti per luoghi: campi di internamento, città di cattura,
    movimentazioni battaglioni.

    Target: Arolsen (lager), Bundesarchiv (mappe), NARA, Europeana,
            Internet Archive, Memoire des Hommes.
    """
    log.info("=== PIPELINE LUOGHI ===")

    # Luoghi ad alto valore: campi di concentramento/internamento IMI
    LUOGHI_FISSI = [
        "Stalag XVII-B Krems-Gneixendorf",
        "Stalag IV-B Mühlberg",
        "Stalag II-B Hammerstein",
        "Lager Berlino internati italiani",
        "Lager Hannover italiani 1943 1945",
        "Lager Amburgo italiani prigionieri",
        "Mauthausen italiani 1943 1945",
        "Gusen campo concentramento italiani",
        "Dachau italiani prigionieri",
        "Blechhammer lager italiani",
        "Wietzendorf lager italiani",
        "Sandbostel lager italiani",
        "Belgrado internati italiani 1943",
        "Atene prigionieri italiani 1943",
    ]

    conn = get_conn()
    conn.row_factory = lambda c, r: dict(zip([col[0] for col in c.description], r))
    db_luoghi = conn.execute(
        "SELECT id, valore FROM entita WHERE tipo='luogo' "
        "AND (valore LIKE '%lager%' OR valore LIKE '%stalag%' OR "
        "     valore LIKE '%campo%' OR valore LIKE '%oflag%') "
        "ORDER BY id LIMIT 300"
    ).fetchall()
    conn.close()

    LUOGHI_PROVIDERS = [
        "arolsen", "bundesarchiv", "nara", "europeana",
        "internet_archive", "ddb", "archivportal_d",
    ]

    total_saved = 0
    done = 0
    all_queries = [(l, None) for l in LUOGHI_FISSI] + \
                  [(r["valore"], r["id"]) for r in db_luoghi]

    def process(item):
        valore, lid = item
        if len((valore or "").strip()) < 4:
            return 0
        cues = {"luogo": valore, "periodo": "1943-1945", "tipo": "campo internamento lager"}
        return index_query(valore, cues, "entita", lid or 0, LUOGHI_PROVIDERS)

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as ex:
        futures = {ex.submit(process, item): item for item in all_queries}
        for fut in as_completed(futures):
            done += 1
            try:
                total_saved += fut.result()
            except Exception as e:
                log.warning("Errore luogo: %s", e)
            if done % 20 == 0:
                log.info("Luoghi: %d/%d — fonti: %d", done, len(all_queries), total_saved)
                time.sleep(BATCH_SLEEP)

    log.info("LUOGHI completato: %d query, %d fonti", done, total_saved)
    return total_saved


# ─── Pipeline 1GM — SOLDATI ALBO D'ORO ──────────────────────────────────────────

def pipeline_soldati_1gm(limit: int = None, offset: int = 0):
    """Cerca fonti per caduti e decorati della Prima Guerra Mondiale.

    Sorgenti: caduti_albooro, caduti_ministero, caduti_sardi, caduti_bologna,
              decorati_nastroazzurro, decorati (ISTORECO 1GM).
    Provider: cwgc, europeana, internet_archive, gallica, hathitrust,
              ussme, memoire_des_hommes, antenati, wikitree, iwm_lives.
    """
    log.info("=== PIPELINE SOLDATI 1GM (offset=%d, limit=%s) ===", offset, limit)
    conn = get_conn()
    conn.row_factory = lambda c, r: dict(zip([col[0] for col in c.description], r))

    # Caduti Albo d'Oro (cognome + nome)
    q_ao = "SELECT id, nominativo, grado, reparto, luogo_morte FROM caduti_albooro WHERE nominativo IS NOT NULL AND nominativo != '' ORDER BY id"
    if limit:
        q_ao += f" LIMIT {limit} OFFSET {offset}"
    rows_ao = conn.execute(q_ao).fetchall()

    # Decorati Nastro Azzurro
    q_na = "SELECT id, cognome, nome FROM decorati_nastroazzurro WHERE cognome IS NOT NULL AND cognome != '' ORDER BY id"
    if limit:
        q_na += f" LIMIT {limit} OFFSET {offset}"
    rows_na = conn.execute(q_na).fetchall()

    conn.close()
    log.info("Soldati 1GM: Albo d'Oro=%d, Nastro Azzurro=%d", len(rows_ao), len(rows_na))

    SOLDATI_1GM_PROVIDERS = [
        "cwgc", "europeana", "internetarchive", "gallica",
        "hathitrust", "ussme", "memoiredeshommes",
        "antenati", "wikitree", "iwm_lives",
    ]

    total_saved = 0
    done = 0

    def process_albooro(row):
        nom = (row["nominativo"] or "").strip()
        # nominativo è "COGNOME NOME" o solo "COGNOME"
        parts = nom.split(None, 1)
        cognome = parts[0] if parts else nom
        nome = parts[1] if len(parts) > 1 else ""
        query = f"{cognome} {nome}".strip()
        if len(query) < 3:
            return 0
        cues = {"persona": query, "cognome": cognome, "nome": nome,
                "nazione": "Italia", "periodo": "1915-1918"}
        return index_query(query, cues, "caduti_albooro", row["id"], SOLDATI_1GM_PROVIDERS)

    def process_nastroazzurro(row):
        cognome = (row["cognome"] or "").strip().upper()
        nome = (row["nome"] or "").strip()
        query = f"{cognome} {nome}".strip()
        if len(query) < 3:
            return 0
        cues = {"persona": query, "cognome": cognome, "nome": nome,
                "nazione": "Italia", "periodo": "1915-1918"}
        return index_query(query, cues, "decorati_nastroazzurro", row["id"], SOLDATI_1GM_PROVIDERS)

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as ex:
        futures = {}
        for row in rows_ao:
            futures[ex.submit(process_albooro, row)] = ("albooro", row)
        for row in rows_na:
            futures[ex.submit(process_nastroazzurro, row)] = ("nastroazzurro", row)
        for fut in as_completed(futures):
            done += 1
            try:
                total_saved += fut.result()
            except Exception as e:
                log.warning("Errore soldato 1GM: %s", e)
            if done % 100 == 0:
                log.info("Soldati 1GM: %d/%d — fonti: %d", done, len(rows_ao)+len(rows_na), total_saved)
                time.sleep(BATCH_SLEEP)

    log.info("SOLDATI 1GM completato: %d soldati, %d fonti", done, total_saved)
    return total_saved


# ─── Pipeline 1GM — EVENTI ─────────────────────────────────────────────────────

def pipeline_eventi_1gm():
    """Cerca fonti per eventi della Prima Guerra Mondiale.

    Eventi: battaglie del fronte italo-austriaco, offensive, capitolazioni.
    Include giornali d'epoca (Europeana Press, IA Newspapers, Gallica/BnF).
    """
    log.info("=== PIPELINE EVENTI 1GM ===")

    EVENTI_1GM_FISSI = [
        "Battaglia di Caporetto 1917",
        "Battaglia di Vittorio Veneto 1918",
        "Undicesima battaglia dell'Isonzo 1917",
        "Battaglia di Ortigara 1917",
        "Battaglia del Piave 1918",
        "Battaglia del Monte Grappa 1918",
        "Battaglia di Asiago 1916",
        "Battaglia del Carso 1915 1916",
        "Stragi di Caporetto ritirata 1917",
        "Prima battaglia dell'Isonzo 1915",
        "Seconda battaglia dell'Isonzo 1915",
        "Terza battaglia dell'Isonzo 1915",
        "Quarta battaglia dell'Isonzo 1915",
        "Quinta battaglia dell'Isonzo 1916",
        "Sesta battaglia dell'Isonzo 1916",
        "Settima battaglia dell'Isonzo 1916",
        "Ottava battaglia dell'Isonzo 1916",
        "Nona battaglia dell'Isonzo 1916",
        "Decima battaglia dell'Isonzo 1917",
        "Battaglia di Gorizia 1916",
        "Spedizione di Fiume D'Annunzio 1919",
        "Armistizio di Villa Giusti 1918",
        "Battaglia di Galicia italiani 1914",
        "Fronte macedone italiani 1916 1918",
        "Battaglia del Solstizio 1918",
    ]

    # Eventi dal DB entita (tipo='evento') che sembrano 1GM
    conn = get_conn()
    conn.row_factory = lambda c, r: dict(zip([col[0] for col in c.description], r))
    db_eventi = conn.execute(
        "SELECT id, valore FROM entita WHERE tipo='evento' "
        "AND (valore LIKE '%isonzo%' OR valore LIKE '%caporetto%' OR "
        "     valore LIKE '%piave%' OR valore LIKE '%grappa%' OR "
        "     valore LIKE '%carso%' OR valore LIKE '%ortigara%' OR "
        "     valore LIKE '%asiago%' OR valore LIKE '%gorizia%' OR "
        "     valore LIKE '%vittorio veneto%' OR valore LIKE '%1915%' OR "
        "     valore LIKE '%1916%' OR valore LIKE '%1917%' OR valore LIKE '%1918%') "
        "ORDER BY id LIMIT 500"
    ).fetchall()
    conn.close()
    log.info("Eventi 1GM: DB=%d + %d fissi = %d totali",
             len(db_eventi), len(EVENTI_1GM_FISSI), len(db_eventi) + len(EVENTI_1GM_FISSI))

    EVENTI_1GM_PROVIDERS = [
        "europeana", "internetarchive", "gallica", "hathitrust",
        "googlebooks", "cwgc", "memoiredeshommes", "iwm_lives",
        "wikitree", "internetculturale",
    ]

    total_saved = 0
    done = 0
    all_queries = [(e, None) for e in EVENTI_1GM_FISSI] + \
                  [(r["valore"], r["id"]) for r in db_eventi]

    def process(item):
        valore, eid = item
        if len((valore or "").strip()) < 5:
            return 0
        cues = {"evento": valore, "periodo": "1914-1918", "nazione": "Italia",
                "tipo": "articolo giornale documento storico"}
        saved = index_query(valore, cues, "entita", eid or 0, EVENTI_1GM_PROVIDERS)
        # Cerca anche in inglese per archivi angloamericani
        query_en = valore.replace("Battaglia di", "Battle of") \
                         .replace("Battaglia del", "Battle of") \
                         .replace("Battaglia", "Battle") \
                         .replace("Armistizio", "Armistice")
        if query_en != valore:
            saved += index_query(query_en, cues, "entita", eid or 0,
                                 ["cwgc", "iwm_lives", "europeana", "internetarchive"])
        return saved

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as ex:
        futures = {ex.submit(process, item): item for item in all_queries}
        for fut in as_completed(futures):
            done += 1
            try:
                total_saved += fut.result()
            except Exception as e:
                log.warning("Errore evento 1GM: %s", e)
            if done % 20 == 0:
                log.info("Eventi 1GM: %d/%d — fonti: %d", done, len(all_queries), total_saved)
                time.sleep(BATCH_SLEEP)

    log.info("EVENTI 1GM completato: %d query, %d fonti", done, total_saved)
    return total_saved


# ─── Pipeline 1GM — LUOGHI ─────────────────────────────────────────────────────

def pipeline_luoghi_1gm():
    """Cerca fonti per luoghi della Prima Guerra Mondiale.

    Target: campi di battaglia, trincee, fortificazioni del fronte italo-austriaco.
    Provider: europeana, internet_archive, gallica, cwgc, iwm_lives.
    """
    log.info("=== PIPELINE LUOGHI 1GM ===")

    LUOGHI_1GM_FISSI = [
        "Caporetto Kobarid fronte italiano 1917",
        "Piave fiume fronte 1917 1918",
        "Monte Grappa fortificazioni 1917 1918",
        "Monte Ortigara battaglia 1917",
        "Asiago altopiano battaglie 1916 1918",
        "Carso Isonzo fronte 1915 1917",
        "Gorizia isonzo battaglia 1916",
        "Vittorio Veneto offensiva finale 1918",
        "Tolmino fronte isonzo 1915 1917",
        "Sabotino monte isonzo 1916",
        "San Michele monte carso 1916",
        "Podgora monte gorizia 1916",
        "Marmolada ghiacciaio guerra 1916 1918",
        "Pasubio monte strategico 1916 1918",
        "Cima Undici altopiano asiago 1917",
        "Val d'Assa altopiano vicentino 1916",
        "Trento irredentismo 1915 1918",
        "Trieste irredentismo 1915 1918",
        "Fiume D'Annunzio impresa 1919",
        "Salonico fronte macedone 1916 1918",
    ]

    conn = get_conn()
    conn.row_factory = lambda c, r: dict(zip([col[0] for col in c.description], r))
    db_luoghi = conn.execute(
        "SELECT id, valore FROM entita WHERE tipo='luogo' "
        "AND (valore LIKE '%isonzo%' OR valore LIKE '%caporetto%' OR "
        "     valore LIKE '%piave%' OR valore LIKE '%grappa%' OR "
        "     valore LIKE '%carso%' OR valore LIKE '%gorizia%' OR "
        "     valore LIKE '%asiago%' OR valore LIKE '%trento%' OR "
        "     valore LIKE '%trieste%' OR valore LIKE '%fiume%') "
        "ORDER BY id LIMIT 300"
    ).fetchall()
    conn.close()

    LUOGHI_1GM_PROVIDERS = [
        "europeana", "internetarchive", "gallica", "hathitrust",
        "cwgc", "iwm_lives", "internetculturale",
    ]

    total_saved = 0
    done = 0
    all_queries = [(l, None) for l in LUOGHI_1GM_FISSI] + \
                  [(r["valore"], r["id"]) for r in db_luoghi]

    def process(item):
        valore, lid = item
        if len((valore or "").strip()) < 4:
            return 0
        cues = {"luogo": valore, "periodo": "1915-1918", "tipo": "campo battaglia trincea fortezza"}
        return index_query(valore, cues, "entita", lid or 0, LUOGHI_1GM_PROVIDERS)

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as ex:
        futures = {ex.submit(process, item): item for item in all_queries}
        for fut in as_completed(futures):
            done += 1
            try:
                total_saved += fut.result()
            except Exception as e:
                log.warning("Errore luogo 1GM: %s", e)
            if done % 20 == 0:
                log.info("Luoghi 1GM: %d/%d — fonti: %d", done, len(all_queries), total_saved)
                time.sleep(BATCH_SLEEP)

    log.info("LUOGHI 1GM completato: %d query, %d fonti", done, total_saved)
    return total_saved


# ─── Pipeline DOCUMENTI 1GM (foto + diari) ─────────────────────────────────────

def pipeline_documenti_1gm():
    """Archivia metadati + deep link di foto/diari WWI da collezioni aperte.

    Usa archivio_documenti.py per:
    1. Seed delle 18 collezioni curate (livello collezione)
    2. Fetch item-level da Internet Archive, Library of Congress, Wikimedia Commons
    3. Fetch Europeana se VDF_EUROPEANA_KEY è impostata

    Nessun file binario scaricato: solo metadati + link diretto alla fonte.
    """
    import os
    from archivio_documenti import (
        create_schema as _ad_create_schema,
        seed_sources as _ad_seed,
        upsert_documenti as _ad_upsert,
        fetch_internet_archive as _ad_fetch_ia,
        fetch_loc as _ad_fetch_loc,
        fetch_wikimedia_commons as _ad_fetch_wc,
        fetch_europeana as _ad_fetch_eu,
        fetch_gallica_sru as _ad_fetch_gallica,
        fetch_tna_discovery as _ad_fetch_tna,
        fetch_iwm_collections as _ad_fetch_iwm,
    )

    log.info("=== PIPELINE DOCUMENTI 1GM ===")
    conn = get_conn()
    try:
        _ad_create_schema(conn)

        # 1. Seed collezioni
        n_seed = _ad_seed()
        log.info("Documenti 1GM: seed %d collezioni-fonte", n_seed)

        # 2. Internet Archive — diari WWI
        try:
            ia_rows = _ad_fetch_ia(rows=200)
            n_ia = _ad_upsert(conn, ia_rows)
            log.info("Documenti 1GM: Internet Archive +%d diari", n_ia)
        except Exception as e:
            log.warning("Documenti 1GM: Internet Archive saltato: %s", e)
            n_ia = 0

        # 3. Library of Congress — foto WWI
        try:
            loc_rows = _ad_fetch_loc(rows=200)
            n_loc = _ad_upsert(conn, loc_rows)
            log.info("Documenti 1GM: Library of Congress +%d foto", n_loc)
        except Exception as e:
            log.warning("Documenti 1GM: Library of Congress saltato: %s", e)
            n_loc = 0

        # 4. Wikimedia Commons — foto WWI
        try:
            wc_rows = _ad_fetch_wc(rows=200)
            n_wc = _ad_upsert(conn, wc_rows)
            log.info("Documenti 1GM: Wikimedia Commons +%d foto", n_wc)
        except Exception as e:
            log.warning("Documenti 1GM: Wikimedia Commons saltato: %s", e)
            n_wc = 0

        # 5. Europeana (richiede API key)
        key = os.environ.get("VDF_EUROPEANA_KEY")
        n_eu = 0
        if key:
            try:
                eu_rows = _ad_fetch_eu("prima guerra mondiale OR first world war", key, rows=200)
                n_eu = _ad_upsert(conn, eu_rows)
                log.info("Documenti 1GM: Europeana +%d oggetti", n_eu)
            except Exception as e:
                log.warning("Documenti 1GM: Europeana saltato: %s", e)
        else:
            log.info("Documenti 1GM: Europeana saltato (impostare VDF_EUROPEANA_KEY)")

        # 6. Gallica BnF SRU — foto, manoscritti, periodici francesi WWI
        try:
            gallica_rows = _ad_fetch_gallica("guerre mondiale 1914 1918", rows=200)
            n_gallica = _ad_upsert(conn, gallica_rows)
            log.info("Documenti 1GM: Gallica BnF +%d documenti", n_gallica)
        except Exception as e:
            log.warning("Documenti 1GM: Gallica BnF saltato: %s", e)
            n_gallica = 0

        # 7. TNA Discovery — war diaries WO 95
        try:
            tna_rows = _ad_fetch_tna("WO 95 war diary", rows=200)
            n_tna = _ad_upsert(conn, tna_rows)
            log.info("Documenti 1GM: TNA Discovery +%d diari", n_tna)
        except Exception as e:
            log.warning("Documenti 1GM: TNA Discovery saltato: %s", e)
            n_tna = 0

        # 8. IWM Collections — private papers WWI
        try:
            iwm_rows = _ad_fetch_iwm("first world war private papers", rows=200)
            n_iwm = _ad_upsert(conn, iwm_rows)
            log.info("Documenti 1GM: IWM Collections +%d documenti", n_iwm)
        except Exception as e:
            log.warning("Documenti 1GM: IWM Collections saltato: %s", e)
            n_iwm = 0

        total = n_seed + n_ia + n_loc + n_wc + n_eu + n_gallica + n_tna + n_iwm
        log.info("DOCUMENTI 1GM completato: %d record totali", total)

        # Stats per tipo
        by_type = conn.execute(
            "SELECT doc_type, COUNT(*) as n FROM archivio_documenti GROUP BY doc_type ORDER BY n DESC"
        ).fetchall()
        log.info("  Per tipo:")
        for r in by_type:
            log.info("    %-15s %d", r[0], r[1])

        by_provider = conn.execute(
            "SELECT provider, COUNT(*) as n FROM archivio_documenti GROUP BY provider ORDER BY n DESC"
        ).fetchall()
        log.info("  Per provider:")
        for r in by_provider:
            log.info("    %-30s %d", r[0], r[1])

    finally:
        conn.close()
    return total


def pipeline_cimeetrincee():
    """Scraping cimeetrincee.it: storie e soldati + foto d'epoca.

    1. /storie-e-soldati/ → archivio_documenti (provider=CimeTrincee, doc_type=storia)
    2. /foto-depoca/ → fonti_risorse (metadati + link diretto immagini)
    3. Collegamenti: storie → caduti/decorati, storie/foto → eventi canonici
    """
    from archivio_documenti import create_schema as _ad_create_schema, upsert_documenti as _ad_upsert
    from database import insert_fonti_risorsa, get_conn as _get_db_conn
    import scraper_cimeetrincee as sct

    log.info("=== PIPELINE CIMETRINCEE ===")
    conn = get_conn()
    db_conn = _get_db_conn()
    try:
        _ad_create_schema(conn)

        # 1. Storie e soldati → archivio_documenti
        storie = sct.scrape_storie_e_soldati()
        n_storie = 0
        if storie:
            n_storie = _ad_upsert(conn, storie)
            log.info("CimeTrincee: storie e soldati +%d record in archivio_documenti", n_storie)

        # 2. Foto d'epoca → fonti_risorse
        foto = sct.scrape_foto_depoca()
        n_foto = 0
        for record in foto:
            try:
                rid = insert_fonti_risorsa(record)
                if rid:
                    n_foto += 1
            except Exception as e:
                log.debug("Foto skip (probabile duplicato): %s", e)
        log.info("CimeTrincee: foto d'epoca +%d record in fonti_risorse", n_foto)

        # 3. Collegamenti storie → caduti/decorati + eventi
        n_collegamenti = _collega_storie_cimeetrincee(db_conn, storie)
        log.info("CimeTrincee: %d collegamenti creati", n_collegamenti)

        total = n_storie + n_foto
        log.info("CIMETRINCEE completato: %d storie + %d foto = %d record totali", n_storie, n_foto, total)

    finally:
        conn.close()
        db_conn.close()
    return total


def _collega_storie_cimeetrincee(conn, storie: list) -> int:
    """Crea collegamenti tra storie cimeetrincee e entita/eventi esistenti.
    - Storie → caduti_albooro (match cognome+nome)
    - Storie → decorati (match cognome+nome)
    - Storie/foto → eventi canonici (match keyword nel titolo)
    """
    import re
    n = 0
    # Eventi canonici 1GM con keyword di match
    eventi_keywords = {
        "caporetto": "Caporetto",
        "carso": "Carso",
        "isonzo": "Isonzo",
        "vittorio veneto": "Vittorio Veneto",
        "piave": "Piave",
        "trento": "Trento",
        "trieste": "Trieste",
        "gorizia": "Gorizia",
        "udine": "Udine",
        "col di lana": "Col di Lana",
        "adamello": "Adamello",
        "ortigara": "Ortigara",
        "pasubio": "Pasubio",
        "grappa": "Grappa",
        "sabbia": "Sabbia",
        "tagliamento": "Tagliamento",
    }

    for s in storie:
        title = (s.get("title") or "").lower()
        slug = s.get("external_id", "")
        url = s.get("source_url", "")
        raw = s.get("raw_json", {})
        soldier_name = raw.get("soldier_name")

        # Match con caduti (Albo d'Oro)
        if soldier_name:
            parts = soldier_name.split()
            if len(parts) >= 2:
                cognome, nome = parts[0], parts[1]
                try:
                    rows = conn.execute(
                        "SELECT id, cognome, nome FROM caduti_albooro WHERE cognome = ? AND nome LIKE ?",
                        (cognome, f"{nome}%"),
                    ).fetchall()
                    for row in rows:
                        conn.execute(
                            "INSERT OR IGNORE INTO collegamenti (entita_a_tipo, entita_a_id, entita_b_tipo, entita_b_id, tipo_collegamento, fonte, note) "
                            "VALUES (?, ?, ?, ?, ?, ?, ?)",
                            ("documento", slug, "caduto", row["id"], "riferimento",
                             "CimeTrincee", f"Storia su {soldier_name} — {url}"),
                        )
                        n += 1
                except Exception:
                    pass

            # Match con decorati
            try:
                rows = conn.execute(
                    "SELECT id, cognome, nome FROM decorati WHERE cognome = ? AND nome LIKE ?",
                    (cognome, f"{nome}%"),
                ).fetchall()
                for row in rows:
                    conn.execute(
                        "INSERT OR IGNORE INTO collegamenti (entita_a_tipo, entita_a_id, entita_b_tipo, entita_b_id, tipo_collegamento, fonte, note) "
                        "VALUES (?, ?, ?, ?, ?, ?, ?)",
                        ("documento", slug, "decorato", row["id"], "riferimento",
                         "CimeTrincee", f"Storia su {soldier_name} — {url}"),
                    )
                    n += 1
            except Exception:
                pass

        # Match con eventi canonici (keyword nel titolo)
        for kw, event_name in eventi_keywords.items():
            if kw in title:
                try:
                    ev_row = conn.execute(
                        "SELECT id FROM eventi_1gm WHERE nome LIKE ?", (f"%{event_name}%",),
                    ).fetchone()
                    if ev_row:
                        conn.execute(
                            "INSERT OR IGNORE INTO collegamenti (entita_a_tipo, entita_a_id, entita_b_tipo, entita_b_id, tipo_collegamento, fonte, note) "
                            "VALUES (?, ?, ?, ?, ?, ?, ?)",
                            ("documento", slug, "evento", ev_row["id"], "contesto",
                             "CimeTrincee", f"Storia relativa a {event_name} — {url}"),
                        )
                        n += 1
                except Exception:
                    pass

    conn.commit()
    return n


# ─── Report summary ────────────────────────────────────────────────────────────

def print_stats():
    conn = get_conn()
    conn.row_factory = lambda c, r: dict(zip([col[0] for col in c.description], r))
    tot  = conn.execute("SELECT COUNT(*) as n FROM fonti_indice").fetchone()["n"]
    arch = conn.execute(
        "SELECT archivio, COUNT(*) as n FROM fonti_indice "
        "GROUP BY archivio ORDER BY n DESC LIMIT 20"
    ).fetchall()
    url_ok = conn.execute(
        "SELECT COUNT(*) as n FROM fonti_indice WHERE url_catalogo IS NOT NULL AND url_catalogo != ''"
    ).fetchone()["n"]
    conn.close()
    log.info("=== STATS FONTI_INDICE ===")
    log.info("Totale: %d | Con URL: %d", tot, url_ok)
    for a in arch:
        log.info("  %-50s %d", a["archivio"], a["n"])


# ─── Entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Pipeline indicizzazione massiva archivi")
    parser.add_argument("mode", choices=["soldati","reparti","eventi","luoghi","all","stats",
                                           "soldati_1gm","eventi_1gm","luoghi_1gm","all_1gm",
                                           "documenti_1gm","cimeetrincee"],
                        help="Pipeline da eseguire")
    parser.add_argument("--limit",  type=int, default=None, help="Max soldati (default: tutti)")
    parser.add_argument("--offset", type=int, default=0,    help="Offset soldati")
    args = parser.parse_args()

    log.info("START mass_index — mode=%s limit=%s offset=%s", args.mode, args.limit, args.offset)
    start = time.time()

    if args.mode in ("soldati", "all"):
        pipeline_soldati(limit=args.limit, offset=args.offset)
    if args.mode in ("reparti", "all"):
        pipeline_reparti()
    if args.mode in ("eventi", "all"):
        pipeline_eventi()
    if args.mode in ("luoghi", "all"):
        pipeline_luoghi()
    if args.mode in ("soldati_1gm", "all_1gm"):
        pipeline_soldati_1gm(limit=args.limit, offset=args.offset)
    if args.mode in ("eventi_1gm", "all_1gm"):
        pipeline_eventi_1gm()
    if args.mode in ("luoghi_1gm", "all_1gm"):
        pipeline_luoghi_1gm()
    if args.mode == "documenti_1gm":
        pipeline_documenti_1gm()
    if args.mode == "cimeetrincee":
        pipeline_cimeetrincee()
    if args.mode == "stats":
        print_stats()

    print_stats()
    elapsed = time.time() - start
    log.info("DONE in %.1f sec", elapsed)

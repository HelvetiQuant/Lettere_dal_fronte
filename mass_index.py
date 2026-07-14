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
MIN_SCORE      = 0.45  # scarta risultati con score troppo basso
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
    parser.add_argument("mode", choices=["soldati","reparti","eventi","luoghi","all","stats"],
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
    if args.mode == "stats":
        print_stats()

    print_stats()
    elapsed = time.time() - start
    log.info("DONE in %.1f sec", elapsed)

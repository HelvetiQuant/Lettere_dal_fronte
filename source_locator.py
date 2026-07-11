"""Source Locator — indice leggero delle fonti storiche.

Principio: il DB locale è un catalogo/mappa, non un magazzino.
- fonti_indice     = scheda di collocazione (dove sta, cosa contiene, come recuperarla)
- source_fetch_cache = solo ciò che è stato davvero scaricato, con scadenza

Flusso: query → find_candidate_sources (solo metadati) →
        fetch_source_on_demand (solo whitelist, solo se serve) →
        build_minimal_context_for_ai (minimo indispensabile).

Regola di sicurezza: l'AI non scarica mai direttamente. Il backend
controlla i metadati e scarica solo da domini autorizzati.

Non tocca nessuna tabella esistente.
Dipende da: database.py, memory_router.py (extract_cues)
"""

import hashlib
import json
import re
from datetime import datetime
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse

import requests

from database import get_conn

# lazy import: memory_router importa source_locator (per event sources),
# quindi evitiamo il circular import a livello di modulo.
def _extract_cues(query: str):
    from memory_router import extract_cues
    return extract_cues(query)

# ─── Config ────────────────────────────────────────────────────────────────────

CACHE_DIR = Path(__file__).parent / "source_cache"
CACHE_DIR.mkdir(exist_ok=True)

MAX_FETCH_BYTES = 50 * 1024 * 1024   # 50 MB per file
FETCH_TIMEOUT = 60
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) ricerca-storica-IMI/1.0"

# Solo il backend scarica, e solo da questi domini (correzione richiesta:
# l'AI propone, il backend controlla e recupera).
AUTHORIZED_DOMAINS = {
    # Italian / Ministero della Cultura
    "dam-antenati.cultura.gov.it",
    "iiif-antenati.cultura.gov.it",
    "antenati.cultura.gov.it",
    "dati.acs.beniculturali.it",
    # NARA / USA
    "catalog.archives.gov",
    "s3.amazonaws.com",              # media NARA catalog
    "nara-media-001.s3.amazonaws.com",
    # CWGC / Commonwealth
    "www.cwgc.org",
    "cwgc.org",
    "archive.cwgc.org",
    # Albo d'Oro
    "www.cadutigrandeguerra.it",
    "cadutigrandeguerra.it",
    # Decorati
    "decoratialvalormilitare.istitutonastroazzurro.org",
    "www.istitutonastroazzurro.org",
    # Generici
    "archive.org",
    "ia800000.us.archive.org",
    # Catalogo fonti esterne (25 fonti)
    "www.memoiredeshommes.sga.defense.gouv.fr",
    "memoiredeshommes.sga.defense.gouv.fr",
    "grandeguerre.icrc.org",
    "www.deutsche-digitale-bibliothek.de",
    "deutsche-digitale-bibliothek.de",
    "www.oesta.gv.at",
    "oesta.gv.at",
    "archivinformationssystem.at",
    "www.familysearch.org",
    "familysearch.org",
    "www.europeana.eu",
    "europeana.eu",
    "collections.arolsen-archives.org",
    "archiviodiari.org",
    "catalogo.archiviodiari.it",
    "900trentino.museostorico.it",
    "www.briefsammlung.de",
    "briefsammlung.de",
    "francearchives.gouv.fr",
    "www.francearchives.gouv.fr",
    "digitalcommons.chapman.edu",
    "www.cheminsdememoire.gouv.fr",
    "cheminsdememoire.gouv.fr",
    "donnees.culture.gouv.fr",
    "livesofthefirstworldwar.iwm.org.uk",
    "discovery.nationalarchives.gov.uk",
    "trove.nla.gov.au",
    "www.awm.gov.au",
    "awm.gov.au",
    "www.quirinale.it",
    "quirinale.it",
    "www.archivioluce.com",
    "archivioluce.com",
}

ACCESS_TYPES = ("online", "login", "richiesta", "locale")
FETCH_STATUSES = ("mai_scaricato", "scaricato", "non_accessibile", "errore")


# ─── Tabelle ───────────────────────────────────────────────────────────────────

def _init_tables():
    conn = get_conn()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS fonti_indice (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            archivio TEXT,
            fondo TEXT,
            serie TEXT,
            segnatura TEXT,
            titolo TEXT,
            tipo_fonte TEXT,
            soggetti_collegati TEXT,
            persone_possibili TEXT,
            reparto TEXT,
            luogo TEXT,
            data_inizio TEXT,
            data_fine TEXT,
            url_catalogo TEXT,
            url_file TEXT,
            iiif_manifest TEXT,
            page_start INTEGER,
            page_end INTEGER,
            hash_se_disponibile TEXT,
            access_type TEXT DEFAULT 'online',
            fetch_status TEXT DEFAULT 'mai_scaricato',
            last_checked_at TEXT,
            confidence REAL DEFAULT 0.5,
            note TEXT,
            created_at TEXT NOT NULL,
            UNIQUE(archivio, segnatura, titolo)
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS source_fetch_cache (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            source_id INTEGER NOT NULL REFERENCES fonti_indice(id),
            url_fetched TEXT,
            path_file TEXT,
            sha256 TEXT,
            size_bytes INTEGER,
            content_type TEXT,
            permanent INTEGER DEFAULT 0,
            fetched_at TEXT NOT NULL,
            expires_at TEXT
        )
    """)
    for idx in [
        "CREATE INDEX IF NOT EXISTS idx_fi_reparto ON fonti_indice(reparto)",
        "CREATE INDEX IF NOT EXISTS idx_fi_luogo ON fonti_indice(luogo)",
        "CREATE INDEX IF NOT EXISTS idx_fi_archivio ON fonti_indice(archivio)",
        "CREATE INDEX IF NOT EXISTS idx_fi_fetch_status ON fonti_indice(fetch_status)",
        "CREATE INDEX IF NOT EXISTS idx_fi_soggetti ON fonti_indice(soggetti_collegati)",
        "CREATE INDEX IF NOT EXISTS idx_sfc_source ON source_fetch_cache(source_id)",
    ]:
        conn.execute(idx)
    conn.commit()
    conn.close()


# ─── Registrazione metadati ────────────────────────────────────────────────────

def register_source_metadata(**meta) -> dict:
    """Registra (o aggiorna) la scheda di collocazione di una fonte.

    Salva SOLO metadati: niente PDF, niente OCR, niente immagini.
    Ritorna {'id': ..., 'created': bool}.
    """
    allowed = {
        "archivio", "fondo", "serie", "segnatura", "titolo", "tipo_fonte",
        "soggetti_collegati", "persone_possibili", "reparto", "luogo",
        "data_inizio", "data_fine", "url_catalogo", "url_file",
        "iiif_manifest", "page_start", "page_end", "hash_se_disponibile",
        "access_type", "confidence", "note", "last_checked_at",
    }
    data = {k: v for k, v in meta.items() if k in allowed and v not in (None, "")}
    for k in ("soggetti_collegati", "persone_possibili"):
        if k in data and isinstance(data[k], (list, dict)):
            data[k] = json.dumps(data[k], ensure_ascii=False)
    if data.get("access_type") not in (None, *ACCESS_TYPES):
        data["access_type"] = "online"

    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        "SELECT id FROM fonti_indice WHERE archivio IS ? AND segnatura IS ? AND titolo IS ?",
        (data.get("archivio"), data.get("segnatura"), data.get("titolo")),
    )
    row = cur.fetchone()
    now = datetime.now().isoformat(timespec="seconds")
    # last_checked_at: usa il valore passato o il timestamp corrente
    checked_at = data.pop("last_checked_at", now) or now
    if row:
        sets = ", ".join(f"{k}=?" for k in data)
        cur.execute(
            f"UPDATE fonti_indice SET {sets}, last_checked_at=? WHERE id=?",
            (*data.values(), checked_at, row[0]),
        )
        conn.commit()
        conn.close()
        return {"id": row[0], "created": False}
    data["created_at"] = now
    data["last_checked_at"] = checked_at
    cols = ", ".join(data)
    marks = ", ".join("?" for _ in data)
    cur.execute(f"INSERT INTO fonti_indice ({cols}) VALUES ({marks})", tuple(data.values()))
    new_id = cur.lastrowid
    conn.commit()
    conn.close()
    return {"id": new_id, "created": True}


# ─── Ricerca candidati ─────────────────────────────────────────────────────────

def find_candidate_sources(query: str, limit: int = 20) -> dict:
    """Cerca nell'indice leggero le fonti candidate per la query.

    Classifica ogni fonte:
      - 'locale'        : già scaricata in cache (o hash noto in archivio_fonti)
      - 'richiamabile'  : online con URL noto e dominio autorizzato
      - 'da_richiedere' : accesso solo su richiesta / login / dominio non autorizzato
    """
    cues = _extract_cues(query)
    conn = get_conn()
    conn.row_factory = _dict_factory
    cur = conn.cursor()

    conditions, params = [], []
    if cues.get("persona"):
        conditions.append("(persone_possibili LIKE ? OR soggetti_collegati LIKE ? OR titolo LIKE ?)")
        p = f"%{cues['persona']}%"
        params += [p, p, p]
    if cues.get("reparto"):
        conditions.append("(reparto LIKE ? OR titolo LIKE ?)")
        p = f"%{cues['reparto']}%"
        params += [p, p]
    if cues.get("luogo"):
        conditions.append("(luogo LIKE ? OR titolo LIKE ?)")
        p = f"%{cues['luogo']}%"
        params += [p, p]
    if cues.get("archivio"):
        conditions.append("(archivio LIKE ? OR fondo LIKE ? OR tipo_fonte LIKE ?)")
        p = f"%{cues['archivio']}%"
        params += [p, p, p]
    if cues.get("data"):
        conditions.append("(data_inizio LIKE ? OR data_fine LIKE ? OR titolo LIKE ?)")
        p = f"%{cues['data']}%"
        params += [p, p, p]

    if not conditions:
        # fallback: tokenizza la query su parole > 3 caratteri
        tokens = [t for t in re.findall(r"\w{4,}", query)][:4]
        for t in tokens:
            conditions.append(
                "(titolo LIKE ? OR fondo LIKE ? OR serie LIKE ? OR note LIKE ?)")
            p = f"%{t}%"
            params += [p, p, p, p]
        if not conditions:
            conn.close()
            return {"cues": cues, "candidates": [], "total": 0}

    sql = (
        "SELECT * FROM fonti_indice WHERE " + " OR ".join(conditions) +
        " ORDER BY confidence DESC LIMIT ?"
    )
    cur.execute(sql, (*params, limit))
    rows = cur.fetchall()

    candidates = []
    for r in rows:
        r["availability"] = _classify_availability(cur, r)
        candidates.append(r)
    conn.close()
    return {"cues": cues, "candidates": candidates, "total": len(candidates)}


def find_sources_by_subject(subject: str, limit: int = 100) -> dict:
    """Recupera tutte le fonti in fonti_indice collegate a un soggetto/evento esatto.

    Utile per mostrare le fonti multilaterali di un evento (es. 'Eccidio di Cefalonia').
    """
    if not subject or not subject.strip():
        return {"subject": subject, "candidates": [], "total": 0}
    subject = subject.strip()
    conn = get_conn()
    conn.row_factory = _dict_factory
    cur = conn.cursor()
    cur.execute(
        "SELECT * FROM fonti_indice WHERE soggetti_collegati = ? "
        "ORDER BY confidence DESC, archivio LIMIT ?",
        (subject, limit),
    )
    rows = cur.fetchall()
    candidates = []
    for r in rows:
        r["availability"] = _classify_availability(cur, r)
        # decodifica eventuale nota JSON per estrarre fazione/descrizione
        if r.get("note"):
            try:
                r["note_parsed"] = json.loads(r["note"])
            except Exception:
                r["note_parsed"] = None
        candidates.append(r)
    conn.close()
    return {"subject": subject, "candidates": candidates, "total": len(candidates)}


def list_event_subjects(limit: int = 100) -> list:
    """Restituisce i soggetti_collegati distinti che rappresentano eventi curati.

    Euristicamente considera eventi le voci la cui prima parola inizia con
    una lettera maiuscola e contengono date/location (es. 'Eccidio di Cefalonia',
    'Battaglia di Tobruk').
    """
    conn = get_conn()
    conn.row_factory = _dict_factory
    cur = conn.cursor()
    cur.execute(
        "SELECT DISTINCT soggetti_collegati FROM fonti_indice "
        "WHERE soggetti_collegati IS NOT NULL AND soggetti_collegati != '' "
        "ORDER BY soggetti_collegati LIMIT ?",
        (limit,),
    )
    rows = [r["soggetti_collegati"] for r in cur.fetchall()]
    conn.close()
    # filtra: almeno 2 parole, prima parola capitalizzata, contiene un anno o luogo noto
    event_like = []
    for s in rows:
        if not s:
            continue
        parts = s.split()
        if len(parts) < 2:
            continue
        first = parts[0]
        if not first[0].isupper():
            continue
        # pattern evento: contiene anno 19xx o luogo evento noto
        if (
            re.search(r"\b(19[3-5][0-9])\b", s)
            or any(k in s.lower() for k in [
                "cefalonia", "mauthausen", "gusen", "tobruk", "russia", "armir",
                "achse", "lavoro forzato", "internamento", "campagna",
            ])
        ):
            event_like.append(s)
    return event_like


def _classify_availability(cur, row: dict) -> str:
    cur.execute(
        "SELECT COUNT(*) AS n FROM source_fetch_cache WHERE source_id=? AND path_file IS NOT NULL",
        (row["id"],),
    )
    if cur.fetchone()["n"] > 0 or row.get("fetch_status") == "scaricato":
        return "locale"
    url = row.get("url_file") or row.get("iiif_manifest")
    if row.get("access_type") == "online" and url and _domain_authorized(url):
        return "richiamabile"
    return "da_richiedere"


def _domain_authorized(url: str) -> bool:
    try:
        host = urlparse(url).hostname or ""
    except Exception:
        return False
    return host in AUTHORIZED_DOMAINS or any(host.endswith("." + d) for d in AUTHORIZED_DOMAINS)


def _dict_factory(cursor, row):
    return {d[0]: row[i] for i, d in enumerate(cursor.description)}


# ─── Fetch on demand ───────────────────────────────────────────────────────────

def fetch_source_on_demand(source_id: int, force: bool = False,
                           permanent: bool = False) -> dict:
    """Scarica UNA fonte, solo se autorizzata. Il backend decide, mai l'AI.

    - dominio non in whitelist  → rifiuto (da_richiedere)
    - già in cache e not force  → ritorna la cache
    - dimensione > MAX_FETCH_BYTES → interrompe
    """
    conn = get_conn()
    conn.row_factory = _dict_factory
    cur = conn.cursor()
    cur.execute("SELECT * FROM fonti_indice WHERE id=?", (source_id,))
    src = cur.fetchone()
    if not src:
        conn.close()
        return {"ok": False, "error": "fonte non trovata"}

    # cache esistente
    if not force:
        cur.execute(
            "SELECT * FROM source_fetch_cache WHERE source_id=? AND path_file IS NOT NULL "
            "ORDER BY fetched_at DESC LIMIT 1", (source_id,))
        cached = cur.fetchone()
        if cached and Path(cached["path_file"]).exists():
            conn.close()
            return {"ok": True, "from_cache": True, **cached}

    url = src.get("url_file") or src.get("iiif_manifest")
    if not url:
        conn.close()
        return {"ok": False, "error": "nessun URL noto", "suggestion": "generare richiesta email"}
    if not _domain_authorized(url):
        conn.close()
        return {"ok": False, "error": f"dominio non autorizzato: {urlparse(url).hostname}",
                "suggestion": "aggiungere ad AUTHORIZED_DOMAINS solo dopo verifica manuale"}
    if src.get("access_type") in ("login", "richiesta"):
        conn.close()
        return {"ok": False, "error": f"access_type={src['access_type']}",
                "suggestion": "generare richiesta email all'archivio"}

    now = datetime.now().isoformat(timespec="seconds")
    try:
        resp = requests.get(url, headers={"User-Agent": USER_AGENT},
                            timeout=FETCH_TIMEOUT, stream=True)
        resp.raise_for_status()
        ctype = resp.headers.get("Content-Type", "application/octet-stream").split(";")[0]
        clen = int(resp.headers.get("Content-Length") or 0)
        if clen > MAX_FETCH_BYTES:
            raise ValueError(f"file troppo grande ({clen} byte)")

        chunks, total = [], 0
        for chunk in resp.iter_content(chunk_size=65536):
            total += len(chunk)
            if total > MAX_FETCH_BYTES:
                raise ValueError("superato limite dimensione durante il download")
            chunks.append(chunk)
        content = b"".join(chunks)
        sha = hashlib.sha256(content).hexdigest()
        ext = _guess_ext(ctype, url)
        path = CACHE_DIR / f"{sha[:16]}{ext}"
        path.write_bytes(content)

        cur.execute(
            "INSERT INTO source_fetch_cache (source_id, url_fetched, path_file, sha256, "
            "size_bytes, content_type, permanent, fetched_at) VALUES (?,?,?,?,?,?,?,?)",
            (source_id, url, str(path), sha, total, ctype, int(permanent), now))
        cur.execute(
            "UPDATE fonti_indice SET fetch_status='scaricato', hash_se_disponibile=?, "
            "last_checked_at=? WHERE id=?", (sha, now, source_id))
        conn.commit()
        conn.close()
        return {"ok": True, "from_cache": False, "path_file": str(path),
                "sha256": sha, "size_bytes": total, "content_type": ctype}
    except Exception as e:
        status = "non_accessibile" if isinstance(e, requests.HTTPError) else "errore"
        cur.execute("UPDATE fonti_indice SET fetch_status=?, last_checked_at=? WHERE id=?",
                    (status, now, source_id))
        conn.commit()
        conn.close()
        return {"ok": False, "error": str(e)}


def _guess_ext(content_type: str, url: str) -> str:
    mapping = {
        "application/pdf": ".pdf", "image/jpeg": ".jpg", "image/png": ".png",
        "image/tiff": ".tiff", "application/json": ".json", "text/html": ".html",
        "text/plain": ".txt",
    }
    if content_type in mapping:
        return mapping[content_type]
    suffix = Path(urlparse(url).path).suffix
    return suffix if suffix and len(suffix) <= 5 else ".bin"


# ─── Contesto minimo per l'AI ──────────────────────────────────────────────────

def build_minimal_context_for_ai(query: str, max_sources: int = 5,
                                 allow_fetch: bool = False) -> dict:
    """Costruisce il contesto minimo da passare all'AI.

    - metadati sempre inclusi (leggeri)
    - contenuto testuale solo se già in cache locale (json/txt/html, troncato)
    - se allow_fetch=True il backend scarica al massimo 2 fonti 'richiamabili'
      (mai l'AI direttamente)
    """
    found = find_candidate_sources(query, limit=max_sources * 2)
    candidates = found["candidates"][:max_sources]

    fetched_now = 0
    context_blocks = []
    for c in candidates:
        block = {
            "source_id": c["id"],
            "archivio": c.get("archivio"),
            "fondo": c.get("fondo"),
            "segnatura": c.get("segnatura"),
            "titolo": c.get("titolo"),
            "tipo_fonte": c.get("tipo_fonte"),
            "reparto": c.get("reparto"),
            "luogo": c.get("luogo"),
            "data": c.get("data_inizio"),
            "url_catalogo": c.get("url_catalogo"),
            "availability": c["availability"],
            "confidence": c.get("confidence"),
        }
        if allow_fetch and c["availability"] == "richiamabile" and fetched_now < 2:
            result = fetch_source_on_demand(c["id"])
            if result.get("ok"):
                fetched_now += 1
                block["availability"] = "locale"
                block["fetched"] = True
        # contenuto solo se testuale e già locale
        snippet = _read_cached_text(c["id"])
        if snippet:
            block["excerpt"] = snippet[:2000]
        context_blocks.append(block)

    return {
        "query": query,
        "cues": found["cues"],
        "sources": context_blocks,
        "note": "Il documento originale resta la fonte primaria. "
                "Excerpt presenti solo per fonti testuali già in cache.",
    }


def _read_cached_text(source_id: int) -> Optional[str]:
    conn = get_conn()
    conn.row_factory = _dict_factory
    cur = conn.cursor()
    cur.execute(
        "SELECT path_file, content_type FROM source_fetch_cache "
        "WHERE source_id=? AND content_type IN ('application/json','text/plain','text/html') "
        "ORDER BY fetched_at DESC LIMIT 1", (source_id,))
    row = cur.fetchone()
    conn.close()
    if not row or not row["path_file"]:
        return None
    p = Path(row["path_file"])
    if not p.exists():
        return None
    try:
        text = p.read_text(encoding="utf-8", errors="ignore")
        if row["content_type"] == "text/html":
            text = re.sub(r"<[^>]+>", " ", text)
            text = re.sub(r"\s+", " ", text)
        return text.strip()
    except Exception:
        return None


# ─── Statistiche ───────────────────────────────────────────────────────────────

def get_stats() -> dict:
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM fonti_indice")
    total = cur.fetchone()[0]
    cur.execute("SELECT fetch_status, COUNT(*) FROM fonti_indice GROUP BY fetch_status")
    by_status = dict(cur.fetchall())
    cur.execute("SELECT access_type, COUNT(*) FROM fonti_indice GROUP BY access_type")
    by_access = dict(cur.fetchall())
    cur.execute("SELECT COUNT(*), COALESCE(SUM(size_bytes),0) FROM source_fetch_cache")
    n_cache, cache_bytes = cur.fetchone()
    conn.close()
    return {
        "total_sources": total,
        "by_fetch_status": by_status,
        "by_access_type": by_access,
        "cache_files": n_cache,
        "cache_bytes": cache_bytes,
    }

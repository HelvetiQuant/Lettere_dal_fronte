"""Base SourceProvider — interfaccia comune per tutti i provider.

Ogni provider implementa:
  search()           → cerca metadati nell'archivio remoto
  get_metadata()     → metadati dettagliati per un record
  get_document()     → scarica il documento (PDF/immagine)
  get_iiif_manifest()→ manifest IIIF se disponibile
  build_direct_link()→ URL diretto alla pagina/frame corretta

Principio: il DB locale salva solo metadati + URL.
I documenti pesanti vengono scaricati on-demand dal backend.
L'AI non scarica mai direttamente.
"""

import abc
import hashlib
import json
import re
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional
from urllib.parse import urlparse

import requests

from database import get_conn

# ─── Config ────────────────────────────────────────────────────────────────────

CACHE_DIR = Path(__file__).parent.parent / "source_cache"
CACHE_DIR.mkdir(exist_ok=True)

MAX_FETCH_BYTES = 50 * 1024 * 1024
FETCH_TIMEOUT = 60
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) ricerca-storica-IMI/1.0"

CACHE_TTL_DAYS = 30  # default, configurabile per provider


class SourceProvider(abc.ABC):
    """Interfaccia base per tutti i provider di fonti storiche."""

    name: str = "base"
    display_name: str = "Base Provider"
    country: str = ""
    archive_name: str = ""
    base_url: str = ""
    authorized_domains: set = set()
    cache_ttl_days: int = CACHE_TTL_DAYS

    @abc.abstractmethod
    def search(self, query: str, filters: dict = None) -> List[dict]:
        """Cerca nell'archivio remoto. Ritorna lista di metadati (dict).
        Non scarica documenti. Solo metadati + URL."""
        ...

    @abc.abstractmethod
    def get_metadata(self, record_id: str) -> dict:
        """Recupera metadati dettagliati per un record specifico."""
        ...

    def get_document(self, record_id: str) -> dict:
        """Scarica il documento originale (PDF/immagine).
        Override per provider che supportano download diretto."""
        return {"ok": False, "error": "download non supportato da questo provider"}

    def get_iiif_manifest(self, record_id: str) -> Optional[dict]:
        """Recupera il manifest IIIF se disponibile.
        Override per provider IIIF (Antenati, Gallica, ecc.)."""
        return None

    def build_direct_link(self, record_id: str, page: int = None) -> str:
        """Costruisce URL diretto alla pagina/frame corretta."""
        link = f"{self.base_url}/{record_id}"
        if page is not None:
            link += f"?page={page}"
        return link

    def get_thumbnail(self, record_id: str) -> Optional[str]:
        """URL thumbnail se disponibile."""
        return None

    # ─── Helper di dominio ────────────────────────────────────────────────

    def is_authorized(self, url: str) -> bool:
        try:
            host = urlparse(url).hostname or ""
        except Exception:
            return False
        return host in self.authorized_domains or any(
            host.endswith("." + d) for d in self.authorized_domains
        )

    # ─── Registrazione nel DB locale ──────────────────────────────────────

    def register_in_db(self, meta: dict) -> int:
        """Registra metadati nella tabella fonti_indice (upsert)."""
        conn = get_conn()
        cur = conn.cursor()
        now = datetime.now().isoformat(timespec="seconds")

        # mappa campi provider → colonne fonti_indice
        data = {
            "archivio": meta.get("archivio") or self.archive_name,
            "fondo": meta.get("fondo") or "",
            "serie": meta.get("serie") or "",
            "segnatura": meta.get("segnatura") or meta.get("signature") or "",
            "titolo": meta.get("titolo") or meta.get("title") or "",
            "tipo_fonte": meta.get("tipo_fonte") or meta.get("source_type") or "",
            "soggetti_collegati": json.dumps(meta.get("soggetti", []), ensure_ascii=False) if meta.get("soggetti") else None,
            "persone_possibili": json.dumps(meta.get("persone", []), ensure_ascii=False) if meta.get("persone") else None,
            "reparto": meta.get("unit") or meta.get("reparto") or "",
            "luogo": meta.get("luogo") or meta.get("place") or "",
            "data_inizio": meta.get("data_inizio") or meta.get("date_start") or "",
            "data_fine": meta.get("data_fine") or meta.get("date_end") or "",
            "url_catalogo": meta.get("catalog_url") or "",
            "url_file": meta.get("direct_url") or meta.get("url_file") or "",
            "iiif_manifest": meta.get("iiif_manifest") or "",
            "page_start": meta.get("page_number") or meta.get("page_start"),
            "page_end": meta.get("page_end"),
            "access_type": meta.get("access_type") or "online",
            "confidence": meta.get("confidence") or 0.5,
            "note": meta.get("description") or "",
        }
        data = {k: v for k, v in data.items() if v not in (None, "", [])}

        # upsert
        cur.execute(
            "SELECT id FROM fonti_indice WHERE archivio IS ? AND segnatura IS ? AND titolo IS ?",
            (data.get("archivio"), data.get("segnatura"), data.get("titolo")),
        )
        row = cur.fetchone()
        if row:
            sets = ", ".join(f"{k}=?" for k in data)
            cur.execute(f"UPDATE fonti_indice SET {sets}, last_checked_at=? WHERE id=?",
                        (*data.values(), now, row[0]))
            fid = row[0]
        else:
            data["created_at"] = now
            cols = ", ".join(data)
            marks = ", ".join("?" for _ in data)
            cur.execute(f"INSERT INTO fonti_indice ({cols}) VALUES ({marks})", tuple(data.values()))
            fid = cur.lastrowid
        conn.commit()
        conn.close()
        return fid

    # ─── Fetch con cache ──────────────────────────────────────────────────

    def fetch_with_cache(self, url: str, source_id: int = None,
                         permanent: bool = False) -> dict:
        """Scarica un URL e salva in cache. Solo domini autorizzati."""
        if not self.is_authorized(url):
            return {"ok": False, "error": f"dominio non autorizzato: {urlparse(url).hostname}"}

        conn = get_conn()
        conn.row_factory = _dict_factory
        cur = conn.cursor()

        # check cache
        if source_id:
            cur.execute(
                "SELECT * FROM source_fetch_cache WHERE source_id=? AND path_file IS NOT NULL "
                "ORDER BY fetched_at DESC LIMIT 1", (source_id,))
            cached = cur.fetchone()
            if cached and Path(cached["path_file"]).exists():
                # check TTL
                fetched = datetime.fromisoformat(cached["fetched_at"])
                ttl_days = self.cache_ttl_days
                if (datetime.now() - fetched).days < ttl_days or cached.get("permanent"):
                    conn.close()
                    return {"ok": True, "from_cache": True, **cached}

        now = datetime.now().isoformat(timespec="seconds")
        try:
            resp = requests.get(url, headers={"User-Agent": USER_AGENT},
                                timeout=FETCH_TIMEOUT, stream=True, verify=False)
            resp.raise_for_status()
            ctype = resp.headers.get("Content-Type", "application/octet-stream").split(";")[0]
            clen = int(resp.headers.get("Content-Length") or 0)
            if clen > MAX_FETCH_BYTES:
                raise ValueError(f"file troppo grande ({clen} byte)")

            chunks, total = [], 0
            for chunk in resp.iter_content(chunk_size=65536):
                total += len(chunk)
                if total > MAX_FETCH_BYTES:
                    raise ValueError("superato limite dimensione")
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
            if source_id:
                cur.execute("UPDATE fonti_indice SET fetch_status='scaricato', "
                            "hash_se_disponibile=?, last_checked_at=? WHERE id=?",
                            (sha, now, source_id))
            conn.commit()
            conn.close()
            return {"ok": True, "from_cache": False, "path_file": str(path),
                    "sha256": sha, "size_bytes": total, "content_type": ctype}
        except Exception as e:
            if source_id:
                cur.execute("UPDATE fonti_indice SET fetch_status='errore', "
                            "last_checked_at=? WHERE id=?", (now, source_id))
                conn.commit()
            conn.close()
            return {"ok": False, "error": str(e)}


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _dict_factory(cursor, row):
    return {d[0]: row[i] for i, d in enumerate(cursor.description)}


def _guess_ext(content_type: str, url: str) -> str:
    mapping = {
        "application/pdf": ".pdf", "image/jpeg": ".jpg", "image/png": ".png",
        "image/tiff": ".tiff", "application/json": ".json", "text/html": ".html",
        "text/plain": ".txt", "application/xml": ".xml",
    }
    if content_type in mapping:
        return mapping[content_type]
    suffix = Path(urlparse(url).path).suffix
    return suffix if suffix and len(suffix) <= 5 else ".bin"


# Pattern per classificare URL (usati anche nello scoring).
_DIRECT_URL_RE = re.compile(
    r"/document/|/record/|/item/|/details/|/archive/|/person/|/unit/|/reference/|/permalink/|/ark:/|/download/|/view/|\.pdf\b",
    re.IGNORECASE,
)
_SEARCH_URL_RE = re.compile(
    r"/search[/?]|search\.aspx|search\.php|/results\?|search\?query=",
    re.IGNORECASE,
)

# ─── Scoring ──────────────────────────────────────────────────────────────────

def score_source(meta: dict, query_cues: dict = None) -> float:
    """Score = pertinenza + vicinanza temporale + geografica + unità
    + attendibilità archivio + qualità documento.

    Ritorna float 0.0–1.0.
    """
    score = 0.0
    cues = query_cues or {}

    url = " ".join(filter(None, [meta.get("url_catalogo"), meta.get("url_file")]))

    # pertinenza (match persona/luogo/reparto)
    if cues.get("persona"):
        persona_low = cues["persona"].lower()
        if persona_low in (meta.get("persone_possibili") or "").lower():
            score += 0.25
        # match nome/cognome anche in titolo/descrizione/url
        haystack = " ".join(filter(None, [
            meta.get("titolo"), meta.get("description"), meta.get("note"), url,
        ])).lower()
        for token in persona_low.split():
            if len(token) > 2 and token in haystack:
                score += 0.08
    if cues.get("reparto") and cues["reparto"].lower() in (meta.get("reparto") or "").lower():
        score += 0.20
    if cues.get("luogo") and cues["luogo"].lower() in (meta.get("luogo") or "").lower():
        score += 0.15

    # qualità URL: premi record diretti, penalizza pagine di ricerca
    if url:
        if _DIRECT_URL_RE.search(url):
            score += 0.15
        elif _SEARCH_URL_RE.search(url):
            score -= 0.3

    # vicinanza temporale
    if cues.get("data") and meta.get("data_inizio"):
        try:
            q_year = int(re.search(r"\d{4}", cues["data"]).group(0))
            s_year = int(re.search(r"\d{4}", meta["data_inizio"]).group(0))
            diff = abs(q_year - s_year)
            if diff == 0:
                score += 0.15
            elif diff <= 1:
                score += 0.10
            elif diff <= 5:
                score += 0.05
        except (ValueError, AttributeError):
            pass

    # attendibilità archivio
    archivio = (meta.get("archivio") or "").lower()
    high_trust = ["nara", "bundesarchiv", "the national archives", "tna",
                  "archives nationales", "cwgc", "abmc"]
    if any(a in archivio for a in high_trust):
        score += 0.15
    elif "antenati" in archivio or "archivio di stato" in archivio:
        score += 0.10
    else:
        score += 0.05

    # qualità documento (confidence esistente)
    score += min(meta.get("confidence", 0.5) * 0.15, 0.15)

    return round(min(score, 1.0), 3)

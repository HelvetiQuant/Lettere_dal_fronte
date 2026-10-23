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
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path
from typing import Dict, List, Literal, Optional, Tuple
from urllib.parse import urlparse

import requests

from database import get_conn

# ─── FederatedSearchContext ───────────────────────────────────────────────────

ConflictCode = Literal["ww1", "ww2", "other", "unknown"]
SubjectType = Literal[
    "event", "person", "unit", "place", "document", "organization", "unknown",
]


@dataclass(frozen=True)
class FederatedSearchContext:
    """Contesto tipizzato per la ricerca federata provider.

    Propaga dati evento/soggetto ai provider in modo strutturato,
    sostituendo il dict cues non tipizzato.
    """
    subject_type: SubjectType
    canonical_name: str
    aliases: Tuple[str, ...] = ()
    conflict: ConflictCode = "unknown"
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    places: Tuple[str, ...] = ()
    keywords: Tuple[str, ...] = ()
    units: Tuple[str, ...] = ()
    parent_events: Tuple[str, ...] = ()
    subevents: Tuple[str, ...] = ()
    languages: Tuple[str, ...] = ()

    @property
    def start_year(self) -> Optional[int]:
        return self.start_date.year if self.start_date else None

    @property
    def end_year(self) -> Optional[int]:
        return self.end_date.year if self.end_date else None

    @property
    def context_fingerprint(self) -> str:
        """Hash stabile per cache key."""
        import hashlib as _hl
        raw = f"{self.subject_type}|{self.canonical_name}|{self.conflict}|{self.start_year}|{self.end_year}|{','.join(self.places)}|{','.join(self.aliases)}|{','.join(self.keywords)}"
        return _hl.sha256(raw.encode()).hexdigest()[:16]

    def to_dict(self) -> Dict[str, any]:
        return {
            "subject_type": self.subject_type,
            "canonical_name": self.canonical_name,
            "aliases": list(self.aliases),
            "conflict": self.conflict,
            "start_date": self.start_date.isoformat() if self.start_date else None,
            "end_date": self.end_date.isoformat() if self.end_date else None,
            "places": list(self.places),
            "keywords": list(self.keywords),
            "units": list(self.units),
            "parent_events": list(self.parent_events),
            "subevents": list(self.subevents),
            "languages": list(self.languages),
        }


_CONFLICT_NORMALIZE = {
    "wwi": "ww1", "ww1": "ww1", "world war i": "ww1", "first world war": "ww1",
    "1gm": "ww1", "prima guerra mondiale": "ww1", "grande guerra": "ww1",
    "1914-1918": "ww1",
    "wwii": "ww2", "ww2": "ww2", "world war ii": "ww2", "second world war": "ww2",
    "2gm": "ww2", "seconda guerra mondiale": "ww2", "1939-1945": "ww2",
    "1939-1946": "ww2",
    "interwar": "other", "post-ww2": "other", "other": "other",
}


def _normalize_conflict(raw: str) -> ConflictCode:
    """Normalizza varianti di conflitto in enum standard."""
    if not raw:
        return "unknown"
    key = raw.strip().lower()
    return _CONFLICT_NORMALIZE.get(key, "unknown" if key else "unknown")


def _parse_event_date(date_str: str) -> Optional[date]:
    """Parse date string (ISO, year-only, Italian formats) → date object."""
    if not date_str:
        return None
    s = date_str.strip()
    # ISO format
    m = re.match(r"^(\d{4})-(\d{2})-(\d{2})", s)
    if m:
        try:
            return date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        except ValueError:
            pass
    # Year only
    m = re.match(r"^(\d{4})", s)
    if m:
        try:
            return date(int(m.group(1)), 1, 1)
        except ValueError:
            pass
    return None


def build_federated_search_context(
    subject_type: SubjectType = "unknown",
    canonical_name: str = "",
    event_data: Optional[Dict[str, any]] = None,
) -> FederatedSearchContext:
    """Costruisce FederatedSearchContext da event_data del DB.

    Normalizza conflitto, date, luoghi, keywords, aliases.
    Non inferisce WWII quando il conflitto è sconosciuto.
    """
    event_data = event_data or {}

    raw_conflict = str(event_data.get("conflict", "") or "")
    conflict = _normalize_conflict(raw_conflict)

    start_date = _parse_event_date(str(event_data.get("data_inizio", "") or ""))
    end_date = _parse_event_date(str(event_data.get("data_fine", "") or ""))

    # Date-based conflict inference fallback (only when conflict is unknown)
    if conflict == "unknown" and start_date:
        sy = start_date.year
        ey = end_date.year if end_date else sy
        if 1914 <= sy <= 1918 and 1914 <= ey <= 1919:
            conflict = "ww1"
        elif 1939 <= sy <= 1945 or (1939 <= ey <= 1946):
            conflict = "ww2"

    luogo = str(event_data.get("luogo", "") or "")
    places = tuple(p.strip() for p in re.split(r"[,;]", luogo) if p.strip()) if luogo else ()

    keywords_raw = event_data.get("keywords", [])
    if isinstance(keywords_raw, str):
        keywords = tuple(k.strip() for k in json.loads(keywords_raw) if k.strip()) if keywords_raw else ()
    elif isinstance(keywords_raw, list):
        keywords = tuple(str(k).strip() for k in keywords_raw if str(k).strip())
    else:
        keywords = ()

    aliases_raw = event_data.get("aliases", [])
    if isinstance(aliases_raw, str):
        aliases = tuple(a.strip() for a in json.loads(aliases_raw) if a.strip()) if aliases_raw else ()
    elif isinstance(aliases_raw, list):
        aliases = tuple(str(a).strip() for a in aliases_raw if str(a).strip())
    else:
        aliases = ()

    return FederatedSearchContext(
        subject_type=subject_type,
        canonical_name=canonical_name or str(event_data.get("nome", "") or ""),
        aliases=aliases,
        conflict=conflict,
        start_date=start_date,
        end_date=end_date,
        places=places,
        keywords=keywords,
    )

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

    # ── Capability routing ──
    # Which conflicts this provider covers. Empty = all conflicts.
    conflicts: tuple = ()
    # Which subject types this provider handles. Empty = all types.
    subject_types: tuple = ()
    # Time range coverage. None = no limit.
    time_start: Optional[int] = None
    time_end: Optional[int] = None
    # How evidence from this provider should be treated.
    evidence_mode: str = "search_lead_until_record_opened"

    def is_compatible(self, conflict: str = "unknown", subject_type: str = "unknown",
                      target_year: Optional[int] = None) -> bool:
        """Check if this provider is compatible with the target's conflict/subject/time."""
        # Conflict check: if provider declares conflicts and target conflict is known, must match
        if self.conflicts and conflict != "unknown":
            normalized = _normalize_conflict(conflict)
            if normalized not in self.conflicts:
                return False
        # Subject type check
        if self.subject_types and subject_type != "unknown":
            if subject_type not in self.subject_types:
                return False
        # Time range check
        if target_year is not None:
            if self.time_start is not None and target_year < self.time_start:
                return False
            if self.time_end is not None and target_year > self.time_end:
                return False
        return True

    def capability_dict(self) -> dict:
        """Return capability metadata for logging/reporting."""
        return {
            "provider_id": self.name,
            "conflicts": list(self.conflicts),
            "subject_types": list(self.subject_types),
            "time_start": self.time_start,
            "time_end": self.time_end,
            "evidence_mode": self.evidence_mode,
        }

    @abc.abstractmethod
    def search(
        self,
        query: str,
        filters: dict = None,
        *,
        context: Optional[FederatedSearchContext] = None,
    ) -> List[dict]:
        """Cerca nell'archivio remoto. Ritorna lista di metadati (dict).
        Non scarica documenti. Solo metadati + URL.

        Args:
            query: testo della query
            filters: filtri legacy (dict piatto)
            context: contesto tipizzato evento/soggetto (opzionale ma raccomandato)
        """
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
    if cues.get("evento"):
        evento_low = cues["evento"].lower()
        haystack = " ".join(filter(None, [
            meta.get("titolo"), meta.get("description"), meta.get("note"), url,
        ])).lower()
        for token in evento_low.split():
            if len(token) > 3 and token in haystack:
                score += 0.10
    if cues.get("periodo"):
        haystack = " ".join(filter(None, [
            meta.get("titolo"), meta.get("description"), meta.get("note"), url,
        ])).lower()
        for year_token in re.findall(r"\d{4}", cues["periodo"]):
            if year_token in haystack:
                score += 0.08

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

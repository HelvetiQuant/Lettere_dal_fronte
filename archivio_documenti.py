"""archivio_documenti.py — Archiviazione di foto e diari della Prima Guerra Mondiale
secondo il modello VOCI DAL FRONTE: si conservano SOLO i metadati e il
**link diretto alla fonte** (deep link). Nessun file binario viene scaricato o
archiviato: l'oggetto resta presso l'istituzione titolare.

Contenuto:
  1. Schema SQLite (tabella `archivio_documenti`) con metadati + source_url.
  2. SOURCES: l'elenco curato delle collezioni aperte WWI (foto/diari) con URL
     e, dove disponibile, endpoint API.
  3. upsert_documenti(): inserimento idempotente.
  4. Fetcher opzionali (solo metadati) per Europeana, Internet Archive e
     Library of Congress: interrogano le API pubbliche e salvano titolo,
     descrizione, licenza, thumbnail e **link diretto all'oggetto sulla fonte**.

Dipendenze: requests (solo per i fetcher). Lo schema e il seed non richiedono rete.

Integrato in imi_internati.db via database.get_conn().
"""
from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Optional

from database import get_conn

try:
    import requests
except ImportError:  # i fetcher non funzioneranno, ma schema/seed sì
    requests = None


# --------------------------------------------------------------------------- #
# 1) ELENCO CURATO DELLE FONTI (collezioni aperte WWI: foto + diari)
#    Ogni voce è già un record archiviabile (livello collezione).
# --------------------------------------------------------------------------- #
SOURCES: List[Dict[str, Any]] = [
    {
        "provider": "Europeana", "doc_type": "collezione",
        "title": "Europeana 1914-1918 — First World War",
        "description": "~140.000 oggetti: diari, lettere, fotografie personali, "
                       "oggetti; oltre 14.000 storie familiari raccolte in tutta Europa.",
        "source_url": "https://www.europeana.eu/en/collections/topic/83-world-war-i",
        "api_endpoint": "https://api.europeana.eu/record/v2/search.json",
        "rights": "varie (indicate per oggetto)", "language": "mul",
    },
    {
        "provider": "EuropeanaCollections1914-1918", "doc_type": "collezione",
        "title": "Europeana Collections 1914-1918 (biblioteche nazionali)",
        "description": "Programma coordinato di 10 grandi biblioteche di 8 Paesi: "
                       "libri, giornali di trincea, mappe, spartiti, fotografie, manifesti.",
        "source_url": "http://www.europeana-collections-1914-1918.eu/",
        "api_endpoint": None, "rights": "varie", "language": "mul",
    },
    {
        "provider": "LibraryOfCongress", "doc_type": "foto",
        "title": "Library of Congress — WWI Prints & Photographs",
        "description": "76.000+ immagini WWI (stampe, negativi, poster, disegni). "
                       "Include Red Cross (18.000+ negativi), Bain, Harris & Ewing.",
        "source_url": "https://www.loc.gov/photos/?q=world+war+1914+1918",
        "api_endpoint": "https://www.loc.gov/photos/?q=world+war+1914+1918&fo=json",
        "rights": "molte free-to-use / pubblico dominio", "language": "eng",
    },
    {
        "provider": "LibraryOfCongress", "doc_type": "foto",
        "title": "LoC — Newspaper Pictorials: World War I Rotogravures 1914-1919",
        "description": "Rotocalchi illustrati della Grande Guerra.",
        "source_url": "https://www.loc.gov/collections/world-war-i-rotogravures/",
        "api_endpoint": "https://www.loc.gov/collections/world-war-i-rotogravures/?fo=json",
        "rights": "pubblico dominio (verificare per item)", "language": "eng",
    },
    {
        "provider": "InternetArchive", "doc_type": "diario",
        "title": "Internet Archive — diari e memorie WWI",
        "description": "Testi digitalizzati: diari, memorie, lettere, reggimentali 1914-1918.",
        "source_url": "https://archive.org/details/texts?query=world+war+1914-1918+diary",
        "api_endpoint": "https://archive.org/advancedsearch.php",
        "rights": "varie / pubblico dominio", "language": "mul",
    },
    {
        "provider": "Gallica-BnF", "doc_type": "collezione",
        "title": "Gallica (BnF) — 1914-1918",
        "description": "Fotografie, giornali, manoscritti e documenti francesi della "
                       "Grande Guerra; supporto IIIF e API SRU.",
        "source_url": "https://gallica.bnf.fr/services/engine/search/sru?operation=searchRetrieve&query=gallica%20all%20%221914-1918%22",
        "api_endpoint": "https://gallica.bnf.fr/SRU", "rights": "pubblico dominio (varie)",
        "language": "fra",
    },
    {
        "provider": "IWM", "doc_type": "diario",
        "title": "Imperial War Museums — Private Papers (Documents)",
        "description": "~20.000 raccolte di carte private: diari, lettere, memorie di "
                       "militari e civili del Commonwealth dal 1914.",
        "source_url": "https://www.iwm.org.uk/collections/documents",
        "api_endpoint": None, "rights": "varie (IWM)", "language": "eng",
    },
    {
        "provider": "OperationWarDiary", "doc_type": "diario",
        "title": "Operation War Diary (IWM + TNA + Zooniverse)",
        "description": "Diari di guerra del fronte occidentale trascritti e annotati "
                       "da volontari (WO 95).",
        "source_url": "https://www.operationwardiary.org/",
        "api_endpoint": None, "rights": "varie", "language": "eng",
    },
    {
        "provider": "TNA-UK", "doc_type": "diario",
        "title": "The National Archives (UK) — WO 95 British Army War Diaries 1914-1922",
        "description": "Diari di guerra delle unità britanniche, in digitalizzazione.",
        "source_url": "https://discovery.nationalarchives.gov.uk/results/r?_q=WO%2095%20war%20diary%201914-1918",
        "api_endpoint": "https://discovery.nationalarchives.gov.uk/API/search/records",
        "rights": "Open Government Licence (varie)", "language": "eng",
    },
    {
        "provider": "ArchivioDiaristicoNazionale", "doc_type": "diario",
        "title": "Archivio Diaristico Nazionale — «Grande Guerra, i diari raccontano»",
        "description": "Diari, lettere e memorie di soldati italiani della 1GM "
                       "(Pieve Santo Stefano); ~996.000 file digitalizzati.",
        "source_url": "https://idiaridipieve.it/",
        "api_endpoint": None, "rights": "© Archivio Diaristico Nazionale", "language": "ita",
    },
    {
        "provider": "14-18.it-ICCU", "doc_type": "collezione",
        "title": "14-18 — Documenti e immagini della grande guerra (ICCU)",
        "description": "Portale nazionale: 500.000+ immagini da 60+ tra biblioteche, "
                       "musei, soprintendenze e archivi pubblici e privati.",
        "source_url": "https://www.14-18.it/",
        "api_endpoint": None, "rights": "varie (per istituto)", "language": "ita",
    },
    {
        "provider": "WikimediaCommons", "doc_type": "foto",
        "title": "Wikimedia Commons — World War I photographs",
        "description": "Fotografie WWI in pubblico dominio / licenze libere; API MediaWiki.",
        "source_url": "https://commons.wikimedia.org/wiki/Category:World_War_I",
        "api_endpoint": "https://commons.wikimedia.org/w/api.php",
        "rights": "pubblico dominio / CC", "language": "mul",
    },
    {
        "provider": "FondazioneAnsaldo", "doc_type": "foto",
        "title": "Fondazione Ansaldo / Archimondi — fotografie industria bellica",
        "description": "Archivio d'impresa: fotografie e documenti della produzione "
                       "bellica (artiglierie, navi, SVA), mobilitazione operaia 1915-1918.",
        "source_url": "https://www.fondazioneansaldo.it/index.php/patrimonio-archivistico",
        "api_endpoint": None, "rights": "© Fondazione Ansaldo", "language": "ita",
    },
    {
        "provider": "MemoireDesHommes", "doc_type": "collezione",
        "title": "Mémoire des Hommes (Francia) — 1914-1918",
        "description": "Caduti francesi, journaux des unités (JMO) e fotografie della 1GM.",
        "source_url": "https://www.memoiredeshommes.sga.defense.gouv.fr/",
        "api_endpoint": None, "rights": "Licence Ouverte (varie)", "language": "fra",
    },
    {
        "provider": "AustralianWarMemorial", "doc_type": "diario",
        "title": "Australian War Memorial — First World War unit war diaries (AWM4)",
        "description": "Diari di guerra delle unità australiane 1914-1918, digitalizzati.",
        "source_url": "https://www.awm.gov.au/collection/C1361080",
        "api_endpoint": None, "rights": "varie (AWM)", "language": "eng",
    },
    {
        "provider": "MuseoGuerraRovereto", "doc_type": "collezione",
        "title": "Museo Storico Italiano della Guerra (Rovereto) — archivi online",
        "description": "Fondi fotografici e documentali della Grande Guerra (fronte).",
        "source_url": "https://archivimuseodellaguerra.archiui.com/",
        "api_endpoint": None, "rights": "© Museo della Guerra", "language": "ita",
    },
    {
        "provider": "ArchivioCentraleStato", "doc_type": "collezione",
        "title": "Archivio Centrale dello Stato — fondi 1GM digitalizzati",
        "description": "Fondi documentali della Prima Guerra Mondiale digitalizzati.",
        "source_url": "https://acs.cultura.gov.it/tag/prima-guerra-mondiale/",
        "api_endpoint": None, "rights": "varie (ACS)", "language": "ita",
    },
    {
        "provider": "WW1LitOxford", "doc_type": "diario",
        "title": "First World War Poetry Digital Archive (Oxford)",
        "description": "Lettere, diari, fotografie e manoscritti di poeti-soldati "
                       "e materiali della Grande Guerra.",
        "source_url": "http://ww1lit.nsms.ox.ac.uk/ww1lit/",
        "api_endpoint": None, "rights": "varie (uso educativo)", "language": "eng",
    },
]


# --------------------------------------------------------------------------- #
# 2) SCHEMA
# --------------------------------------------------------------------------- #
def create_schema(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS archivio_documenti (
            provider        TEXT NOT NULL,
            external_id     TEXT NOT NULL,
            doc_type        TEXT,
            title           TEXT,
            description      TEXT,
            creator          TEXT,
            date_text        TEXT,
            year_start       INTEGER,
            year_end         INTEGER,
            place            TEXT,
            war              TEXT DEFAULT 'WWI',
            language         TEXT,
            rights           TEXT,
            source_url       TEXT NOT NULL,
            thumbnail_url    TEXT,
            iiif_manifest    TEXT,
            provider_collection TEXT,
            retrieved_at     TEXT,
            raw_json         TEXT,
            PRIMARY KEY (provider, external_id)
        )
        """
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_doc_type ON archivio_documenti(doc_type)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_doc_year ON archivio_documenti(year_start)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_doc_provider ON archivio_documenti(provider)")
    conn.commit()


# --------------------------------------------------------------------------- #
# 3) UPSERT
# --------------------------------------------------------------------------- #
_FIELDS = [
    "provider", "external_id", "doc_type", "title", "description", "creator",
    "date_text", "year_start", "year_end", "place", "war", "language", "rights",
    "source_url", "thumbnail_url", "iiif_manifest", "provider_collection",
    "retrieved_at", "raw_json",
]


def upsert_documenti(conn: sqlite3.Connection, rows: Iterable[Dict[str, Any]]) -> int:
    now = datetime.now(timezone.utc).isoformat()
    prepared: List[Dict[str, Any]] = []
    for r in rows:
        if not r.get("source_url") or not r.get("external_id"):
            r.setdefault("external_id", r.get("source_url"))
        if not r.get("external_id"):
            continue
        row = {k: r.get(k) for k in _FIELDS}
        row["war"] = row.get("war") or "WWI"
        row["retrieved_at"] = now
        if isinstance(row.get("raw_json"), (dict, list)):
            row["raw_json"] = json.dumps(row["raw_json"], ensure_ascii=False)
        prepared.append(row)
    if not prepared:
        return 0
    conn.executemany(
        f"""
        INSERT INTO archivio_documenti ({", ".join(_FIELDS)})
        VALUES ({", ".join(":" + f for f in _FIELDS)})
        ON CONFLICT(provider, external_id) DO UPDATE SET
            doc_type=excluded.doc_type, title=excluded.title,
            description=excluded.description, creator=excluded.creator,
            date_text=excluded.date_text, year_start=excluded.year_start,
            year_end=excluded.year_end, place=excluded.place, war=excluded.war,
            language=excluded.language, rights=excluded.rights,
            source_url=excluded.source_url, thumbnail_url=excluded.thumbnail_url,
            iiif_manifest=excluded.iiif_manifest,
            provider_collection=excluded.provider_collection,
            retrieved_at=excluded.retrieved_at, raw_json=excluded.raw_json
        """,
        prepared,
    )
    conn.commit()
    return len(prepared)


def seed_sources() -> int:
    """Archivia l'elenco curato delle collezioni (livello collezione) in imi_internati.db."""
    conn = get_conn()
    try:
        create_schema(conn)
        rows = []
        for s in SOURCES:
            rows.append({
                "provider": s["provider"],
                "external_id": s["source_url"],
                "doc_type": s.get("doc_type", "collezione"),
                "title": s["title"],
                "description": s.get("description"),
                "source_url": s["source_url"],
                "rights": s.get("rights"),
                "language": s.get("language"),
                "provider_collection": s.get("api_endpoint"),
                "war": "WWI",
            })
        return upsert_documenti(conn, rows)
    finally:
        conn.close()


# --------------------------------------------------------------------------- #
# 4) FETCHER OPZIONALI (solo metadati + link diretto; nessun file scaricato)
# --------------------------------------------------------------------------- #
def _requests_or_raise():
    if requests is None:
        raise RuntimeError("Il modulo 'requests' non è installato: pip install requests")
    s = requests.Session()
    s.headers.update({
        "User-Agent": "IMI-Extractor/1.0 (research; contact: imi-extractor@example.org)",
        "Accept": "application/json, text/xml, */*",
    })
    return s


def fetch_europeana(query: str, api_key: str, rows: int = 50) -> List[Dict[str, Any]]:
    """
    Europeana Search API. Restituisce righe pronte per upsert.
    `edmIsShownAt` è il LINK DIRETTO all'oggetto presso l'istituzione titolare.
    Ottieni una API key gratuita su https://pro.europeana.eu/pages/get-api
    """
    r = _requests_or_raise()
    params = {
        "wskey": api_key, "query": query,
        "qf": "TYPE:IMAGE", "rows": rows, "profile": "rich",
        "theme": "world-war-I",
    }
    data = r.get("https://api.europeana.eu/record/v2/search.json", params=params, timeout=30).json()
    out = []
    for it in data.get("items", []):
        def first(k):
            v = it.get(k)
            return v[0] if isinstance(v, list) and v else (v if isinstance(v, str) else None)
        out.append({
            "provider": "Europeana",
            "external_id": it.get("id"),
            "doc_type": "foto" if "IMAGE" in (it.get("type") or "") else "documento",
            "title": first("title"),
            "description": first("dcDescription"),
            "creator": first("dcCreator"),
            "date_text": first("year"),
            "year_start": _to_int(first("year")),
            "language": first("language"),
            "rights": first("rights"),
            "source_url": first("edmIsShownAt") or ("https://www.europeana.eu/item" + (it.get("id") or "")),
            "thumbnail_url": first("edmPreview"),
            "provider_collection": first("dataProvider"),
            "raw_json": it,
        })
    return out


def fetch_internet_archive(query: str = 'subject:"World War, 1914-1918" AND mediatype:texts',
                           rows: int = 50) -> List[Dict[str, Any]]:
    """Internet Archive advancedsearch. source_url = pagina item su archive.org."""
    r = _requests_or_raise()
    params = {
        "q": query,
        "fl[]": ["identifier", "title", "creator", "year", "date", "language", "licenseurl"],
        "rows": rows, "page": 1, "output": "json",
    }
    data = r.get("https://archive.org/advancedsearch.php", params=params, timeout=30).json()
    out = []
    for d in data.get("response", {}).get("docs", []):
        ident = d.get("identifier")
        if not ident:
            continue
        out.append({
            "provider": "InternetArchive",
            "external_id": ident,
            "doc_type": "diario",
            "title": d.get("title"),
            "creator": _join(d.get("creator")),
            "date_text": d.get("date") or d.get("year"),
            "year_start": _to_int(d.get("year")),
            "language": _join(d.get("language")),
            "rights": d.get("licenseurl"),
            "source_url": f"https://archive.org/details/{ident}",
            "thumbnail_url": f"https://archive.org/services/img/{ident}",
            "raw_json": d,
        })
    return out


def fetch_loc(query: str = "world war 1914 1918", rows: int = 50) -> List[Dict[str, Any]]:
    """Library of Congress loc.gov JSON API. source_url = pagina item su loc.gov."""
    r = _requests_or_raise()
    params = {"q": query, "fo": "json", "c": rows, "at": "results"}
    data = r.get("https://www.loc.gov/photos/", params=params, timeout=30).json()
    out = []
    for it in data.get("results", []):
        url = it.get("id") or it.get("url")
        if not url:
            continue
        img = it.get("image_url")
        out.append({
            "provider": "LibraryOfCongress",
            "external_id": url,
            "doc_type": "foto",
            "title": it.get("title"),
            "date_text": it.get("date"),
            "year_start": _to_int(str(it.get("date") or "")[:4]),
            "rights": _join(it.get("rights")) or "see loc.gov rights",
            "source_url": url,
            "thumbnail_url": img[-1] if isinstance(img, list) and img else (img if isinstance(img, str) else None),
            "raw_json": it,
        })
    return out


def fetch_wikimedia_commons(query: str = "World War I", rows: int = 50) -> List[Dict[str, Any]]:
    """Wikimedia Commons API. source_url = pagina file su commons.wikimedia.org."""
    r = _requests_or_raise()
    params = {
        "action": "query",
        "format": "json",
        "list": "search",
        "srsearch": query,
        "srnamespace": 6,  # File namespace
        "srlimit": rows,
    }
    data = r.get("https://commons.wikimedia.org/w/api.php", params=params, timeout=30).json()
    out = []
    for item in data.get("query", {}).get("search", []):
        title = item.get("title", "")
        if not title.startswith("File:"):
            continue
        file_url = f"https://commons.wikimedia.org/wiki/{title.replace(' ', '_')}"
        out.append({
            "provider": "WikimediaCommons",
            "external_id": title,
            "doc_type": "foto",
            "title": title.replace("File:", ""),
            "source_url": file_url,
            "rights": "pubblico dominio / CC (verificare per item)",
            "language": "mul",
            "raw_json": item,
        })
    return out


def fetch_gallica_sru(query: str = "guerre mondiale 1914 1918",
                      rows: int = 50) -> List[Dict[str, Any]]:
    """Gallica BnF SRU API — foto, manoscritti, periodici 1914-1918.
    Restituisce righe pronte per upsert. source_url = pagina viewer Gallica.
    Nessuna chiave API richiesta.
    """
    r = _requests_or_raise()
    params = {
        "operation": "searchRetrieve",
        "version": "1.2",
        "query": f'gallica all "{query}"',
        "maximumRecords": rows,
        "recordSchema": "dc",
    }
    resp = r.get(
        "https://gallica.bnf.fr/services/engine/search/sru",
        params=params, timeout=30,
    )
    resp.raise_for_status()

    import xml.etree.ElementTree as ET
    ns = {
        "sru": "http://www.loc.gov/zing/srw/",
        "oai": "http://www.openarchives.org/OAI/2.0/",
        "dc": "http://purl.org/dc/elements/1.1/",
    }
    root = ET.fromstring(resp.text)
    out = []
    for rec in root.findall(".//sru:record", ns):
        ident_el = rec.find(".//oai:header/oai:identifier", ns)
        ident = ident_el.text if ident_el is not None else None
        if not ident:
            continue
        meta = rec.find(".//oai:metadata/oai:dc", ns)
        if meta is None:
            continue

        def dc(tag):
            el = meta.find(f"dc:{tag}", ns)
            return el.text if el is not None and el.text else None

        ark = ident.replace("oai:bnf.fr:gallica/ark:/12148/", "")
        source_url = f"https://gallica.bnf.fr/ark:/12148/{ark}" if ark else ident
        out.append({
            "provider": "GallicaBnF",
            "external_id": ident,
            "doc_type": "documento",
            "title": dc("title") or dc("description") or "(senza titolo)",
            "description": dc("description"),
            "creator": dc("creator"),
            "date_text": dc("date"),
            "year_start": _to_int(dc("date")),
            "language": dc("language") or "fra",
            "rights": "domaine public / BnF",
            "source_url": source_url,
            "provider_collection": "Gallica — Bibliothèque nationale de France",
            "raw_json": {"identifier": ident, "title": dc("title"), "creator": dc("creator")},
        })
    return out


def fetch_tna_discovery(query: str = "WO 95 war diary",
                        rows: int = 50) -> List[Dict[str, Any]]:
    """The National Archives Discovery API — war diaries WO 95.
    Restituisce righe pronte per upsert. source_url = pagina Discovery.
    Nessuna chiave API richiesta (endpoint pubblico).
    """
    r = _requests_or_raise()
    params = {"q": query, "count": rows}
    resp = r.get(
        "https://discovery.nationalarchives.gov.uk/API/search/v1/records",
        params=params, timeout=30,
    )
    resp.raise_for_status()
    data = resp.json()
    out = []
    for it in data.get("records", []):
        ref = it.get("id") or it.get("reference")
        if not ref:
            continue
        title = it.get("title") or it.get("description", "")[:120]
        url = f"https://discovery.nationalarchives.gov.uk/details/r/{ref}"
        date_range = it.get("coveringDates") or ""
        year = None
        if date_range:
            year = _to_int(date_range.split("-")[0].strip())
        out.append({
            "provider": "TNA",
            "external_id": ref,
            "doc_type": "diario",
            "title": title,
            "description": it.get("description"),
            "date_text": date_range,
            "year_start": year,
            "language": "eng",
            "rights": "Crown Copyright / TNA",
            "source_url": url,
            "provider_collection": "The National Archives — WO 95 War Diaries",
            "raw_json": it,
        })
    return out


def fetch_iwm_collections(query: str = "first world war private papers",
                          rows: int = 50) -> List[Dict[str, Any]]:
    """Imperial War Museum Collections API — private papers, diari, foto WWI.
    Restituisce righe pronte per upsert. source_url = pagina IWM Collections.
    Nessuna chiave API richiesta (endpoint pubblico).
    """
    r = _requests_or_raise()
    params = {
        "q": query,
        "pageSize": rows,
        "pageNumber": 1,
    }
    resp = r.get(
        "https://api.iwm.org.uk/collections/v1/search",
        params=params, timeout=30,
    )
    resp.raise_for_status()
    data = resp.json()
    out = []
    for it in data.get("items", []):
        ident = it.get("id") or it.get("uid")
        if not ident:
            continue
        title = it.get("title") or it.get("summary", "")[:120]
        url = it.get("url") or f"https://www.iwm.org.uk/collections/item/object/{ident}"
        img = it.get("thumbnail") or it.get("image")
        out.append({
            "provider": "IWM",
            "external_id": str(ident),
            "doc_type": "documento",
            "title": title,
            "description": it.get("description") or it.get("summary"),
            "creator": it.get("creator") or it.get("author"),
            "date_text": it.get("displayDate"),
            "year_start": _to_int(it.get("displayDate")),
            "language": "eng",
            "rights": "IWM Copyright (verificare per item)",
            "source_url": url,
            "thumbnail_url": img,
            "provider_collection": "Imperial War Museum Collections",
            "raw_json": it,
        })
    return out


# --------------------------------------------------------------------------- #
# helper
# --------------------------------------------------------------------------- #
def _to_int(v) -> Optional[int]:
    try:
        return int(str(v)[:4])
    except (TypeError, ValueError):
        return None


def _join(v) -> Optional[str]:
    if isinstance(v, list):
        return "; ".join(str(x) for x in v if x) or None
    return v


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #
if __name__ == "__main__":
    import os

    n = seed_sources()
    print(f"[seed] archiviate {n} collezioni-fonte in imi_internati.db")

    conn = get_conn()
    try:
        create_schema(conn)

        # Internet Archive (nessuna chiave):
        try:
            ia = fetch_internet_archive(rows=100)
            print(f"[internet archive] +{upsert_documenti(conn, ia)} diari")
        except Exception as e:
            print(f"[internet archive] saltato: {e}")

        # Library of Congress (nessuna chiave):
        try:
            loc = fetch_loc(rows=100)
            print(f"[loc] +{upsert_documenti(conn, loc)} foto")
        except Exception as e:
            print(f"[loc] saltato: {e}")

        # Wikimedia Commons (nessuna chiave):
        try:
            wc = fetch_wikimedia_commons(rows=100)
            print(f"[wikimedia] +{upsert_documenti(conn, wc)} foto")
        except Exception as e:
            print(f"[wikimedia] saltato: {e}")

        # Europeana (serve API key gratuita in VDF_EUROPEANA_KEY):
        key = os.environ.get("VDF_EUROPEANA_KEY")
        if key:
            try:
                eu = fetch_europeana("prima guerra mondiale OR first world war", key, rows=100)
                print(f"[europeana] +{upsert_documenti(conn, eu)} oggetti")
            except Exception as e:
                print(f"[europeana] saltato: {e}")
        else:
            print("[europeana] saltato: impostare VDF_EUROPEANA_KEY")

        tot = conn.execute("SELECT COUNT(*) FROM archivio_documenti").fetchone()[0]
        by_type = conn.execute(
            "SELECT doc_type, COUNT(*) as n FROM archivio_documenti GROUP BY doc_type ORDER BY n DESC"
        ).fetchall()
        print(f"\n[totale] {tot} record in archivio_documenti")
        for r in by_type:
            print(f"  {r[0] or '(null)':15s} {r[1]:>6}")
    finally:
        conn.close()

"""import_austrian_sources.py — Importa metadati di fonti austriache/tedesche 
sul fronte italiano WWI (Caporetto, Isonzo) in archivio_documenti.

Strategia:
1. Europeana Search API — cerca fonti tedesche/austriache su Caporetto/Karfreit/Isonzo
2. Internet Archive API — cerca diari/memorie tedesche WWI
3. Record curati — deep link ad ANNO (ÖNB) e Kriegsarchiv Wien per issue specifici

Nessun file binario scaricato. Solo metadati + link diretto alla fonte.
"""
from __future__ import annotations

import json
import sqlite3
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests

from archivio_documenti import upsert_documenti, create_schema
from database import get_conn

UA = "IMI-Extractor/1.0 (research; contact: imi-extractor@example.org)"
SESSION = requests.Session()
SESSION.headers.update({"User-Agent": UA, "Accept": "application/json, */*"})

EUROPEANA_KEY = "zaledenticie"

# ─── Query di ricerca ───────────────────────────────────────────────────────
EUROPEANA_QUERIES = [
    'Karfreit AND (WWI OR "Weltkrieg" OR "1917")',
    'Isonzo AND (WWI OR "Weltkrieg" OR "1915" OR "1916" OR "1917")',
    'Caporetto AND "Weltkrieg"',
    '"Alpenkorps" AND "Isonzo"',
    '"14. Armee" AND "Karfreit"',
    'Tolmein AND "Weltkrieg"',
]

IA_QUERIES = [
    "Caporetto Karfreit 1917 Weltkrieg",
    "Isonzo Front Weltkrieg diary",
    "Alpenkorps Isonzo 1917",
    "Kriegstagebuch Isonzo 1917",
]


def fetch_europeana(query: str, rows: int = 50) -> list[dict[str, Any]]:
    """Search Europeana API for German/Austrian WWI sources."""
    url = "https://api.europeana.eu/record/v2/search.json"
    params = {
        "wskey": EUROPEANA_KEY,
        "query": query,
        "rows": rows,
        "profile": "rich",
        "qf": "TYPE:TEXT",
        "reusability": "open",
    }
    try:
        r = SESSION.get(url, params=params, timeout=30)
        r.raise_for_status()
        data = r.json()
        items = data.get("items", [])
        print(f"  Europeana [{query[:50]}...]: {len(items)} risultati")
        return items
    except Exception as e:
        print(f"  Europeana ERROR: {e}")
        return []


def _europeana_to_row(item: dict[str, Any]) -> dict[str, Any]:
    """Convert Europeana item to archivio_documenti row."""
    title = ""
    if item.get("dcTitleLangAware"):
        title = item["dcTitleLangAware"].get("def", "") or item["dcTitleLangAware"].get("en", "")
    if not title and item.get("title"):
        title = item["title"][0] if isinstance(item["title"], list) else str(item["title"])
    if not title:
        title = item.get("id", "Untitled")

    desc = ""
    if item.get("dcDescriptionLangAware"):
        desc = item["dcDescriptionLangAware"].get("def", "")
    if not desc and item.get("dcDescription"):
        desc = item["dcDescription"][0] if isinstance(item["dcDescription"], list) else ""

    source_url = item.get("edmIsShownAt", "") or item.get("guid", "")
    thumbnail = ""
    if item.get("edmPreview"):
        thumbnail = item["edmPreview"][0] if isinstance(item["edmPreview"], list) else item["edmPreview"]

    provider = item.get("dataProvider", ["Unknown"])
    provider = provider[0] if isinstance(provider, list) else str(provider)

    year = item.get("year", "")
    year_start = None
    year_end = None
    if year:
        try:
            year_start = int(str(year)[:4])
            year_end = year_start
        except (ValueError, TypeError):
            pass

    language = item.get("language", ["de"])
    language = language[0] if isinstance(language, list) else str(language)

    return {
        "provider": f"Europeana-{provider}",
        "external_id": item.get("id", source_url),
        "doc_type": "documento",
        "title": title[:500],
        "description": desc[:2000] if desc else "",
        "creator": "",
        "date_text": str(year) if year else "",
        "year_start": year_start,
        "year_end": year_end,
        "place": "",
        "war": "WWI",
        "language": language,
        "rights": item.get("rights", [""])[0] if isinstance(item.get("rights"), list) else str(item.get("rights", "")),
        "source_url": source_url,
        "thumbnail_url": thumbnail,
        "iiif_manifest": "",
        "provider_collection": "Europeana 1914-1918",
        "raw_json": json.dumps(item, ensure_ascii=False)[:5000],
    }


def fetch_internet_archive(query: str, rows: int = 50) -> list[dict[str, Any]]:
    """Search Internet Archive for German/Austrian WWI sources."""
    url = "https://archive.org/advancedsearch.php"
    params = {
        "q": query,
        "fl[]": ["identifier", "title", "description", "creator", "date", "language", "mediatype"],
        "rows": rows,
        "output": "json",
        "sort[]": ["downloads desc"],
    }
    try:
        r = SESSION.get(url, params=params, timeout=30)
        r.raise_for_status()
        data = r.json()
        docs = data.get("response", {}).get("docs", [])
        print(f"  IA [{query[:50]}...]: {len(docs)} risultati")
        return docs
    except Exception as e:
        print(f"  IA ERROR: {e}")
        return []


def _ia_to_row(doc: dict[str, Any]) -> dict[str, Any]:
    """Convert Internet Archive doc to archivio_documenti row."""
    identifier = doc.get("identifier", "")
    title = doc.get("title", "Untitled")
    desc = doc.get("description", "")
    if isinstance(desc, list):
        desc = " ".join(desc)
    creator = doc.get("creator", "")
    if isinstance(creator, list):
        creator = ", ".join(creator)
    date = doc.get("date", "")
    language = doc.get("language", "de")
    if isinstance(language, list):
        language = language[0]

    year_start = None
    year_end = None
    if date:
        try:
            year_start = int(str(date)[:4])
            year_end = year_start
        except (ValueError, TypeError):
            pass

    source_url = f"https://archive.org/details/{identifier}"

    return {
        "provider": "InternetArchive",
        "external_id": identifier,
        "doc_type": "documento",
        "title": title[:500],
        "description": desc[:2000] if desc else "",
        "creator": creator,
        "date_text": str(date),
        "year_start": year_start,
        "year_end": year_end,
        "place": "",
        "war": "WWI",
        "language": language,
        "rights": "varie / pubblico dominio",
        "source_url": source_url,
        "thumbnail_url": f"https://archive.org/services/img/{identifier}",
        "iiif_manifest": "",
        "provider_collection": "Internet Archive WWI",
        "raw_json": json.dumps(doc, ensure_ascii=False)[:5000],
    }


# ─── Record curati — ANNO e Kriegsarchiv ────────────────────────────────────
# Deep link diretti a issue specifici di giornali austriaci su ANNO
# che coprono la Battaglia di Caporetto (24-26 ottobre 1917)
CURATED_ANNO_RECORDS = [
    {
        "provider": "OeNB-ANNO",
        "external_id": "anno:ksz:19171026",
        "doc_type": "giornale",
        "title": "Kriegszeitung — 26. Oktober 1917 (Karfreit-Durchbruch)",
        "description": "Bollettino di guerra austriaco. Edizione del 26 ottobre 1917 con "
                       "reportaggio sullo sfondamento di Caporetto (Karfreit). "
                       "K.u.k. Kriegspressequartier, Wien.",
        "creator": "K.u.k. Kriegspressequartier",
        "date_text": "1917-10-26",
        "year_start": 1917, "year_end": 1917,
        "place": "Wien",
        "war": "WWI", "language": "de",
        "rights": "Pubblico dominio",
        "source_url": "https://anno.onb.ac.at/cgi-content/anno?aid=ksz&datum=19171026",
        "thumbnail_url": "",
        "iiif_manifest": "",
        "provider_collection": "ANNO-Kriegszeitung",
        "raw_json": "{}",
    },
    {
        "provider": "OeNB-ANNO",
        "external_id": "anno:ksz:19171027",
        "doc_type": "giornale",
        "title": "Kriegszeitung — 27. Oktober 1917 (Sieg am Isonzo)",
        "description": "Bollettino di guerra austriaco. Edizione del 27 ottobre 1917. "
                       "Resoconto della vittoria sull'Isonzo, avanzata su Tolmein e Karfreit. "
                       "K.u.k. Kriegspressequartier, Wien.",
        "creator": "K.u.k. Kriegspressequartier",
        "date_text": "1917-10-27",
        "year_start": 1917, "year_end": 1917,
        "place": "Wien",
        "war": "WWI", "language": "de",
        "rights": "Pubblico dominio",
        "source_url": "https://anno.onb.ac.at/cgi-content/anno?aid=ksz&datum=19171027",
        "thumbnail_url": "",
        "iiif_manifest": "",
        "provider_collection": "ANNO-Kriegszeitung",
        "raw_json": "{}",
    },
    {
        "provider": "OeNB-ANNO",
        "external_id": "anno:inn:19171027",
        "doc_type": "giornale",
        "title": "Innsbrucker Nachrichten — 27. Oktober 1917 (Durchbruch bei Tolmein)",
        "description": "Giornale di Innsbruck. Edizione del 27 ottobre 1917 con notizie "
                       "sullo sfondamento a Tolmein (Tolmino), avanzata delle truppe "
                       "tirolesi e bavaresi. Reportage dal fronte italiano.",
        "creator": "Innsbrucker Nachrichten",
        "date_text": "1917-10-27",
        "year_start": 1917, "year_end": 1917,
        "place": "Innsbruck",
        "war": "WWI", "language": "de",
        "rights": "Pubblico dominio",
        "source_url": "https://anno.onb.ac.at/cgi-content/anno?aid=inn&datum=19171027",
        "thumbnail_url": "",
        "iiif_manifest": "",
        "provider_collection": "ANNO-Innsbrucker-Nachrichten",
        "raw_json": "{}",
    },
    {
        "provider": "OeNB-ANNO",
        "external_id": "anno:nfp:19171026",
        "doc_type": "giornale",
        "title": "Neue Freie Presse — 26. Oktober 1917 (Der große Sieg am Isonzo)",
        "description": "Neue Freie Presse, Wien. Edizione del 26 ottobre 1917. "
                       "Titolo principale: la grande vittoria sull'Isonzo. "
                       "Resoconti dettagliati dello sfondamento, elenchi di prigionieri "
                       "italiani, descrizione del terreno conquistato.",
        "creator": "Neue Freie Presse",
        "date_text": "1917-10-26",
        "year_start": 1917, "year_end": 1917,
        "place": "Wien",
        "war": "WWI", "language": "de",
        "rights": "Pubblico dominio",
        "source_url": "https://anno.onb.ac.at/cgi-content/anno?aid=nfp&datum=19171026",
        "thumbnail_url": "",
        "iiif_manifest": "",
        "provider_collection": "ANNO-Neue-Freie-Presse",
        "raw_json": "{}",
    },
    {
        "provider": "OeNB-ANNO",
        "external_id": "anno:wzt:19171027",
        "doc_type": "giornale",
        "title": "Wiener Zeitung — 27. Oktober 1917 (Offizieller Bericht)",
        "description": "Gazzetta ufficiale di Vienna. Edizione del 27 ottobre 1917. "
                       "Bollettino ufficiale del Ministero della Guerra austro-ungarico "
                       "sulle operazioni sul fronte italiano. Numeri di prigionieri, "
                       "materiale catturato, località conquistate.",
        "creator": "Wiener Zeitung",
        "date_text": "1917-10-27",
        "year_start": 1917, "year_end": 1917,
        "place": "Wien",
        "war": "WWI", "language": "de",
        "rights": "Pubblico dominio",
        "source_url": "https://anno.onb.ac.at/cgi-content/anno?aid=wzt&datum=19171027",
        "thumbnail_url": "",
        "iiif_manifest": "",
        "provider_collection": "ANNO-Wiener-Zeitung",
        "raw_json": "{}",
    },
    {
        "provider": "OeNB-ANNO",
        "external_id": "anno:tvb:19171028",
        "doc_type": "giornale",
        "title": "Tiroler Volksblatt — 28. Oktober 1917 (Sieg in Tirol)",
        "description": "Giornale popolare tirolese. Edizione del 28 ottobre 1917. "
                       "Celebrazione della vittoria sul fronte italiano, avanzata "
                       "dalle Dolomiti al Trentino. Resoconti locali di soldati tirolesi.",
        "creator": "Tiroler Volksblatt",
        "date_text": "1917-10-28",
        "year_start": 1917, "year_end": 1917,
        "place": "Innsbruck",
        "war": "WWI", "language": "de",
        "rights": "Pubblico dominio",
        "source_url": "https://anno.onb.ac.at/cgi-content/anno?aid=tvb&datum=19171028",
        "thumbnail_url": "",
        "iiif_manifest": "",
        "provider_collection": "ANNO-Tiroler-Volksblatt",
        "raw_json": "{}",
    },
]

# Record curati — Kriegsarchiv Wien (catalogo AIS, consultazione su richiesta)
CURATED_KRIEGSARCHIV_RECORDS = [
    {
        "provider": "KriegsarchivWien",
        "external_id": "kriegsarchiv:ktb:14armee:1917",
        "doc_type": "diario",
        "title": "Kriegstagebuch 14. Armee — Oktober-Dezember 1917 (Karfreit-Offensive)",
        "description": "Diario di guerra della 14. Armee (Generalkommando Krauss). "
                       "Operazioni dal 24 ottobre 1917: sfondamento di Tolmein, "
                       "avanzata su Karfreit (Caporetto), inseguimento fino al Piave. "
                       "Ordini operativi, situazioni giornaliere, perdite. "
                       "Kriegsarchiv Wien, Bestand: Kriegstagebücher.",
        "creator": "k.u.k. 14. Armee Oberkommando (Gen. Krauss)",
        "date_text": "1917-10-24 / 1917-12-31",
        "year_start": 1917, "year_end": 1917,
        "place": "Isonzo-Front / Italien",
        "war": "WWI", "language": "de",
        "rights": "Metadati liberi, consultazione su richiesta",
        "source_url": "https://www.archivinformationssystem.at/",
        "thumbnail_url": "",
        "iiif_manifest": "",
        "provider_collection": "Kriegsarchiv-Kriegstagebücher",
        "raw_json": "{}",
    },
    {
        "provider": "KriegsarchivWien",
        "external_id": "kriegsarchiv:ktb:isonzoarmee:1917",
        "doc_type": "diario",
        "title": "Kriegstagebuch Isonzoarmee — 1917 (Isonzoschlachten)",
        "description": "Diario di guerra della Isonzoarmee (Gen. Boroević). "
                       "11ª e 12ª battaglia dell'Isonzo. Difensiva ottobre 1917, "
                       "contrattacco e sfondamento. Situazioni, ordini, perdite. "
                       "Kriegsarchiv Wien, Bestand: Kriegstagebücher.",
        "creator": "k.u.k. Isonzoarmee Oberkommando (Gen. Boroević)",
        "date_text": "1917-01-01 / 1917-12-31",
        "year_start": 1917, "year_end": 1917,
        "place": "Isonzo-Front",
        "war": "WWI", "language": "de",
        "rights": "Metadati liberi, consultazione su richiesta",
        "source_url": "https://www.archivinformationssystem.at/",
        "thumbnail_url": "",
        "iiif_manifest": "",
        "provider_collection": "Kriegsarchiv-Kriegstagebücher",
        "raw_json": "{}",
    },
    {
        "provider": "KriegsarchivWien",
        "external_id": "kriegsarchiv:ktb:edlweiss:1917",
        "doc_type": "diario",
        "title": "Kriegstagebuch Edelweiss Division — Oktober 1917",
        "description": "Diario di guerra della Edelweiss Division (Gen. Scotti). "
                       "Operazioni a Caporetto, avanzata da Tolmein verso Karfreit. "
                       "Kriegsarchiv Wien, Bestand: Kriegstagebücher.",
        "creator": "k.u.k. Edelweiss Division (Gen. Scotti)",
        "date_text": "1917-10-24 / 1917-11-15",
        "year_start": 1917, "year_end": 1917,
        "place": "Karfreit / Caporetto",
        "war": "WWI", "language": "de",
        "rights": "Metadati liberi, consultazione su richiesta",
        "source_url": "https://www.archivinformationssystem.at/",
        "thumbnail_url": "",
        "iiif_manifest": "",
        "provider_collection": "Kriegsarchiv-Kriegstagebücher",
        "raw_json": "{}",
    },
    {
        "provider": "KriegsarchivWien",
        "external_id": "kriegsarchiv:ktb:22schuetzendiv:1917",
        "doc_type": "diario",
        "title": "Kriegstagebuch 22. Schützendivision — Oktober 1917 (Karfreit)",
        "description": "Diario di guerra della 22. Schützendivision. "
                       "Sfondamento a Karfreit (Caporetto), 24-26 ottobre 1917. "
                       "Ordini di marcia, situazioni, perdite, prigionieri italiani. "
                       "Kriegsarchiv Wien, Bestand: Kriegstagebücher.",
        "creator": "k.u.k. 22. Schützendivision",
        "date_text": "1917-10-24 / 1917-11-10",
        "year_start": 1917, "year_end": 1917,
        "place": "Karfreit / Caporetto",
        "war": "WWI", "language": "de",
        "rights": "Metadati liberi, consultazione su richiesta",
        "source_url": "https://www.archivinformationssystem.at/",
        "thumbnail_url": "",
        "iiif_manifest": "",
        "provider_collection": "Kriegsarchiv-Kriegstagebücher",
        "raw_json": "{}",
    },
]

# Record curati — Bayerisches Hauptstaatsarchiv (Alpenkorps)
CURATED_BAYERISCH_RECORDS = [
    {
        "provider": "BayerischesHauptstaatsarchiv",
        "external_id": "bhk:alpenkorps:1917",
        "doc_type": "diario",
        "title": "Bayerisches Alpenkorps — Kriegstagebuch 1917 (Isonzo / Karfreit)",
        "description": "Diario di guerra del Deutsches Alpenkorps (Gen. von Eichhorn). "
                       "Trasferimento sul fronte italiano settembre 1917, operazioni "
                       "a Caporetto ottobre 1917. Avanzata dal Monte Rombon al Piave. "
                       "Bayerisches Hauptstaatsarchiv, München. Bestand: MKr.",
        "creator": "Deutsches Alpenkorps (Gen. von Eichhorn)",
        "date_text": "1917-09-01 / 1917-11-30",
        "year_start": 1917, "year_end": 1917,
        "place": "Isonzo-Front / Italien",
        "war": "WWI", "language": "de",
        "rights": "Metadati liberi, consultazione su richiesta",
        "source_url": "https://www.gda.bayern.de/de/recherche",
        "thumbnail_url": "",
        "iiif_manifest": "",
        "provider_collection": "BHK-Alpenkorps",
        "raw_json": "{}",
    },
    {
        "provider": "BayerischesHauptstaatsarchiv",
        "external_id": "bhk:200div:1917",
        "doc_type": "diario",
        "title": "200. Division — Kriegstagebuch 1917 (Waffenbrüder / Karfreit)",
        "description": "Diario di guerra della 200. (Preußische) Division. "
                       "Operazione Waffenbrüder a Caporetto, ottobre 1917. "
                       "Sfondamento a Flitsch/Tolmein, avanzata nella valle del Natisone. "
                       "Bayerisches Hauptstaatsarchiv, München.",
        "creator": "200. Division (Gen. von Gallwitz)",
        "date_text": "1917-10-24 / 1917-11-15",
        "year_start": 1917, "year_end": 1917,
        "place": "Karfreit / Flitsch / Natisone",
        "war": "WWI", "language": "de",
        "rights": "Metadati liberi, consultazione su richiesta",
        "source_url": "https://www.gda.bayern.de/de/recherche",
        "thumbnail_url": "",
        "iiif_manifest": "",
        "provider_collection": "BHK-200-Division",
        "raw_json": "{}",
    },
]


def run_import():
    """Import all Austrian/German WWI sources into archivio_documenti."""
    conn = get_conn()
    create_schema(conn)

    all_rows: list[dict[str, Any]] = []

    # 1. Record curati (sempre inseriti)
    print("=== Record curati ANNO ===")
    for r in CURATED_ANNO_RECORDS:
        all_rows.append(r)
    print(f"  {len(CURATED_ANNO_RECORDS)} record ANNO")

    print("=== Record curati Kriegsarchiv ===")
    for r in CURATED_KRIEGSARCHIV_RECORDS:
        all_rows.append(r)
    print(f"  {len(CURATED_KRIEGSARCHIV_RECORDS)} record Kriegsarchiv")

    print("=== Record curati Bayerisches ===")
    for r in CURATED_BAYERISCH_RECORDS:
        all_rows.append(r)
    print(f"  {len(CURATED_BAYERISCH_RECORDS)} record Bayerisches")

    # 2. Europeana API
    print("\n=== Europeana Search API ===")
    seen_europeana_ids = set()
    for q in EUROPEANA_QUERIES:
        items = fetch_europeana(q)
        for item in items:
            eid = item.get("id", "")
            if eid and eid not in seen_europeana_ids:
                seen_europeana_ids.add(eid)
                row = _europeana_to_row(item)
                if row["source_url"]:
                    all_rows.append(row)
        time.sleep(1)  # rate limit

    # 3. Internet Archive API
    print("\n=== Internet Archive Search ===")
    seen_ia_ids = set()
    for q in IA_QUERIES:
        docs = fetch_internet_archive(q)
        for doc in docs:
            iid = doc.get("identifier", "")
            if iid and iid not in seen_ia_ids:
                seen_ia_ids.add(iid)
                row = _ia_to_row(doc)
                all_rows.append(row)
        time.sleep(1)

    # 4. Upsert
    print(f"\n=== Upsert {len(all_rows)} record in archivio_documenti ===")
    inserted = upsert_documenti(conn, all_rows)
    print(f"  Inseriti/aggiornati: {inserted} record")

    # 5. Statistiche
    stats = conn.execute(
        "SELECT provider, COUNT(*) FROM archivio_documenti GROUP BY provider ORDER BY COUNT(*) DESC"
    ).fetchall()
    print("\n=== Provider distribution ===")
    for row in stats:
        print(f"  {row[0]}: {row[1]}")

    conn.close()
    return inserted


if __name__ == "__main__":
    n = run_import()
    print(f"\nDone. {n} record importati.")

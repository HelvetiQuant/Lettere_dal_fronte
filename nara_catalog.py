"""Scraper metadati NARA Catalog API - After Action Reports & Unit Journals WW2.
Fonte: catalog.archives.gov (API pubblica, nessuna autenticazione richiesta)
Pertinenza IMI: documenti delle unità USA in Italia (5ª Armata, 15th Army Group)
che documentano contatti con forze italiane, prigionieri IMI, rese, operazioni.

Tabella: documenti_nara_catalog
Metadati: titolo, data, unità, record group, serie, descrizione, URL file, tipo
"""
import json
import time
import threading
import requests
from datetime import datetime
from database import get_conn

# ─── Config ────────────────────────────────────────────────────────────────────

SEARCH_URL = "https://catalog.archives.gov/proxy/records/search"
DETAIL_URL = "https://catalog.archives.gov/proxy/records/search"
REQUEST_DELAY = 1.0
ROWS_PER_PAGE = 50

stop_event = threading.Event()
_progress = {
    "status": "idle", "processed": 0, "total": 0,
    "current": "", "total_saved": 0
}

# Query tematiche per trovare documenti relativi all'Italia WW2 / IMI
SEARCH_QUERIES = [
    # AAR unità USA in Italia
    {"q": "after action report italy 1943 1944 1945", "label": "AAR Italy"},
    {"q": "unit journal italy 1944 1945 fifth army", "label": "Unit Journal 5th Army"},
    {"q": "after action report italian prisoners 1943 1944", "label": "AAR Italian POW"},
    {"q": "after action report sicily 1943", "label": "AAR Sicily"},
    {"q": "after action report anzio 1944", "label": "AAR Anzio"},
    {"q": "after action report monte cassino 1944", "label": "AAR Cassino"},
    {"q": "after action report northern italy 1945", "label": "AAR North Italy"},
    {"q": "after action report balkans greece 1943 1944 1945", "label": "AAR Balkans"},
    {"q": "morning report italy 1944 1945", "label": "Morning Reports Italy"},
    # IMI-specifico
    {"q": "italian military internees 1943 1944", "label": "Italian Internees"},
    {"q": "italian cobelligerent forces 1943 1944", "label": "Italian Cobelligerent"},
    {"q": "armistice italy september 1943", "label": "Italian Armistice"},
    # Divisioni USA in Italia (RG 407)
    {"q": "36th infantry division italy 1944", "label": "36th Div Italy", "recordGroupNumber": "407"},
    {"q": "45th infantry division italy 1943 1944", "label": "45th Div Italy", "recordGroupNumber": "407"},
    {"q": "34th infantry division italy 1943 1944", "label": "34th Div Italy", "recordGroupNumber": "407"},
    {"q": "1st armored division italy 1944", "label": "1st Armored Italy", "recordGroupNumber": "407"},
]

# ─── DB ────────────────────────────────────────────────────────────────────────

def _init_table():
    conn = get_conn()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS documenti_nara_catalog (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            na_id TEXT UNIQUE NOT NULL,
            title TEXT,
            description TEXT,
            record_group TEXT,
            series TEXT,
            inclusive_dates TEXT,
            unit TEXT,
            location TEXT,
            document_type TEXT,
            has_digital_objects INTEGER DEFAULT 0,
            file_urls TEXT,
            search_query TEXT,
            source_url TEXT,
            elaborato_il TEXT NOT NULL
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_nara_cat_naid ON documenti_nara_catalog(na_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_nara_cat_rg ON documenti_nara_catalog(record_group)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_nara_cat_type ON documenti_nara_catalog(document_type)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_nara_cat_date ON documenti_nara_catalog(inclusive_dates)")
    conn.commit()
    conn.close()


def _count_saved() -> int:
    conn = get_conn()
    try:
        return conn.execute("SELECT COUNT(*) FROM documenti_nara_catalog").fetchone()[0]
    except Exception:
        return 0
    finally:
        conn.close()


def _record_exists(na_id: str) -> bool:
    conn = get_conn()
    try:
        r = conn.execute("SELECT id FROM documenti_nara_catalog WHERE na_id = ?", (na_id,)).fetchone()
        return r is not None
    finally:
        conn.close()


def _save_record(rec: dict):
    conn = get_conn()
    try:
        conn.execute("""
            INSERT OR IGNORE INTO documenti_nara_catalog
            (na_id, title, description, record_group, series, inclusive_dates,
             unit, location, document_type, has_digital_objects, file_urls,
             search_query, source_url, elaborato_il)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        """, (
            rec["na_id"], rec["title"], rec["description"],
            rec["record_group"], rec["series"], rec["inclusive_dates"],
            rec["unit"], rec["location"], rec["document_type"],
            rec["has_digital_objects"],
            json.dumps(rec["file_urls"], ensure_ascii=False) if rec["file_urls"] else None,
            rec["search_query"], rec["source_url"], rec["elaborato_il"],
        ))
        conn.commit()
    except Exception as e:
        print(f"  Errore save na_id={rec['na_id']}: {e}")
    finally:
        conn.close()


# ─── API ───────────────────────────────────────────────────────────────────────

def _parse_hit(hit: dict, query_label: str) -> dict:
    """Estrae i campi rilevanti da un hit dell'API NARA."""
    na_id = str(hit.get("_id", ""))
    src = hit.get("_source", {})
    rec = src.get("record", {})

    title = rec.get("title") or ""
    description = rec.get("scopeAndContentNote") or rec.get("description") or ""
    if isinstance(description, list):
        description = " ".join(str(d) for d in description)

    # Record group e serie
    parents = rec.get("ancestors", []) or []
    rg = ""
    series = ""
    for p in parents:
        pt = p.get("levelOfDescription", "")
        if pt == "recordGroup":
            rg = str(p.get("naId", "") or p.get("title", "") or "")
        elif pt == "series":
            series = str(p.get("title", "") or "")
    if not rg:
        rg = str(rec.get("recordGroupNumber", "") or "")

    # Date
    dates = rec.get("inclusiveDates") or ""
    if isinstance(dates, list):
        dates = dates[0] if dates else ""

    # Unità/Creator
    creators = rec.get("creators", []) or []
    unit = creators[0].get("termName", "") if creators else ""
    if not unit:
        unit = rec.get("creatingOrganization", "") or ""

    # Location
    location = rec.get("physicalOccurrences", [])
    if isinstance(location, list) and location:
        location = location[0].get("locationName", "")
    else:
        location = str(location) if location else ""

    # Tipo documento
    doc_type = rec.get("generalRecordsTypeArray", [])
    if isinstance(doc_type, list) and doc_type:
        doc_type = doc_type[0].get("termName", "") if isinstance(doc_type[0], dict) else str(doc_type[0])
    else:
        doc_type = str(doc_type) if doc_type else ""

    # Oggetti digitali
    objects = rec.get("objects", []) or []
    file_urls = []
    for obj in objects:
        url = obj.get("url") or obj.get("path") or ""
        if url:
            file_urls.append(url)

    return {
        "na_id": na_id,
        "title": title[:500],
        "description": str(description)[:2000],
        "record_group": rg[:50],
        "series": series[:200],
        "inclusive_dates": str(dates)[:100],
        "unit": str(unit)[:200],
        "location": str(location)[:200],
        "document_type": doc_type[:100],
        "has_digital_objects": 1 if objects else 0,
        "file_urls": file_urls,
        "search_query": query_label,
        "source_url": f"https://catalog.archives.gov/id/{na_id}",
        "elaborato_il": datetime.now().isoformat(),
    }


def _fetch_page(session: requests.Session, params: dict) -> tuple[list, int]:
    """Ritorna (hits, total)."""
    for attempt in range(5):
        try:
            r = session.get(SEARCH_URL, params=params, timeout=30)
            r.raise_for_status()
            body = r.json().get("body", {})
            hits_obj = body.get("hits", {})
            total = hits_obj.get("total", {}).get("value", 0)
            hits = hits_obj.get("hits", [])
            return hits, total
        except Exception as e:
            wait = REQUEST_DELAY * (2 ** attempt)
            print(f"    Retry {attempt+1}/5: {e} (wait {wait:.0f}s)")
            time.sleep(wait)
    return [], 0


# ─── Scraping ──────────────────────────────────────────────────────────────────

def get_progress() -> dict:
    return dict(_progress)


def request_stop():
    stop_event.set()


def clear_stop_request():
    stop_event.clear()


def scrape_all(resume: bool = True):
    stop_event.clear()
    _init_table()

    session = requests.Session()
    session.headers.update({
        "User-Agent": "IMI-Research/1.0 (academic historical research WW2 Italy)",
        "Accept": "application/json",
    })

    total_saved_start = _count_saved() if resume else 0
    _progress.update({
        "status": "processing", "processed": 0,
        "total": 0, "current": "", "total_saved": total_saved_start
    })

    print(f"NARA Catalog: avvio scraping ({len(SEARCH_QUERIES)} query)")

    grand_total = 0

    for query_cfg in SEARCH_QUERIES:
        if stop_event.is_set():
            break

        label = query_cfg["label"]
        q = query_cfg["q"]
        extra = {k: v for k, v in query_cfg.items() if k not in ("q", "label")}

        _progress["current"] = label

        # Prima pagina per conoscere il totale
        params = {"q": q, "rows": ROWS_PER_PAGE, "offset": 0, **extra}
        hits, total = _fetch_page(session, params)

        if total == 0:
            print(f"  [{label}]: 0 risultati")
            continue

        print(f"  [{label}]: {total:,} risultati")
        saved_this_query = 0
        offset = 0

        while offset < min(total, 10000):  # Cap 10k per query (API limit)
            if stop_event.is_set():
                break

            if offset > 0:
                params["offset"] = offset
                hits, _ = _fetch_page(session, params)

            for hit in hits:
                na_id = str(hit.get("_id", ""))
                if not na_id:
                    continue
                if resume and _record_exists(na_id):
                    continue
                rec = _parse_hit(hit, label)
                _save_record(rec)
                saved_this_query += 1
                grand_total += 1

            _progress["total_saved"] = _count_saved()
            offset += ROWS_PER_PAGE

            if offset % 500 == 0:
                print(f"    [{label}] offset={offset}/{total} | +{saved_this_query} | DB={_progress['total_saved']:,}")

            time.sleep(REQUEST_DELAY)

        print(f"  [{label}]: +{saved_this_query} salvati")
        _progress["processed"] += 1

    _progress["status"] = "done"
    _progress["current"] = ""
    final = _count_saved()
    _progress["total_saved"] = final
    print(f"\n=== NARA Catalog completato. Totale record: {final:,} (+{grand_total} questa sessione) ===")


def count_documenti_nara_catalog() -> int:
    return _count_saved()

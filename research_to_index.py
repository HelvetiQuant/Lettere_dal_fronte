"""Research-to-Index — nessuna ricerca va persa.

Quando l'utente cerca un soldato/evento/luogo che non esiste nel DB locale,
il sistema crea automaticamente una scheda minima e la arricchisce con
metadati dalle fonti esterne trovate tramite Source Federation Layer.

Tabelle:
- research_subjects: soggetti di ricerca (soldati, eventi, luoghi, unità)
- research_subject_sources: collegamento soggetto → fonti_indice
- research_gaps: campi mancanti con suggerimenti provider

Funzioni:
- auto_index_if_not_found(query)
- create_minimal_subject_from_query(query)
- enrich_subject_from_sources(subject_id)
- update_subject_confidence(subject_id)
- link_subject_to_source(subject_id, source_id, relation_type, confidence, note)
- identify_research_gaps(subject_id)
- index_external_sources_for_soldier(soldier_id)
"""

import re
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

from database import get_conn, search_all
from source_providers.federation import federated_search, get_registry
from source_providers.base import score_source, _dict_factory


# ─── Tabelle ───────────────────────────────────────────────────────────────────

def _init_tables():
    conn = get_conn()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS research_subjects (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            subject_type TEXT NOT NULL,
            name TEXT,
            normalized_name TEXT,
            date_start TEXT,
            date_end TEXT,
            place TEXT,
            unit TEXT,
            status TEXT DEFAULT 'not_verified',
            confidence REAL DEFAULT 0.1,
            created_from_query TEXT,
            linked_soldier_id INTEGER,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS research_subject_sources (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            subject_id INTEGER NOT NULL REFERENCES research_subjects(id),
            source_locator_id INTEGER REFERENCES fonti_indice(id),
            relation_type TEXT,
            confidence REAL DEFAULT 0.3,
            evidence_note TEXT,
            created_at TEXT NOT NULL
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS research_gaps (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            subject_id INTEGER NOT NULL REFERENCES research_subjects(id),
            missing_field TEXT,
            suggested_provider TEXT,
            priority TEXT DEFAULT 'medium',
            status TEXT DEFAULT 'open',
            created_at TEXT NOT NULL
        )
    """)
    for idx in [
        "CREATE INDEX IF NOT EXISTS idx_rs_type ON research_subjects(subject_type)",
        "CREATE INDEX IF NOT EXISTS idx_rs_status ON research_subjects(status)",
        "CREATE INDEX IF NOT EXISTS idx_rs_soldier ON research_subjects(linked_soldier_id)",
        "CREATE INDEX IF NOT EXISTS idx_rss_subject ON research_subject_sources(subject_id)",
        "CREATE INDEX IF NOT EXISTS idx_rss_source ON research_subject_sources(source_locator_id)",
        "CREATE INDEX IF NOT EXISTS idx_rg_subject ON research_gaps(subject_id)",
        "CREATE INDEX IF NOT EXISTS idx_rg_status ON research_gaps(status)",
    ]:
        conn.execute(idx)
    conn.commit()
    conn.close()


# ─── Helper ────────────────────────────────────────────────────────────────────

def _normalize_name(name: str) -> str:
    return re.sub(r'\s+', ' ', name.strip().lower())


def _detect_subject_type(query: str) -> str:
    q = query.lower()
    if any(w in q for w in ['soldato', 'militare', 'internato', 'caduto', 'decorato',
                            'sergente', 'tenente', 'capitano', 'colonnello', 'generale',
                            'fante', 'alpino', 'artigliere', 'bersagliere']):
        return 'soldier'
    if any(w in q for w in ['battaglia', 'combattimento', 'offensiva', 'ritirata',
                            'armistizio', 'cattura', 'deportazione']):
        return 'event'
    if any(w in q for w in ['reparto', 'divisione', 'brigata', 'reggimento', 'battaglione',
                            'compagnia', 'corpo', 'armata']):
        return 'unit'
    if any(w in q for w in ['documento', 'diario', 'rapporto', 'lettera', 'ordine',
                            'fonogramma', 'mappa', 'cartina']):
        return 'document'
    if any(w in q for w in ['città', 'citta', 'paese', 'villaggio', 'regione',
                            'provincia', 'monte', 'fiume', 'valle', 'passo']):
        return 'place'
    # default: se sembra un nome proprio (Maiuscolo + spazio), è soldier
    parts = query.split()
    if len(parts) >= 2 and parts[0][0].isupper():
        return 'soldier'
    return 'soldier'


def _extract_name_parts(query: str) -> dict:
    parts = query.strip().split()
    if len(parts) >= 2:
        return {"cognome": parts[0], "nome": parts[1] if len(parts) > 1 else ""}
    elif len(parts) == 1:
        return {"cognome": parts[0], "nome": ""}
    return {"cognome": "", "nome": ""}


# ─── Funzioni core ─────────────────────────────────────────────────────────────

def create_minimal_subject_from_query(query: str, subject_type: str = None) -> dict:
    """Crea un record minimo in research_subjects da una query."""
    stype = subject_type or _detect_subject_type(query)
    name_parts = _extract_name_parts(query)
    now = datetime.now().isoformat()

    name = query.strip()
    normalized = _normalize_name(name)

    conn = get_conn()
    # evita duplicati
    existing = conn.execute(
        "SELECT id FROM research_subjects WHERE normalized_name = ? AND subject_type = ?",
        (normalized, stype)
    ).fetchone()
    if existing:
        conn.close()
        return {"id": existing[0], "already_existed": True}

    cur = conn.execute(
        """INSERT INTO research_subjects
           (subject_type, name, normalized_name, status, confidence, created_from_query, created_at, updated_at)
           VALUES (?, ?, ?, 'not_verified', 0.1, ?, ?, ?)""",
        (stype, name, normalized, query, now, now)
    )
    subject_id = cur.lastrowid
    conn.commit()
    conn.close()

    return {"id": subject_id, "already_existed": False, "name": name, "type": stype}


def _safe_str(val, default="") -> str:
    """Converte qualsiasi valore in stringa sicura per SQLite."""
    if val is None:
        return default
    if isinstance(val, list):
        return str(val[0]) if val else default
    if isinstance(val, (int, float, bool)):
        return str(val)
    return str(val)


def upsert_source_locator(result: dict) -> Optional[int]:
    """Salva o aggiorna un risultato federato in fonti_indice. Ritorna source_id."""
    archivio = _safe_str(result.get("archivio") or result.get("provider", "unknown"))
    titolo = _safe_str(result.get("titolo") or result.get("title", "") or "Senza titolo")
    provider = _safe_str(result.get("provider", ""))
    record_id = _safe_str(result.get("provider_record_id", ""))
    segnatura = f"{provider}:{record_id}" if record_id else f"{provider}:{titolo[:50]}"

    catalog_url = _safe_str(result.get("catalog_url") or result.get("direct_url", ""))
    direct_url = _safe_str(result.get("direct_url", ""))
    iiif = _safe_str(result.get("iiif_manifest", ""))
    access_type = _safe_str(result.get("access_type", "online"))
    description = _safe_str(result.get("description", ""))
    source_type = _safe_str(result.get("source_type", ""))
    confidence = result.get("confidence", 0.5)
    if not isinstance(confidence, (int, float)):
        confidence = 0.5
    score = result.get("score", 0.0)
    if not isinstance(score, (int, float)):
        score = 0.0

    now = datetime.now().isoformat()

    conn = get_conn()
    # check esistente per archivio + segnatura + titolo
    existing = conn.execute(
        "SELECT id FROM fonti_indice WHERE archivio = ? AND segnatura = ? AND titolo = ?",
        (archivio, segnatura, titolo)
    ).fetchone()
    if existing:
        # aggiorna last_checked
        conn.execute(
            "UPDATE fonti_indice SET last_checked_at = ?, confidence = ? WHERE id = ?",
            (now, max(confidence, score), existing[0])
        )
        conn.commit()
        conn.close()
        return existing[0]

    cur = conn.execute(
        """INSERT INTO fonti_indice
           (archivio, fondo, serie, segnatura, titolo, tipo_fonte,
            url_catalogo, url_file, iiif_manifest,
            access_type, fetch_status, confidence, note, created_at, last_checked_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'mai_scaricato', ?, ?, ?, ?)""",
        (archivio, provider, "", segnatura, titolo, source_type,
         catalog_url, direct_url, iiif,
         access_type, max(confidence, score), description[:500], now, now)
    )
    source_id = cur.lastrowid
    conn.commit()
    conn.close()
    return source_id


def link_subject_to_source(subject_id: int, source_id: int,
                           relation_type: str = "mentions",
                           confidence: float = 0.3,
                           evidence_note: str = "") -> int:
    """Collega una fonte a un soggetto di ricerca."""
    now = datetime.now().isoformat()
    conn = get_conn()
    # evita duplicati
    existing = conn.execute(
        "SELECT id FROM research_subject_sources WHERE subject_id = ? AND source_locator_id = ?",
        (subject_id, source_id)
    ).fetchone()
    if existing:
        conn.close()
        return existing[0]
    cur = conn.execute(
        """INSERT INTO research_subject_sources
           (subject_id, source_locator_id, relation_type, confidence, evidence_note, created_at)
           VALUES (?, ?, ?, ?, ?, ?)""",
        (subject_id, source_id, relation_type, confidence, evidence_note, now)
    )
    link_id = cur.lastrowid
    conn.commit()
    conn.close()
    return link_id


def update_subject_confidence(subject_id: int) -> float:
    """Ricalcola confidence in base al numero e qualità delle fonti collegate."""
    conn = get_conn()
    rows = conn.execute(
        """SELECT confidence, relation_type FROM research_subject_sources
           WHERE subject_id = ?""",
        (subject_id,)
    ).fetchall()

    if not rows:
        conn.close()
        return 0.1

    # pesi: confirms=1.0, mentions=0.5, possibly_related=0.3, contradicts=-0.2
    weights = {"confirms": 1.0, "mentions": 0.5, "possibly_related": 0.3, "contradicts": -0.2}
    total = 0.0
    for r in rows:
        w = weights.get(r[1], 0.3)
        total += r[0] * w

    # normalizza: più fonti = più confidence, ma con saturazione
    import math
    confidence = min(0.95, 0.1 + total / (1 + math.log1p(len(rows))))

    # determina status
    if confidence >= 0.7:
        status = "verified"
    elif confidence >= 0.4:
        status = "partially_verified"
    else:
        status = "not_verified"

    now = datetime.now().isoformat()
    conn.execute(
        "UPDATE research_subjects SET confidence = ?, status = ?, updated_at = ? WHERE id = ?",
        (confidence, status, now, subject_id)
    )
    conn.commit()
    conn.close()
    return confidence


def identify_research_gaps(subject_id: int) -> List[dict]:
    """Identifica campi mancanti e suggerisce provider per riempirli."""
    conn = get_conn()
    subject = conn.execute(
        "SELECT * FROM research_subjects WHERE id = ?", (subject_id,)
    ).fetchone()
    if not subject:
        conn.close()
        return []

    subject = dict(subject) if subject else {}
    gaps = []
    now = datetime.now().isoformat()

    # campi da verificare
    field_provider_map = {
        "date_start": "antenati",
        "date_end": "cwgc",
        "place": "antenati",
        "unit": "bundesarchiv",
    }

    for field, provider in field_provider_map.items():
        if not subject.get(field):
            # check se gap già esiste
            existing = conn.execute(
                "SELECT id FROM research_gaps WHERE subject_id = ? AND missing_field = ? AND status = 'open'",
                (subject_id, field)
            ).fetchone()
            if not existing:
                conn.execute(
                    """INSERT INTO research_gaps
                       (subject_id, missing_field, suggested_provider, priority, status, created_at)
                       VALUES (?, ?, ?, 'medium', 'open', ?)""",
                    (subject_id, field, provider, now)
                )
            gaps.append({"field": field, "suggested_provider": provider})

    conn.commit()
    conn.close()
    return gaps


def enrich_subject_from_sources(subject_id: int) -> dict:
    """Per ogni fonte collegata, estrae dati strutturati e aggiorna il soggetto."""
    conn = get_conn()
    sources = conn.execute(
        """SELECT rs.source_locator_id, rs.relation_type, rs.confidence, rs.evidence_note,
                  fi.archivio, fi.titolo, fi.titolo, fi.url_catalogo, fi.confidence as src_confidence
           FROM research_subject_sources rs
           JOIN fonti_indice fi ON rs.source_locator_id = fi.id
           WHERE rs.subject_id = ?""",
        (subject_id,)
    ).fetchall()

    enriched = {"sources_count": len(sources), "fields_updated": []}

    # per ora arricchimento semplice: se ci sono fonti con confidence alta,
    # aggiorna status
    if sources:
        max_conf = max(s[2] for s in sources)
        if max_conf > 0.7:
            now = datetime.now().isoformat()
            conn.execute(
                "UPDATE research_subjects SET status = 'partially_verified', updated_at = ? WHERE id = ?",
                (now, subject_id)
            )
            enriched["fields_updated"].append("status → partially_verified")

    conn.commit()
    conn.close()

    # ricalcola confidence
    new_conf = update_subject_confidence(subject_id)
    enriched["new_confidence"] = new_conf

    return enriched


def auto_index_if_not_found(query: str) -> dict:
    """Funzione principale: cerca locale → se non trova, crea soggetto + arricchisce.

    Flusso:
    1. search_local_db(query)
    2. se trova → ritorna risultati locali
    3. se non trova → create_minimal_subject_from_query(query)
    4. federation_search(query) — interroga provider esterni
    5. per ogni risultato → upsert_source_locator + link_subject_to_source
    6. update_subject_confidence + identify_research_gaps
    7. ritorna dashboard soggetto
    """
    # Step 1: search locale
    local = search_all(query, limit=10)
    local_count = sum(
        len(v) for k, v in local.items()
        if isinstance(v, list) and k not in ("tokens", "term")
    )

    if local_count > 0:
        return {
            "found_locally": True,
            "local_results": local,
            "subject_id": None,
        }

    # Step 2: crea soggetto minimo
    subject = create_minimal_subject_from_query(query)
    subject_id = subject["id"]

    # Step 3: ricerca federata
    cues = {"persona": query}
    fed_results = federated_search(query, cues=cues)

    # Step 4: per ogni risultato, salva in fonti_indice e collega
    indexed_sources = []
    for result in fed_results:
        if "error" in result:
            continue
        source_id = upsert_source_locator(result)
        if source_id:
            rel_type = "mentions"
            conf = result.get("score", result.get("confidence", 0.3))
            note = f"Provider: {result.get('provider', '?')}"
            link_subject_to_source(subject_id, source_id, rel_type, conf, note)
            indexed_sources.append({
                "source_id": source_id,
                "archivio": result.get("archivio"),
                "titolo": result.get("titolo", "")[:80],
                "provider": result.get("provider"),
                "score": result.get("score", 0),
                "access_type": result.get("access_type"),
            })

    # Step 5: aggiorna confidence e identifica gaps
    update_subject_confidence(subject_id)
    identify_research_gaps(subject_id)

    return {
        "found_locally": False,
        "subject_id": subject_id,
        "subject_type": subject.get("type"),
        "indexed_sources": indexed_sources,
        "sources_count": len(indexed_sources),
    }


def index_external_sources_for_soldier(soldier_id: int) -> dict:
    """Per un soldato ESISTENTE nel DB locale, cerca fonti esterne e le indicizza.

    Differenza vs auto_index: il soldato c'è già, vogliamo arricchirlo con fonti
    esterne non presenti nel DB.
    """
    conn = get_conn()
    conn.row_factory = _dict_factory
    soldier = conn.execute(
        "SELECT * FROM internati WHERE id = ?", (soldier_id,)
    ).fetchone()
    conn.close()

    if not soldier:
        return {"ok": False, "error": f"soldier_id {soldier_id} non trovato"}

    # estrai cue
    query = f"{soldier.get('nome', '')} {soldier.get('cognome', '')}".strip()
    cues = {"persona": query}
    if soldier.get("luogo_nascita"):
        cues["luogo"] = soldier["luogo_nascita"]
    if soldier.get("luogo_internamento"):
        cues["luogo_internamento"] = soldier["luogo_internamento"]
    if soldier.get("grado"):
        cues["grado"] = soldier["grado"]

    # ricerca federata con TUTTI i provider
    fed_results = federated_search(query, cues=cues)

    # crea/aggiorna soggetto collegato al soldato
    now = datetime.now().isoformat()
    conn = get_conn()
    existing_subj = conn.execute(
        "SELECT id FROM research_subjects WHERE linked_soldier_id = ?",
        (soldier_id,)
    ).fetchone()

    if existing_subj:
        subject_id = existing_subj[0]
    else:
        cur = conn.execute(
            """INSERT INTO research_subjects
               (subject_type, name, normalized_name, status, confidence,
                created_from_query, linked_soldier_id, created_at, updated_at)
               VALUES ('soldier', ?, ?, 'partially_verified', 0.3, ?, ?, ?, ?)""",
            (query, _normalize_name(query), query, soldier_id, now, now)
        )
        subject_id = cur.lastrowid
        conn.commit()
    conn.close()

    # indicizza risultati — classificati per rilevanza
    indexed = []
    catalog_refs = []
    skipped = 0

    # estrai cognome per match nel titolo
    cognome = (soldier.get("cognome") or "").lower().strip()
    nome = (soldier.get("nome") or "").lower().strip()

    for result in fed_results:
        if "error" in result:
            skipped += 1
            continue

        score = result.get("score", 0)
        if not isinstance(score, (int, float)):
            score = 0
        titolo = _safe_str(result.get("titolo", "")).lower()
        description = _safe_str(result.get("description", "")).lower()
        has_record_id = bool(result.get("provider_record_id"))

        # match nome nel titolo/descrizione?
        name_match = False
        if cognome and len(cognome) >= 3:
            if cognome in titolo or cognome in description:
                name_match = True
            elif nome and len(nome) >= 3 and nome in titolo:
                name_match = True

        # classifica risultato
        is_stub = score <= 0.15 and not has_record_id
        is_relevant = name_match or (score >= 0.25 and has_record_id)

        if is_stub and not is_relevant:
            # provider stub: salva come riferimento catalogo, confidence bassa
            source_id = upsert_source_locator(result)
            if source_id:
                link_subject_to_source(subject_id, source_id, "possibly_related",
                                       0.15, f"Stub provider: {result.get('provider', '?')}")
                catalog_refs.append({
                    "source_id": source_id,
                    "archivio": _safe_str(result.get("archivio")),
                    "titolo": _safe_str(result.get("titolo", ""))[:80],
                    "provider": _safe_str(result.get("provider")),
                    "score": score,
                    "access_type": _safe_str(result.get("access_type")),
                    "catalog_url": _safe_str(result.get("catalog_url", "")),
                    "relevance": "catalog_ref",
                })
            continue

        if not is_relevant and not is_stub:
            # risultato API ma non pertinente (es. TNA ritorna record casuali)
            skipped += 1
            continue

        # risultato pertinente — indicizza con confidence appropriata
        source_id = upsert_source_locator(result)
        if source_id:
            rel_type = "confirms" if name_match else "mentions"
            conf = max(score, 0.4 if name_match else 0.3)
            note = f"Provider: {result.get('provider', '?')}, score: {score:.2f}"
            if name_match:
                note += ", nome trovato nel titolo"
            link_subject_to_source(subject_id, source_id, rel_type, conf, note)
            indexed.append({
                "source_id": source_id,
                "archivio": _safe_str(result.get("archivio")),
                "titolo": _safe_str(result.get("titolo", ""))[:80],
                "provider": _safe_str(result.get("provider")),
                "score": score,
                "access_type": _safe_str(result.get("access_type")),
                "catalog_url": _safe_str(result.get("catalog_url", "")),
                "relevance": "relevant",
                "name_match": name_match,
            })

    update_subject_confidence(subject_id)
    identify_research_gaps(subject_id)

    return {
        "ok": True,
        "soldier_id": soldier_id,
        "soldier_name": query,
        "subject_id": subject_id,
        "indexed_sources": indexed,
        "sources_count": len(indexed),
        "catalog_refs": catalog_refs,
        "catalog_refs_count": len(catalog_refs),
        "skipped": skipped,
        "total_fed_results": len(fed_results),
    }


def get_research_stats() -> dict:
    """Statistiche research-to-index."""
    conn = get_conn()
    try:
        n_subjects = conn.execute("SELECT COUNT(*) FROM research_subjects").fetchone()[0]
        n_verified = conn.execute("SELECT COUNT(*) FROM research_subjects WHERE status='verified'").fetchone()[0]
        n_partial = conn.execute("SELECT COUNT(*) FROM research_subjects WHERE status='partially_verified'").fetchone()[0]
        n_not = conn.execute("SELECT COUNT(*) FROM research_subjects WHERE status='not_verified'").fetchone()[0]
        n_links = conn.execute("SELECT COUNT(*) FROM research_subject_sources").fetchone()[0]
        n_gaps = conn.execute("SELECT COUNT(*) FROM research_gaps WHERE status='open'").fetchone()[0]
        n_sources = conn.execute("SELECT COUNT(*) FROM fonti_indice").fetchone()[0]
    except sqlite3.OperationalError:
        return {"initialized": False}
    conn.close()
    return {
        "initialized": True,
        "subjects": n_subjects,
        "verified": n_verified,
        "partially_verified": n_partial,
        "not_verified": n_not,
        "subject_source_links": n_links,
        "open_gaps": n_gaps,
        "fonti_indice_total": n_sources,
    }


# ─── Init ──────────────────────────────────────────────────────────────────────

_init_tables()

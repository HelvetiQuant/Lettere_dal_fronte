"""Fact Extractor — estrae claim strutturati da record DB e testo non strutturato.

Pipeline:
1. extract_claims_from_record() — estrae claim deterministici da campi strutturati
   (data_nascita, luogo_nascita, grado, luogo_cattura, data_cattura, sorte, etc.)
2. extract_claims_from_text_ai() — usa AI per estrarre claim da raw_text, documenti,
   trascrizioni non strutturate
3. extract_claims_from_fragments() — processa frammenti di ricerca e crea claim
4. auto_build_timeline() — dopo l'estrazione, costruisce la timeline automaticamente

Ogni claim ha:
- subject (persona/evento/luogo)
- predicate (born_at, captured_at, interned_at, died_at, decorated_for, ...)
- object_value (valore specifico)
- temporal_range (date)
- place (luogo)
- epistemic_status (confirmed/probable/possible)
- evidence (fonte: tabella + record_id)

Mappatura predicati → standard semantico:
- born_at: luogo e data di nascita
- resident_at: residenza
- held_rank: grado militare
- served_in: reparto/unità
- captured_at: luogo e data cattura
- interned_at: campo di internamento
- worked_at: arbeitskommando/lavoro forzato
- died_at: luogo e data decesso
- cause_of_death: causa morte
- buried_at: luogo sepoltura
- decorated_with: decorazione
- decoration_motivation: motivazione decorazione
"""
import json
import re
import logging
from typing import Dict, List, Optional, Any, Tuple

from database import get_conn
from claim_service import create_claim, add_evidence, build_timeline, detect_conflicts
from ai_client import call_ai, call_ai_json, is_any_provider_available

log = logging.getLogger("fact_extractor")


# ═══ DATE PARSING ═════════════════════════════════════════════════════════

def _parse_date(raw: str) -> Tuple[str, str, str]:
    """Parse date string in vari formati → (iso_start, iso_end, precision).

    Supporta:
    - 1943-09-12 (ISO)
    - 12-9-1943 (DD-MM-YYYY)
    - 13-2-1945
    - 1912-01-09
    - "9 gennaio 1912"
    - "1943" (solo anno)
    """
    if not raw or not raw.strip():
        return "", "", ""

    raw = raw.strip()

    # ISO format: YYYY-MM-DD
    m = re.match(r"^(\d{4})-(\d{2})-(\d{2})", raw)
    if m:
        return f"{m.group(1)}-{m.group(2)}-{m.group(3)}", "", "day"

    # DD-MM-YYYY
    m = re.match(r"^(\d{1,2})-(\d{1,2})-(\d{4})", raw)
    if m:
        d, mo, y = m.group(1), m.group(2), m.group(3)
        return f"{y}-{mo.zfill(2)}-{d.zfill(2)}", "", "day"

    # "9 gennaio 1912" o "9 gennaio 1912"
    months_it = {
        "gennaio": "01", "febbraio": "02", "marzo": "03", "aprile": "04",
        "maggio": "05", "giugno": "06", "luglio": "07", "agosto": "08",
        "settembre": "09", "ottobre": "10", "novembre": "11", "dicembre": "12",
    }
    m = re.match(r"^(\d{1,2})\s+([a-zA-Zà]+)\s+(\d{4})", raw, re.I)
    if m:
        d, mo_name, y = m.group(1), m.group(2).lower(), m.group(3)
        mo = months_it.get(mo_name)
        if mo:
            return f"{y}-{mo}-{d.zfill(2)}", "", "day"

    # Solo anno: YYYY
    m = re.match(r"^(\d{4})$", raw)
    if m:
        return f"{m.group(1)}-01-01", f"{m.group(1)}-12-31", "year"

    return "", "", ""


def _clean_value(v) -> str:
    if v is None:
        return ""
    return str(v).strip()


# ═══ TABLE EXISTENCE ══════════════════════════════════════════════════════

def _table_exists(conn, table: str) -> bool:
    row = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?", (table,)
    ).fetchone()
    return row is not None


# ═══ EXTRACTION FROM STRUCTURED DB RECORDS ════════════════════════════════

# Mappatura campi internati → predicati claim
_INTERNATI_FIELD_MAP = [
    # (field_name, predicate, object_type, epistemic_status, confidence)
    ("data_nascita", "born_at", "date", "probable", 0.8),
    ("luogo_nascita", "born_at", "place", "probable", 0.8),
    ("residenza", "resident_at", "place", "probable", 0.7),
    ("grado", "held_rank", "rank", "probable", 0.8),
    ("luogo_cattura", "captured_at", "place", "probable", 0.7),
    ("data_cattura", "captured_at", "date", "probable", 0.7),
    ("luogo_internamento", "interned_at", "place", "probable", 0.7),
    ("matricola", "has_service_number", "id", "probable", 0.9),
    ("arbeitskommando", "worked_at", "place", "possible", 0.5),
    ("mansione", "had_role", "role", "possible", 0.5),
    ("sorte", "had_fate", "fate", "probable", 0.7),
    ("data", "event_date", "date", "possible", 0.5),
]

# Mappatura caduti_albooro
_CADUTI_FIELD_MAP = [
    ("nominativo", "has_name", "name", "confirmed", 0.9),
    ("grado", "held_rank", "rank", "probable", 0.7),
    ("reparto", "served_in", "unit", "probable", 0.7),
    ("anno_morte", "died_in", "year", "probable", 0.7),
    ("luogo_morte", "died_at", "place", "probable", 0.7),
    ("comune_attuale", "from_municipality", "place", "probable", 0.6),
    ("classe", "born_in_year", "year", "possible", 0.4),
]

# Mappatura decorati
_DECORATI_FIELD_MAP = [
    ("data_nascita", "born_at", "date", "probable", 0.8),
    ("comune_nascita", "born_at", "place", "probable", 0.8),
    ("data_morte", "died_at", "date", "probable", 0.7),
    ("luogo_morte", "died_at", "place", "probable", 0.7),
    ("causa_morte", "cause_of_death", "cause", "probable", 0.7),
    ("grado", "held_rank", "rank", "probable", 0.8),
    ("corpo_militare", "served_in", "unit", "probable", 0.7),
    ("reparto", "served_in", "unit", "probable", 0.7),
    ("decorazione", "decorated_with", "decoration", "confirmed", 0.9),
    ("luogo_cattura", "captured_at", "place", "probable", 0.6),
    ("luogo_internamento", "interned_at", "place", "probable", 0.6),
    ("matricola", "has_service_number", "id", "probable", 0.9),
]


def extract_claims_from_record(
    table: str,
    record_id: int,
    entity_type: str = "persona",
    entity_id: int = None,
    entity_label: str = "",
) -> Dict:
    """Estrae claim strutturati da un record DB.

    Returns: {"claims_created": int, "claims_existing": int, "claim_ids": list}
    """
    conn = get_conn()
    if not _table_exists(conn, table):
        conn.close()
        return {"error": f"table {table} not found"}

    row = conn.execute(f"SELECT * FROM {table} WHERE id=?", (record_id,)).fetchone()
    if not row:
        conn.close()
        return {"error": f"record {table}:{record_id} not found"}

    cols = [d[1] for d in conn.execute(f"PRAGMA table_info({table})").fetchall()]
    record = dict(zip(cols, row))
    conn.close()

    field_map = {
        "internati": _INTERNATI_FIELD_MAP,
        "caduti_albooro": _CADUTI_FIELD_MAP,
        "decorati": _DECORATI_FIELD_MAP,
    }.get(table, [])

    if not field_map:
        return {"error": f"no field map for table {table}"}

    if not entity_label:
        if table == "internati":
            entity_label = f"{record.get('cognome','')} {record.get('nome','')}".strip()
        elif table == "decorati":
            entity_label = f"{record.get('cognome','')} {record.get('nome','')}".strip()
        elif table == "caduti_albooro":
            entity_label = record.get("nominativo", "")

    if not entity_id:
        entity_id = record_id

    claims_created = 0
    claims_existing = 0
    claim_ids = []

    for field, predicate, obj_type, epistemic, confidence in field_map:
        raw_val = _clean_value(record.get(field))
        if not raw_val or raw_val == "None":
            continue

        # Parse date if applicable
        date_start, date_end, precision = "", "", ""
        if obj_type in ("date", "year"):
            date_start, date_end, precision = _parse_date(raw_val)
            if not date_start:
                continue
            object_value = date_start
        else:
            object_value = raw_val

        # Per campi con luogo + data (es. captured_at), combina luogo e data
        place = ""
        if predicate == "captured_at" and obj_type == "place":
            place = raw_val
            date_val = _clean_value(record.get("data_cattura"))
            if date_val:
                date_start, date_end, precision = _parse_date(date_val)
        elif predicate == "captured_at" and obj_type == "date":
            place = _clean_value(record.get("luogo_cattura"))
        elif predicate == "born_at" and obj_type == "place":
            place = raw_val
            date_val = _clean_value(record.get("data_nascita"))
            if date_val:
                date_start, date_end, precision = _parse_date(date_val)
        elif predicate == "born_at" and obj_type == "date":
            place = _clean_value(record.get("luogo_nascita"))
        elif predicate == "died_at" and obj_type == "place":
            place = raw_val
            date_val = _clean_value(record.get("data_morte") or record.get("anno_morte"))
            if date_val:
                date_start, date_end, precision = _parse_date(date_val)
        elif predicate == "died_at" and obj_type == "date":
            place = _clean_value(record.get("luogo_morte"))
        elif predicate == "interned_at":
            place = raw_val
        elif predicate == "died_in" and obj_type == "year":
            place = _clean_value(record.get("luogo_morte"))
        elif obj_type == "place":
            place = raw_val

        result = create_claim(
            subject_type=entity_type,
            subject_id=entity_id,
            subject_label=entity_label,
            predicate=predicate,
            object_type=obj_type,
            object_label=raw_val if obj_type not in ("date", "year") else "",
            object_value=object_value,
            original_value=raw_val,
            temporal_range_start=date_start,
            temporal_range_end=date_end,
            temporal_precision=precision or None,
            place=place,
            epistemic_status=epistemic,
            confidence=confidence,
            extraction_method="db_field_mapping",
            created_by="fact_extractor",
        )

        if result.get("already_existed"):
            claims_existing += 1
        else:
            claims_created += 1

        claim_id = result["id"]
        claim_ids.append(claim_id)

        add_evidence(
            claim_id=claim_id,
            source_id=record_id,
            source_table=table,
            supporting_quote=raw_val,
            evidence_role="supports",
            strength=confidence,
            note=f"Estratto da campo '{field}' di {table}.{record_id}",
        )

    return {
        "claims_created": claims_created,
        "claims_existing": claims_existing,
        "claim_ids": claim_ids,
        "table": table,
        "record_id": record_id,
        "entity_label": entity_label,
    }


# ═══ EXTRACTION FROM UNSTRUCTURED TEXT (AI) ═══════════════════════════════

_CLAIM_EXTRACTION_PROMPT = """Sei un estrattore di fatti storici strutturati da testo non strutturato.
Estrai SOLO fatti esplicitamente presenti nel testo. Non inventare nulla.

Per ogni fatto, produci un oggetto JSON con:
- predicate: uno tra born_at, resident_at, held_rank, served_in, captured_at, interned_at, worked_at, died_at, cause_of_death, buried_at, decorated_with, had_fate, has_service_number, participated_in, transferred_to
- object_value: il valore specifico (luogo, data ISO, grado, nome unità, ecc.)
- object_type: date | place | rank | unit | name | id | cause | fate | decoration | role
- date: data in formato ISO (YYYY-MM-DD) se presente, altrimenti vuoto
- place: luogo se presente
- confidence: 0.0-1.0 (quanto è chiaro il fatto nel testo)
- quote: la frase esatta del testo da cui hai estratto il fatto

Restituisci SOLO un array JSON di oggetti fatto. Se non ci sono fatti chiari, restituisci [].
"""


def extract_claims_from_text_ai(
    text: str,
    entity_type: str = "persona",
    entity_id: int = None,
    entity_label: str = "",
    source_table: str = "",
    source_id: int = None,
    research_plan_id: int = None,
    session_id: int = None,
) -> Dict:
    """Usa AI per estrarre claim da testo non strutturato.

    Returns: {"claims_created": int, "claims_existing": int, "claim_ids": list, "ok": bool}
    """
    if not text or not text.strip():
        return {"ok": True, "claims_created": 0, "claims_existing": 0, "claim_ids": []}

    if not is_any_provider_available():
        return {"ok": False, "error": "no_ai_provider", "claims_created": 0}

    result = call_ai_json(
        task_type="propose_claims",
        system=_CLAIM_EXTRACTION_PROMPT,
        user=f"Testo da analizzare:\n\n{text[:4000]}\n\nEstrai i fatti strutturati. Solo JSON array.",
        max_tokens=2048,
        temperature=0.1,
        research_plan_id=research_plan_id,
        session_id=session_id,
    )

    if not result.get("ok") or not result.get("data"):
        return {"ok": False, "error": result.get("error", "ai_call_failed"),
                "claims_created": 0, "claim_ids": []}

    data = result["data"]
    if isinstance(data, dict):
        data = data.get("claims", [data])
    if not isinstance(data, list):
        data = []

    claims_created = 0
    claims_existing = 0
    claim_ids = []

    for fact in data:
        if not isinstance(fact, dict):
            continue
        predicate = fact.get("predicate", "").strip()
        object_value = fact.get("object_value", "").strip()
        if not predicate or not object_value:
            continue

        date_str = fact.get("date", "").strip()
        date_start, date_end, precision = _parse_date(date_str) if date_str else ("", "", "")

        claim_result = create_claim(
            subject_type=entity_type,
            subject_id=entity_id,
            subject_label=entity_label,
            predicate=predicate,
            object_type=fact.get("object_type", "text"),
            object_value=object_value,
            original_value=object_value,
            temporal_range_start=date_start,
            temporal_range_end=date_end,
            temporal_precision=precision or None,
            place=fact.get("place", "").strip(),
            epistemic_status="possible",
            confidence=fact.get("confidence", 0.4),
            extraction_method="ai_text_extraction",
            created_by="fact_extractor_ai",
        )

        if claim_result.get("already_existed"):
            claims_existing += 1
        else:
            claims_created += 1

        claim_id = claim_result["id"]
        claim_ids.append(claim_id)

        add_evidence(
            claim_id=claim_id,
            source_id=source_id,
            source_table=source_table,
            supporting_quote=fact.get("quote", "")[:500],
            evidence_role="supports",
            strength=fact.get("confidence", 0.4),
            note=f"Estratto da AI da testo di {source_table}:{source_id}",
        )

    return {
        "ok": True,
        "claims_created": claims_created,
        "claims_existing": claims_existing,
        "claim_ids": claim_ids,
        "provider": result.get("provider"),
        "model": result.get("model"),
        "cost": result.get("cost", 0),
    }


# ═══ EXTRACTION FROM RESEARCH FRAGMENTS ═══════════════════════════════════

def extract_claims_from_fragments(
    fragments: List[Dict],
    entity_type: str,
    entity_id: int,
    entity_label: str = "",
    research_plan_id: int = None,
    session_id: int = None,
) -> Dict:
    """Processa frammenti di ricerca e crea claim.

    Per frammenti strutturati (person_record, entity_match) usa mapping diretto.
    Per frammenti non strutturati (external_source con testo) usa AI.
    """
    total_created = 0
    total_existing = 0
    all_claim_ids = []

    for frag in fragments:
        frag_type = frag.get("type", "")

        if frag_type == "person_record":
            table = frag.get("source", "").replace("db_", "")
            record_id = frag.get("id")
            if table and record_id:
                result = extract_claims_from_record(
                    table=table,
                    record_id=record_id,
                    entity_type=entity_type,
                    entity_id=entity_id,
                    entity_label=entity_label,
                )
                total_created += result.get("claims_created", 0)
                total_existing += result.get("claims_existing", 0)
                all_claim_ids.extend(result.get("claim_ids", []))

        elif frag_type == "entity_match" and frag.get("source") == "fts":
            result = create_claim(
                subject_type=entity_type,
                subject_id=entity_id,
                subject_label=entity_label,
                predicate="identified_as",
                object_type="name",
                object_value=frag.get("value", ""),
                original_value=frag.get("value", ""),
                epistemic_status="probable",
                confidence=0.6,
                extraction_method="fts_match",
                created_by="fact_extractor",
            )
            if result.get("already_existed"):
                total_existing += 1
            else:
                total_created += 1
            all_claim_ids.append(result["id"])
            add_evidence(
                claim_id=result["id"],
                source_table="entita",
                source_id=frag.get("entity_id"),
                supporting_quote=frag.get("clue", ""),
                evidence_role="supports",
                strength=0.5,
                note="Match FTS",
            )

        elif frag_type == "external_source":
            provider = frag.get("source", "external")
            title = frag.get("title", "")
            url = frag.get("url", "")
            if title:
                result = create_claim(
                    subject_type=entity_type,
                    subject_id=entity_id,
                    subject_label=entity_label,
                    predicate="mentioned_in",
                    object_type="source",
                    object_value=f"{provider}: {title}",
                    original_value=title,
                    epistemic_status="possible",
                    confidence=frag.get("score", 0.3),
                    extraction_method="federated_search",
                    created_by="fact_extractor",
                )
                if result.get("already_existed"):
                    total_existing += 1
                else:
                    total_created += 1
                all_claim_ids.append(result["id"])
                add_evidence(
                    claim_id=result["id"],
                    source_table="external_source",
                    supporting_quote=title,
                    evidence_role="contextualizes",
                    strength=frag.get("score", 0.3),
                    note=f"Fonte esterna: {provider} — {url}",
                )

    return {
        "claims_created": total_created,
        "claims_existing": total_existing,
        "claim_ids": all_claim_ids,
    }


# ═══ AUTO BUILD TIMELINE ══════════════════════════════════════════════════

def auto_build_timeline(entity_type: str, entity_id: int) -> List[Dict]:
    """Costruisce la timeline dopo l'estrazione claim.
    Wrapper attorno a claim_service.build_timeline con ordinamento migliorato.
    """
    timeline = build_timeline(entity_type, entity_id)

    def sort_key(t):
        d = t.get("date_start") or ""
        return (d != "", d)

    timeline.sort(key=sort_key)
    return timeline


# ═══ FULL EXTRACTION PIPELINE ═════════════════════════════════════════════

def extract_facts_for_entity(
    entity_type: str,
    entity_id: int,
    entity_label: str = "",
    raw_text: str = "",
    research_plan_id: int = None,
    session_id: int = None,
) -> Dict:
    """Pipeline completa di estrazione fatti per un'entita'.

    1. Cerca record correlati nelle tabelle DB
    2. Estrae claim strutturati dai campi
    3. Se raw_text disponibile, estrae claim con AI
    4. Rileva conflitti
    5. Costruisce timeline

    Returns: {
        claims_created, claims_existing, claim_ids,
        conflicts, timeline, ai_extraction
    }
    """
    all_claim_ids = []
    total_created = 0
    total_existing = 0
    ai_result = None

    conn = get_conn()

    if entity_type == "persona":
        for table in ["internati", "decorati", "caduti_albooro"]:
            if not _table_exists(conn, table):
                continue
            row = conn.execute(
                f"SELECT * FROM {table} WHERE id=?", (entity_id,)
            ).fetchone()
            if not row:
                if entity_label and table == "internati":
                    parts = entity_label.split()
                    if len(parts) >= 1:
                        row = conn.execute(
                            f"SELECT * FROM {table} WHERE cognome LIKE ? LIMIT 1",
                            (f"{parts[0]}%",)
                        ).fetchone()
                elif entity_label and table == "decorati":
                    parts = entity_label.split()
                    if len(parts) >= 1:
                        row = conn.execute(
                            f"SELECT * FROM {table} WHERE cognome LIKE ? LIMIT 1",
                            (f"{parts[0]}%",)
                        ).fetchone()
                continue

            cols = [d[1] for d in conn.execute(f"PRAGMA table_info({table})").fetchall()]
            record = dict(zip(cols, row))

            # ID collision guard: verify the record name matches entity_label
            # before extracting claims. Different tables may have different
            # records with the same numeric ID.
            record_name = ""
            if "cognome" in record:
                record_name = f"{record.get('cognome', '')} {record.get('nome', '')}".strip()
            elif "nominativo" in record:
                record_name = record.get("nominativo", "")
            if record_name and entity_label:
                from entity_resolution import normalize_name
                norm_record = normalize_name(record_name)
                norm_entity = normalize_name(entity_label)
                # Check if names share at least the surname
                record_parts = norm_record.split()
                entity_parts = norm_entity.split()
                if record_parts and entity_parts:
                    if record_parts[0] != entity_parts[0]:
                        # Name mismatch — skip this table to avoid ID collision
                        continue

            result = extract_claims_from_record(
                table=table,
                record_id=record["id"],
                entity_type=entity_type,
                entity_id=entity_id,
                entity_label=entity_label,
            )
            total_created += result.get("claims_created", 0)
            total_existing += result.get("claims_existing", 0)
            all_claim_ids.extend(result.get("claim_ids", []))

            if table == "internati" and record.get("raw_text") and is_any_provider_available():
                ai_result = extract_claims_from_text_ai(
                    text=record["raw_text"],
                    entity_type=entity_type,
                    entity_id=entity_id,
                    entity_label=entity_label,
                    source_table=table,
                    source_id=record["id"],
                    research_plan_id=research_plan_id,
                    session_id=session_id,
                )
                if ai_result.get("ok"):
                    total_created += ai_result.get("claims_created", 0)
                    total_existing += ai_result.get("claims_existing", 0)
                    all_claim_ids.extend(ai_result.get("claim_ids", []))

    conn.close()

    conflicts = detect_conflicts(entity_type, entity_id)
    timeline = auto_build_timeline(entity_type, entity_id)

    return {
        "claims_created": total_created,
        "claims_existing": total_existing,
        "claim_ids": all_claim_ids,
        "conflicts": conflicts,
        "timeline": timeline,
        "ai_extraction": ai_result,
        "entity_type": entity_type,
        "entity_id": entity_id,
        "entity_label": entity_label,
    }

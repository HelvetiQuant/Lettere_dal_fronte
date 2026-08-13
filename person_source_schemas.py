"""PERSON_SOURCE_SCHEMAS — registro mapping per 5 tabelle PERSON.

Per ogni tabella definisce:
  - claim_fields: mapping colonna_db → predicate canonico
  - provenance_fields: mapping colonna_db → predicate provenance
  - identity_fields: campi usati per identity resolution
  - conflict_fields: campi che indicano conflitto se divergenti
  - war_period: periodo bellico (WWI | WWII | BOTH)
  - name_fields: (colonna_cognome, colonna_nome, colonna_nominativo)
  - validators: funzioni di validazione valore per predicate
  - normalizers: funzioni di normalizzazione valore per predicate

Invarianti:
  1. Ogni tabella ha il proprio mapping — nessun fallback implicito
  2. I predicate sono univoci e semanticamente corretti per tabella
  3. I campi non mappati non vengono estratti come claim
  4. raw_value non viene mai sovrascritto da normalizzazione
  5. war_period è usato per barriere temporali WWI/WWII
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Callable, Tuple, Any


# ─── War period classification ──────────────────────────────────────────────

WAR_PERIOD_WWI = "WWI"
WAR_PERIOD_WWII = "WWII"
WAR_PERIOD_BOTH = "BOTH"
WAR_PERIOD_UNKNOWN = "UNKNOWN"


# ─── Typed schema definition ────────────────────────────────────────────────

@dataclass
class SourceSchema:
    """Schema definition for a PERSON source table."""
    table_name: str
    war_period: str  # WWI | WWII | BOTH | UNKNOWN
    name_fields: Tuple[str, str, str]  # (cognome_col, nome_col, nominativo_col)
    claim_fields: Dict[str, str] = field(default_factory=dict)  # col_name → predicate
    provenance_fields: Dict[str, str] = field(default_factory=dict)  # col_name → predicate
    identity_fields: List[str] = field(default_factory=list)  # fields for identity resolution
    conflict_fields: List[str] = field(default_factory=list)  # fields that conflict if different
    authority_tier: int = 2  # 1=official, 2=primary, 3=secondary, 4=unofficial
    description: str = ""


# ─── Value validators ───────────────────────────────────────────────────────

def _validate_year(val: str) -> bool:
    """Check if value contains a year (18xx-19xx)."""
    if not val:
        return False
    return bool(re.search(r"(18|19)\d{2}", str(val).strip()))

def _validate_date(val: str) -> bool:
    """Check if value looks like a date (YYYY-MM-DD or DD/MM/YYYY or similar)."""
    if not val:
        return False
    s = str(val).strip()
    return bool(re.match(r"^\d{4}[-/]\d{1,2}[-/]\d{1,2}$|^\d{1,2}[-/]\d{1,2}[-/]\d{4}$", s))

def _validate_non_empty(val: str) -> bool:
    """Check if value is non-empty and not a placeholder."""
    if not val:
        return False
    s = str(val).strip()
    return s != "" and s != "-" and s.lower() != "n.d." and s.lower() != "n/a"

def _validate_place(val: str) -> bool:
    """Check if value looks like a place name."""
    if not _validate_non_empty(val):
        return False
    s = str(val).strip()
    # Reject pure numbers or codes
    if s.isdigit():
        return False
    return True

def _validate_rank(val: str) -> bool:
    """Check if value looks like a military rank."""
    if not _validate_non_empty(val):
        return False
    s = str(val).strip().lower()
    # Reject if it's clearly not a rank (e.g., a place or number)
    if s.isdigit():
        return False
    return True

def _validate_unit(val: str) -> bool:
    """Check if value looks like a military unit."""
    if not _validate_non_empty(val):
        return False
    s = str(val).strip()
    # Reject if it's clearly a place (no numbers, no regiment/battaglione/etc)
    if not any(kw in s.lower() for kw in ["reggimento", "battaglione", "compagnia", "reparto", "brigata", "divisione", "regt", "batt", "coy", "bty", "sqdn", "bn", "regiment", "battalion"]):
        # Accept if contains a number (likely unit designation)
        if not re.search(r"\d", s):
            return False
    return True


# ─── Value normalizers ──────────────────────────────────────────────────────

def _normalize_place(val: str) -> str:
    """Normalize place name: strip, title case for Italian, preserve original."""
    if not val:
        return ""
    s = str(val).strip()
    return s

def _normalize_year(val: str) -> str:
    """Extract 4-digit year from value."""
    if not val:
        return ""
    s = str(val).strip()
    m = re.search(r"(18|19)\d{2}", s)
    return m.group(0) if m else s

def _normalize_date(val: str) -> str:
    """Normalize date to YYYY-MM-DD if possible."""
    if not val:
        return ""
    s = str(val).strip()
    # Already ISO
    m = re.match(r"^(\d{4})-(\d{1,2})-(\d{1,2})$", s)
    if m:
        y, mo, d = m.groups()
        return f"{y}-{int(mo):02d}-{int(d):02d}"
    # DD/MM/YYYY
    m = re.match(r"^(\d{1,2})/(\d{1,2})/(\d{4})$", s)
    if m:
        d, mo, y = m.groups()
        return f"{y}-{int(mo):02d}-{int(d):02d}"
    return s

def _normalize_text(val: str) -> str:
    """Basic text normalization: strip whitespace."""
    if not val:
        return ""
    return str(val).strip()

def _normalize_rank(val: str) -> str:
    """Normalize rank: strip, preserve case."""
    return _normalize_text(val)

def _normalize_unit(val: str) -> str:
    """Normalize unit: strip, preserve case."""
    return _normalize_text(val)


# ─── Predicate → (validator, normalizer) registry ──────────────────────────

PREDICATE_VALIDATORS: Dict[str, Callable[[str], bool]] = {
    "birth_date": _validate_date,
    "birth_year": _validate_year,
    "birth_place": _validate_place,
    "birth_province": _validate_place,
    "death_date": _validate_date,
    "death_year": _validate_year,
    "death_place": _validate_place,
    "death_country": _validate_place,
    "death_cause": _validate_non_empty,
    "age_at_death": _validate_non_empty,
    "paternity": _validate_non_empty,
    "maternity": _validate_non_empty,
    "rank": _validate_rank,
    "military_unit": _validate_unit,
    "military_branch": _validate_non_empty,
    "military_id": _validate_non_empty,
    "service_number": _validate_non_empty,
    "fate": _validate_non_empty,
    "internment_place": _validate_place,
    "work_command": _validate_non_empty,
    "assignment": _validate_non_empty,
    "residence": _validate_place,
    "capture_place": _validate_place,
    "capture_date": _validate_date,
    "date_note": _validate_non_empty,
    "decoration_type": _validate_non_empty,
    "decoration_year": _validate_year,
    "draft_class": _validate_non_empty,
    "municipality": _validate_place,
    "current_municipality": _validate_place,
    "burial_place": _validate_place,
    "burial_country": _validate_place,
    "capture_front": _validate_non_empty,
    "return_date": _validate_date,
    "return_place": _validate_place,
}

PREDICATE_NORMALIZERS: Dict[str, Callable[[str], str]] = {
    "birth_date": _normalize_date,
    "birth_year": _normalize_year,
    "birth_place": _normalize_place,
    "birth_province": _normalize_place,
    "death_date": _normalize_date,
    "death_year": _normalize_year,
    "death_place": _normalize_place,
    "death_country": _normalize_place,
    "death_cause": _normalize_text,
    "age_at_death": _normalize_text,
    "paternity": _normalize_text,
    "maternity": _normalize_text,
    "rank": _normalize_rank,
    "military_unit": _normalize_unit,
    "military_branch": _normalize_text,
    "military_id": _normalize_text,
    "service_number": _normalize_text,
    "fate": _normalize_text,
    "internment_place": _normalize_place,
    "work_command": _normalize_text,
    "assignment": _normalize_text,
    "residence": _normalize_place,
    "capture_place": _normalize_place,
    "capture_date": _normalize_date,
    "date_note": _normalize_text,
    "decoration_type": _normalize_text,
    "decoration_year": _normalize_year,
    "draft_class": _normalize_text,
    "municipality": _normalize_place,
    "current_municipality": _normalize_place,
    "burial_place": _normalize_place,
    "burial_country": _normalize_place,
    "capture_front": _normalize_text,
    "return_date": _normalize_date,
    "return_place": _normalize_place,
}


# ─── Schema registry for 5 PERSON tables ────────────────────────────────────

PERSON_SOURCE_SCHEMAS: Dict[str, SourceSchema] = {

    # ─── internati — IMI WWII, 20,465 records ───────────────────────────────
    "internati": SourceSchema(
        table_name="internati",
        war_period=WAR_PERIOD_WWII,
        name_fields=("cognome", "nome", ""),
        authority_tier=1,
        description="Internati Militari Italiani — deportati nel Terzo Reich dopo 8 settembre 1943",
        claim_fields={
            "sorte": "fate",
            "luogo_internamento": "internment_place",
            "residenza": "residence",
            "data": "date_note",
            "grado": "rank",
            "matricola": "military_id",
            "luogo_nascita": "birth_place",
            "data_nascita": "birth_date",
            "luogo_cattura": "capture_place",
            "data_cattura": "capture_date",
            "arbeitskommando": "work_command",
            "mansione": "assignment",
            "reparto": "military_unit",
            "arma": "military_branch",
        },
        provenance_fields={
            "lettera": "archive_letter",
            "file_pdf": "source_document",
            "pagina": "source_page",
        },
        identity_fields=[
            "data_nascita", "luogo_nascita", "matricola", "grado", "reparto",
        ],
        conflict_fields=[
            "data_nascita", "luogo_nascita", "matricola", "reparto",
        ],
    ),

    # ─── caduti_albooro — WWI, 342,555 records ──────────────────────────────
    "caduti_albooro": SourceSchema(
        table_name="caduti_albooro",
        war_period=WAR_PERIOD_WWI,
        name_fields=("", "", "nominativo"),
        authority_tier=1,
        description="Caduti Albo d'Oro — caduti italiani WWI",
        claim_fields={
            "paternita": "paternity",
            "classe": "draft_class",
            "comune_attuale": "current_municipality",
            "grado": "rank",
            "reparto": "military_unit",
            "anno_morte": "death_year",
            "luogo_morte": "death_place",
            "causa_morte": "death_cause",
        },
        provenance_fields={
            "detail_url": "source_url",
            "volume_name": "source_volume",
        },
        identity_fields=[
            "paternita", "classe", "grado", "reparto", "anno_morte", "luogo_morte",
        ],
        conflict_fields=[
            "paternita", "reparto", "anno_morte", "luogo_morte", "causa_morte",
        ],
    ),

    # ─── decorati_nastroazzurro — WWI, 279,832 records ──────────────────────
    "decorati_nastroazzurro": SourceSchema(
        table_name="decorati_nastroazzurro",
        war_period=WAR_PERIOD_WWI,
        name_fields=("cognome", "nome", ""),
        authority_tier=1,
        description="Decorati al Nastro Azzurro — decorati italiani WWI",
        claim_fields={
            "arma": "military_branch",
            "anno_decorazione": "decoration_year",
            "tipo_decorazione": "decoration_type",
        },
        provenance_fields={
            "source_id": "source_ref",
        },
        identity_fields=[
            "anno_decorazione", "arma",
        ],
        conflict_fields=[
            "anno_decorazione", "arma",
        ],
    ),

    # ─── caduti_cwgc — WWI+WWII, 506,446 records ────────────────────────────
    "caduti_cwgc": SourceSchema(
        table_name="caduti_cwgc",
        war_period=WAR_PERIOD_BOTH,
        name_fields=("cognome", "nome", ""),
        authority_tier=2,
        description="Commonwealth War Graves Commission — caduti Commonwealth WWI/WWII",
        claim_fields={
            "rank": "rank",
            "service_number": "service_number",
            "service": "military_branch",
            "regiment": "military_unit",
            "data_morte": "death_date",
            "eta": "age_at_death",
            "cimitero": "burial_place",
            "paese_cimitero": "burial_country",
            "data_nascita": "birth_date",
            "nationality": "nationality",
        },
        provenance_fields={
            "cwgc_id": "source_ref",
            "memorial": "source_memorial",
            "grave_ref": "source_grave_ref",
        },
        identity_fields=[
            "data_nascita", "data_morte", "service_number", "rank", "regiment",
        ],
        conflict_fields=[
            "data_nascita", "data_morte", "service_number", "regiment",
        ],
    ),

    # ─── lebi_records — WWII IMI, 166K records (LeBI/ANRP) ───────────────────
    "lebi_records": SourceSchema(
        table_name="lebi_records",
        war_period=WAR_PERIOD_WWII,
        name_fields=("cognome", "nome", ""),
        authority_tier=1,
        description="Lessico Biografico degli IMI — ANRP, schede biografiche complete internati militari italiani WWII",
        claim_fields={
            "data_nascita": "birth_date",
            "luogo_nascita": "birth_place",
            "provincia_nascita": "birth_province",
            "grado": "rank",
            "reparto": "military_unit",
            "arma": "military_branch",
            "matricola": "military_id",
            "fronte_cattura": "capture_front",
            "luogo_cattura": "capture_place",
            "data_cattura": "capture_date",
            "campi_internamento": "internment_place",
            "sorte": "fate",
            "data_decesso": "death_date",
            "luogo_decesso": "death_place",
            "causa_morte": "death_cause",
            "luogo_sepoltura": "burial_place",
            "data_rientro": "return_date",
            "luogo_rientro": "return_place",
        },
        provenance_fields={
            "detail_url": "source_url",
            "pdf_url": "source_document",
            "fonti": "source_ref",
            "lebi_id": "source_id",
        },
        identity_fields=[
            "data_nascita", "luogo_nascita", "provincia_nascita",
            "matricola", "grado", "reparto", "data_decesso",
        ],
        conflict_fields=[
            "data_nascita", "luogo_nascita", "matricola",
            "reparto", "data_decesso", "luogo_decesso",
        ],
    ),

    # ─── caduti_ministero — WWII, 162,646 records ───────────────────────────
    "caduti_ministero": SourceSchema(
        table_name="caduti_ministero",
        war_period=WAR_PERIOD_WWII,
        name_fields=("cognome", "nome", ""),
        authority_tier=1,
        description="Caduti Ministero Difesa — caduti italiani WWII",
        claim_fields={
            "paternita": "paternity",
            "maternita": "maternity",
            "data_nascita": "birth_date",
            "data_decesso": "death_date",
            "provincia_nascita": "birth_province",
            "comune_nascita": "birth_place",
            "nazione_decesso": "death_country",
            "luogo_sepoltura": "burial_place",
            "grado": "rank",
            "reparto": "military_unit",
            "anno_morte": "death_year",
            "luogo_morte": "death_place",
            "causa_morte": "death_cause",
        },
        provenance_fields={
            "scheda_url": "source_url",
            "codice_volume": "source_volume",
            "pagina": "source_page",
            "sub": "source_sub",
        },
        identity_fields=[
            "data_nascita", "comune_nascita", "provincia_nascita",
            "paternita", "maternita", "data_decesso",
        ],
        conflict_fields=[
            "data_nascita", "comune_nascita", "paternita", "maternita", "data_decesso",
        ],
    ),
}


# ─── Helper functions ───────────────────────────────────────────────────────

def get_schema(table_name: str) -> Optional[SourceSchema]:
    """Get schema for a table, or None if not registered."""
    return PERSON_SOURCE_SCHEMAS.get(table_name)

def get_all_claim_predicates() -> set:
    """Return all unique claim predicates across all schemas."""
    preds = set()
    for schema in PERSON_SOURCE_SCHEMAS.values():
        preds.update(schema.claim_fields.values())
    return preds

def get_all_provenance_predicates() -> set:
    """Return all unique provenance predicates across all schemas."""
    preds = set()
    for schema in PERSON_SOURCE_SCHEMAS.values():
        preds.update(schema.provenance_fields.values())
    return preds

def validate_and_normalize_value(predicate: str, raw_value: str) -> Tuple[str, str, str]:
    """Validate and normalize a value for a predicate.

    Returns:
        (normalized_value, validation_status, normalizer_note)
        validation_status: "valid" | "invalid" | "skipped"
        normalizer_note: description of normalization applied (if any)
    """
    raw_str = str(raw_value).strip() if raw_value else ""

    validator = PREDICATE_VALIDATORS.get(predicate, _validate_non_empty)
    normalizer = PREDICATE_NORMALIZERS.get(predicate, _normalize_text)

    if not raw_str or raw_str == "-":
        return "", "skipped", "empty_or_dash"

    if not validator(raw_str):
        return raw_str, "invalid", "validation_failed"

    normalized = normalizer(raw_str)
    note = ""
    if normalized != raw_str:
        note = f"normalized_from:{raw_str}"

    # V7.3-FASE4: Typed place normalization
    if predicate in ("birth_place", "birth_province", "death_place", "death_country",
                      "internment_place", "capture_place", "burial_place", "burial_country",
                      "residence", "municipality", "current_municipality"):
        from linking.normalization import normalize_place, PREDICATE_TO_PLACE_TYPE
        place_type = PREDICATE_TO_PLACE_TYPE.get(predicate, "unknown")
        np = normalize_place(raw_str, place_type=place_type)
        normalized = np.normalized
        if np.place_type != "unknown":
            note = f"place_type:{np.place_type}" + (f";normalized_from:{raw_str}" if normalized != raw_str else "")

    # V7.3-FASE4: Paternity parsing — extract structured father name
    if predicate == "paternity":
        from linking.normalization import parse_paternity
        rel = parse_paternity(raw_str)
        if rel.related_name and rel.confidence >= 0.75:
            parts = []
            if rel.related_cognome:
                parts.append(f"father_cognome:{rel.related_cognome}")
            if rel.related_nome:
                parts.append(f"father_nome:{rel.related_nome}")
            parts.append(f"relation_confidence:{rel.confidence:.2f}")
            note = ";".join(parts) + (f";normalized_from:{raw_str}" if normalized != raw_str else "")

    # V7.3-FASE6: Military ontology — classify rank/unit as fact vs context
    if predicate in ("rank", "grado", "military_unit", "reparto", "regiment",
                      "military_branch", "arma", "assignment", "work_command",
                      "arbeitskommando"):
        from military_ontology import enrich_claim_with_ontology
        ontology = enrich_claim_with_ontology(predicate, raw_str, "person_record")
        ont_parts = [f"ontology:{ontology.get('ontology_class', '')}"]
        if "rank_canonical" in ontology:
            ont_parts.append(f"rank_canonical:{ontology['rank_canonical']}")
            ont_parts.append(f"rank_category:{ontology.get('rank_category', '')}")
        if "unit_type" in ontology:
            ont_parts.append(f"unit_type:{ontology['unit_type']}")
            if ontology.get("unit_number"):
                ont_parts.append(f"unit_number:{ontology['unit_number']}")
            if ontology.get("unit_branch", "unknown") != "unknown":
                ont_parts.append(f"unit_branch:{ontology['unit_branch']}")
        note = ";".join(ont_parts) + (f";normalized_from:{raw_str}" if normalized != raw_str else "")

    return normalized, "valid", note

def get_identity_fields_for_table(table_name: str) -> List[str]:
    """Get identity fields for a specific table."""
    schema = get_schema(table_name)
    if not schema:
        return []
    return schema.identity_fields

def get_conflict_fields_for_table(table_name: str) -> List[str]:
    """Get conflict fields for a specific table."""
    schema = get_schema(table_name)
    if not schema:
        return []
    return schema.conflict_fields

def get_war_period_for_table(table_name: str) -> str:
    """Get war period classification for a table."""
    schema = get_schema(table_name)
    if not schema:
        return WAR_PERIOD_UNKNOWN
    return schema.war_period

def get_name_fields_for_table(table_name: str) -> Tuple[str, str, str]:
    """Get (cognome_col, nome_col, nominativo_col) for a table."""
    schema = get_schema(table_name)
    if not schema:
        return ("", "", "")
    return schema.name_fields

def extract_claims_from_record(
    table_name: str,
    record: Dict[str, Any],
    record_id: Any = None,
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """Extract claims and provenance from a DB record using the schema registry.

    Returns:
        (claims_list, provenance_list)
        Each claim dict has: predicate, value_raw, value_normalized, validation_status, normalizer_note, source_field
        Each provenance dict has: predicate, value_raw, value_normalized, source_field
    """
    schema = get_schema(table_name)
    if not schema:
        return [], []

    if record_id is None:
        record_id = record.get("id", "")

    source_id = f"local_db:{table_name}:{record_id}"

    claims = []
    for col_name, predicate in schema.claim_fields.items():
        raw_val = record.get(col_name, "")
        if not raw_val and raw_val != 0:
            continue
        raw_str = str(raw_val).strip()
        if not raw_str or raw_str == "-":
            continue

        normalized, status, note = validate_and_normalize_value(predicate, raw_str)
        if status == "skipped":
            continue

        claims.append({
            "predicate": predicate,
            "value_raw": raw_str,
            "value_normalized": normalized,
            "validation_status": status,
            "normalizer_note": note,
            "source_field": col_name,
            "source_id": source_id,
            "table": table_name,
            "record_id": record_id,
        })

    provenance = []
    for col_name, predicate in schema.provenance_fields.items():
        raw_val = record.get(col_name, "")
        if not raw_val and raw_val != 0:
            continue
        raw_str = str(raw_val).strip()
        if not raw_str or raw_str == "-":
            continue

        provenance.append({
            "predicate": predicate,
            "value_raw": raw_str,
            "value_normalized": raw_str,
            "source_field": col_name,
            "source_id": source_id,
            "table": table_name,
            "record_id": record_id,
        })

    return claims, provenance

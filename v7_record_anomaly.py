"""V7.2 Record Anomaly Detection — pre-extraction validation of raw DB records.

Inspired by the GPT manual pipeline's step 1: before any claim extraction,
the raw record is inspected for structural anomalies that could produce
false or misleading claims.

Anomalies detected:
  - SYNTHETIC_DATE: dates like 1921-01-01 where day/month are likely auto-generated
  - MISPLACED_FIELD: e.g. "Carab." in the nome field (rank in name field)
  - OCR_DEFORMED_PLACE: place names with unusual character patterns
  - INCOMPLETE_NAME: missing cognome or nome
  - AMBIGUOUS_FATE_FIELD: "sorte" containing burial or death info instead of fate
  - MISSING_DATE_CONTEXT: "deceduto" without date or circumstance

Each anomaly produces a verification question, NOT an automatic correction.
The original value is always preserved.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any


@dataclass
class AnomalyFlag:
    """A single anomaly detected on a raw record field."""
    field_name: str
    anomaly_type: str  # SYNTHETIC_DATE|MISPLACED_FIELD|OCR_DEFORMED_PLACE|INCOMPLETE_NAME|AMBIGUOUS_FATE_FIELD|MISSING_DATE_CONTEXT
    raw_value: str
    severity: str = "warning"  # warning|error
    question: str = ""  # verification question for the researcher
    suggested_action: str = ""  # e.g. "reject_day_month", "move_to_rank", "needs_image_review"


@dataclass
class RecordAnomalyReport:
    """Report of all anomalies found in a raw record."""
    table: str
    record_id: str
    anomalies: List[AnomalyFlag] = field(default_factory=list)

    @property
    def has_anomalies(self) -> bool:
        return len(self.anomalies) > 0

    @property
    def has_errors(self) -> bool:
        return any(a.severity == "error" for a in self.anomalies)

    def get_for_field(self, field_name: str) -> List[AnomalyFlag]:
        return [a for a in self.anomalies if a.field_name == field_name]

    def to_dict(self) -> dict:
        return {
            "table": self.table,
            "record_id": self.record_id,
            "anomalies": [
                {
                    "field_name": a.field_name,
                    "anomaly_type": a.anomaly_type,
                    "raw_value": a.raw_value,
                    "severity": a.severity,
                    "question": a.question,
                    "suggested_action": a.suggested_action,
                }
                for a in self.anomalies
            ],
        }


# ─── Known military rank abbreviations that might end up in name fields ──────

_RANK_ABBREVIATIONS = {
    "carab.", "carab", "carabiniere", "carabinieri",
    "sold.", "sold", "soldato",
    "cap.", "cap", "caporale",
    "serg.", "serg", "sergente",
    "mag.", "mag", "maggiore",
    "ten.", "ten", "tenente",
    "col.", "col", "colonnello",
    "gen.", "gen", "generale",
    "magg.", "magg",
    "cap.magg.", "cap.magg",
    "fante", "alpino", "bersagliere", "artigliere", "geniere",
    "mar.", "mar", "marinaio",
    "avv.", "avv",
    "sgt.", "sgt",
    "c.le", "c.le",
}


def detect_anomalies(
    table: str,
    record: Dict[str, Any],
    record_id: str = "",
) -> RecordAnomalyReport:
    """Detect structural anomalies in a raw DB record.

    Args:
        table: Source table name (internati, caduti_albooro, decorati, eventi_1gm)
        record: Raw record as dict
        record_id: Record identifier for traceability

    Returns:
        RecordAnomalyReport with all detected anomalies
    """
    report = RecordAnomalyReport(table=table, record_id=record_id)
    rid = record_id or str(record.get("id", ""))

    # ── SYNTHETIC_DATE: 1921-01-01, 1915-01-01, etc. ──
    date_fields = ["data_nascita", "data_morte", "data_cattura", "data", "data_inizio", "data_fine"]
    for fname in date_fields:
        val = str(record.get(fname, "")).strip()
        if not val:
            continue
        # Check for YYYY-01-01 pattern (synthetic Jan 1st)
        m = re.match(r"^(\d{4})-01-01$", val)
        if m:
            year = m.group(1)
            report.anomalies.append(AnomalyFlag(
                field_name=fname,
                anomaly_type="SYNTHETIC_DATE",
                raw_value=val,
                severity="warning",
                question=f"La data {val} ha giorno e mese al 01/01 — è sintetica o derivata da 'Cl. {year}'?",
                suggested_action="reject_day_month",
            ))

    # ── MISPLACED_FIELD: rank abbreviation in nome field ──
    nome_val = str(record.get("nome", "")).strip()
    if nome_val:
        nome_lower = nome_val.lower().rstrip(".")
        for rank_abbr in _RANK_ABBREVIATIONS:
            if nome_lower == rank_abbr.rstrip(".") or nome_lower.startswith(rank_abbr.rstrip(".") + " "):
                report.anomalies.append(AnomalyFlag(
                    field_name="nome",
                    anomaly_type="MISPLACED_FIELD",
                    raw_value=nome_val,
                    severity="error",
                    question=f"Il campo nome contiene '{nome_val}' che sembra un grado militare, non un nome di battesimo",
                    suggested_action="move_to_rank_field",
                ))
                break

    # ── INCOMPLETE_NAME: missing cognome or nome ──
    cognome_val = str(record.get("cognome", "")).strip()
    if not cognome_val or cognome_val == "-":
        report.anomalies.append(AnomalyFlag(
            field_name="cognome",
            anomaly_type="INCOMPLETE_NAME",
            raw_value=cognome_val,
            severity="error",
            question="Cognome mancante o vuoto",
            suggested_action="needs_image_review",
        ))

    if not nome_val or nome_val == "-":
        # Only flag if not already flagged as misplaced
        if not any(a.field_name == "nome" and a.anomaly_type == "MISPLACED_FIELD" for a in report.anomalies):
            report.anomalies.append(AnomalyFlag(
                field_name="nome",
                anomaly_type="INCOMPLETE_NAME",
                raw_value=nome_val,
                severity="warning",
                question="Nome mancante o vuoto",
                suggested_action="needs_image_review",
            ))

    # ── OCR_DEFORMED_PLACE: unusual character patterns in place fields ──
    place_fields = ["luogo_nascita", "luogo_internamento", "luogo_morte", "luogo_cattura",
                    "residenza", "luogo", "comune", "comune_nascita"]
    for fname in place_fields:
        val = str(record.get(fname, "")).strip()
        if not val or val == "-":
            continue
        # Detect OCR deformation patterns: mixed case, unusual sequences, hyphenation
        ocr_issues = _detect_ocr_place_anomaly(val)
        if ocr_issues:
            report.anomalies.append(AnomalyFlag(
                field_name=fname,
                anomaly_type="OCR_DEFORMED_PLACE",
                raw_value=val,
                severity="warning",
                question=f"Il toponimo '{val}' presenta possibili deformazioni OCR: {ocr_issues}",
                suggested_action="geographic_normalization_needed",
            ))

    # ── AMBIGUOUS_FATE_FIELD: sorte containing burial/death info ──
    sorte_val = str(record.get("sorte", "")).strip().lower()
    if sorte_val:
        burial_keywords = ["sepolto", "sepolta", "sepolto a", "tomba", "cimitero"]
        death_keywords = ["deceduto", "morto", "morte", "caduto", "ucciso"]
        for kw in burial_keywords:
            if kw in sorte_val:
                report.anomalies.append(AnomalyFlag(
                    field_name="sorte",
                    anomaly_type="AMBIGUOUS_FATE_FIELD",
                    raw_value=str(record.get("sorte", "")),
                    severity="warning",
                    question=f"Il campo sorte contiene '{kw}' — potrebbe indicare luogo di sepoltura, non sorte generale",
                    suggested_action="reclassify_as_burial_place",
                ))
                break
        if not any(a.field_name == "sorte" for a in report.anomalies):
            for kw in death_keywords:
                if kw in sorte_val:
                    # Check if there's no date associated
                    has_date = bool(str(record.get("data_morte", "")).strip() or
                                   str(record.get("data", "")).strip())
                    if not has_date:
                        report.anomalies.append(AnomalyFlag(
                            field_name="sorte",
                            anomaly_type="MISSING_DATE_CONTEXT",
                            raw_value=str(record.get("sorte", "")),
                            severity="warning",
                            question=f"Sorte='{sorte_val}' ma nessuna data di morte associata",
                            suggested_action="flag_missing_death_date",
                        ))
                    break

    # ── AMBIGUOUS_FATE_FIELD: internamento containing death/burial ──
    intern_val = str(record.get("luogo_internamento", "")).strip().lower()
    if intern_val:
        for kw in ["sepolto", "sepolta", "tomba", "cimitero", "deceduto", "morto"]:
            if kw in intern_val:
                report.anomalies.append(AnomalyFlag(
                    field_name="luogo_internamento",
                    anomaly_type="AMBIGUOUS_FATE_FIELD",
                    raw_value=str(record.get("luogo_internamento", "")),
                    severity="warning",
                    question=f"Il campo luogo_internamento contiene '{kw}' — potrebbe indicare sepoltura, non internamento",
                    suggested_action="reclassify_as_burial_place",
                ))
                break

    return report


def _detect_ocr_place_anomaly(place_name: str) -> str:
    """Detect OCR deformation patterns in a place name.

    Returns description of the issue, or empty string if no anomaly detected.
    """
    issues = []

    # Mixed case within a single word (e.g., "stencle-Bai-Figan")
    words = place_name.replace("-", " ").split()
    for w in words:
        if len(w) > 3 and w != w.upper() and w != w.lower() and not w.istitle():
            # Has mixed case but not title case
            issues.append("mixed_case")
            break

    # Unusual consonant clusters (OCR artifacts)
    if re.search(r"[bcdfghjklmnpqrstvwxz]{4,}", place_name, re.I):
        issues.append("consonant_cluster")

    # Hyphenated fragments that look like OCR decomposition
    if place_name.count("-") >= 2:
        parts = place_name.split("-")
        if any(len(p) <= 3 for p in parts):
            issues.append("hyphenated_fragments")

    # Contains digits (OCR misread)
    if re.search(r"\d", place_name):
        issues.append("contains_digits")

    # Very short fragments
    if len(place_name) < 4 and place_name.isalpha():
        issues.append("too_short")

    return ", ".join(issues)


def apply_anomaly_rules_to_claims(
    claims: List[Dict[str, Any]],
    anomaly_report: RecordAnomalyReport,
) -> List[Dict[str, Any]]:
    """Apply anomaly-based rules to extracted claims.

    For each claim, check if its source field has an anomaly and adjust
    status/confidence accordingly.

    Rules:
    - SYNTHETIC_DATE → reject day/month precision, keep year only
    - MISPLACED_FIELD → reject the claim entirely
    - OCR_DEFORMED_PLACE → mark as 'probable' with normalization_needed
    - AMBIGUOUS_FATE_FIELD → reclassify predicate (sorte → buried_at)
    - INCOMPLETE_NAME → reject name claim
    - MISSING_DATE_CONTEXT → mark as 'unverified'

    Args:
        claims: List of claim dicts with 'predicate', 'value_normalized', 'source' fields
        anomaly_report: Anomaly report for the source record

    Returns:
        Modified claims list with adjusted statuses
    """
    for claim in claims:
        source = claim.get("source", "")
        # Extract field name from source like "local_db:internati:123:data_nascita"
        parts = source.split(":")
        field_name = parts[-1] if len(parts) > 1 else ""

        anomalies = anomaly_report.get_for_field(field_name)
        for anomaly in anomalies:
            if anomaly.anomaly_type == "SYNTHETIC_DATE":
                # Keep year, reject day/month
                val = claim.get("value_normalized", "")
                m = re.match(r"^(\d{4})-01-01$", val)
                if m:
                    claim["value_normalized"] = m.group(1)
                    claim["value_raw"] = val
                    claim["normalization_status"] = "year_only_from_synthetic"
                    claim["status"] = "REJECTED_PRECISION"
                    claim["confidence"] = 0.3
                    claim["anomaly_note"] = f"Data sintetica: giorno/mese generati automaticamente, mantenuto solo anno"

            elif anomaly.anomaly_type == "MISPLACED_FIELD":
                claim["status"] = "REJECTED"
                claim["confidence"] = 0.0
                claim["anomaly_note"] = f"Campo malposto: {anomaly.raw_value} non appartiene a questo campo"

            elif anomaly.anomaly_type == "OCR_DEFORMED_PLACE":
                claim["value_raw"] = claim.get("value_normalized", "")
                claim["normalization_status"] = "probable"
                claim["status"] = "PROBABLE"
                claim["confidence"] = min(claim.get("confidence", 0.5), 0.4)
                claim["anomaly_note"] = f"Toponimo con possibili deformazioni OCR: {anomaly.question}"

            elif anomaly.anomaly_type == "AMBIGUOUS_FATE_FIELD":
                # Reclassify: if "sepolto a" in sorte, change predicate to buried_at
                raw = anomaly.raw_value.lower()
                if "sepolto" in raw or "sepolta" in raw:
                    claim["predicate"] = "buried_at"
                    claim["value_raw"] = anomaly.raw_value
                    claim["normalization_status"] = "reclassified"
                    claim["anomaly_note"] = "Riclassificato da sorte a luogo di sepoltura"
                else:
                    claim["status"] = "UNVERIFIED"
                    claim["confidence"] = 0.2
                    claim["anomaly_note"] = anomaly.question

            elif anomaly.anomaly_type == "INCOMPLETE_NAME":
                claim["status"] = "REJECTED"
                claim["confidence"] = 0.0
                claim["anomaly_note"] = "Nome/cognome incompleto"

            elif anomaly.anomaly_type == "MISSING_DATE_CONTEXT":
                claim["status"] = "UNVERIFIED"
                claim["confidence"] = 0.2
                claim["anomaly_note"] = "Sorte indicata senza data o circostanza associata"

    return claims

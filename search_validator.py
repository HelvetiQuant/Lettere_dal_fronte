"""Search Validation Layer.

Confronta i risultati del DB locale con fonti esterne (federated search, web search)
per validare i dati. Se rileva discrepanze (province errate, omonimie, dati mancanti),
restituisce opzioni per la conferma dell'utente.

Flusso:
1. search_all() dal DB locale
2. federated_search() sui provider esterni configurati
3. Confronto e validazione
4. Se ci sono dubbi → needs_confirmation con opzioni
5. Se tutto coerente → validated con fonti di conferma
"""
from __future__ import annotations

import re
import sqlite3
from collections import defaultdict
from pathlib import Path
from typing import Any

from database import get_conn, DB_PATH
from source_providers.federation import federated_search, get_registry

# ─── Known place-province corrections (verified) ──────────────────────────────

PLACE_PROVINCE_FIXES: dict[str, tuple[str, str]] = {
    "nibbiano": ("Piacenza", "Bergamo"),
}

# ─── OCR character fixes ──────────────────────────────────────────────────────

OCR_CHAR_FIXES: dict[str, str] = {
    "ñ": "n",
    "Ã¨": "è",
    "Ã©": "é",
    "Ã¬": "ì",
    "Ã²": "ò",
    "Ã¹": "ù",
    "Ã ": "à",
    "â€™": "'",
}

# ─── Helpers ──────────────────────────────────────────────────────────────────

PLACE_COLS = {
    "luogo", "luogo_nascita", "comune_nascita", "luogo_morte",
    "luogo_cattura", "luogo_internamento", "residenza", "place",
    "luogo_sepoltura", "cimitero", "paese_cimitero", "provincia_nascita",
    "comune", "comune_residenza", "comune_attuale", "luogo_dimora",
}


def _has_ocr_issues(value: str) -> list[str]:
    """Restituisce lista di caratteri OCR problematici trovati nel valore."""
    found = []
    for bad_char in OCR_CHAR_FIXES:
        if bad_char in value:
            found.append(bad_char)
    return found


def _check_province(place_value: str) -> dict | None:
    """Verifica se un toponimo ha una provincia errata associata.
    Restituisce dict con correzione o None.
    """
    val_lower = place_value.lower().strip()
    for place, (correct_prov, wrong_prov) in PLACE_PROVINCE_FIXES.items():
        if place in val_lower and wrong_prov.lower() in val_lower:
            corrected = re.sub(
                rf"\({re.escape(wrong_prov)}\)",
                f"({correct_prov})",
                place_value,
                flags=re.IGNORECASE,
            )
            # Also fix OCR chars in the corrected value
            for bad, good in OCR_CHAR_FIXES.items():
                corrected = corrected.replace(bad, good)
            return {
                "issue": "wrong_province",
                "place": place,
                "wrong_province": wrong_prov,
                "correct_province": correct_prov,
                "original": place_value,
                "corrected": corrected,
            }
    return None


def _check_ocr_chars(field_name: str, value: str) -> dict | None:
    """Verifica se un valore ha caratteri OCR errati."""
    issues = _has_ocr_issues(value)
    if not issues:
        return None
    corrected = value
    for bad in issues:
        corrected = corrected.replace(bad, OCR_CHAR_FIXES[bad])
    return {
        "issue": "ocr_character",
        "field": field_name,
        "chars_found": issues,
        "original": value,
        "corrected": corrected,
    }


def _extract_cues(records: dict) -> dict:
    """Estrae cue (persona, luogo, data) dai risultati di search_all per la federated search."""
    cues: dict[str, Any] = {"names": set(), "places": set(), "dates": set()}

    for category in ("internati", "decorati", "caduti"):
        for rec in records.get(category, []):
            for k, v in rec.items():
                if not v or not isinstance(v, str):
                    continue
                kl = k.lower()
                if kl in {"cognome", "nome", "nominativo"}:
                    cues["names"].add(v.strip())
                elif kl in PLACE_COLS:
                    cues["places"].add(v.strip())
                elif kl in {"data_nascita", "data_morte", "data_cattura", "data"}:
                    cues["dates"].add(v.strip())

    return {k: list(v)[:10] for k, v in cues.items()}


def _validate_record_fields(record: dict) -> list[dict]:
    """Valida i campi di un singolo record per problemi OCR e province errate."""
    issues = []
    for k, v in record.items():
        if not v or not isinstance(v, str):
            continue
        kl = k.lower()
        # Check OCR chars in any string field
        ocr_issue = _check_ocr_chars(k, v)
        if ocr_issue:
            issues.append(ocr_issue)
        # Check province in place columns
        if kl in PLACE_COLS:
            prov_issue = _check_province(v)
            if prov_issue:
                issues.append(prov_issue)
    return issues


def _check_homonyms(records: dict) -> list[dict]:
    """Rileva possibili omonimie: stesso nome ma dati discordanti per la stessa colonna."""
    from collections import defaultdict

    name_groups: dict[str, list[dict]] = defaultdict(list)
    for category in ("internati", "decorati", "caduti"):
        for rec in records.get(category, []):
            name_parts = []
            for k in ("cognome", "nome", "nominativo"):
                v = rec.get(k)
                if v and isinstance(v, str):
                    name_parts.append(v.strip().lower())
            if name_parts:
                full_name = " ".join(name_parts)
                rec_copy = dict(rec)
                rec_copy["_category"] = category
                name_groups[full_name].append(rec_copy)

    homonym_alerts = []
    for name, group in name_groups.items():
        if len(group) < 2:
            continue
        # Check for conflicting values in the same column
        conflicts = []
        col_values: dict[str, set[str]] = defaultdict(set)
        for rec in group:
            for k, v in rec.items():
                if k.startswith("_") or not v or not isinstance(v, str):
                    continue
                kl = k.lower()
                if kl in PLACE_COLS or kl in {"data_nascita", "data_morte", "data_cattura", "data"}:
                    col_values[kl].add(v.strip().lower())
        for col, vals in col_values.items():
            if len(vals) > 1:
                conflicts.append({
                    "column": col,
                    "values": list(vals),
                    "records": [{"category": r.get("_category"), "id": r.get("id"), "table": r.get("table")} for r in group],
                })
        if conflicts:
            homonym_alerts.append({
                "issue": "possible_homonym",
                "name": name,
                "conflicts": conflicts,
            })
    return homonym_alerts


def validate_search(query: str, local_results: dict, external_enabled: bool = True) -> dict:
    """Esegue la validazione dei risultati di ricerca.

    Args:
        query: termine di ricerca originale
        local_results: risultati di search_all()
        external_enabled: se True, interroga anche fonti esterne

    Returns:
        dict con:
        - status: "validated" | "needs_confirmation" | "local_only"
        - results: risultati locali
        - validations: liste di conferme/issue trovate
        - external_sources: risultati da fonti esterne (se abilitate)
        - confirmations: opzioni che richiedono conferma utente
    """
    validations = []
    confirmations = []

    # 1. Valida campi di ogni record per OCR e province
    total_records = 0
    for category in ("internati", "decorati", "caduti", "menzioni"):
        records = local_results.get(category, [])
        total_records += len(records)
        for rec in records:
            issues = _validate_record_fields(rec)
            for issue in issues:
                if issue["issue"] == "wrong_province":
                    confirmations.append({
                        "type": "province_correction",
                        "record_id": rec.get("id"),
                        "record_table": rec.get("table", category),
                        "category": category,
                        **issue,
                    })
                else:
                    validations.append({
                        "type": "ocr_fix",
                        "record_id": rec.get("id"),
                        "record_table": rec.get("table", category),
                        "category": category,
                        **issue,
                    })

    # 2. Rileva omonimie
    homonym_alerts = _check_homonyms(local_results)
    for alert in homonym_alerts:
        confirmations.append({
            "type": "homonym_check",
            **alert,
        })

    # 3. Ricerca su fonti esterne (se abilitata)
    external_sources = []
    if external_enabled and total_records > 0:
        cues = _extract_cues(local_results)
        try:
            ext_results = federated_search(query, cues=cues)
            external_sources = ext_results[:20]  # top 20
            # Confronta: se fonti esterne trovano dati aggiuntivi, aggiungi come validazioni
            for ext in external_sources:
                if ext.get("error"):
                    continue
                validations.append({
                    "type": "external_source_match",
                    "provider": ext.get("provider", ""),
                    "title": ext.get("title", "")[:200],
                    "url": ext.get("url", ""),
                    "score": ext.get("score", 0),
                })
        except Exception as exc:
            validations.append({
                "type": "external_search_error",
                "error": str(exc),
            })

    # Determina status
    if confirmations:
        status = "needs_confirmation"
    elif external_sources and len(validations) > 0:
        status = "validated"
    else:
        status = "local_only"

    return {
        "status": status,
        "query": query,
        "results": local_results,
        "validations": validations,
        "external_sources": external_sources,
        "confirmations": confirmations,
        "summary": {
            "total_records": total_records,
            "validations_count": len(validations),
            "confirmations_count": len(confirmations),
            "external_sources_count": len(external_sources),
        },
    }


def apply_confirmation(confirmation: dict, db_name: str = "imi_internati") -> dict:
    """Applica una correzione confermata dall'utente al database.

    Args:
        confirmation: dict con type, record_id, record_table, e dati correzione
        db_name: nome del database da modificare

    Returns:
        dict con esito dell'operazione
    """
    conn = get_conn()
    try:
        if confirmation["type"] == "province_correction":
            table = confirmation.get("record_table", "internati")
            record_id = confirmation["record_id"]
            corrected = confirmation["corrected"]
            # Find which column to update
            original = confirmation["original"]
            # Determine column name from the record
            cols = [r[1] for r in conn.execute(f'PRAGMA table_info("{table}")')]
            place_cols = [c for c in cols if c.lower() in PLACE_COLS]

            updated = False
            for col in place_cols:
                try:
                    row = conn.execute(f'SELECT "{col}" FROM "{table}" WHERE id = ?', (record_id,)).fetchone()
                    if row and row[0] and str(row[0]).strip() == original.strip():
                        conn.execute(f'UPDATE "{table}" SET "{col}" = ? WHERE id = ?', (corrected, record_id))
                        conn.commit()
                        updated = True
                        return {
                            "ok": True,
                            "action": "province_corrected",
                            "table": table,
                            "column": col,
                            "record_id": record_id,
                            "old_value": original,
                            "new_value": corrected,
                        }
                except Exception:
                    continue

            if not updated:
                return {"ok": False, "error": "Record non trovato o valore non corrispondente"}

        elif confirmation["type"] == "ocr_fix":
            table = confirmation.get("record_table", "internati")
            record_id = confirmation["record_id"]
            field = confirmation["field"]
            corrected = confirmation["corrected"]
            original = confirmation["original"]

            try:
                conn.execute(f'UPDATE "{table}" SET "{field}" = ? WHERE id = ?', (corrected, record_id))
                conn.commit()
                return {
                    "ok": True,
                    "action": "ocr_fixed",
                    "table": table,
                    "column": field,
                    "record_id": record_id,
                    "old_value": original,
                    "new_value": corrected,
                }
            except Exception as exc:
                return {"ok": False, "error": str(exc)}

        return {"ok": False, "error": f"Tipo conferma non supportato: {confirmation['type']}"}
    finally:
        conn.close()

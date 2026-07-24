"""Entity Resolution — varianti d'identita', matching, scoring spiegabile.

Genera varianti spiegabili (grafie, OCR, translitterazioni, linguistiche),
calcola punteggi di corrispondenza composti con breakdown, e gestisce
decisioni umane di conferma/respingimento/omonimia.

Nessun singolo algoritmo determina l'identita'. Il punteggio e' composto
da multipli segnali pesati.
"""
import json
import re
import unicodedata
from datetime import datetime
from typing import Dict, List, Optional, Tuple

from database import get_conn


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


# ═══ NORMALIZATION ═════════════════════════════════════════════════════════

def normalize_name(name: str) -> str:
    """Normalizza un nome: lowercase, senza accenti, senza spazi extra."""
    if not name:
        return ""
    name = unicodedata.normalize("NFKD", name)
    name = "".join(c for c in name if not unicodedata.combining(c))
    name = name.lower().strip()
    name = re.sub(r"\s+", " ", name)
    name = re.sub(r"['`']", "", name)
    return name


def strip_titles(name: str) -> str:
    """Rimuove titoli onomastici italiani e tedeschi."""
    titles = [
        "signor", "signora", "sig.", "sig.ra", "don", "fra", "s.",
        "herr", "frau", "mr", "mrs", "mister",
    ]
    tokens = name.strip().split()
    while tokens and tokens[0].lower().rstrip(".") in titles:
        tokens.pop(0)
    return " ".join(tokens)


# ═══ VARIANT GENERATION ════════════════════════════════════════════════════

def generate_variants(name: str, field: str = "name",
                      birth_date: str = None,
                      birth_place: str = None) -> List[Dict]:
    """Genera varianti spiegabili per un nome o valore.

    Tipi di variante:
    - name_swap: cognome/nome invertito
    - initial: iniziali del nome
    - ocr_error: errori OCR probabili
    - transliteration: translitterazioni
    - accent_variant: varianti di accenti/apostrofi
    - language_variant: varianti linguistiche
    - historical_spelling: grafie storiche
    """
    variants = []
    name = (name or "").strip()
    if not name:
        return variants

    # 1. Name swap (cognome/nome → nome/cognome)
    parts = name.split()
    if len(parts) >= 2:
        swapped = " ".join([parts[-1]] + parts[:-1])
        if swapped.lower() != name.lower():
            variants.append({
                "original": name,
                "variant": swapped,
                "type": "name_swap",
                "origin": "anagraphic_convention",
                "confidence": 0.7,
            })

    # 2. Initials
    if len(parts) >= 2:
        initials = " ".join(p[0] + "." for p in parts if p)
        variants.append({
            "original": name,
            "variant": f"{parts[0]} {initials[len(parts[0])+1:]}",
            "type": "initial",
            "origin": "abbreviation",
            "confidence": 0.5,
        })

    # 3. Accent variants
    normalized = normalize_name(name)
    if normalized != name.lower():
        variants.append({
            "original": name,
            "variant": normalized,
            "type": "accent_variant",
            "origin": "normalization",
            "confidence": 0.9,
        })

    # 4. OCR error variants (comuni confusioni)
    ocr_pairs = [
        ("n", "ri"), ("m", "rn"), ("0", "O"), ("l", "I"), ("l", "1"),
        ("d", "cl"), ("u", "v"), ("e", "c"), ("h", "b"), ("nn", "m"),
    ]
    for orig_char, ocr_char in ocr_pairs:
        if orig_char in name.lower():
            ocr_variant = name.lower().replace(orig_char, ocr_char, 1)
            if ocr_variant != name.lower():
                variants.append({
                    "original": name,
                    "variant": ocr_variant,
                    "type": "ocr_error",
                    "origin": "ocr_confusion",
                    "confidence": 0.3,
                })

    # 5. Transliteration (Italian → German)
    translit_map = {
        "ch": "k", "gh": "g", "sci": "shi", "ce": "che", "ci": "chi",
        "ge": "ghe", "gi": "ghi",
    }
    translit = name
    for it_pat, de_pat in translit_map.items():
        translit = translit.replace(it_pat, de_pat)
    if translit.lower() != name.lower():
        variants.append({
            "original": name,
            "variant": translit,
            "type": "transliteration",
            "origin": "italian_to_german",
            "confidence": 0.4,
        })

    # 6. Strip titles
    stripped = strip_titles(name)
    if stripped.lower() != name.lower():
        variants.append({
            "original": name,
            "variant": stripped,
            "type": "title_strip",
            "origin": "onomastic_convention",
            "confidence": 0.8,
        })

    return variants


def save_variants(entity_type: str, entity_id: int, field_name: str,
                  original_value: str, variants: List[Dict]):
    """Salva le varianti nel database."""
    conn = get_conn()
    now = _now()
    for v in variants:
        conn.execute(
            "INSERT INTO entity_variants (entity_type, entity_id, field_name, "
            "original_value, variant_value, variant_type, origin, confidence, "
            "verified, created_at) VALUES (?,?,?,?,?,?,?,?,?,?)",
            (entity_type, entity_id, field_name, original_value,
             v["variant"], v["type"], v["origin"], v["confidence"], 0, now)
        )
    conn.commit()
    conn.close()


# ═══ SCORING ═══════════════════════════════════════════════════════════════

# Pesi dei segnali per il punteggio composto
SIGNAL_WEIGHTS = {
    "name_similarity": 0.25,
    "birth_date": 0.15,
    "birth_place": 0.10,
    "nationality": 0.05,
    "service_number": 0.15,
    "military_unit": 0.10,
    "rank": 0.05,
    "capture_place": 0.05,
    "capture_date": 0.05,
    "camp": 0.05,
    "arbeitungskommando": 0.05,
    "family_member": 0.05,
    "temporal_coherence": 0.05,
    "geographic_coherence": 0.05,
}


def levenshtein(a: str, b: str) -> int:
    """Distanza di Levenshtein."""
    if not a:
        return len(b)
    if not b:
        return len(a)
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        curr = [i]
        for j, cb in enumerate(b, 1):
            curr.append(min(
                prev[j] + 1,
                curr[j - 1] + 1,
                prev[j - 1] + (ca != cb),
            ))
        prev = curr
    return prev[-1]


def jaro_winkler(s1: str, s2: str) -> float:
    """Similarita' Jaro-Winkler (0-1)."""
    s1, s2 = s1.lower(), s2.lower()
    if s1 == s2:
        return 1.0
    if not s1 or not s2:
        return 0.0

    match_dist = max(len(s1), len(s2)) // 2 - 1
    match_dist = max(0, match_dist)
    s1_matches = [False] * len(s1)
    s2_matches = [False] * len(s2)
    matches = 0

    for i, c in enumerate(s1):
        start = max(0, i - match_dist)
        end = min(i + match_dist + 1, len(s2))
        for j in range(start, end):
            if s2_matches[j]:
                continue
            if c != s2[j]:
                continue
            s1_matches[i] = True
            s2_matches[j] = True
            matches += 1
            break

    if matches == 0:
        return 0.0

    # Transpositions
    k = 0
    transpositions = 0
    for i in range(len(s1)):
        if not s1_matches[i]:
            continue
        while not s2_matches[k]:
            k += 1
        if s1[i] != s2[k]:
            transpositions += 1
        k += 1

    jaro = (matches / len(s1) + matches / len(s2) +
            (matches - transpositions / 2) / matches) / 3

    # Winkler prefix bonus
    prefix = 0
    for i in range(min(4, len(s1), len(s2))):
        if s1[i] == s2[i]:
            prefix += 1
        else:
            break
    return jaro + prefix * 0.1 * (1 - jaro)


def compute_match_score(local: Dict, candidate: Dict) -> Dict:
    """Calcola punteggio di corrispondenza composto con breakdown.

    Restituisce:
    - score: punteggio complessivo (0-1)
    - breakdown: contributo di ogni segnale
    - contrary_signals: segnali contrari
    - missing_data: dati mancanti
    - threshold_applied: soglia applicata
    """
    breakdown = {}
    contrary = []
    missing = []

    # Name similarity
    local_name = normalize_name(local.get("name") or local.get("nominativo") or "")
    cand_name = normalize_name(candidate.get("name") or candidate.get("nominativo") or "")
    if local_name and cand_name:
        name_sim = jaro_winkler(local_name, cand_name)
        breakdown["name_similarity"] = name_sim * SIGNAL_WEIGHTS["name_similarity"]
        if name_sim < 0.7:
            contrary.append({"signal": "name_similarity", "value": name_sim,
                             "reason": "nome significativamente diverso"})
    else:
        missing.append("name")

    # Birth date
    local_dob = local.get("birth_date") or local.get("data_nascita") or ""
    cand_dob = candidate.get("birth_date") or candidate.get("data_nascita") or ""
    if local_dob and cand_dob:
        if local_dob == cand_dob:
            breakdown["birth_date"] = 1.0 * SIGNAL_WEIGHTS["birth_date"]
        elif local_dob[:4] == cand_dob[:4]:
            breakdown["birth_date"] = 0.7 * SIGNAL_WEIGHTS["birth_date"]
        else:
            contrary.append({"signal": "birth_date", "value": f"{local_dob} vs {cand_dob}",
                             "reason": "anno di nascita incompatibile"})
    else:
        missing.append("birth_date")

    # Birth place
    local_place = normalize_name(local.get("birth_place") or local.get("luogo_nascita") or "")
    cand_place = normalize_name(candidate.get("birth_place") or candidate.get("luogo_nascita") or "")
    if local_place and cand_place:
        if local_place == cand_place:
            breakdown["birth_place"] = 1.0 * SIGNAL_WEIGHTS["birth_place"]
        elif local_place in cand_place or cand_place in local_place:
            breakdown["birth_place"] = 0.8 * SIGNAL_WEIGHTS["birth_place"]
        else:
            contrary.append({"signal": "birth_place", "value": f"{local_place} vs {cand_place}",
                             "reason": "luogo di nascita diverso"})
    else:
        missing.append("birth_place")

    # Service number
    local_sn = local.get("service_number") or local.get("matricola") or ""
    cand_sn = candidate.get("service_number") or candidate.get("matricola") or ""
    if local_sn and cand_sn:
        if local_sn == cand_sn:
            breakdown["service_number"] = 1.0 * SIGNAL_WEIGHTS["service_number"]
        else:
            contrary.append({"signal": "service_number", "value": f"{local_sn} vs {cand_sn}",
                             "reason": "matricola diversa"})
    else:
        missing.append("service_number")

    # Military unit
    local_unit = normalize_name(local.get("military_unit") or local.get("reparto") or "")
    cand_unit = normalize_name(candidate.get("military_unit") or candidate.get("reparto") or "")
    if local_unit and cand_unit:
        unit_sim = jaro_winkler(local_unit, cand_unit)
        breakdown["military_unit"] = unit_sim * SIGNAL_WEIGHTS["military_unit"]
    else:
        missing.append("military_unit")

    # Camp
    local_camp = normalize_name(local.get("camp") or local.get("luogo_morte") or "")
    cand_camp = normalize_name(candidate.get("camp") or candidate.get("luogo_morte") or "")
    if local_camp and cand_camp:
        if local_camp == cand_camp:
            breakdown["camp"] = 1.0 * SIGNAL_WEIGHTS["camp"]
        elif local_camp in cand_camp or cand_camp in local_camp:
            breakdown["camp"] = 0.7 * SIGNAL_WEIGHTS["camp"]
    else:
        missing.append("camp")

    # Temporal coherence
    local_dates = [d for d in [local.get("birth_date"), local.get("capture_date"),
                               local.get("death_date")] if d]
    cand_dates = [d for d in [candidate.get("birth_date"), candidate.get("capture_date"),
                              candidate.get("death_date")] if d]
    if local_dates and cand_dates:
        local_range = (min(local_dates), max(local_dates))
        cand_range = (min(cand_dates), max(cand_dates))
        if local_range[0][:4] <= cand_range[1][:4] and cand_range[0][:4] <= local_range[1][:4]:
            breakdown["temporal_coherence"] = 1.0 * SIGNAL_WEIGHTS["temporal_coherence"]
        else:
            contrary.append({"signal": "temporal_coherence",
                             "value": f"{local_range} vs {cand_range}",
                             "reason": "intervalli temporali non sovrapponibili"})
    else:
        missing.append("temporal_data")

    score = sum(breakdown.values())
    # Normalizza per i pesi dei segnali disponibili
    available_weight = sum(SIGNAL_WEIGHTS[k] for k in breakdown)
    if available_weight > 0:
        score = score / available_weight

    return {
        "score": round(score, 4),
        "breakdown": breakdown,
        "contrary_signals": contrary,
        "missing_data": missing,
        "threshold_applied": 0.75,
        "algorithm_version": "v1.0",
    }


def save_match_candidate(local_entity_type: str, local_entity_id: int,
                         local_table: str, local_record_id: int,
                         candidate_source: str,
                         candidate_record_id: int = None,
                         candidate_external_id: str = None,
                         score_result: Dict = None) -> int:
    """Salva un candidato di match nel database."""
    conn = get_conn()
    now = _now()
    conn.execute(
        """INSERT INTO entity_match_candidates (
            local_entity_type, local_entity_id, local_table, local_record_id,
            candidate_source, candidate_record_id, candidate_external_id,
            score, score_breakdown_json, contrary_signals_json,
            missing_data_json, threshold_applied, algorithm_version,
            status, created_at, updated_at
        ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (local_entity_type, local_entity_id, local_table, local_record_id,
         candidate_source, candidate_record_id, candidate_external_id,
         score_result.get("score", 0) if score_result else 0,
         json.dumps(score_result.get("breakdown", {})) if score_result else None,
         json.dumps(score_result.get("contrary_signals", [])) if score_result else None,
         json.dumps(score_result.get("missing_data", [])) if score_result else None,
         score_result.get("threshold_applied", 0.75) if score_result else 0.75,
         score_result.get("algorithm_version", "v1.0") if score_result else "v1.0",
         "candidate", now, now)
    )
    mc_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
    conn.commit()
    conn.close()
    return mc_id


def review_match(match_id: int, decision: str, reviewer: str,
                 reason: str = "") -> Dict:
    """Revisione umana di un match.
    decision: confirmed | rejected | open | omonymy
    """
    conn = get_conn()
    now = _now()
    mc = conn.execute(
        "SELECT id FROM entity_match_candidates WHERE id=?", (match_id,)
    ).fetchone()
    if not mc:
        conn.close()
        return {"error": "match not found"}

    conn.execute(
        "UPDATE entity_match_candidates SET review_decision=?, reviewer=?, "
        "review_reason=?, status=?, reviewed_at=?, updated_at=? WHERE id=?",
        (decision, reviewer, reason, decision, now, now, match_id)
    )
    conn.commit()
    conn.close()
    return {"ok": True, "match_id": match_id, "decision": decision}


def get_match_candidates(entity_type: str, entity_id: int) -> List[Dict]:
    """Recupera candidati di match per un'entita'."""
    conn = get_conn()
    rows = conn.execute(
        "SELECT * FROM entity_match_candidates WHERE local_entity_type=? "
        "AND local_entity_id=? ORDER BY score DESC, created_at DESC",
        (entity_type, entity_id)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]

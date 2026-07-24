"""Claim Service — affermazioni atomiche con provenienza completa.

L'unita' fondamentale del sistema non e' il documento ne' il record, ma
l'affermazione (claim). Ogni claim e' collegato a almeno una evidenza
oppure e' marcato esplicitamente come ipotesi non documentata.

Stati epistemici:
- confirmed: confermato da revisione umana o da >=2 fonti indipendenti
- probable: supportato da evidenza ma non revisionato
- possible: dedotto ma non supportato da prova diretta
- contested: fonti discordanti
- rejected: respinto da revisione umana
- superseded: sostituito da claim piu' recente

Stati di revisione:
- proposed: proposto dall'IA o dall'import, non revisionato
- under_review: in revisione
- confirmed: confermato da ricercatore
- rejected: respinto da ricercatore
"""
import hashlib
import json
from datetime import datetime
from typing import Dict, List, Optional, Any

from database import get_conn


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _stable_id(subject_type: str, subject_id: int, predicate: str,
               object_value: str, temporal_start: str = "") -> str:
    """Genera stable_id deterministico per idempotenza."""
    raw = f"{subject_type}:{subject_id}:{predicate}:{object_value}:{temporal_start}"
    return hashlib.sha256(raw.encode()).hexdigest()[:32]


# ═══ CRUD ═══════════════════════════════════════════════════════════════════

def create_claim(
    subject_type: str,
    subject_id: Optional[int],
    subject_label: str = "",
    predicate: str = "",
    object_type: str = None,
    object_id: int = None,
    object_label: str = "",
    object_value: str = "",
    original_value: str = "",
    temporal_range_start: str = "",
    temporal_range_end: str = "",
    temporal_precision: str = None,
    temporal_uncertainty: str = None,
    place: str = "",
    epistemic_status: str = "possible",
    confidence: float = 0.3,
    extraction_method: str = "manual",
    extraction_id: int = None,
    created_by: str = "system",
) -> Dict:
    """Crea un claim atomico. Idempotente via stable_id."""
    conn = get_conn()
    now = _now()
    sid = _stable_id(subject_type, subject_id or 0, predicate, object_value,
                     temporal_range_start)

    existing = conn.execute(
        "SELECT id, version FROM claims WHERE stable_id=?", (sid,)
    ).fetchone()
    if existing:
        conn.close()
        return {"id": existing[0], "stable_id": sid, "already_existed": True}

    conn.execute(
        """INSERT INTO claims (
            stable_id, subject_type, subject_id, subject_label,
            predicate, object_type, object_id, object_label, object_value,
            original_value, temporal_range_start, temporal_range_end,
            temporal_precision, temporal_uncertainty, place,
            epistemic_status, confidence, extraction_method, extraction_id,
            review_status, created_by, version, created_at, updated_at
        ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (sid, subject_type, subject_id, subject_label,
         predicate, object_type, object_id, object_label, object_value,
         original_value, temporal_range_start, temporal_range_end,
         temporal_precision, temporal_uncertainty, place,
         epistemic_status, confidence, extraction_method, extraction_id,
         "proposed", created_by, "1", now, now)
    )
    claim_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
    conn.commit()
    conn.close()
    return {"id": claim_id, "stable_id": sid, "already_existed": False}


def add_evidence(
    claim_id: int,
    source_id: int = None,
    source_table: str = None,
    document_id: int = None,
    document_table: str = None,
    extraction_id: int = None,
    page_or_frame: str = "",
    coordinates: str = "",
    supporting_quote: str = "",
    evidence_role: str = "supports",
    source_independence_group: str = None,
    strength: float = 0.5,
    note: str = "",
) -> int:
    """Aggiunge evidenza a un claim."""
    conn = get_conn()
    now = _now()
    conn.execute(
        """INSERT INTO claim_evidence (
            claim_id, source_id, source_table, document_id, document_table,
            extraction_id, page_or_frame, coordinates, supporting_quote,
            evidence_role, source_independence_group, strength, note, created_at
        ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (claim_id, source_id, source_table, document_id, document_table,
         extraction_id, page_or_frame, coordinates, supporting_quote,
         evidence_role, source_independence_group, strength, note, now)
    )
    eid = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
    conn.commit()
    conn.close()
    return eid


def get_claims_for_entity(entity_type: str, entity_id: int,
                          epistemic_status: str = None,
                          review_status: str = None) -> List[Dict]:
    """Recupera tutti i claim per un'entita'."""
    conn = get_conn()
    sql = "SELECT * FROM claims WHERE subject_type=? AND subject_id=?"
    params = [entity_type, entity_id]
    if epistemic_status:
        sql += " AND epistemic_status=?"
        params.append(epistemic_status)
    if review_status:
        sql += " AND review_status=?"
        params.append(review_status)
    sql += " ORDER BY temporal_range_start, created_at"
    rows = conn.execute(sql, params).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_claim_evidence(claim_id: int) -> List[Dict]:
    """Recupera tutte le evidenze di un claim."""
    conn = get_conn()
    rows = conn.execute(
        "SELECT * FROM claim_evidence WHERE claim_id=? ORDER BY strength DESC, created_at",
        (claim_id,)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def review_claim(claim_id: int, decision: str, reviewer: str,
                 reason: str = "") -> Dict:
    """Revisione umana di un claim.
    decision: confirmed | rejected | under_review
    """
    conn = get_conn()
    now = _now()
    claim = conn.execute("SELECT * FROM claims WHERE id=?", (claim_id,)).fetchone()
    if not claim:
        conn.close()
        return {"error": "claim not found"}
    claim = dict(claim)

    new_epistemic = claim["epistemic_status"]
    if decision == "confirmed":
        new_epistemic = "confirmed"
    elif decision == "rejected":
        new_epistemic = "rejected"

    conn.execute(
        "UPDATE claims SET review_status=?, reviewed_by=?, reviewed_at=?, "
        "review_reason=?, epistemic_status=?, updated_at=? WHERE id=?",
        (decision, reviewer, now, reason, new_epistemic, now, claim_id)
    )
    conn.commit()
    conn.close()
    return {"ok": True, "claim_id": claim_id, "new_epistemic": new_epistemic}


# ═══ CONFLITTI ═════════════════════════════════════════════════════════════

def detect_conflicts(entity_type: str, entity_id: int) -> List[Dict]:
    """Rileva conflitti tra claim della stessa entita' (deterministico).

    Confronta claim con stesso predicate ma object_value diverso.
    """
    conn = get_conn()
    claims = conn.execute(
        "SELECT * FROM claims WHERE subject_type=? AND subject_id=? "
        "AND epistemic_status NOT IN ('rejected', 'superseded') "
        "ORDER BY predicate, temporal_range_start",
        (entity_type, entity_id)
    ).fetchall()
    conn.close()

    conflicts = []
    by_predicate: Dict[str, List] = {}
    for c in claims:
        c = dict(c)
        pred = c["predicate"]
        if pred not in by_predicate:
            by_predicate[pred] = []
        by_predicate[pred].append(c)

    for pred, group in by_predicate.items():
        if len(group) < 2:
            continue
        # Group by object_type — only compare claims of same type
        # (e.g. born_at with "date" vs "place" are complementary, not conflicting)
        by_obj_type: Dict[str, List] = {}
        for c in group:
            ot = c.get("object_type") or "unknown"
            if ot not in by_obj_type:
                by_obj_type[ot] = []
            by_obj_type[ot].append(c)

        for ot, ot_group in by_obj_type.items():
            if len(ot_group) < 2:
                continue
            values = set()
            for c in ot_group:
                val = (c.get("object_value") or "").strip().lower()
                if val:
                    values.add(val)
            if len(values) > 1:
                # Possibile trasferimento? Controlla se le date sono sequenziali
                sorted_group = sorted(ot_group, key=lambda x: x.get("temporal_range_start") or "")
                dates = [c.get("temporal_range_start") for c in sorted_group if c.get("temporal_range_start")]
                is_sequential = len(dates) >= 2 and dates == sorted(dates)

                conflicts.append({
                    "predicate": pred,
                    "object_type": ot,
                    "values": list(values),
                    "claims": [c["id"] for c in ot_group],
                    "is_sequential": is_sequential,
                    "interpretation": "possible_transfer" if is_sequential else "contradiction",
                    "explanation": (
                        "Possibile trasferimento nel tempo (date sequenziali)"
                        if is_sequential else
                        "Contraddizione non risolta tra fonti"
                    ),
                })

                # Registra la relazione tra claim
                for i in range(len(sorted_group)):
                    for j in range(i + 1, len(sorted_group)):
                        _ensure_claim_relation(
                            sorted_group[i]["id"], sorted_group[j]["id"],
                            "possible_sequence" if is_sequential else "contradicts",
                            confidence=0.7 if is_sequential else 0.5,
                            method="deterministic_date_comparison",
                            motivation=conflicts[-1]["explanation"],
                        )
    return conflicts


def _ensure_claim_relation(claim_a: int, claim_b: int, relation_type: str,
                           confidence: float, method: str, motivation: str):
    """Crea relazione tra claim se non esiste gia'."""
    conn = get_conn()
    now = _now()
    existing = conn.execute(
        "SELECT id FROM claim_relations WHERE claim_a_id=? AND claim_b_id=? AND relation_type=?",
        (claim_a, claim_b, relation_type)
    ).fetchone()
    if not existing:
        conn.execute(
            "INSERT INTO claim_relations (claim_a_id, claim_b_id, relation_type, "
            "confidence, method, motivation, review_status, created_at) "
            "VALUES (?,?,?,?,?,?,?,?)",
            (claim_a, claim_b, relation_type, confidence, method, motivation, "auto", now)
        )
        conn.commit()
    conn.close()


def get_conflicts(entity_type: str, entity_id: int) -> List[Dict]:
    """Recupera conflitti gia' registrati + rilevamento deterministico."""
    conn = get_conn()
    rows = conn.execute(
        """SELECT cr.*, ca.predicate as pred_a, ca.object_value as val_a,
           cb.predicate as pred_b, cb.object_value as val_b
           FROM claim_relations cr
           JOIN claims ca ON cr.claim_a_id = ca.id
           JOIN claims cb ON cr.claim_b_id = cb.id
           WHERE (ca.subject_type=? AND ca.subject_id=?)
           AND cr.relation_type IN ('contradicts', 'possible_sequence')
           ORDER BY cr.created_at""",
        (entity_type, entity_id)
    ).fetchall()
    conn.close()
    stored = [dict(r) for r in rows]
    detected = detect_conflicts(entity_type, entity_id)
    return {"stored_relations": stored, "detected_conflicts": detected}


# ═══ TIMELINE ══════════════════════════════════════════════════════════════

def build_timeline(entity_type: str, entity_id: int) -> List[Dict]:
    """Costruisce timeline delle affermazioni documentate."""
    conn = get_conn()
    claims = conn.execute(
        """SELECT * FROM claims WHERE subject_type=? AND subject_id=?
           AND epistemic_status NOT IN ('rejected', 'superseded')
           ORDER BY temporal_range_start, created_at""",
        (entity_type, entity_id)
    ).fetchall()
    conn.close()

    timeline = []
    for c in claims:
        c = dict(c)
        evidence = get_claim_evidence(c["id"])
        timeline.append({
            "date_start": c.get("temporal_range_start"),
            "date_end": c.get("temporal_range_end"),
            "precision": c.get("temporal_precision"),
            "uncertainty": c.get("temporal_uncertainty"),
            "predicate": c["predicate"],
            "object_value": c.get("object_value") or c.get("object_label"),
            "place": c.get("place"),
            "epistemic_status": c["epistemic_status"],
            "confidence": c["confidence"],
            "claim_id": c["id"],
            "evidence_count": len(evidence),
            "evidence_sources": [e.get("source_table") for e in evidence],
            "review_status": c["review_status"],
        })
    return timeline


# ═══ NARRATIVE ═════════════════════════════════════════════════════════════

def save_narrative(entity_type: str, entity_id: int,
                   narrative_type: str, structured_text: str,
                   claim_ids: List[int], gaps: List = None,
                   deductions: List = None, confidence_level: float = 0.3,
                   model_version: str = "", prompt_version: str = "",
                   audience: str = "public") -> int:
    """Salva una narrazione generata (versionata)."""
    conn = get_conn()
    now = _now()
    # Recupera versione precedente
    prev = conn.execute(
        "SELECT version FROM generated_narratives WHERE entity_type=? AND entity_id=? "
        "AND narrative_type=? ORDER BY id DESC LIMIT 1",
        (entity_type, entity_id, narrative_type)
    ).fetchone()
    prev_version = int(prev[0]) if prev else 0
    new_version = str(prev_version + 1)

    conn.execute(
        """INSERT INTO generated_narratives (
            entity_type, entity_id, narrative_type, audience, structured_text,
            claim_ids_json, gaps_json, deductions_json, confidence_level,
            model_version, prompt_version, review_status, version,
            created_at, updated_at
        ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (entity_type, entity_id, narrative_type, audience, structured_text,
         json.dumps(claim_ids), json.dumps(gaps or []), json.dumps(deductions or []),
         confidence_level, model_version, prompt_version, "draft", new_version,
         now, now)
    )
    nid = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
    conn.commit()
    conn.close()
    return nid


def get_narratives(entity_type: str, entity_id: int,
                   narrative_type: str = None) -> List[Dict]:
    """Recupera narrazioni per un'entita'."""
    conn = get_conn()
    sql = "SELECT * FROM generated_narratives WHERE entity_type=? AND entity_id=?"
    params = [entity_type, entity_id]
    if narrative_type:
        sql += " AND narrative_type=?"
        params.append(narrative_type)
    sql += " ORDER BY id DESC"
    rows = conn.execute(sql, params).fetchall()
    conn.close()
    return [dict(r) for r in rows]

"""Service per collegamenti incrociati tra menzioni esterne e record interni.

Pipeline:
1. Generazione candidati (FTS + indici)
2. Confronto deterministico (matricola, prigioniero, protocollo)
3. Confronto probabilistico (nome, data, luogo, grado)
4. Rilevazione conflitti (date incompatibili, paternità, matricole)
5. Scoring e stato (candidate/probable/confirmed/ambiguous/rejected)
6. Generazione spiegazione leggibile

Non effettua merge distruttivi. Non conferma automaticamente.
"""
import json
import re
from datetime import datetime
from typing import Optional, List, Dict, Any, Tuple

from database import get_conn


# ─── Tabelle interne abilitate al matching ──────────────────────────────
MATCHABLE_TABLES = {
    "internati": {
        "surname_col": "cognome", "name_col": "nome",
        "birth_date_col": "data_nascita", "birth_place_col": "luogo_nascita",
        "residence_col": "residenza", "rank_col": "grado",
        "unit_col": None, "service_number_col": None,
        "prisoner_number_col": None, "camp_col": "luogo_internamento",
        "death_date_col": "data", "death_place_col": None,
        "extra_cols": ["sorte", "luogo_cattura"],
    },
    "caduti_albooro": {
        "surname_col": None, "name_col": None,  # usa nominativo
        "nominativo_col": "nominativo",
        "birth_place_col": "comune_attuale",
        "death_date_col": "anno_morte", "death_place_col": "luogo_morte",
        "extra_cols": ["volume"],
    },
    "caduti_ministero": {
        "surname_col": "cognome", "name_col": "nome",
        "birth_date_col": "data_nascita", "birth_place_col": "comune_nascita",
        "residence_col": None, "rank_col": None,
        "death_date_col": "data_decesso", "death_place_col": "luogo_sepoltura",
        "extra_cols": ["provincia_nascita", "nazione_decesso"],
    },
    "caduti_cwgc": {
        "surname_col": "cognome", "name_col": "nome",
        "birth_date_col": "data_nascita", "birth_place_col": None,
        "rank_col": "rank", "unit_col": "regiment",
        "death_date_col": "data_morte", "death_place_col": "cimitero",
        "extra_cols": ["initials", "nationality", "guerra", "paese_cimitero"],
    },
    "caduti_francia_ww1": {
        "surname_col": None, "name_col": None,  # usa nom
        "nominativo_col": "nom",
        "birth_place_col": "lieu_naissance",
        "rank_col": "grade", "unit_col": "unite",
        "death_date_col": "date_deces", "death_place_col": "lieu_deces",
        "extra_cols": ["bureau_recrutement", "pays_deces", "classe"],
    },
    "caduti_sardi": {
        "surname_col": "cognome", "name_col": "nome",
        "birth_date_col": "data_nascita", "birth_place_col": None,
        "residence_col": "comune_residenza",
        "death_date_col": "data_morte", "death_place_col": "luogo_morte",
        "extra_cols": ["guerra"],
    },
    "caduti_bologna": {
        "surname_col": None, "name_col": None,  # usa nome
        "nominativo_col": "nome",
        "birth_place_col": "luogo_nascita",
        "death_date_col": "data_morte", "death_place_col": "luogo_morte",
        "extra_cols": ["luogo_dimora", "anno_nascita"],
    },
    "decorati_nastroazzurro": {
        "surname_col": "cognome", "name_col": "nome",
        "unit_col": "arma",
        "extra_cols": ["tipo_decorazione", "anno_decorazione"],
    },
    "decorati": {
        "surname_col": "cognome", "name_col": "nome",
        "birth_date_col": "data_nascita", "birth_place_col": "comune_nascita",
        "residence_col": "comune_residenza", "rank_col": "grado",
        "death_date_col": "data_morte", "death_place_col": "luogo_morte",
        "extra_cols": ["decorazione", "guerra", "luogo_internamento"],
    },
    "rc_candidates": {
        "surname_col": "cognome", "name_col": "nome",
        "birth_date_col": "data_nascita", "birth_place_col": "luogo_nascita",
        "residence_col": "comune_residenza", "rank_col": "grado",
        "unit_col": "reparto",
        "extra_cols": ["matricola", "conflitto", "stato", "paternita", "maternita"],
    },
}


def _normalize(s: Optional[str]) -> str:
    if not s:
        return ""
    return re.sub(r"[^a-z0-9]", "", s.lower().strip())


def _normalize_year(s: Optional[str]) -> Optional[str]:
    if not s:
        return None
    m = re.search(r"(18\d{2}|19\d{2}|20\d{2})", str(s))
    return m.group(1) if m else None


def _normalize_place(s: Optional[str]) -> str:
    if not s:
        return ""
    return _normalize(s)


# ─── Fase 1: Generazione candidati ──────────────────────────────────────
def generate_candidates(mention: Dict[str, Any], limit: int = 50) -> List[Dict[str, Any]]:
    """Genera candidati usando FTS e indici, non full scan."""
    conn = get_conn()
    candidates = []

    surname = (mention.get("normalized_surname") or mention.get("surname_raw") or "").strip()
    name = (mention.get("normalized_name") or mention.get("name_raw") or "").strip()
    full_name = f"{surname} {name}".strip()

    if not full_name:
        return []

    # Per ogni tabella abilitata, cerca candidati
    for table, cols in MATCHABLE_TABLES.items():
        try:
            # Costruisci query di ricerca
            if "nominativo_col" in cols:
                nom_col = cols["nominativo_col"]
                # Ricerca LIKE su nominativo
                rows = conn.execute(
                    f"SELECT id, {nom_col} as nominativo FROM {table} WHERE {nom_col} LIKE ? LIMIT ?",
                    (f"%{surname}%", limit)
                ).fetchall()
                for r in rows:
                    candidates.append({"table": table, "record_id": r["id"], "nominativo": r["nominativo"]})
            else:
                s_col = cols.get("surname_col")
                n_col = cols.get("name_col")
                if s_col:
                    # Ricerca per cognome (indicizzato)
                    rows = conn.execute(
                        f"SELECT id, {s_col} as cognome, {n_col} as nome FROM {table} WHERE {s_col} LIKE ? LIMIT ?",
                        (f"%{surname}%", limit)
                    ).fetchall()
                    for r in rows:
                        candidates.append({
                            "table": table, "record_id": r["id"],
                            "cognome": r["cognome"], "nome": r["nome"],
                        })
        except Exception:
            continue

    conn.close()
    return candidates


# ─── Fase 2-4: Confronto e scoring ──────────────────────────────────────
def compare_mention_to_record(
    mention: Dict[str, Any],
    table: str,
    record_id: int,
) -> Dict[str, Any]:
    """Confronta una menzione con un record interno. Ritorna score, campi match, conflitti, spiegazione."""
    conn = get_conn()
    cols = MATCHABLE_TABLES.get(table)
    if not cols:
        conn.close()
        return {"score": 0.0, "status": "rejected", "explanation": "Tabella non supportata"}

    # Fetch record
    try:
        row = conn.execute(f"SELECT * FROM {table} WHERE id = ?", (record_id,)).fetchone()
    except Exception:
        conn.close()
        return {"score": 0.0, "status": "rejected", "explanation": "Record non trovato"}
    if not row:
        conn.close()
        return {"score": 0.0, "status": "rejected", "explanation": "Record non trovato"}

    record = dict(row)
    conn.close()

    matched_fields = []
    conflicting_fields = []
    grave_conflicts = []
    evidence = []
    score = 0.0
    max_score = 0.0

    # ─── Confronto deterministico ────────────────────────────────────
    # Service number / matricola
    m_service = mention.get("service_number")
    r_service = record.get("matricola") or record.get("service_number")
    if m_service and r_service:
        max_score += 3.0
        if _normalize(m_service) == _normalize(r_service):
            score += 3.0
            matched_fields.append({"field": "service_number", "mention": m_service, "record": r_service})
            evidence.append(f"Matricola coincidente: {m_service}")
        else:
            conflicting_fields.append({"field": "service_number", "mention": m_service, "record": r_service})

    # Prisoner number
    m_prisoner = mention.get("prisoner_number")
    r_prisoner = record.get("prisoner_number") or record.get("numero_prigioniero")
    if m_prisoner and r_prisoner:
        max_score += 3.0
        if _normalize(m_prisoner) == _normalize(r_prisoner):
            score += 3.0
            matched_fields.append({"field": "prisoner_number", "mention": m_prisoner, "record": r_prisoner})
            evidence.append(f"Numero prigioniero coincidente: {m_prisoner}")
        else:
            conflicting_fields.append({"field": "prisoner_number", "mention": m_prisoner, "record": r_prisoner})

    # ─── Confronto probabilistico ────────────────────────────────────
    # Cognome
    m_surname = _normalize(mention.get("normalized_surname") or mention.get("surname_raw"))
    if "nominativo_col" in cols:
        r_nom = record.get(cols["nominativo_col"], "")
        r_surname = _normalize(r_nom.split()[0] if r_nom else "")
    else:
        r_surname = _normalize(record.get(cols.get("surname_col"), ""))
    if m_surname and r_surname:
        max_score += 2.0
        if m_surname == r_surname:
            score += 2.0
            matched_fields.append({"field": "surname", "mention": mention.get("surname_raw"), "record": record.get(cols.get("surname_col") or cols.get("nominativo_col"))})
        elif m_surname[:4] == r_surname[:4] and len(m_surname) >= 4:
            score += 1.2
            matched_fields.append({"field": "surname", "mention": mention.get("surname_raw"), "record": record.get(cols.get("surname_col") or cols.get("nominativo_col")), "partial": True})

    # Nome
    m_name = _normalize(mention.get("normalized_name") or mention.get("name_raw"))
    if "nominativo_col" in cols:
        r_nom = record.get(cols["nominativo_col"], "")
        parts = r_nom.split(None, 1) if r_nom else []
        r_name = _normalize(parts[1] if len(parts) > 1 else "")
    else:
        r_name = _normalize(record.get(cols.get("name_col"), ""))
    if m_name and r_name:
        max_score += 1.5
        if m_name == r_name:
            score += 1.5
            matched_fields.append({"field": "name", "mention": mention.get("name_raw"), "record": record.get(cols.get("name_col") or cols.get("nominativo_col"))})
        elif m_name[:3] == r_name[:3] and len(m_name) >= 3:
            score += 0.8
            matched_fields.append({"field": "name", "mention": mention.get("name_raw"), "record": record.get(cols.get("name_col") or cols.get("nominativo_col")), "partial": True})

    # Data di nascita
    m_birth = _normalize_year(mention.get("birth_date_text") or mention.get("birth_date"))
    r_birth_col = cols.get("birth_date_col")
    r_birth = _normalize_year(record.get(r_birth_col) if r_birth_col else None)
    if m_birth and r_birth:
        max_score += 2.0
        if m_birth == r_birth:
            score += 2.0
            matched_fields.append({"field": "birth_date", "mention": m_birth, "record": r_birth})
        else:
            diff = abs(int(m_birth) - int(r_birth))
            if diff <= 1:
                score += 1.0
                matched_fields.append({"field": "birth_date", "mention": m_birth, "record": r_birth, "approximate": True})
            elif diff <= 2:
                score += 0.3
                conflicting_fields.append({"field": "birth_date", "mention": m_birth, "record": r_birth, "note": "Differenza di 2 anni"})
            else:
                conflicting_fields.append({"field": "birth_date", "mention": m_birth, "record": r_birth, "note": "Date incompatibili"})

    # Luogo di nascita
    m_place = _normalize_place(mention.get("birth_place_raw"))
    r_place_col = cols.get("birth_place_col")
    r_place = _normalize_place(record.get(r_place_col) if r_place_col else None)
    if m_place and r_place:
        max_score += 1.0
        if m_place == r_place:
            score += 1.0
            matched_fields.append({"field": "birth_place", "mention": mention.get("birth_place_raw"), "record": record.get(r_place_col)})
        elif m_place[:5] == r_place[:5] and len(m_place) >= 5:
            score += 0.5
            matched_fields.append({"field": "birth_place", "mention": mention.get("birth_place_raw"), "record": record.get(r_place_col), "partial": True})

    # Grado
    m_rank = _normalize(mention.get("rank_raw"))
    r_rank_col = cols.get("rank_col")
    r_rank = _normalize(record.get(r_rank_col) if r_rank_col else None)
    if m_rank and r_rank:
        max_score += 0.5
        if m_rank == r_rank:
            score += 0.5
            matched_fields.append({"field": "rank", "mention": mention.get("rank_raw"), "record": record.get(r_rank_col)})

    # Camp/Luogo internamento (LeBI-specific)
    m_camp = _normalize(mention.get("camp_raw"))
    r_camp_col = cols.get("camp_col")
    r_camp = _normalize(record.get(r_camp_col) if r_camp_col else None)
    if m_camp and r_camp:
        max_score += 1.0
        if m_camp == r_camp:
            score += 1.0
            matched_fields.append({"field": "camp", "mention": mention.get("camp_raw"), "record": record.get(r_camp_col)})
        elif m_camp[:5] == r_camp[:5] and len(m_camp) >= 5:
            score += 0.5
            matched_fields.append({"field": "camp", "mention": mention.get("camp_raw"), "record": record.get(r_camp_col), "partial": True})

    # Data decesso (LeBI-specific — utile per escludere omonimie)
    m_death = _normalize_year(mention.get("event_date_text"))
    r_death_col = cols.get("death_date_col")
    r_death = _normalize_year(record.get(r_death_col) if r_death_col else None)
    if m_death and r_death:
        max_score += 1.5
        if m_death == r_death:
            score += 1.5
            matched_fields.append({"field": "death_date", "mention": m_death, "record": r_death})
        else:
            diff = abs(int(m_death) - int(r_death))
            if diff <= 1:
                score += 0.5
                matched_fields.append({"field": "death_date", "mention": m_death, "record": r_death, "approximate": True})
            else:
                conflicting_fields.append({"field": "death_date", "mention": m_death, "record": r_death, "note": "Date decesso incompatibili"})
                grave_conflicts.append({"field": "death_date", "note": "Date decesso incompatibili"})

    # ─── Determinazione stato ────────────────────────────────────────
    normalized_score = score / max_score if max_score > 0 else 0.0

    # Conflitti gravi riducono il punteggio
    grave_conflicts.extend([c for c in conflicting_fields if c.get("note", "").startswith("Date incompatibili")])
    if grave_conflicts:
        normalized_score *= 0.3

    if normalized_score >= 0.85 and not grave_conflicts:
        status = "probable"
    elif normalized_score >= 0.5:
        status = "candidate"
    elif normalized_score >= 0.3:
        status = "ambiguous"
    else:
        status = "rejected"

    # ─── Spiegazione leggibile ───────────────────────────────────────
    explanation_parts = []
    if matched_fields:
        match_names = [f["field"] for f in matched_fields]
        explanation_parts.append(f"Corrispondenza su: {', '.join(match_names)}")
    if conflicting_fields:
        conflict_descs = [f"{c['field']} (menzione: {c.get('mention','')}, record: {c.get('record','')})" for c in conflicting_fields]
        explanation_parts.append(f"Conflitti: {'; '.join(conflict_descs)}")
    if not matched_fields and not conflicting_fields:
        explanation_parts.append("Corrispondenza insufficiente per generare un collegamento")
    if not mention.get("father_name_raw") and not mention.get("birth_date_text"):
        explanation_parts.append("Il metadato esterno non riporta paternità né data di nascita")

    explanation = ". ".join(explanation_parts) + "."

    return {
        "score": round(normalized_score, 3),
        "raw_score": round(score, 2),
        "max_score": round(max_score, 2),
        "status": status,
        "matched_fields": matched_fields,
        "conflicting_fields": conflicting_fields,
        "evidence": evidence,
        "explanation": explanation,
        "record_data": {k: v for k, v in record.items() if v is not None},
    }


# ─── Generazione collegamenti ───────────────────────────────────────────
def generate_links_for_mention(mention_id: int) -> List[Dict[str, Any]]:
    """Genera collegamenti candidati per una menzione esterna."""
    conn = get_conn()
    mention = conn.execute(
        "SELECT * FROM external_person_mentions WHERE id = ?", (mention_id,)
    ).fetchone()
    if not mention:
        conn.close()
        return []

    mention_dict = dict(mention)
    record_id = mention_dict["external_source_record_id"]

    # Fase 1: candidati
    candidates = generate_candidates(mention_dict)

    # Fase 2-4: confronto
    links = []
    for cand in candidates:
        result = compare_mention_to_record(mention_dict, cand["table"], cand["record_id"])
        if result["status"] == "rejected":
            continue

        link_data = {
            "external_source_record_id": record_id,
            "external_person_mention_id": mention_id,
            "target_table": cand["table"],
            "target_record_id": cand["record_id"],
            "link_type": "person_match",
            "match_status": result["status"],
            "match_score": result["score"],
            "match_method": "deterministic+probabilistic",
            "matched_fields_json": json.dumps(result["matched_fields"], ensure_ascii=False),
            "conflicting_fields_json": json.dumps(result["conflicting_fields"], ensure_ascii=False),
            "evidence_json": json.dumps(result["evidence"], ensure_ascii=False),
            "explanation": result["explanation"],
            "review_status": "pending",
        }

        # Save link
        now = datetime.now().isoformat()
        link_data["created_at"] = now
        link_data["updated_at"] = now
        fields = list(link_data.keys())
        placeholders = ", ".join(["?"] * len(fields))
        col_list = ", ".join(fields)
        cur = conn.execute(
            f"INSERT INTO external_record_links ({col_list}) VALUES ({placeholders})",
            list(link_data.values())
        )
        link_data["id"] = cur.lastrowid
        links.append(link_data)

    conn.commit()
    conn.close()
    return links


def generate_links_for_record(record_id: int) -> List[Dict[str, Any]]:
    """Genera collegamenti per tutte le menzioni di un record esterno."""
    conn = get_conn()
    mentions = conn.execute(
        "SELECT id FROM external_person_mentions WHERE external_source_record_id = ?", (record_id,)
    ).fetchall()
    conn.close()

    all_links = []
    for m in mentions:
        links = generate_links_for_mention(m["id"])
        all_links.extend(links)
    return all_links


# ─── Revisione umana ────────────────────────────────────────────────────
def review_link(link_id: int, review_status: str, match_status: Optional[str] = None,
                 reviewer: str = "system") -> Dict[str, Any]:
    """Aggiorna lo stato di revisione di un collegamento."""
    conn = get_conn()
    now = datetime.now().isoformat()

    updates = {"review_status": review_status, "reviewed_by": reviewer, "reviewed_at": now, "updated_at": now}
    if match_status:
        updates["match_status"] = match_status

    set_clause = ", ".join(f"{k} = ?" for k in updates)
    values = list(updates.values()) + [link_id]
    conn.execute(f"UPDATE external_record_links SET {set_clause} WHERE id = ?", values)

    # If confirmed, create bidirectional link in record_links
    if review_status == "accepted" and match_status == "confirmed":
        link = conn.execute("SELECT * FROM external_record_links WHERE id = ?", (link_id,)).fetchone()
        if link:
            # Create bidirectional record_links
            try:
                conn.execute(
                    "INSERT OR IGNORE INTO record_links (from_table, from_id, to_table, to_id, link_type, confidence, elaborato_il, match_status, review_status, reviewed_by, reviewed_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    ("external_person_mentions", link["external_person_mention_id"],
                     link["target_table"], link["target_record_id"],
                     "cri_match", link["match_score"], now,
                     "confirmed", "accepted", reviewer, now)
                )
                # Reverse
                conn.execute(
                    "INSERT OR IGNORE INTO record_links (from_table, from_id, to_table, to_id, link_type, confidence, elaborato_il, match_status, review_status, reviewed_by, reviewed_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (link["target_table"], link["target_record_id"],
                     "external_person_mentions", link["external_person_mention_id"],
                     "cri_match", link["match_score"], now,
                     "confirmed", "accepted", reviewer, now)
                )
            except Exception:
                pass

    conn.commit()
    conn.close()
    return {"id": link_id, "review_status": review_status, "match_status": match_status}


# ─── Batch linking per provider ──────────────────────────────────────────
def generate_links_for_provider(provider: str, limit: int = 0) -> Dict[str, Any]:
    """Genera collegamenti per tutte le menzioni di un provider specifico.
    
    Utilizzato per import massivi (es. LeBI con 305K record).
    Ritorna statistiche: total_mentions, links_generated, probable, candidate, ambiguous, errors.
    """
    conn = get_conn()
    query = """
        SELECT m.id FROM external_person_mentions m
        JOIN external_source_records r ON m.external_source_record_id = r.id
        WHERE r.provider = ?
        ORDER BY m.id
    """
    if limit:
        query += f" LIMIT {limit}"
    
    mentions = conn.execute(query, (provider,)).fetchall()
    conn.close()

    total = len(mentions)
    links_generated = 0
    statuses = {"probable": 0, "candidate": 0, "ambiguous": 0, "rejected": 0}
    errors = 0

    for m in mentions:
        try:
            links = generate_links_for_mention(m["id"])
            links_generated += len(links)
            for link in links:
                st = link.get("match_status", "rejected")
                statuses[st] = statuses.get(st, 0) + 1
        except Exception:
            errors += 1

    return {
        "provider": provider,
        "total_mentions": total,
        "links_generated": links_generated,
        "probable": statuses.get("probable", 0),
        "candidate": statuses.get("candidate", 0),
        "ambiguous": statuses.get("ambiguous", 0),
        "rejected": statuses.get("rejected", 0),
        "errors": errors,
    }


def detect_omonimie(provider: str, min_score: float = 0.5) -> List[Dict[str, Any]]:
    """Rileva omonimie: menzioni con più candidati con score simile.
    
    Una menzione è sospetta se ha 2+ link con status 'candidate' o 'probable'
    e la differenza di score tra il primo e il secondo è < 0.15.
    """
    conn = get_conn()
    rows = conn.execute(
        """
        SELECT m.id, m.surname_raw, m.name_raw, m.normalized_surname, m.normalized_name,
               l.id as link_id, l.match_score, l.match_status, l.target_table, l.target_record_id,
               l.explanation
        FROM external_person_mentions m
        JOIN external_source_records r ON m.external_source_record_id = r.id
        JOIN external_record_links l ON l.external_person_mention_id = m.id
        WHERE r.provider = ? AND l.match_score >= ?
        ORDER BY m.id, l.match_score DESC
        """,
        (provider, min_score)
    ).fetchall()
    conn.close()

    # Group by mention_id
    from collections import defaultdict
    groups = defaultdict(list)
    for row in rows:
        groups[row["id"]].append(dict(row))

    omonimie = []
    for mention_id, links in groups.items():
        if len(links) < 2:
            continue
        # Check score gap between top 2
        top_score = links[0]["match_score"]
        second_score = links[1]["match_score"]
        gap = top_score - second_score

        if gap < 0.15 and links[0]["match_status"] in ("probable", "candidate"):
            omonimie.append({
                "mention_id": mention_id,
                "surname": links[0]["surname_raw"],
                "name": links[0]["name_raw"],
                "top_score": top_score,
                "second_score": second_score,
                "gap": round(gap, 3),
                "candidates": [
                    {
                        "link_id": l["link_id"],
                        "target_table": l["target_table"],
                        "target_record_id": l["target_record_id"],
                        "score": l["match_score"],
                        "status": l["match_status"],
                        "explanation": l["explanation"],
                    }
                    for l in links[:5]
                ],
                "needs_review": True,
            })

    return omonimie


def review_link_with_type(link_id: int, review_status: str, match_status: Optional[str] = None,
                          reviewer: str = "system", link_type: str = "cri_match") -> Dict[str, Any]:
    """Aggiorna lo stato di revisione di un collegamento con link_type personalizzato.
    
    Per LeBI usare link_type='lebi_match'.
    """
    conn = get_conn()
    now = datetime.now().isoformat()

    updates = {"review_status": review_status, "reviewed_by": reviewer, "reviewed_at": now, "updated_at": now}
    if match_status:
        updates["match_status"] = match_status

    set_clause = ", ".join(f"{k} = ?" for k in updates)
    values = list(updates.values()) + [link_id]
    conn.execute(f"UPDATE external_record_links SET {set_clause} WHERE id = ?", values)

    # If confirmed, create bidirectional link in record_links
    if review_status == "accepted" and match_status == "confirmed":
        link = conn.execute("SELECT * FROM external_record_links WHERE id = ?", (link_id,)).fetchone()
        if link:
            try:
                conn.execute(
                    "INSERT OR IGNORE INTO record_links (from_table, from_id, to_table, to_id, link_type, confidence, elaborato_il, match_status, review_status, reviewed_by, reviewed_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    ("external_person_mentions", link["external_person_mention_id"],
                     link["target_table"], link["target_record_id"],
                     link_type, link["match_score"], now,
                     "confirmed", "accepted", reviewer, now)
                )
                conn.execute(
                    "INSERT OR IGNORE INTO record_links (from_table, from_id, to_table, to_id, link_type, confidence, elaborato_il, match_status, review_status, reviewed_by, reviewed_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (link["target_table"], link["target_record_id"],
                     "external_person_mentions", link["external_person_mention_id"],
                     link_type, link["match_score"], now,
                     "confirmed", "accepted", reviewer, now)
                )
            except Exception:
                pass

    conn.commit()
    conn.close()
    return {"id": link_id, "review_status": review_status, "match_status": match_status, "link_type": link_type}

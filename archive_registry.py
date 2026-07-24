"""Archive Registry — registro unificato delle fonti storiche.

Ogni fonte dichiara le proprie capabilities, periodi, aree, tipi di entita',
modalita' di accesso e affidabilita'. Il motore seleziona dinamicamente
le fonti in base agli indizi raccolti.

Riutilizza e estende il registry esistente in source_providers/federation.py
senza duplicarlo: i provider esistenti vengono importati come
archive_connectors con le loro meta-capabilities.
"""
import json
from datetime import datetime
from typing import Dict, List, Optional

from database import get_conn


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


# ═══ SEED FROM EXISTING PROVIDERS ══════════════════════════════════════════

def seed_from_federation():
    """Importa i provider esistenti da federation.py in archive_connectors.

    Idempotente: usa INSERT OR IGNORE su code.
    """
    from source_providers.federation import get_registry
    reg = get_registry()
    conn = get_conn()
    now = _now()

    for name, provider in reg.items():
        code = name.lower().replace(" ", "_").replace(".", "_")
        existing = conn.execute(
            "SELECT id FROM archive_connectors WHERE code=?", (code,)
        ).fetchone()
        if existing:
            continue

        # Determina integration_type e access_mode dal provider
        caps = provider.authorized_domains
        has_search = hasattr(provider, "search")
        has_get_doc = hasattr(provider, "get_document")

        if has_search and has_get_doc:
            integration_type = "full_api"
            access_mode = "auto"
        elif has_search:
            integration_type = "metadata_only"
            access_mode = "auto"
        else:
            integration_type = "metadata_only"
            access_mode = "assisted"

        conn.execute(
            """INSERT OR IGNORE INTO archive_connectors (
                code, name, scope, integration_type, capabilities_json,
                access_mode, authority_score, languages, status,
                config_json, version, created_at, updated_at
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (code, provider.display_name or provider.name,
             provider.archive_name or provider.country or "",
             integration_type,
             json.dumps({
                 "search": has_search,
                 "get_metadata": hasattr(provider, "get_metadata"),
                 "get_document": has_get_doc,
                 "authorized_domains": list(caps),
                 "base_url": provider.base_url,
             }),
             access_mode,
             0.5,  # default authority
             "",
             "active",
             json.dumps({"provider_class": type(provider).__name__}),
             "1.0", now, now)
        )
    conn.commit()
    conn.close()


# ═══ CRUD ═════════════════════════════════════════════════════════════════

def list_connectors(status: str = "active") -> List[Dict]:
    """Lista tutti i connector registrati."""
    conn = get_conn()
    rows = conn.execute(
        "SELECT * FROM archive_connectors WHERE status=? ORDER BY authority_score DESC, name",
        (status,)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_connector(code: str) -> Optional[Dict]:
    """Recupera un connector per code."""
    conn = get_conn()
    row = conn.execute(
        "SELECT * FROM archive_connectors WHERE code=?", (code,)
    ).fetchone()
    conn.close()
    return dict(row) if row else None


def get_connector_capabilities(code: str) -> Dict:
    """Recupera le capabilities di un connector."""
    c = get_connector(code)
    if not c:
        return {"error": "connector not found"}
    caps = json.loads(c.get("capabilities_json") or "{}")
    return {
        "code": code,
        "name": c["name"],
        "integration_type": c.get("integration_type"),
        "access_mode": c.get("access_mode"),
        "capabilities": caps,
        "authority_score": c.get("authority_score"),
        "status": c.get("status"),
        "last_verified_at": c.get("last_verified_at"),
    }


def health_check_connector(code: str) -> Dict:
    """Verifica lo stato di un connector."""
    c = get_connector(code)
    if not c:
        return {"ok": False, "error": "connector not found"}

    # Per i provider importati da federation, usa il provider reale
    from source_providers.federation import get_provider
    provider = get_provider(code.replace("_", " ").title())

    now = _now()
    conn = get_conn()
    conn.execute(
        "UPDATE archive_connectors SET last_verified_at=? WHERE code=?",
        (now, code)
    )
    conn.commit()
    conn.close()

    if provider:
        return {
            "ok": True,
            "code": code,
            "name": c["name"],
            "has_search": hasattr(provider, "search"),
            "has_get_metadata": hasattr(provider, "get_metadata"),
            "has_get_document": hasattr(provider, "get_document"),
            "last_verified_at": now,
        }
    return {
        "ok": c.get("status") == "active",
        "code": code,
        "name": c["name"],
        "last_verified_at": now,
    }


# ═══ DYNAMIC SOURCE SELECTION ═════════════════════════════════════════════

def recommend_sources(
    entity_type: str,
    context: Dict,
    clues: List[str] = None,
    gaps: List[str] = None,
    max_results: int = 10,
) -> List[Dict]:
    """Seleziona dinamicamente le fonti piu' pertinenti.

    Criteri:
    - tipo di entita' (persona, evento, luogo, reparto, ...)
    - periodo storico
    - area geografica
    - nazionalita'
    - tipo di informazione mancante (gaps)
    - indizi gia' raccolti (clues)
    - probabilita' attesa di trovare un dato utile
    - qualita' e indipendenza della fonte
    """
    conn = get_conn()
    connectors = conn.execute(
        "SELECT * FROM archive_connectors WHERE status='active' ORDER BY authority_score DESC"
    ).fetchall()
    conn.close()

    period = context.get("period", "")
    geography = context.get("geography", "")
    nationality = context.get("nationality", "")
    war = context.get("war", "")

    scored = []
    for c in connectors:
        c = dict(c)
        score = 0.0
        reasons = []

        # Match entity_type
        entity_types = (c.get("entity_types") or "").lower()
        if entity_type and entity_type.lower() in entity_types:
            score += 0.3
            reasons.append(f"entity_type_match: {entity_type}")

        # Match period
        historical_periods = (c.get("historical_periods") or "").lower()
        if period:
            if period.lower() in historical_periods:
                score += 0.2
                reasons.append(f"period_match: {period}")
            elif "ww2" in period.lower() and "ww2" in historical_periods:
                score += 0.2
                reasons.append("ww2_match")
            elif "ww1" in period.lower() and "ww1" in historical_periods:
                score += 0.2
                reasons.append("ww1_match")

        # Match geography
        geo_areas = (c.get("geographic_areas") or "").lower()
        if geography and geography.lower() in geo_areas:
            score += 0.15
            reasons.append(f"geography_match: {geography}")

        # Authority score
        authority = c.get("authority_score", 0.5)
        score += authority * 0.2
        reasons.append(f"authority={authority}")

        # Access mode bonus (auto > assisted)
        if c.get("access_mode") == "auto":
            score += 0.1
            reasons.append("auto_access")

        # Gap-specific bonus
        if gaps:
            doc_types = (c.get("document_types") or "").lower()
            for gap in gaps:
                if gap.lower() in doc_types:
                    score += 0.1
                    reasons.append(f"gap_coverage: {gap}")

        # Clue-specific bonus
        if clues:
            scope = (c.get("scope") or "").lower()
            for clue in clues:
                if clue.lower() in scope:
                    score += 0.05
                    reasons.append(f"clue_match: {clue}")

        scored.append({
            "code": c["code"],
            "name": c["name"],
            "score": round(score, 4),
            "reasons": reasons,
            "access_mode": c.get("access_mode"),
            "integration_type": c.get("integration_type"),
            "authority_score": authority,
        })

    scored.sort(key=lambda x: x["score"], reverse=True)
    return scored[:max_results]


# ═══ UPDATE ═══════════════════════════════════════════════════════════════

def update_connector(code: str, updates: Dict) -> Dict:
    """Aggiorna un connector."""
    conn = get_conn()
    now = _now()
    c = conn.execute(
        "SELECT id FROM archive_connectors WHERE code=?", (code,)
    ).fetchone()
    if not c:
        conn.close()
        return {"error": "connector not found"}

    allowed = {"scope", "historical_periods", "geographic_areas", "entity_types",
               "document_types", "integration_type", "access_mode", "authority_score",
               "reliability_criteria", "provenance_group", "languages", "cost_priority",
               "status", "terms_limitations", "config_json", "capabilities_json"}
    sets = []
    params = []
    for k, v in updates.items():
        if k in allowed:
            if k.endswith("_json") and isinstance(v, (dict, list)):
                v = json.dumps(v)
            sets.append(f"{k}=?")
            params.append(v)
    if not sets:
        conn.close()
        return {"error": "no valid fields"}
    sets.append("updated_at=?")
    params.append(now)
    params.append(code)
    conn.execute(
        f"UPDATE archive_connectors SET {', '.join(sets)} WHERE code=?", params
    )
    conn.commit()
    conn.close()
    return {"ok": True, "code": code}

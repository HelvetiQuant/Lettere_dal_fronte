"""Research Next Step Planner — conditional, not generic.

Replaces the V4 deterministic report's hardcoded ICRC suggestion for all targets.
Next steps depend on:
- Subject type (WWI fallen, WWII/IMI, unknown)
- Origin record state (PRESENT_LOCAL, ABSENT)
- Identity resolution (UNRESOLVED, PARTIAL, RESOLVED)
- External corroboration (NONE, PARTIAL, ACCEPTED, CONFLICTING)
- Research goal (identification, biographical enrichment, burial, captivity)

Rules:
- ICRC only if captivity/internment/displacement is a research goal or claim
- Fogli matricolari via comune → distretto → Archivio di Stato mapping
- AUSSME for unit diaries and operational history when pertinent
- Onorcaduti/cemeteries only for burial research goal
- IMI/LeBI/ANRP only for WWII/IMI compatible subjects
- No foreign source without geographic, military, or detention reason
"""
from __future__ import annotations

from typing import Dict, List


def plan_next_steps(
    target: Dict,
    origin: Dict,
    identity_resolution: str,
    external_corroboration: str,
) -> List[Dict]:
    """Plan conditional next steps based on target and evidence state.

    Args:
        target: TargetIdentity dict with conflict, display_name, etc.
        origin: OriginRecord dict with presence, provenance
        identity_resolution: UNRESOLVED | PARTIAL | RESOLVED
        external_corroboration: NONE | PARTIAL | ACCEPTED | CONFLICTING

    Returns:
        List of next step dicts, ordered by priority
    """
    steps = []
    conflict = target.get("conflict", "UNKNOWN")
    origin_presence = origin.get("presence", "ABSENT")
    origin_provenance = origin.get("provenance", "UNVERIFIED")

    # ── Step 1: Verify origin lineage if present but unverified ──
    if origin_presence == "PRESENT_LOCAL" and origin_provenance == "UNVERIFIED":
        steps.append({
            "step_id": "verify_origin_lineage",
            "action": "Verificare la lineage del record d'origine (URL completo, base URL, identificativo archivistico)",
            "condition": "origin.presence=PRESENT_LOCAL, origin.provenance=UNVERIFIED",
            "priority": 1,
            "source_type": "archive",
            "authority_id": "",
        })

    # ── Step 2: Fogli matricolari via Archivio di Stato ──
    birth_place = target.get("assertions", [])
    has_birth_place = any(a.get("field_name") == "birth_place" and a.get("object_value") for a in birth_place)
    if has_birth_place or origin_presence == "PRESENT_LOCAL":
        steps.append({
            "step_id": "fogli_matricolari",
            "action": "Consultare l'Archivio di Stato territorialmente competente per fogli e ruoli matricolari",
            "condition": "birth_place known or origin record present — military records needed",
            "priority": 2,
            "source_type": "archive",
            "authority_id": "archive_jurisdiction_registry",
        })

    # ── Step 3: AUSSME for unit diaries ──
    unit_claims = [a for a in birth_place if a.get("field_name") == "unit" and a.get("object_value")]
    if unit_claims:
        steps.append({
            "step_id": "aussme_unit_diaries",
            "action": "Consultare l'Archivio dell'Ufficio Storico dello Stato Maggiore dell'Esercito (AUSSME) per diari di reparto e carteggi operativi",
            "condition": "unit known — operational history pertinent",
            "priority": 3,
            "source_type": "archive",
            "authority_id": "aussme",
        })

    # ── Step 4: ICRC only if captivity/internment is relevant ──
    captivity_relevant = (
        conflict in ("WWII", "WWII_IMI")
        or any(a.get("field_name") == "captivity" and a.get("object_value") for a in birth_place)
        or any(a.get("field_name") == "captivity" for a in birth_place if a.get("is_conditional_gap"))
    )
    if captivity_relevant:
        steps.append({
            "step_id": "icrc_captivity",
            "action": "Verificare presso l'ICRC (Archivio Arolsen / CIRC) per schede di prigionia e internamento",
            "condition": "captivity/internment relevant (WWII/IMI subject or captivity claim present)",
            "priority": 4,
            "source_type": "database",
            "authority_id": "icrc",
        })

    # ── Step 5: Onorcaduti for burial research ──
    burial_relevant = (
        any(a.get("field_name") == "burial" and not a.get("object_value") for a in birth_place)
        or conflict in ("WWI", "WWII")
    )
    if burial_relevant and conflict in ("WWI", "WWII"):
        steps.append({
            "step_id": "onorcaduti_burial",
            "action": "Consultare Onorcaduti per luogo di sepoltura e sacrario (senza suggerire un sacrario specifico non supportato)",
            "condition": "burial gap and conflict is WWI or WWII",
            "priority": 5,
            "source_type": "database",
            "authority_id": "onorcaduti",
        })

    # ── Step 6: IMI/LeBI/ANRP only for WWII/IMI ──
    if conflict in ("WWII", "WWII_IMI"):
        steps.append({
            "step_id": "lebi_anrp",
            "action": "Consultare LeBI (Lessico Biografico degli IMI — ANRP) per scheda biografica dell'internato",
            "condition": "WWII/IMI subject — LeBI/ANRP compatible",
            "priority": 6,
            "source_type": "database",
            "authority_id": "lebi",
        })

    # ── Step 7: External corroboration if NONE ──
    if external_corroboration == "NONE" and identity_resolution in ("PARTIAL", "RESOLVED"):
        steps.append({
            "step_id": "external_corroboration",
            "action": "Cercare una seconda fonte indipendente per corroborare l'identificazione",
            "condition": "identity partially/fully resolved but no external corroboration",
            "priority": 7,
            "source_type": "web",
            "authority_id": "",
        })

    # ── Step 8: Identity resolution if UNRESOLVED ──
    if identity_resolution == "UNRESOLVED":
        steps.append({
            "step_id": "identity_resolution",
            "action": "Approfondire la ricerca identitaria: verificare dati anagrafici, paternita e compatibilita temporale",
            "condition": "identity_resolution=UNRESOLVED",
            "priority": 8,
            "source_type": "archive",
            "authority_id": "",
        })

    return steps

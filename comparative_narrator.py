"""Comparative Narrator — Generates faction narratives + common ground + divergence narration.

Pipeline:
FactionBundle A → faction narrative
FactionBundle B → faction narrative
NeutralBundle → neutral narrative
CommonFacts → common ground narrative
Divergences → divergence narration
↓
ComparativeNarrator synthesizes all into structured output

Key principles:
- AI receives pre-structured bundles, NOT raw sources to compare
- AI does NOT decide faction assignment, claim equivalence, or independence
- AI does NOT resolve divergences by intuition
- AI does NOT choose "who is right"
- Common ground uses only CROSS_FACTION_CONFIRMED and CROSS_FACTION_COMPATIBLE
- Divergences are preserved, not averaged
"""
from __future__ import annotations

import json
from typing import Any, Optional

from viewpoint_models import (
    FactionBundle,
    CommonFact,
    CommonFactStatus,
    Divergence,
    DivergenceType,
    Omission,
    OmissionStatus,
    ClaimNature,
    ViewpointResult,
    EventPhase,
)


_SYSTEM_PROMPT = (
    "Sei uno storico specializzato in ricostruzione comparata di eventi bellici del '900. "
    "Il tuo compito è produrre narrazioni evidence-locked a partire da bundle pre-strutturati. "
    "\nREGOLE FONDAMENTALI:\n"
    "1. Non inventare dati. Usa solo le informazioni nei bundle forniti.\n"
    "2. Non scegliere 'chi ha ragione'. Il tuo compito è rappresentare, non giudicare.\n"
    "3. Non mediare valori divergenti. Se le fonti dicono 10.000 e 18.000, riporta entrambi.\n"
    "4. Non trasformare una divergenza in un fatto condiviso.\n"
    "5. Distingui fatti osservabili da interpretazioni.\n"
    "6. Se una fazione non menziona un fatto, scrivi 'non menzionato', non 'negato'.\n"
    "7. Conserva la terminologia originale delle fonti quando significativa.\n"
    "8. Cita le fonti con [ID] tra parentesi quadre.\n"
    "9. Per la ricostruzione comune, usa solo fatti CROSS_FACTION_CONFIRMED o COMPATIBLE.\n"
    "10. Per le divergenze, mostra le posizioni di entrambe le fazioni con le rispettive fonti.\n"
)

def _build_faction_prompt(bundle: FactionBundle) -> str:
    """Build a prompt for a single faction narrative."""
    lines = [
        f"=== RICOSTRUZIONE SECONDO LA FAZIONE: {bundle.faction_alignment.value} ===",
        f"Fonti: {bundle.raw_source_count} (lineage indipendenti: {bundle.independent_lineage_count})",
        "",
        "CLAIM DOCUMENTALI:",
    ]

    for claim in bundle.claims:
        nature_label = ""
        if claim.claim_nature == ClaimNature.INTERPRETATION:
            nature_label = " [INTERPRETAZIONE]"
        elif claim.claim_nature == ClaimNature.CAUSAL_INTERPRETATION:
            nature_label = " [INTERPRETAZIONE CAUSALE]"
        elif claim.claim_nature == ClaimNature.ATTRIBUTION:
            nature_label = " [ATTRIBUZIONE]"

        lines.append(
            f"- {claim.predicate}: {claim.value}{nature_label} "
            f"[fonti: {', '.join(claim.source_ids)}]"
        )

    lines.append("")
    lines.append("MODELLO EVENTO:")
    for key, val in bundle.event_model.items():
        if val:
            lines.append(f"  {key}: {val}")

    lines.append("")
    lines.append("Produce una narrazione evidence-locked in italiano per questa fazione.")
    lines.append("Mantieni la terminologia originale. Non aggiungere interpretazioni.")
    lines.append("Distingui fatti da interpretazioni con etichette esplicite.")

    return "\n".join(lines)


def _build_common_ground_prompt(common_facts: list[CommonFact]) -> str:
    """Build prompt for common ground reconstruction."""
    confirmed = [f for f in common_facts if f.status == CommonFactStatus.CROSS_FACTION_CONFIRMED]
    compatible = [f for f in common_facts if f.status == CommonFactStatus.CROSS_FACTION_COMPATIBLE]

    lines = [
        "=== RICOSTRUZIONE COMUNE ===",
        f"Fatti confermati cross-faction: {len(confirmed)}",
        f"Fatti compatibili cross-faction: {len(compatible)}",
        "",
        "FATTI CONFERMATI (CROSS_FACTION_CONFIRMED):",
    ]

    for f in confirmed:
        lines.append(
            f"- {f.predicate}: {f.normalized_value} "
            f"(fazioni: {', '.join(f.supporting_factions)}, "
            f"lineage indipendenti: {f.independent_lineage_count})"
        )

    lines.append("")
    lines.append("FATTI COMPATIBILI (CROSS_FACTION_COMPATIBLE):")
    for f in compatible:
        lines.append(
            f"- {f.predicate}: {f.normalized_value} "
            f"(fazioni: {', '.join(f.supporting_factions)})"
        )

    lines.append("")
    lines.append("Produce una RICOSTRUZIONE COMUNE che utilizza solo i fatti sopra elencati.")
    lines.append("NON forzare conclusioni su punti controversi.")
    lines.append("NON includere fatti SINGLE_PERSPECTIVE o in conflitto.")
    lines.append("Se un'informazione manca, scrivi 'non documentato in modo cross-faction'.")

    return "\n".join(lines)


def _build_divergence_prompt(divergences: list[Divergence]) -> str:
    """Build prompt for divergence narration."""
    lines = [
        "=== DIVERGENZE ===",
        f"Totale divergenze: {len(divergences)}",
        "",
    ]

    for div in divergences:
        lines.append(f"Divergenza {div.divergence_id} ({div.divergence_type.value}):")
        lines.append(f"  Predicato: {div.predicate}")
        lines.append(f"  Natura: {div.claim_nature.value}")
        for pos in div.faction_positions:
            lines.append(
                f"  Fazione {pos['faction']}: {pos['value']} "
                f"[fonti: {', '.join(pos.get('source_ids', []))}] "
                f"(confidenza: {pos.get('confidence', 0):.2f})"
            )
        lines.append(f"  Risoluzione: {div.resolution.value}")
        if div.resolution_reason:
            lines.append(f"  Ragione: {div.resolution_reason}")
        lines.append("")

    lines.append("Produce una narrazione delle divergenze che:")
    lines.append("- Mostra le posizioni di ogni fazione con le rispettive fonti")
    lines.append("- NON media e NON sceglie chi ha ragione")
    lines.append("- Per le perdite: riporta entrambe le cifre come DISPUTED_QUANTIFICATION")
    lines.append("- Per le interpretazioni: le etichetta come prospettive attribuite")
    lines.append("- Per le omissioni: distingue 'non menzionato' da 'negato'")

    return "\n".join(lines)


def _build_omission_prompt(omissions: list[Omission]) -> str:
    """Build prompt for omission narration."""
    lines = [
        "=== OMISSIONI ASIMMETRICHE ===",
        f"Totale omissioni: {len(omissions)}",
        "",
    ]

    for om in omissions:
        lines.append(f"Omissione {om.omission_id}:")
        lines.append(f"  Predicato: {om.predicate}")
        lines.append(f"  Fazione che menziona: {om.mentioning_faction}")
        lines.append(f"  Fazioni silenziose: {', '.join(om.silent_factions)}")
        lines.append(f"  Status: {om.status.value}")
        lines.append(f"  Nota: {om.note}")
        lines.append("")

    lines.append("Produce una narrazione delle omissioni che:")
    lines.append("- Distingue 'non menzionato' da 'negato' da 'contraddetto'")
    lines.append("- NON interpreta il silenzio come negazione")
    lines.append("- Indica quale fazione non menziona e quale menziona")
    lines.append("- Specifica se il silenzio può essere dovuto a corpus incompleto")

    return "\n".join(lines)


def generate_faction_narrative(bundle: FactionBundle) -> str:
    """Generate a deterministic narrative for a single faction.

    This is a deterministic fallback. AI generation is optional.
    """
    lines = [
        f"## Ricostruzione secondo la prospettiva {bundle.faction_alignment.value}",
        "",
        f"**Fonti utilizzate:** {bundle.raw_source_count} "
        f"({bundle.independent_lineage_count} lineage indipendenti)",
        "",
    ]

    model = bundle.event_model

    if model.get("event_identification"):
        lines.append(f"**Identificazione evento:** {model['event_identification']}")
    if model.get("chronology"):
        chron = model["chronology"]
        if chron.get("start_date"):
            lines.append(f"**Data inizio:** {chron['start_date']}")
        if chron.get("end_date"):
            lines.append(f"**Data fine:** {chron['end_date']}")
    if model.get("locations"):
        lines.append(f"**Località:** {', '.join(model['locations'])}")
    if model.get("units"):
        lines.append(f"**Reparti:** {', '.join(model['units'])}")
    if model.get("objectives"):
        lines.append(f"**Obiettivi dichiarati:** {'; '.join(model['objectives'])}")
    if model.get("movements"):
        lines.append(f"**Movimenti:** {'; '.join(model['movements'])}")
    if model.get("casualties", {}).get("values"):
        lines.append(f"**Perdite dichiarate:** {', '.join(model['casualties']['values'])}")
    if model.get("declared_results"):
        lines.append(f"**Risultati dichiarati:** {model['declared_results']}")
    if model.get("attributed_causes"):
        lines.append(f"**Cause attribuite:** {'; '.join(model['attributed_causes'])}")
        lines.append("  *(Queste sono interpretazioni attribuite, non fatti osservabili)*")
    if model.get("consequences"):
        lines.append(f"**Conseguenze:** {'; '.join(model['consequences'])}")
    if model.get("terminology"):
        terms = [t["term"] for t in model["terminology"]]
        lines.append(f"**Terminologia utilizzata:** {', '.join(terms)}")

    lines.append("")
    lines.append("---")
    return "\n".join(lines)


def generate_common_ground_narrative(common_facts: list[CommonFact]) -> str:
    """Generate the common ground reconstruction narrative.

    Uses ONLY CROSS_FACTION_CONFIRMED and CROSS_FACTION_COMPATIBLE facts.
    Does NOT force conclusions on controversial points.
    """
    confirmed = [f for f in common_facts if f.status == CommonFactStatus.CROSS_FACTION_CONFIRMED]
    compatible = [f for f in common_facts if f.status == CommonFactStatus.CROSS_FACTION_COMPATIBLE]

    lines = [
        "## Ricostruzione comune",
        "",
        "*Questa sezione è costruita esclusivamente sull'intersezione dei fatti "
        "confermati o compatibili tra fazioni indipendenti.*",
        "",
    ]

    if not confirmed and not compatible:
        lines.append("*Non sono stati identificati fatti comuni tra le fazioni documentate. "
                     "Le divergenze tra le versioni sono riportate nella sezione dedicata.*")
        return "\n".join(lines)

    if confirmed:
        lines.append("### Fatti confermati da fonti indipendenti contrapposte")
        lines.append("")
        for f in confirmed:
            lines.append(
                f"- **{f.predicate}**: {f.normalized_value} "
                f"(confermato da {', '.join(f.supporting_factions)}, "
                f"{f.independent_lineage_count} lineage indipendenti)"
            )
        lines.append("")

    if compatible:
        lines.append("### Fatti compatibili tra fazioni")
        lines.append("")
        for f in compatible:
            lines.append(
                f"- **{f.predicate}**: {f.normalized_value} "
                f"(compatibile tra {', '.join(f.supporting_factions)})"
            )
        lines.append("")

    # Synthesis paragraph
    lines.append("### Sintesi")
    lines.append("")

    # Build a narrative summary
    summary_parts = []
    for f in confirmed[:5]:
        summary_parts.append(f"{f.predicate}: {f.normalized_value}")

    if summary_parts:
        lines.append(
            "Le fonti appartenenti a prospettive contrapposte concordano sui seguenti elementi: "
            + "; ".join(summary_parts) + ". "
        )

    # Note about what's NOT in common ground
    conflict_count = sum(1 for f in common_facts if f.status == CommonFactStatus.CROSS_FACTION_CONFLICT)
    single_count = sum(1 for f in common_facts if f.status == CommonFactStatus.SINGLE_PERSPECTIVE)

    if conflict_count or single_count:
        lines.append(
            f"Per {conflict_count} elementi le fonti divergono (vedi sezione 'Divergenze'). "
            f"Per {single_count} elementi è disponibile una sola prospettiva."
        )

    lines.append("")
    lines.append("---")
    return "\n".join(lines)


def generate_divergence_narrative(divergences: list[Divergence]) -> str:
    """Generate narrative for divergences."""
    lines = [
        "## Divergenze",
        "",
        f"*{len(divergences)} divergenze identificate tra le fazioni documentate.*",
        "",
    ]

    for div in divergences:
        lines.append(f"### {div.predicate} — {div.divergence_type.value}")
        lines.append("")

        for pos in div.faction_positions:
            nature_label = ""
            if pos.get("claim_nature") == "INTERPRETATION":
                nature_label = " *[interpretazione]*"
            elif pos.get("claim_nature") == "CAUSAL_INTERPRETATION":
                nature_label = " *[interpretazione causale]*"

            lines.append(
                f"- **{pos['faction']}**: {pos['value']}{nature_label} "
                f"[fonti: {', '.join(pos.get('source_ids', []))}]"
            )

        lines.append(f"- **Status**: {div.resolution.value}")
        if div.resolution_reason:
            lines.append(f"  - {div.resolution_reason}")
        if div.note:
            lines.append(f"- {div.note}")
        lines.append("")

    lines.append("---")
    return "\n".join(lines)


_OMISSION_STATUS_IT = {
    "NOT_MENTIONED": "non menzionato",
    "DENIED": "negato esplicitamente",
    "CONTRADICTED": "contraddetto",
    "SOURCE_UNAVAILABLE": "fonte non disponibile",
    "CORPUS_INCOMPLETE": "corpus incompleto",
}


def generate_omission_narrative(omissions: list[Omission]) -> str:
    """Generate narrative for omissions."""
    if not omissions:
        return ""

    lines = [
        "## Cosa una parte racconta e l'altra non menziona",
        "",
    ]

    for om in omissions:
        status_it = _OMISSION_STATUS_IT.get(om.status.value, om.status.value)
        lines.append(f"### {om.predicate}")
        lines.append(f"- **{om.mentioning_faction}** menziona: {om.mentioning_claim.get('value', '')}")
        lines.append(f"- **{', '.join(om.silent_factions)}**: {status_it}")
        lines.append(f"  - {om.note}")
        lines.append("")

    lines.append("*Il silenzio di una fonte non equivale a negazione. "
                 "Può indicare che l'episodio non era noto, non era rilevante per quella prospettiva, "
                 "o che la fonte non è disponibile.*")
    lines.append("")
    lines.append("---")
    return "\n".join(lines)


def try_ai_narration(
    bundles: list[FactionBundle],
    common_facts: list[CommonFact],
    divergences: list[Divergence],
    omissions: list[Omission],
    event_name: str,
) -> Optional[dict[str, str]]:
    """Attempt AI-generated narratives. Returns None if AI unavailable.

    The AI receives pre-structured bundles and synthesizes narratives.
    It does NOT decide faction assignment, equivalence, or independence.
    """
    try:
        from ai_client import call_ai
    except ImportError:
        return None

    # Build the full prompt
    prompt_parts = [
        f"EVENTO: {event_name}",
        "",
    ]

    for bundle in bundles:
        prompt_parts.append(_build_faction_prompt(bundle))
        prompt_parts.append("")

    prompt_parts.append(_build_common_ground_prompt(common_facts))
    prompt_parts.append("")
    prompt_parts.append(_build_divergence_prompt(divergences))
    prompt_parts.append("")
    prompt_parts.append(_build_omission_prompt(omissions))

    prompt_parts.append("")
    prompt_parts.append("Produce in italiano:")
    prompt_parts.append("1. Una narrazione per ogni fazione (evidence-locked)")
    prompt_parts.append("2. Una ricostruzione comune (solo fatti cross-faction)")
    prompt_parts.append("3. Una narrazione delle divergenze")
    prompt_parts.append("4. Una narrazione delle omissioni")
    prompt_parts.append("")
    prompt_parts.append("Separa ogni sezione con '===SEZIONE: [nome]==='")

    full_prompt = "\n".join(prompt_parts)

    try:
        result = call_ai(
            "generate_viewpoints",
            _SYSTEM_PROMPT,
            full_prompt,
            max_tokens=4000,
            temperature=0.1,
            strategy="quality_max",
        )
        if result.get("ok"):
            text = result.get("text", "")
            # Parse sections
            sections = {}
            current_section = "all"
            current_lines = []

            for line in text.split("\n"):
                if line.startswith("===SEZIONE:"):
                    if current_lines:
                        sections[current_section] = "\n".join(current_lines)
                    current_section = line.replace("===SEZIONE:", "").replace("===", "").strip().lower()
                    current_lines = []
                else:
                    current_lines.append(line)

            if current_lines:
                sections[current_section] = "\n".join(current_lines)

            return {
                "used": True,
                "provider": result.get("provider"),
                "model": result.get("model"),
                "sections": sections,
            }
    except Exception:
        pass

    return None

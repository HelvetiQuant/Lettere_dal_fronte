"""V7.3 Conversational Renderer — genera testo narrativo reale dai SelectedClaim.

Produce risposte conversazionali in italiano, strutturate per blocchi,
con citazioni (source_id only), livelli di certezza, e note su limiti/coverage.

Per PERSON: narrazione biografica cronologica
Per EVENT: narrazione stratificata per dimensioni

Il renderer è deterministico — non usa AI. Costruisce il testo dai claim
selezionati, con frasi template che rispettono i livelli di certezza.
"""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import List, Optional, Dict, Any
from dataclasses import dataclass

from domain_model_v73 import (
    Claim, ClaimStatus, Evidence, IdentityCandidate, IdentityStatus,
    WarPeriod,
)
from narration_planner_v73 import (
    SelectedClaim, NarrationPlan, NarrationBlock, CoverageReport,
    ClaimSelector, CoveragePlanner, NarrationPlanner,
    SemanticValidator, GlobalValidator,
    PERSON_CLAIM_FIELDS, EVENT_CLAIM_FIELDS,
)

DB_MAIN = Path(__file__).parent / "imi_internati.db"


# ─── Certainty to Italian phrasing ──────────────────────────────────────────

CERTAINTY_PHRASING = {
    "CONFIRMED": "documentato",
    "PROBABLE": "probabilmente",
    "POSSIBLE": "forse",
    "UNCERTAIN": "non verificato",
    "CONTRADICTED": "contraddittorio",
}

CERTAINTY_PREFIX = {
    "CONFIRMED": "",
    "PROBABLE": "",
    "POSSIBLE": "Secondo le informazioni disponibili, ",
    "UNCERTAIN": "Non è stato possibile verificare ",
    "CONTRADICTED": "Esistono informazioni contraddittorie su ",
}

# ─── Predicate to Italian description ───────────────────────────────────────

PREDICATE_LABELS = {
    "born_at": "nato il",
    "born_in": "nato a",
    "resided_in": "residente a",
    "enlisted_in": "arruolato in",
    "served_in": "ha servito nel",
    "captured_at": "catturato a",
    "captured_in": "catturato in",
    "interned_at": "internato a",
    "interned_in": "internato a",
    "transferred_to": "trasferito a",
    "worked_at": "ha lavorato a",
    "liberated_from": "liberato da",
    "liberated_at": "liberato a",
    "died_at": "deceduto",
    "died_in": "deceduto a",
    "buried_at": "sepolto a",
    "decorated_with": "decorato con",
    "event_context": "contesto",
    "event_phase": "fasi",
    "event_forces": "forze in campo",
    "event_commander": "comandanti",
    "event_location": "luogo",
    "event_duration": "durata",
    "event_outcome": "esito",
    "event_casualties": "perdite",
    "event_significance": "significato storico",
    "event_aftermath": "conseguenze",
}

EVENT_DIMENSION_LABELS = {
    "event_context": "Contesto storico",
    "event_phase": "Svolgimento e fasi",
    "event_forces": "Forze in campo",
    "event_commander": "Comando e leadership",
    "event_location": "Geografia del teatro operativo",
    "event_duration": "Sequenza temporale",
    "event_outcome": "Esito",
    "event_casualties": "Perdite",
    "event_significance": "Significato storico",
    "event_aftermath": "Conseguenze e sviluppi",
}


@dataclass
class ConversationalResponse:
    """A complete conversational response."""
    query: str
    request_type: str  # PERSON or EVENT
    text: str
    blocks: List[Dict[str, Any]]
    coverage_score: float
    identity_status: str
    certainty_summary: Dict[str, int]
    needs_followup: bool
    followup_question: str
    source_count: int
    claim_count: int
    validation_issues: List[Dict[str, str]]

    def to_dict(self) -> dict:
        return {
            "query": self.query,
            "request_type": self.request_type,
            "text": self.text,
            "blocks": self.blocks,
            "coverage_score": self.coverage_score,
            "identity_status": self.identity_status,
            "certainty_summary": self.certainty_summary,
            "needs_followup": self.needs_followup,
            "followup_question": self.followup_question,
            "source_count": self.source_count,
            "claim_count": self.claim_count,
            "validation_issues": self.validation_issues,
        }


class ConversationalRenderer:
    """Genera testo narrativo conversazionale dai SelectedClaim."""

    def render_person(
        self,
        query: str,
        selected: List[SelectedClaim],
        plan: NarrationPlan,
        coverage: CoverageReport,
        candidate: IdentityCandidate,
        db_record: Optional[dict] = None,
    ) -> ConversationalResponse:
        """Render a PERSON conversational response."""

        blocks_output = []
        text_parts = []

        # ─── Opening ─────────────────────────────────────────────────────
        cognome = db_record.get("cognome", "") if db_record else query.split()[0]
        nome = db_record.get("nome", "") if db_record else " ".join(query.split()[1:])

        identity_phrase = self._identity_phrase(candidate, cognome, nome)
        blocks_output.append({
            "block_id": "opening",
            "role": "opening",
            "text": identity_phrase,
        })
        text_parts.append(identity_phrase)

        # ─── Biographical ────────────────────────────────────────────────
        bio_claims = [sc for sc in selected if sc.claim.predicate in ("born_at", "born_in", "resided_in")]
        if bio_claims:
            bio_text = self._render_claims_block(bio_claims, "biographical")
            blocks_output.append({"block_id": "bio", "role": "biographical", "text": bio_text})
            text_parts.append(bio_text)
        else:
            gap_text = f"Non sono disponibili informazioni documentate sulla data e il luogo di nascita di {cognome} {nome}."
            blocks_output.append({"block_id": "bio_gap", "role": "biographical", "text": gap_text})
            text_parts.append(gap_text)

        # ─── Military service ────────────────────────────────────────────
        military_claims = [sc for sc in selected if sc.claim.predicate in ("enlisted_in", "served_in", "decorated_with")]
        if military_claims:
            mil_text = self._render_claims_block(military_claims, "military")
            blocks_output.append({"block_id": "military", "role": "military", "text": mil_text})
            text_parts.append(mil_text)

        # ─── Capture & internment ────────────────────────────────────────
        capture_claims = [sc for sc in selected if sc.claim.predicate in ("captured_at", "captured_in", "interned_at", "interned_in", "transferred_to", "worked_at")]
        if capture_claims:
            cap_text = self._render_claims_block(capture_claims, "capture_internment")
            blocks_output.append({"block_id": "capture", "role": "capture_internment", "text": cap_text})
            text_parts.append(cap_text)
        elif db_record and db_record.get("luogo_internamento"):
            # We have the data but claim wasn't selected (identity issue)
            cap_text = f"Secondo i registri disponibili, {cognome} {nome} risulta internato a {db_record['luogo_internamento']}. Questa informazione non è stata verificata attraverso fonti indipendenti."
            blocks_output.append({"block_id": "capture_unverified", "role": "capture_internment", "text": cap_text})
            text_parts.append(cap_text)

        # ─── Liberation / death ──────────────────────────────────────────
        death_claims = [sc for sc in selected if sc.claim.predicate in ("liberated_from", "liberated_at", "died_at", "died_in", "buried_at")]
        if death_claims:
            death_text = self._render_claims_block(death_claims, "liberation_death")
            blocks_output.append({"block_id": "death", "role": "liberation_death", "text": death_text})
            text_parts.append(death_text)
        elif db_record and db_record.get("sorte"):
            sorte = db_record["sorte"]
            if sorte == "deceduto":
                death_text = f"I registri indicano che {cognome} {nome} è deceduto durante la prigionia. Il luogo e la data del decesso non sono stati verificati attraverso fonti indipendenti."
            elif sorte == "rimpatriato":
                death_text = f"I registri indicano che {cognome} {nome} è stato rimpatriato al termine del conflitto."
            else:
                death_text = f"La sorte di {cognome} {nome} risulta: {sorte}."
            blocks_output.append({"block_id": "death_unverified", "role": "liberation_death", "text": death_text})
            text_parts.append(death_text)

        # ─── Limitations & coverage ──────────────────────────────────────
        limitations = self._render_limitations(coverage, candidate)
        if limitations:
            blocks_output.append({"block_id": "limitations", "role": "limitations", "text": limitations})
            text_parts.append(limitations)

        # ─── Followup ────────────────────────────────────────────────────
        if plan.needs_followup:
            followup = f"Per completare il profilo biografico sarebbe necessario approfondire: {plan.followup_question}"
            blocks_output.append({"block_id": "followup", "role": "research_next_step", "text": followup})
            text_parts.append(followup)

        # ─── Certainty summary ───────────────────────────────────────────
        certainty_summary = {}
        for sc in selected:
            certainty_summary[sc.certainty] = certainty_summary.get(sc.certainty, 0) + 1

        # ─── Source count ────────────────────────────────────────────────
        all_sources = set()
        for sc in selected:
            all_sources.update(sc.citation_source_ids)

        full_text = "\n\n".join(text_parts)

        return ConversationalResponse(
            query=query,
            request_type="PERSON",
            text=full_text,
            blocks=blocks_output,
            coverage_score=coverage.coverage_score,
            identity_status=candidate.identity_status.value,
            certainty_summary=certainty_summary,
            needs_followup=plan.needs_followup,
            followup_question=plan.followup_question,
            source_count=len(all_sources),
            claim_count=len(selected),
            validation_issues=[],
        )

    def render_event(
        self,
        query: str,
        event_data: dict,
        selected: List[SelectedClaim],
        plan: NarrationPlan,
        coverage: CoverageReport,
    ) -> ConversationalResponse:
        """Render an EVENT conversational response."""

        blocks_output = []
        text_parts = []

        event_name = event_data.get("name", query)
        war = event_data.get("war", "")
        data_inizio = event_data.get("data_inizio", "")
        data_fine = event_data.get("data_fine", "")
        location = event_data.get("general_location", "")
        description = event_data.get("description", "")
        aliases = json.loads(event_data.get("aliases_json", "[]") or "[]")

        # ─── Opening ─────────────────────────────────────────────────────
        war_label = "prima guerra mondiale" if war == "WWI" else "seconda guerra mondiale" if war == "WWII" else "conflitto"
        date_range = f"{data_inizio} - {data_fine}" if data_inizio and data_fine else "data non disponibile"

        opening = f"## {event_name}\n\n"
        opening += f"L'evento si colloca nel contesto della {war_label}, nel periodo {date_range}"
        if location:
            opening += f", nel settore di {location}"
        opening += "."
        if aliases:
            opening += f"\n\nNoto anche come: {', '.join(aliases)}."

        blocks_output.append({"block_id": "opening", "role": "direct_answer", "text": opening})
        text_parts.append(opening)

        # ─── Context ─────────────────────────────────────────────────────
        context_claims = [sc for sc in selected if sc.claim.predicate == "event_context"]
        if context_claims:
            ctx_text = self._render_claims_block(context_claims, "context")
            blocks_output.append({"block_id": "context", "role": "context", "text": ctx_text})
            text_parts.append(ctx_text)
        elif description:
            ctx_text = f"### Contesto storico\n\n{description}"
            blocks_output.append({"block_id": "context", "role": "context", "text": ctx_text})
            text_parts.append(ctx_text)

        # ─── Location ────────────────────────────────────────────────────
        loc_claims = [sc for sc in selected if sc.claim.predicate == "event_location"]
        if loc_claims:
            loc_text = self._render_claims_block(loc_claims, "location")
            blocks_output.append({"block_id": "location", "role": "context", "text": loc_text})
            text_parts.append(loc_text)
        elif location:
            loc_text = f"### Teatro operativo\n\nL'evento si è svolto nel settore di {location}."
            blocks_output.append({"block_id": "location", "role": "context", "text": loc_text})
            text_parts.append(loc_text)

        # ─── Duration ────────────────────────────────────────────────────
        dur_claims = [sc for sc in selected if sc.claim.predicate == "event_duration"]
        if dur_claims:
            dur_text = self._render_claims_block(dur_claims, "duration")
            blocks_output.append({"block_id": "duration", "role": "chronology", "text": dur_text})
            text_parts.append(dur_text)
        elif data_inizio and data_fine:
            dur_text = f"### Sequenza temporale\n\nL'evento si è svolto dal {data_inizio} al {data_fine}."
            blocks_output.append({"block_id": "duration", "role": "chronology", "text": dur_text})
            text_parts.append(dur_text)

        # ─── Missing dimensions ──────────────────────────────────────────
        missing_critical = [g for g in coverage.gaps if g.severity == "critical"]
        missing_important = [g for g in coverage.gaps if g.severity == "important"]

        if missing_critical or missing_important:
            missing_text = "### Limiti della copertura narrativa\n\n"
            missing_text += "La narrazione attuale non copre i seguenti aspetti:\n\n"
            for g in missing_critical:
                missing_text += f"- **{g.description}** (critico)\n"
            for g in missing_important:
                missing_text += f"- {g.description} (importante)\n"
            missing_text += "\nPer una copertura completa sarebbe necessario consultare fonti aggiuntive."
            blocks_output.append({"block_id": "limitations", "role": "limitations", "text": missing_text})
            text_parts.append(missing_text)

        # ─── Followup ────────────────────────────────────────────────────
        if plan.needs_followup:
            followup = f"Per completare la copertura dell'evento: {plan.followup_question}"
            blocks_output.append({"block_id": "followup", "role": "research_next_step", "text": followup})
            text_parts.append(followup)

        # ─── Provenance ──────────────────────────────────────────────────
        provenance = json.loads(event_data.get("source_provenance_json", "{}") or "{}")
        if provenance:
            prov_text = "### Provenienza\n\n"
            prov_text += f"Fonte: {provenance.get('source', 'N/D')}"
            if provenance.get("work"):
                prov_text += f", \"{provenance['work']}\""
            if provenance.get("publisher"):
                prov_text += f", {provenance['publisher']}"
            if provenance.get("correction_reason"):
                prov_text += f"\n\nNota: {provenance['correction_reason']}"
            blocks_output.append({"block_id": "provenance", "role": "context", "text": prov_text})
            text_parts.append(prov_text)

        # ─── Certainty summary ───────────────────────────────────────────
        certainty_summary = {}
        for sc in selected:
            certainty_summary[sc.certainty] = certainty_summary.get(sc.certainty, 0) + 1

        all_sources = set()
        for sc in selected:
            all_sources.update(sc.citation_source_ids)

        full_text = "\n\n".join(text_parts)

        return ConversationalResponse(
            query=query,
            request_type="EVENT",
            text=full_text,
            blocks=blocks_output,
            coverage_score=coverage.coverage_score,
            identity_status="N/A",
            certainty_summary=certainty_summary,
            needs_followup=plan.needs_followup,
            followup_question=plan.followup_question,
            source_count=len(all_sources),
            claim_count=len(selected),
            validation_issues=[],
        )

    def _identity_phrase(self, candidate: IdentityCandidate, cognome: str, nome: str) -> str:
        """Generate identity status phrase."""
        full_name = f"{cognome} {nome}".strip()

        if candidate.identity_status == IdentityStatus.RESOLVED:
            return f"## Profilo di {full_name}\n\nL'identità di {full_name} è stata verificata attraverso identificatori indipendenti."
        elif candidate.identity_status == IdentityStatus.NEEDS_REVIEW:
            return f"## Profilo di {full_name}\n\n**Nota**: L'identità di {full_name} non è stata pienamente verificata. Sono disponibili solo identificatori deboli (nome e cognome). Le informazioni che seguono sono da considerarsi candidate e non confermate."
        elif candidate.identity_status == IdentityStatus.REJECTED_HOMONYM:
            return f"## Profilo di {full_name}\n\n**Attenzione**: Esistono identificatori in conflitto per {full_name}. Potrebbe trattarsi di un'omonimia. Le informazioni non possono essere attribuite con certezza a una singola persona."
        elif candidate.identity_status == IdentityStatus.CONFLICTING:
            return f"## Profilo di {full_name}\n\n**Attenzione**: Esistono informazioni contrastanti su {full_name}. Sono presenti conflitti tra identificatori di media forza."
        else:
            return f"## Profilo di {full_name}\n\nL'identità di {full_name} è in stato di valutazione."

    def _render_claims_block(self, claims: List[SelectedClaim], section: str) -> str:
        """Render a block of claims as conversational text."""
        lines = []

        for sc in claims:
            pred = sc.claim.predicate
            value = sc.claim.object_value
            certainty = sc.certainty
            label = PREDICATE_LABELS.get(pred, pred)

            phrase = CERTAINTY_PHRASING.get(certainty, "non verificato")
            prefix = CERTAINTY_PREFIX.get(certainty, "")

            if certainty == "CONFIRMED":
                lines.append(f"- {label.capitalize()}: {value} (fonte verificata)")
            elif certainty == "PROBABLE":
                lines.append(f"- {label.capitalize()}: {value} (probabile, basato su registro archivistico)")
            elif certainty == "POSSIBLE":
                lines.append(f"- {prefix}{label} {value} (informazione non confermata)")
            elif certainty == "CONTRADICTED":
                lines.append(f"- {label.capitalize()}: {value} (informazione contraddittoria: {sc.conflict_reason})")
            else:
                lines.append(f"- {label}: {value} (non verificato)")

        section_title = {
            "biographical": "### Dati biografici",
            "military": "### Servizio militare",
            "capture_internment": "### Cattura e internamento",
            "liberation_death": "### Sorte",
            "context": "### Contesto storico",
            "location": "### Teatro operativo",
            "duration": "### Sequenza temporale",
        }.get(section, f"### {section.title()}")

        return f"{section_title}\n\n" + "\n".join(lines)

    def _render_limitations(self, coverage: CoverageReport, candidate: IdentityCandidate) -> str:
        """Render limitations section."""
        if not coverage.gaps:
            return ""

        lines = ["### Limiti della copertura narrativa\n"]

        critical = [g for g in coverage.gaps if g.severity == "critical"]
        important = [g for g in coverage.gaps if g.severity == "important"]

        if critical:
            lines.append("Informazioni critiche mancanti:")
            for g in critical:
                lines.append(f"- {g.description}")
            lines.append("")

        if important:
            lines.append("Informazioni importanti mancanti:")
            for g in important:
                lines.append(f"- {g.description}")
            lines.append("")

        if candidate.identity_status != IdentityStatus.RESOLVED:
            lines.append(f"Stato dell'identità: {candidate.identity_status.value}. "
                        "Le informazioni biografiche non sono state verificate attraverso "
                        "identificatori indipendenti (data di nascita, paternità, matricola).")

        return "\n".join(lines) if len(lines) > 1 else ""

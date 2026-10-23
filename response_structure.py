"""V7.3-Fase13: Final response structure — 11 sections.

Defines the canonical 11-section structure for all narrative responses,
unifying PERSON and EVENT queries into a single framework.

The 11 sections:
  1.  SINTESI — direct answer / summary
  2.  IDENTITA — identity resolution status and confidence
  3.  DATI_ANAGRAFICI — biographical data (birth, death, family)
  4.  PERCORSO_MILITARE — military career (rank, unit, assignments)
  5.  EVENTI_E_OPERAZIONI — events and operations participated in
  6.  PRIGIONIA_E_INTERNAZIONE — captivity and internment
  7.  CONTESTO_STORICO — historical context (unit, place, period)
  8.  CONFLITTI_E_DISCREPANZE — conflicts and discrepancies
  9.  LIMITI_E_INCERTEZZE — limitations and uncertainties
  10. FONTI_E_PROVENIENZA — sources and provenance
  11. PROSSIMI_PASSI — next steps for research

Key invariants:
  1. Every response has all 11 sections (empty sections are explicit)
  2. Sections are ordered by importance, not chronology
  3. Only PUBLISHED and PUBLISHED_WITH_CAVEAT claims appear in sections
  4. SUPPRESSED and REVIEW_PENDING claims are listed in section 9
  5. Section 1 (SINTESI) is always present, even if "no data found"
  6. Caveats are rendered inline with the relevant section
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any


# ─── Section definitions ─────────────────────────────────────────────────────

SECTION_IDS = [
    "sintesi",
    "identita",
    "dati_anagrafici",
    "percorso_militare",
    "eventi_e_operazioni",
    "prigionia_e_internazione",
    "contesto_storico",
    "conflitti_e_discrepanze",
    "limiti_e_incertezze",
    "fonti_e_provenienza",
    "prossimi_passi",
]

SECTION_TITLES = {
    "sintesi": "Sintesi",
    "identita": "Identità",
    "dati_anagrafici": "Dati Anagrafici",
    "percorso_militare": "Percorso Militare",
    "eventi_e_operazioni": "Eventi e Operazioni",
    "prigionia_e_internazione": "Prigionia e Internamento",
    "contesto_storico": "Contesto Storico",
    "conflitti_e_discrepanze": "Conflitti e Discrepanze",
    "limiti_e_incertezze": "Limiti e Incertezze",
    "fonti_e_provenienza": "Fonti e Provenienza",
    "prossimi_passi": "Prossimi Passi",
}

# Section applicability by request type
SECTION_APPLICABILITY = {
    "PERSON": [
        "sintesi", "identita", "dati_anagrafici", "percorso_militare",
        "eventi_e_operazioni", "prigionia_e_internazione", "contesto_storico",
        "conflitti_e_discrepanze", "limiti_e_incertezze",
        "fonti_e_provenienza", "prossimi_passi",
    ],
    "EVENT": [
        "sintesi", "identita", "dati_anagrafici", "percorso_militare",
        "eventi_e_operazioni", "prigionia_e_internazione", "contesto_storico",
        "conflitti_e_discrepanze", "limiti_e_incertezze",
        "fonti_e_provenienza", "prossimi_passi",
    ],
    "FACT": [
        "sintesi", "identita", "contesto_storico",
        "conflitti_e_discrepanze", "limiti_e_incertezze",
        "fonti_e_provenienza", "prossimi_passi",
    ],
}

# Claim predicate → section mapping
PREDICATE_TO_SECTION: Dict[str, str] = {
    # dati_anagrafici
    "birth_date": "dati_anagrafici", "birth_place": "dati_anagrafici",
    "birth_year": "dati_anagrafici", "death_date": "dati_anagrafici",
    "death_place": "dati_anagrafici", "death_year": "dati_anagrafici",
    "death_country": "dati_anagrafici", "death_cause": "dati_anagrafici",
    "paternity": "dati_anagrafici", "maternity": "dati_anagrafici",
    "age": "dati_anagrafici", "residence": "dati_anagrafici",
    "profession": "dati_anagrafici", "municipality": "dati_anagrafici",
    "draft_class": "dati_anagrafici",
    # percorso_militare
    "rank": "percorso_militare", "grado": "percorso_militare",
    "military_unit": "percorso_militare", "reparto": "percorso_militare",
    "military_branch": "percorso_militare", "arma": "percorso_militare",
    "assignment": "percorso_militare", "work_command": "percorso_militare",
    "arbeitskommando": "percorso_militare",
    "enrollment_date": "percorso_militare", "discharge_date": "percorso_militare",
    "service_number": "percorso_militare", "matricola": "percorso_militare",
    "decoration_type": "percorso_militare", "decorated_with": "percorso_militare",
    # eventi_e_operazioni
    "capture_date": "eventi_e_operazioni", "capture_place": "eventi_e_operazioni",
    "event_participation": "eventi_e_operazioni",
    # prigionia_e_internazione
    "internment_place": "prigionia_e_internazione", "interned_at": "prigionia_e_internazione",
    "interned_in": "prigionia_e_internazione", "camp": "prigionia_e_internazione",
    "camp_type": "prigionia_e_internazione", "camp_location": "prigionia_e_internazione",
    "transfer_date": "prigionia_e_internazione", "transferred_to": "prigionia_e_internazione",
    "liberation_date": "prigionia_e_internazione", "liberated_from": "prigionia_e_internazione",
    "liberated_at": "prigionia_e_internazione",
    "fate": "prigionia_e_internazione", "sorte": "prigionia_e_internazione",
    "burial_place": "prigionia_e_internazione", "buried_at": "prigionia_e_internazione",
    "burial_country": "prigionia_e_internazione",
    # contesto_storico
    "event_context": "contesto_storico", "event_phase": "contesto_storico",
    "event_forces": "contesto_storico", "event_location": "contesto_storico",
    "event_date": "contesto_storico", "event_description": "contesto_storico",
    "unit_history": "contesto_storico", "place_history": "contesto_storico",
}


# ─── Data classes ────────────────────────────────────────────────────────────

@dataclass
class ResponseSection:
    """A single section of the final response."""
    section_id: str
    title: str
    content: str = ""
    claim_ids: List[str] = field(default_factory=list)
    caveats: List[str] = field(default_factory=list)
    is_empty: bool = True
    source_refs: List[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "section_id": self.section_id,
            "title": self.title,
            "content": self.content,
            "claim_ids": self.claim_ids,
            "caveats": self.caveats,
            "is_empty": self.is_empty,
            "source_refs": self.source_refs,
        }


@dataclass
class FinalResponse:
    """The complete 11-section final response."""
    schema_version: str = "7.3-response-v1"
    request_type: str = "PERSON"  # PERSON | EVENT | FACT
    query: str = ""
    sections: List[ResponseSection] = field(default_factory=list)
    # Metadata
    identity_status: str = "UNRESOLVED_IDENTITY"
    evidence_level: str = "unverified"
    total_claims: int = 0
    published_claims: int = 0
    suppressed_claims: int = 0
    review_pending_claims: int = 0
    caveat_summary: str = ""
    # Validation
    validation_passed: bool = False
    validation_errors: List[str] = field(default_factory=list)

    def get_section(self, section_id: str) -> Optional[ResponseSection]:
        for s in self.sections:
            if s.section_id == section_id:
                return s
        return None

    @property
    def non_empty_sections(self) -> List[ResponseSection]:
        return [s for s in self.sections if not s.is_empty]

    @property
    def empty_sections(self) -> List[ResponseSection]:
        return [s for s in self.sections if s.is_empty]

    def to_dict(self) -> dict:
        return {
            "schema_version": self.schema_version,
            "request_type": self.request_type,
            "query": self.query,
            "sections": [s.to_dict() for s in self.sections],
            "metadata": {
                "identity_status": self.identity_status,
                "evidence_level": self.evidence_level,
                "total_claims": self.total_claims,
                "published_claims": self.published_claims,
                "suppressed_claims": self.suppressed_claims,
                "review_pending_claims": self.review_pending_claims,
                "caveat_summary": self.caveat_summary,
            },
            "validation": {
                "passed": self.validation_passed,
                "errors": self.validation_errors,
            },
        }

    def to_markdown(self) -> str:
        """Render the response as markdown."""
        lines = []
        for section in self.sections:
            lines.append(f"## {section.title}")
            lines.append("")
            if section.is_empty:
                lines.append("*Nessun dato disponibile per questa sezione.*")
            else:
                lines.append(section.content)
                if section.caveats:
                    for caveat in section.caveats:
                        lines.append(f"\n> ⚠️ {caveat}")
            lines.append("")
        return "\n".join(lines)


# ─── Response builder ────────────────────────────────────────────────────────

class ResponseBuilder:
    """Builds a FinalResponse from claims, states, and validation results."""

    def build(
        self,
        request_type: str = "PERSON",
        query: str = "",
        identity_status: str = "UNRESOLVED_IDENTITY",
        evidence_level: str = "unverified",
        claims: Optional[List[dict]] = None,
        claim_states: Optional[List[dict]] = None,
        validation_errors: Optional[List[str]] = None,
        caveat_summary: str = "",
    ) -> FinalResponse:
        """Build the final response from components.

        Args:
            request_type: PERSON, EVENT, or FACT
            query: the original query
            identity_status: from identity resolution
            evidence_level: from source quality assessment
            claims: list of claim dicts with claim_id, predicate, value_normalized, state
            claim_states: list of ClaimState dicts
            validation_errors: from semantic validator
            caveat_summary: aggregated caveats
        """
        claims = claims or []
        claim_states = claim_states or []
        validation_errors = validation_errors or []

        # Build state lookup
        state_by_claim_id: Dict[str, dict] = {}
        for cs in claim_states:
            state_by_claim_id[cs.get("claim_id", "")] = cs

        # Initialize sections
        applicable = SECTION_APPLICABILITY.get(request_type, SECTION_IDS)
        sections: Dict[str, ResponseSection] = {}
        for sid in applicable:
            sections[sid] = ResponseSection(
                section_id=sid,
                title=SECTION_TITLES.get(sid, sid),
            )

        # Count claim states
        published = 0
        suppressed = 0
        review_pending = 0

        # Assign claims to sections
        for claim in claims:
            claim_id = claim.get("claim_id", "")
            predicate = claim.get("predicate", "")
            value = claim.get("value_normalized", "")
            state_info = state_by_claim_id.get(claim_id, {})
            state = state_info.get("state", "REVIEW_PENDING")
            caveat = state_info.get("caveat", "")

            if state == "PUBLISHED":
                published += 1
            elif state == "PUBLISHED_WITH_CAVEAT":
                published += 1
            elif state == "SUPPRESSED":
                suppressed += 1
            else:
                review_pending += 1

            # Only include published claims in content sections
            if state not in ("PUBLISHED", "PUBLISHED_WITH_CAVEAT"):
                continue

            # Map predicate to section
            section_id = PREDICATE_TO_SECTION.get(predicate, "contesto_storico")
            if section_id not in sections:
                section_id = "contesto_storico"

            section = sections[section_id]
            section.is_empty = False
            section.claim_ids.append(claim_id)

            # Append content
            if section.content:
                section.content += f"\n- {predicate}: {value}"
            else:
                section.content = f"- {predicate}: {value}"

            # Add caveat
            if caveat:
                section.caveats.append(caveat)

            # Add source refs
            source_refs = claim.get("source_refs", [])
            section.source_refs.extend(source_refs)

        # Build sintesi (summary) section
        sintesi = sections.get("sintesi")
        if sintesi:
            sintesi.is_empty = False
            if published == 0 and review_pending == 0 and suppressed == 0:
                sintesi.content = "Nessun dato trovato per la query effettuata."
            elif identity_status == "UNRESOLVED_IDENTITY":
                sintesi.content = "Identità non risolta. I dati disponibili sono insufficienti per attribuire con certezza le informazioni a una persona specifica."
            elif published > 0:
                sintesi.content = f"Sono state trovate {published} affermazioni pubblicate su {len(claims)} totali."
            else:
                sintesi.content = "Dati trovati ma in attesa di revisione."

        # Build limiti_e_incertezze section
        limiti = sections.get("limiti_e_incertezze")
        if limiti:
            items = []
            if review_pending > 0:
                items.append(f"- {review_pending} affermazioni in attesa di revisione")
            if suppressed > 0:
                items.append(f"- {suppressed} affermazioni soppresse")
            if validation_errors:
                items.append(f"- Errori di validazione: {len(validation_errors)}")
            if items:
                limiti.content = "\n".join(items)
                limiti.is_empty = False

        # Build fonti_e_provenienza section
        fonti = sections.get("fonti_e_provenienza")
        if fonti:
            all_sources = set()
            for s in sections.values():
                all_sources.update(s.source_refs)
            if all_sources:
                fonti.content = "\n".join(f"- {s}" for s in sorted(all_sources))
                fonti.is_empty = False

        # Build prossimi_passi section
        prossimi = sections.get("prossimi_passi")
        if prossimi:
            steps = []
            if identity_status == "UNRESOLVED_IDENTITY":
                steps.append("- Verificare l'identità con ulteriori fonti (matricola, paternità)")
            if review_pending > 0:
                steps.append("- Revisionare le affermazioni in attesa")
            if evidence_level in ("unverified", "possible"):
                steps.append("- Cercare fonti aggiuntive per corroborazione")
            if not steps:
                steps.append("- Nessun passo aggiuntivo necessario")
            prossimi.content = "\n".join(steps)
            prossimi.is_empty = False

        # Assemble final response
        response = FinalResponse(
            request_type=request_type,
            query=query,
            sections=list(sections.values()),
            identity_status=identity_status,
            evidence_level=evidence_level,
            total_claims=len(claims),
            published_claims=published,
            suppressed_claims=suppressed,
            review_pending_claims=review_pending,
            caveat_summary=caveat_summary,
            validation_passed=len(validation_errors) == 0,
            validation_errors=validation_errors,
        )

        return response

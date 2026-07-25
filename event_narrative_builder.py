"""event_narrative_builder.py — Generazione narrazione storica da pacchetto evidenze.

Regole fondamentali:
- La narrazione è generata ESCLUSIVAMENTE dal pacchetto di evidenze recuperato.
- Nessuna memoria generale dell'AI utilizzata come fonte.
- Nessuna frase fattuale senza riferimento a una fonte.
- Per fatti centrali o controversi: almeno 2 fonti indipendenti oppure "attestato da una sola fonte".
- Conflitti e versioni opposte non vengono eliminati dalla sintesi.
- Ogni paragrafo è collegato alle fonti che lo sostengono.

Struttura output:
1. Inquadramento dell'evento
2. Narrazione storica
3. Cronologia e fasi
4. Luoghi e spostamenti
5. Reparti e soggetti coinvolti
6. Cause e conseguenze
7. Fatti concordanti tra le fonti
8. Versioni divergenti
9. Elementi incerti o non verificabili
10. Fonti archivistiche
11. Fonti bibliografiche e web
12. Grafo delle relazioni
13. Soldati e persone collegate
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from event_evidence_pipeline import Claim, EvidencePackage, Source


# ─── Modelli ─────────────────────────────────────────────────────────────────

@dataclass
class Paragraph:
    """Paragrafo della narrazione con fonti collegate."""
    section: str
    text: str
    source_ids: List[str]
    source_labels: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "section": self.section,
            "text": self.text,
            "source_ids": self.source_ids,
            "source_labels": self.source_labels,
        }


@dataclass
class NarrativeReport:
    """Report narrativo completo per un evento."""
    event_name: str
    event_id: Optional[int]
    resolution: Dict[str, Any]
    sections: List[Paragraph]
    inquadramento: str
    narrazione: str
    cronologia: List[Dict[str, Any]]
    luoghi: List[Dict[str, Any]]
    reparti: List[Dict[str, Any]]
    cause_conseguenze: str
    fatti_concordanti: List[Dict[str, Any]]
    versioni_divergenti: List[Dict[str, Any]]
    elementi_incerti: List[Dict[str, Any]]
    fonti_archivistiche: List[Dict[str, Any]]
    fonti_bibliografiche: List[Dict[str, Any]]
    grafo: Dict[str, Any]
    persone_collegate: List[Dict[str, Any]]
    evidence_package: Dict[str, Any]
    ai_used: bool
    ai_model: Optional[str]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "event_name": self.event_name,
            "event_id": self.event_id,
            "resolution": self.resolution,
            "sections": [p.to_dict() for p in self.sections],
            "inquadramento": self.inquadramento,
            "narrazione": self.narrazione,
            "cronologia": self.cronologia,
            "luoghi": self.luoghi,
            "reparti": self.reparti,
            "cause_conseguenze": self.cause_conseguenze,
            "fatti_concordanti": self.fatti_concordanti,
            "versioni_divergenti": self.versioni_divergenti,
            "elementi_incerti": self.elementi_incerti,
            "fonti_archivistiche": self.fonti_archivistiche,
            "fonti_bibliografiche": self.fonti_bibliografiche,
            "grafo": self.grafo,
            "persone_collegate": self.persone_collegate,
            "evidence_package": self.evidence_package,
            "ai_used": self.ai_used,
            "ai_model": self.ai_model,
        }


# ─── Prompt AI ───────────────────────────────────────────────────────────────

NARRATIVE_SYSTEM = (
    "Sei un ricercatore storico specializzato in eventi bellici del '900. "
    "Non inventare dati. Non usare la tua memoria generale come fonte. "
    "Genera la narrazione ESCLUSIVAMENTE dal pacchetto di evidenze fornito. "
    "Per ogni affermazione fattuale cita la fonte con [ID]. "
    "Se un dato non ha fonte, scrivi 'non attestato nelle fonti recuperate'. "
    "Se un fatto è attestato da una sola fonte, scrivi 'attestato da una sola fonte'. "
    "Non eliminare conflitti o versioni opposte. "
    "Restituisci SEMPRE un JSON valido seguito dal testo narrativo."
)

NARRATIVE_PROMPT = """Scrivi in italiano.

Evento: "{event_name}"

Risoluzione:
{resolution}

PACCHETTO EVIDENZE:
{evidence}

--- ISTRUZIONI OBBLIGATORIE ---

1. Non usare alcuna conoscenza generale non presente nel pacchetto di evidenze.
2. Per ogni affermazione fattuale, cita la fonte con [source_id] tra parentesi quadre.
3. Se un fatto centrale è attestato da una sola fonte, scrivi esplicitamente "attestato da una sola fonte [ID]".
4. Se ci sono versioni divergenti, riportale entrambe con le rispettive fonti.
5. Non fondere eventi generali con episodi specifici.
6. Se l'evento è una collezione ambigua (es. "Battaglia del Carso"), avverti che può indicare un insieme di operazioni.

--- FORMATO RICHIESTO ---

Prima il JSON esattamente così:

{{
  "inquadramento": "",
  "narrazione": "",
  "cronologia": [{{"data": "", "fase": "", "descrizione": "", "fonti": []}}],
  "luoghi": [{{"nome": "", "ruolo": "", "fonti": []}}],
  "reparti": [{{"nome": "", "ruolo": "", "fonti": []}}],
  "cause_conseguenze": "",
  "fatti_concordanti": [{{"fatto": "", "fonti": []}}],
  "versioni_divergenti": [{{"fatto": "", "versione_a": "", "fonte_a": "", "versione_b": "", "fonte_b": ""}}],
  "elementi_incerti": [{{"elemento": "", "motivo": "", "fonti": []}}]
}}

Subito dopo, separa con una riga contenente ===NARRATIVA=== e scrivi il testo narrativo completo, suddiviso in paragrafi con sezioni:
1. Inquadramento dell'evento
2. Narrazione storica
3. Cronologia e fasi
4. Luoghi e spostamenti
5. Reparti e soggetti coinvolti
6. Cause e conseguenze
7. Fatti concordanti tra le fonti
8. Versioni divergenti
9. Elementi incerti o non verificabili

Per ogni paragrafo indica le fonti tra parentesi quadre [ID].
"""


# ─── Estrazione JSON ─────────────────────────────────────────────────────────

def _extract_json(text: str) -> Optional[Dict[str, Any]]:
    """Estrae il primo JSON oggetto dalla risposta AI."""
    text = text or ""
    text = text.strip()
    # Rimuovi markdown code fences se presenti
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    match = re.search(r"\{[\s\S]*\}", text)
    if not match:
        return None
    try:
        return json.loads(match.group(0))
    except json.JSONDecodeError:
        # Fallback: bilanciamento parentesi
        start = text.find("{")
        if start == -1:
            return None
        depth = 0
        in_str = False
        esc = False
        for i, ch in enumerate(text[start:], start):
            if in_str:
                if esc:
                    esc = False
                elif ch == "\\":
                    esc = True
                elif ch == '"':
                    in_str = False
                continue
            if ch == '"':
                in_str = True
            elif ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    try:
                        return json.loads(text[start:i + 1])
                    except Exception:
                        return None
        return None


def _split_json_and_narrative(text: str) -> tuple:
    """Separa JSON iniziale dalla narrazione testuale."""
    data = _extract_json(text)
    marker = "===NARRATIVA==="
    idx = text.find(marker)
    if idx != -1:
        narrative = text[idx + len(marker):].strip()
    else:
        # Se non c'è marker, prendi tutto dopo il JSON
        if data:
            json_end = text.find("}")
            # Trova la fine del JSON bilanciato
            start = text.find("{")
            depth = 0
            in_str = False
            esc = False
            for i, ch in enumerate(text[start:], start):
                if in_str:
                    if esc:
                        esc = False
                    elif ch == "\\":
                        esc = True
                    elif ch == '"':
                        in_str = False
                    continue
                if ch == '"':
                    in_str = True
                elif ch == "{":
                    depth += 1
                elif ch == "}":
                    depth -= 1
                    if depth == 0:
                        json_end = i + 1
                        break
            narrative = text[json_end:].strip()
        else:
            narrative = text
    return data, narrative


# ─── Costruzione narrazione senza AI ─────────────────────────────────────────

def _build_narrative_without_ai(evidence: EvidencePackage) -> NarrativeReport:
    """Costruisce la narrazione esclusivamente dai dati strutturati, senza AI."""
    event_data = evidence.resolution
    event_name = evidence.event_name

    # Inquadramento
    inquadramento_parts = []
    inquadramento_parts.append(f"Evento: {event_name}")
    if event_data.get("canonical_id"):
        inquadramento_parts.append(f"ID database: {event_data['canonical_id']}")
    if event_data.get("ambiguity_warning"):
        inquadramento_parts.append(f"AVVISO: {event_data['ambiguity_warning']}")
    if event_data.get("proposed_distinctions"):
        inquadramento_parts.append("Distinzioni proposte:")
        for d in event_data["proposed_distinctions"]:
            inquadramento_parts.append(f"  - {d['type']}: {d['nome']} ({d.get('periodo', '')})")
    inquadramento = "\n".join(inquadramento_parts)

    # Narrazione: solo dalle evidenze
    narration_parts = []
    verified_sources = [s for s in evidence.sources if s.verification_status == "verificata"]
    if verified_sources:
        narration_parts.append("Fonti verificate recuperate:")
        for s in verified_sources[:10]:
            ref = f" [{s.source_id}]"
            narration_parts.append(f"- {s.title} — {s.author_or_institution}{ref}")
    else:
        narration_parts.append("Nessuna fonte verificata recuperata. Le affermazioni seguenti sono da considerarsi non attestate.")

    # Claim strutturati
    if evidence.concordant_facts:
        narration_parts.append("\nFatti concordanti tra le fonti:")
        for c in evidence.concordant_facts:
            src_refs = ", ".join(f"[{sid}]" for sid in c.sources)
            narration_parts.append(f"- {c.text} {src_refs}")

    if evidence.divergent_versions:
        narration_parts.append("\nVersioni divergenti:")
        for c in evidence.divergent_versions:
            src_refs = ", ".join(f"[{sid}]" for sid in c.sources)
            narration_parts.append(f"- {c.text} {src_refs}")

    if evidence.uncertain_elements:
        narration_parts.append("\nElementi incerti o attestati da una sola fonte:")
        for c in evidence.uncertain_elements:
            src_refs = ", ".join(f"[{sid}]" for sid in c.sources)
            narration_parts.append(f"- {c.text} (attestato da una sola fonte) {src_refs}")

    narrazione = "\n".join(narration_parts)

    # Cronologia dai claim di tipo "date"
    cronologia = []
    for c in evidence.claims:
        if c.claim_type == "date":
            cronologia.append({
                "data": c.value,
                "fase": "",
                "descrizione": c.text,
                "fonti": c.sources,
            })
    cronologia.sort(key=lambda x: x["data"])

    # Luoghi dai claim di tipo "place"
    luoghi = []
    seen_places = set()
    for c in evidence.claims:
        if c.claim_type == "place" and c.value not in seen_places:
            seen_places.add(c.value)
            luoghi.append({
                "nome": c.value,
                "ruolo": "menzionato",
                "fonti": c.sources,
            })

    # Reparti dai claim di tipo "unit"
    reparti = []
    seen_units = set()
    for c in evidence.claims:
        if c.claim_type == "unit" and c.value not in seen_units:
            seen_units.add(c.value)
            reparti.append({
                "nome": c.value,
                "ruolo": "menzionato",
                "fonti": c.sources,
            })

    # Cause e conseguenze
    cause_parts = []
    outcome_claims = [c for c in evidence.claims if c.claim_type in ("outcome", "consequence")]
    for c in outcome_claims:
        src_refs = ", ".join(f"[{sid}]" for sid in c.sources)
        cause_parts.append(f"- {c.text} {src_refs}")
    cause_conseguenze = "\n".join(cause_parts) if cause_parts else "Non attestato nelle fonti recuperate."

    # Sezioni paragrafi
    sections: List[Paragraph] = []
    sections.append(Paragraph(
        section="Inquadramento dell'evento",
        text=inquadramento,
        source_ids=[],
    ))
    sections.append(Paragraph(
        section="Narrazione storica",
        text=narrazione,
        source_ids=[s.source_id for s in verified_sources],
    ))
    sections.append(Paragraph(
        section="Cronologia e fasi",
        text="\n".join(f"- {c['data']}: {c['descrizione']}" for c in cronologia) if cronologia else "Non attestato nelle fonti recuperate.",
        source_ids=list(set(sid for c in cronologia for sid in c["fonti"])),
    ))
    sections.append(Paragraph(
        section="Luoghi e spostamenti",
        text="\n".join(f"- {l['nome']}" for l in luoghi) if luoghi else "Non attestato nelle fonti recuperate.",
        source_ids=list(set(sid for l in luoghi for sid in l["fonti"])),
    ))
    sections.append(Paragraph(
        section="Reparti e soggetti coinvolti",
        text="\n".join(f"- {r['nome']}" for r in reparti) if reparti else "Non attestato nelle fonti recuperate.",
        source_ids=list(set(sid for r in reparti for sid in r["fonti"])),
    ))
    sections.append(Paragraph(
        section="Cause e conseguenze",
        text=cause_conseguenze,
        source_ids=list(set(sid for c in outcome_claims for sid in c.sources)),
    ))
    sections.append(Paragraph(
        section="Fatti concordanti tra le fonti",
        text="\n".join(f"- {c.text} [{', '.join(c.sources)}]" for c in evidence.concordant_facts) if evidence.concordant_facts else "Nessun fatto concordante tra fonti indipendenti recuperato.",
        source_ids=list(set(sid for c in evidence.concordant_facts for sid in c.sources)),
    ))
    sections.append(Paragraph(
        section="Versioni divergenti",
        text="\n".join(f"- {c.text} [{', '.join(c.sources)}]" for c in evidence.divergent_versions) if evidence.divergent_versions else "Nessuna versione divergente rilevata.",
        source_ids=list(set(sid for c in evidence.divergent_versions for sid in c.sources)),
    ))
    sections.append(Paragraph(
        section="Elementi incerti o non verificabili",
        text="\n".join(f"- {c.text} (attestato da una sola fonte) [{', '.join(c.sources)}]" for c in evidence.uncertain_elements) if evidence.uncertain_elements else "Nessun elemento incerto rilevato.",
        source_ids=list(set(sid for c in evidence.uncertain_elements for sid in c.sources)),
    ))

    return NarrativeReport(
        event_name=event_name,
        event_id=evidence.event_id,
        resolution=evidence.resolution,
        sections=sections,
        inquadramento=inquadramento,
        narrazione=narrazione,
        cronologia=cronologia,
        luoghi=luoghi,
        reparti=reparti,
        cause_conseguenze=cause_conseguenze,
        fatti_concordanti=[c.to_dict() for c in evidence.concordant_facts],
        versioni_divergenti=[c.to_dict() for c in evidence.divergent_versions],
        elementi_incerti=[c.to_dict() for c in evidence.uncertain_elements],
        fonti_archivistiche=[s.to_dict() for s in evidence.archival_sources],
        fonti_bibliografiche=[s.to_dict() for s in evidence.bibliographic_sources + evidence.web_sources],
        grafo=evidence.graph_data,
        persone_collegate=evidence.related_people,
        evidence_package=evidence.to_dict(),
        ai_used=False,
        ai_model=None,
    )


# ─── Costruzione narrazione con AI ───────────────────────────────────────────

def _build_narrative_with_ai(evidence: EvidencePackage, provider: str = "mistral") -> NarrativeReport:
    """Costruisce la narrazione usando AI, ma esclusivamente dal pacchetto evidenze."""
    import biography as bio

    event_name = evidence.event_name
    evidence_json = json.dumps(evidence.to_dict(), ensure_ascii=False, default=str, indent=2)

    # Limita la dimensione del contesto
    if len(evidence_json) > 20000:
        evidence_json = evidence_json[:20000] + "\n... [troncato]"

    prompt = NARRATIVE_PROMPT.format(
        event_name=event_name,
        resolution=json.dumps(evidence.resolution, ensure_ascii=False, indent=2),
        evidence=evidence_json,
    )

    fallback_order = ["mistral", "gpt", "claude", "perplexity"]
    result = bio._call_with_fallback(
        system=NARRATIVE_SYSTEM,
        prompt=prompt,
        tag=f"narrativa evento: {event_name}",
        preferred=provider,
        fallback_order=fallback_order,
    )

    if result.get("error"):
        # Fallback: narrazione senza AI
        report = _build_narrative_without_ai(evidence)
        report.ai_used = False
        report.ai_model = None
        return report

    raw = result.get("risposta", "")
    json_data, narrative_text = _split_json_and_narrative(raw)

    if json_data is None:
        json_data = {}

    # Costruisce sezioni dalla narrazione AI
    sections: List[Paragraph] = []
    section_names = [
        "Inquadramento dell'evento",
        "Narrazione storica",
        "Cronologia e fasi",
        "Luoghi e spostamenti",
        "Reparti e soggetti coinvolti",
        "Cause e conseguenze",
        "Fatti concordanti tra le fonti",
        "Versioni divergenti",
        "Elementi incerti o non verificabili",
    ]

    # Split narrazione per sezioni
    current_section = ""
    current_text = ""
    for line in narrative_text.split("\n"):
        line_stripped = line.strip()
        # Rileva header sezione
        for sn in section_names:
            if line_stripped.startswith(sn) or line_stripped.startswith(f"## {sn}") or line_stripped.startswith(f"# {sn}"):
                if current_section:
                    # Estrai source IDs dal testo
                    src_ids = re.findall(r"\[([A-Z]+-[A-Z0-9-]+)\]", current_text)
                    sections.append(Paragraph(
                        section=current_section,
                        text=current_text.strip(),
                        source_ids=list(set(src_ids)),
                    ))
                current_section = sn
                current_text = ""
                break
        else:
            current_text += line + "\n"

    if current_section:
        src_ids = re.findall(r"\[([A-Z]+-[A-Z0-9-]+)\]", current_text)
        sections.append(Paragraph(
            section=current_section,
            text=current_text.strip(),
            source_ids=list(set(src_ids)),
        ))

    # Se nessuna sezione rilevata, usa tutto come narrazione
    if not sections:
        src_ids = re.findall(r"\[([A-Z]+-[A-Z0-9-]+)\]", narrative_text)
        sections.append(Paragraph(
            section="Narrazione storica",
            text=narrative_text.strip(),
            source_ids=list(set(src_ids)),
        ))

    return NarrativeReport(
        event_name=event_name,
        event_id=evidence.event_id,
        resolution=evidence.resolution,
        sections=sections,
        inquadramento=json_data.get("inquadramento", ""),
        narrazione=narrative_text,
        cronologia=json_data.get("cronologia", []),
        luoghi=json_data.get("luoghi", []),
        reparti=json_data.get("reparti", []),
        cause_conseguenze=json_data.get("cause_conseguenze", ""),
        fatti_concordanti=json_data.get("fatti_concordanti", []),
        versioni_divergenti=json_data.get("versioni_divergenti", []),
        elementi_incerti=json_data.get("elementi_incerti", []),
        fonti_archivistiche=[s.to_dict() for s in evidence.archival_sources],
        fonti_bibliografiche=[s.to_dict() for s in evidence.bibliographic_sources + evidence.web_sources],
        grafo=evidence.graph_data,
        persone_collegate=evidence.related_people,
        evidence_package=evidence.to_dict(),
        ai_used=True,
        ai_model=result.get("provider"),
    )


# ─── API principale ──────────────────────────────────────────────────────────

def build_narrative(query: str, use_ai: bool = True, provider: str = "mistral") -> Dict[str, Any]:
    """Pipeline completa: raccoglie evidenze e genera narrazione.

    Args:
        query: nome evento da cercare
        use_ai: se True, usa AI per la narrazione (solo dal pacchetto evidenze)
        provider: provider AI preferito

    Returns:
        Dict con il report narrativo completo
    """
    from event_evidence_pipeline import collect_evidence

    evidence = collect_evidence(query)

    if use_ai and evidence.sources:
        report = _build_narrative_with_ai(evidence, provider=provider)
    else:
        report = _build_narrative_without_ai(evidence)

    return report.to_dict()

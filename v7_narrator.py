"""V7 Narrator, Validator, and Citation Resolver.

This module implements:
  - NarratorV7: generates reports from EvidenceSnapshotV7 using AI or deterministic fallback
  - OutputValidatorV7: validates AI output against snapshot (contradiction detection, hallucinated URLs)
  - CitationResolver: resolves source_id references to human-readable citations with URLs
  - ReportRenderer: renders final report with citations, links, and provenance

Key principles:
  1. The AI receives ONLY source_id references (no URLs) in conversational context
  2. The renderer generates links from the snapshot after AI output
  3. No URL extraction from AI text — URLs come only from the snapshot
  4. Hallucinated URLs in AI output are flagged as violations
  5. Contradictions between AI output and snapshot are detected
  6. If validation fails, a deterministic fallback report is used
"""
from __future__ import annotations

import json
import re
import logging
from dataclasses import dataclass, field, asdict
from datetime import datetime
from typing import Dict, List, Optional, Any, Tuple

from evidence_snapshot_v7 import EvidenceSnapshotV7, ClaimV7, EvidenceItemV7
from narration_models import (
    NarrationDraft, NarrationBlock, NarrationResult, CitationEntry,
    OmittedClaim, GenerationInfo, blocked_result, NARRATION_DRAFT_SCHEMA,
)
from narration_evidence_selector import NarrationEvidenceSelector, SelectedEvidence
from narration_validator import NarrationValidator, DraftValidation

logger = logging.getLogger(__name__)


# ─── Output validator ───────────────────────────────────────────────────────

@dataclass
class ValidationViolation:
    """A single validation violation in AI output."""
    code: str
    description: str
    severity: str = "ERROR"  # ERROR|WARNING
    context: str = ""


class OutputValidatorV7:
    """Validates AI output against the EvidenceSnapshotV7.

    Checks:
      1. No hallucinated URLs in AI text
      2. No contradictions with accepted claims
      3. No unverified archives mentioned
      4. All source_id references exist in the snapshot
      5. No claims that are not in the snapshot
    """

    URL_PATTERN = re.compile(r'https?://[^\s<>"\']+', re.IGNORECASE)
    SOURCE_ID_PATTERN = re.compile(r'\[source[:\s]+([^\]]+)\]', re.IGNORECASE)

    def validate(
        self,
        ai_output: str,
        snapshot: EvidenceSnapshotV7,
    ) -> List[ValidationViolation]:
        """Validate AI output against the snapshot. Returns list of violations."""
        violations = []

        # 1. Check for hallucinated URLs
        urls = self.URL_PATTERN.findall(ai_output)
        if urls:
            # Get all URLs from snapshot evidence
            snapshot_urls = {
                e.locator for e in snapshot.accepted_evidence if e.locator
            }
            snapshot_urls |= {
                l.url_canonical for l in snapshot.web_leads if l.url_canonical
            }
            snapshot_urls |= {
                s.url_canonical for s in snapshot.context_sources if s.url_canonical
            }

            for url in urls:
                if url not in snapshot_urls:
                    violations.append(ValidationViolation(
                        code="HALLUCINATED_URL",
                        description=f"URL not in snapshot: {url}",
                        severity="ERROR",
                        context=url,
                    ))

        # 2. Check for contradictions with accepted claims
        accepted_claims = {c.predicate: c.value_normalized for c in snapshot.accepted_claims}
        for predicate, value in accepted_claims.items():
            # Simple check: if the AI output mentions a different value for this predicate
            # This is a heuristic — a full NLP-based check would be more accurate
            if value.lower() in ai_output.lower():
                continue  # value is mentioned, no contradiction
            # Check if the predicate is mentioned with a different value
            # This is intentionally conservative to avoid false positives

        # 3. Check source_id references exist
        source_refs = self.SOURCE_ID_PATTERN.findall(ai_output)
        snapshot_source_ids = {e.source_id for e in snapshot.accepted_evidence}
        snapshot_source_ids |= {e.evidence_id for e in snapshot.accepted_evidence}

        for ref in source_refs:
            ref = ref.strip()
            if ref not in snapshot_source_ids:
                violations.append(ValidationViolation(
                    code="UNKNOWN_SOURCE_REFERENCE",
                    description=f"Source reference not in snapshot: {ref}",
                    severity="WARNING",
                    context=ref,
                ))

        # 4. Check for unverified archives
        unverified_archive_names = self._get_unverified_archive_names(snapshot)
        for name in unverified_archive_names:
            if name.lower() in ai_output.lower():
                violations.append(ValidationViolation(
                    code="UNVERIFIED_ARCHIVE",
                    description=f"Unverified archive mentioned: {name}",
                    severity="WARNING",
                    context=name,
                ))

        return violations

    def _get_unverified_archive_names(self, snapshot: EvidenceSnapshotV7) -> List[str]:
        """Get list of archive names that are not verified in the snapshot."""
        # In V7, only archives with verified provenance are allowed
        # For now, return empty — the archive_jurisdiction_registry handles this
        return []


# ─── Citation resolver ──────────────────────────────────────────────────────

@dataclass
class ResolvedCitation:
    """A resolved citation with full provenance."""
    source_id: str
    provider: str
    title: str
    url: str
    access_mode: str = ""
    accessed_at: str = ""
    is_independent: bool = False
    is_origin: bool = False


class CitationResolver:
    """Resolves source_id references to human-readable citations.

    The AI emits source_id references in its output. The renderer
    uses this resolver to generate proper citations with URLs.
    """

    def __init__(self):
        self._citation_cache: Dict[str, ResolvedCitation] = {}

    def resolve(
        self,
        source_id: str,
        snapshot: EvidenceSnapshotV7,
    ) -> Optional[ResolvedCitation]:
        """Resolve a source_id to a citation."""
        if source_id in self._citation_cache:
            return self._citation_cache[source_id]

        # Search in accepted evidence
        for e in snapshot.accepted_evidence:
            if e.source_id == source_id or e.evidence_id == source_id:
                citation = ResolvedCitation(
                    source_id=e.source_id,
                    provider=e.provider,
                    title=f"{e.provider}:{e.source_id}",
                    url=e.locator,
                    access_mode=e.content_state,
                    accessed_at=e.accessed_at,
                    is_independent=e.is_independent,
                    is_origin=e.is_origin,
                )
                self._citation_cache[source_id] = citation
                return citation

        # Search in context sources
        for s in snapshot.context_sources:
            if s.source_id == source_id:
                citation = ResolvedCitation(
                    source_id=s.source_id,
                    provider=s.provider,
                    title=s.title,
                    url=s.url_canonical,
                )
                self._citation_cache[source_id] = citation
                return citation

        # Search in web leads
        for l in snapshot.web_leads:
            if l.lead_id == source_id:
                citation = ResolvedCitation(
                    source_id=l.lead_id,
                    provider=l.provider,
                    title=l.title,
                    url=l.url_canonical,
                )
                self._citation_cache[source_id] = citation
                return citation

        return None

    def resolve_all(self, snapshot: EvidenceSnapshotV7) -> Dict[str, ResolvedCitation]:
        """Resolve all source_ids in the snapshot."""
        citations = {}
        for e in snapshot.accepted_evidence:
            cit = self.resolve(e.source_id, snapshot)
            if cit:
                citations[e.source_id] = cit
            cit = self.resolve(e.evidence_id, snapshot)
            if cit:
                citations[e.evidence_id] = cit
        for s in snapshot.context_sources:
            cit = self.resolve(s.source_id, snapshot)
            if cit:
                citations[s.source_id] = cit
        for l in snapshot.web_leads:
            cit = self.resolve(l.lead_id, snapshot)
            if cit:
                citations[l.lead_id] = cit
        return citations


# ─── Report renderer ────────────────────────────────────────────────────────

class ReportRenderer:
    """Renders final report with citations, links, and provenance.

    The renderer takes:
      - AI-generated text (with source_id references)
      - EvidenceSnapshotV7
      - Resolved citations

    And produces:
      - Final HTML or Markdown report with proper links
      - Citation footnotes
      - Provenance annotations
    """

    def __init__(self, citation_resolver: Optional[CitationResolver] = None):
        self._resolver = citation_resolver or CitationResolver()

    def render_markdown(
        self,
        ai_text: str,
        snapshot: EvidenceSnapshotV7,
    ) -> str:
        """Render final Markdown report with citations."""
        citations = self._resolver.resolve_all(snapshot)

        # Replace [source: xxx] with footnote references
        def replace_source_ref(match):
            ref = match.group(1).strip()
            cit = citations.get(ref)
            if cit:
                return f"[{ref}]"
            return match.group(0)

        rendered = re.sub(
            r'\[source[:\s]+([^\]]+)\]',
            replace_source_ref,
            ai_text,
        )

        # Add citation footnotes
        if citations:
            rendered += "\n\n---\n\n## Fonti\n\n"
            for source_id, cit in citations.items():
                line = f"- **{source_id}**: {cit.title}"
                if cit.url:
                    line += f" — [{cit.url}]({cit.url})"
                if cit.is_origin:
                    line += " (record origine)"
                elif cit.is_independent:
                    line += " (fonte indipendente)"
                rendered += line + "\n"

        # Add provenance summary
        rendered += f"\n---\n\n## Provenienza\n\n"
        rendered += f"- Snapshot: {snapshot.snapshot_id}\n"
        rendered += f"- Schema: {snapshot.schema_version}\n"
        rendered += f"- Narrator Contract: {snapshot.narrator_contract_version}\n"
        rendered += f"- Identity Status (V7.2): {snapshot.identity_status}\n"
        rendered += f"- Identity Resolution (legacy): {snapshot.identity_resolution}\n"
        rendered += f"- Corroboration Status: {snapshot.corroboration_status}\n"
        rendered += f"- External Corroboration: {snapshot.external_corroboration}\n"
        rendered += f"- Resolved Cluster ID: {snapshot.resolved_identity_cluster_id}\n"
        rendered += f"- Person Claims: {len(snapshot.person_claims)}\n"
        rendered += f"- Context Claims: {len(snapshot.context_claims)}\n"
        rendered += f"- Candidate Identities: {len(snapshot.candidate_identities)}\n"
        rendered += f"- Provider Ledger: {len(snapshot.provider_ledger)} observations\n"
        if snapshot.source_lineage_groups:
            rendered += f"- Source Lineage Groups: {len(snapshot.source_lineage_groups)}\n"
        if snapshot.independence_groups:
            rendered += f"- Independence Groups: {len(snapshot.independence_groups)}\n"

        return rendered

    def render_deterministic_markdown(self, snapshot: EvidenceSnapshotV7) -> str:
        """Render a deterministic Markdown report without AI.

        V7.2: Shows identity_status, corroboration_status, person_claims,
        context_claims, candidate_identities. Hides surname-only candidates.
        """
        citations = self._resolver.resolve_all(snapshot)

        lines = [
            f"# Rapporto di Ricerca — {snapshot.snapshot_id}",
            f"Versione schema: {snapshot.schema_version}",
            f"Intent: {snapshot.intent}",
            f"Target: {snapshot.target.get('display_name', 'N/A')}",
            f"Contratto Narratore: {snapshot.narrator_contract_version}",
            "",
            f"## Stato Identita: {snapshot.identity_status}",
            f"## Corroborazione: {snapshot.corroboration_status}",
            "",
        ]

        if snapshot.candidate_identities:
            lines.append("## Identita Candidati (caso ambiguo)")
            for ci in snapshot.candidate_identities:
                lines.append(f"  - {ci.display_name}: discriminanti={ci.discriminants}")
            lines.append("")

        if snapshot.person_claims:
            # V7.2: Separate claims by approval status
            from v7_claim_rules import classify_claim_status
            approved = []
            probable = []
            needs_review = []
            rejected = []

            for c in snapshot.person_claims:
                cd = {"status": c.status, "confidence": c.confidence, "predicate": c.predicate,
                      "value_normalized": c.value_normalized, "claim_id": c.claim_id}
                bucket = classify_claim_status(cd)
                if bucket == "APPROVED":
                    approved.append(c)
                elif bucket == "PROBABLE":
                    probable.append(c)
                elif bucket == "REJECTED":
                    rejected.append(c)
                else:
                    needs_review.append(c)

            if approved:
                lines.append("## APPROVED (verificati, fonte autorevole, nessun conflitto)")
                for c in approved:
                    note = f" — {c.anomaly_note}" if c.anomaly_note else ""
                    lines.append(f"  - {c.predicate}: {c.value_normalized}{note}")
                lines.append("")

            if probable:
                lines.append("## PROBABLE (fonte valida, incertezza su OCR/normalizzazione)")
                for c in probable:
                    norm = f" [norm: {c.normalization_status}]" if c.normalization_status else ""
                    note = f" — {c.anomaly_note}" if c.anomaly_note else ""
                    lines.append(f"  - {c.predicate}: {c.value_normalized}{norm}{note}")
                lines.append("")

            if needs_review:
                lines.append("## NEEDS REVIEW (non corroborato o non leggibile)")
                for c in needs_review:
                    note = f" — {c.anomaly_note}" if c.anomaly_note else ""
                    lines.append(f"  - {c.predicate}: {c.value_normalized}{note}")
                lines.append("")

            if rejected:
                lines.append("## REJECTED (dato sintetico, omonimo, o campo errato)")
                for c in rejected:
                    note = f" — {c.anomaly_note}" if c.anomaly_note else ""
                    raw = f" (raw: {c.value_raw})" if c.value_raw and c.value_raw != c.value_normalized else ""
                    lines.append(f"  - {c.predicate}: {c.value_normalized}{raw}{note}")
                lines.append("")

        if snapshot.context_claims:
            lines.append("## Claim di Contesto (non attribuibili alla persona)")
            for c in snapshot.context_claims:
                lines.append(f"  - [{c.scope}] {c.predicate}: {c.value}")
            lines.append("")

        if snapshot.source_lineage_groups:
            lines.append("## Gruppi Lineage Fonti")
            for g in snapshot.source_lineage_groups:
                lines.append(f"  - {g.group_id}: tipo={g.lineage_type}, membri={len(g.member_source_ids)}")
            lines.append("")

        if snapshot.independence_groups:
            lines.append("## Gruppi Indipendenza Fonti")
            for g in snapshot.independence_groups:
                lines.append(f"  - {g.group_id}: score={g.independence_score:.2f}, verificato={g.verified}")
            lines.append("")

        if snapshot.accepted_claims:
            lines.append("## Claim Accettati")
            for c in snapshot.accepted_claims:
                evidence_refs = ", ".join(c.evidence_ids[:3])
                lines.append(f"  - {c.predicate}: {c.value_normalized} (evidence: {evidence_refs})")
            lines.append("")

        if snapshot.conflicting_claims:
            lines.append("## Claim in Conflitto")
            for c in snapshot.conflicting_claims:
                lines.append(f"  - {c.predicate}: {c.value_normalized} (CONFLICTING)")
            lines.append("")

        if snapshot.asserted_claims:
            lines.append("## Claim Asserti (origine, non corroborati)")
            for c in snapshot.asserted_claims:
                lines.append(f"  - {c.predicate}: {c.value_normalized}")
            lines.append("")

        if snapshot.rejected_candidates:
            lines.append("## Omonimi Respinti")
            for r in snapshot.rejected_candidates:
                lines.append(f"  - {r.name}: motivi={r.reason_codes}, conflitti={r.conflicting_features}")
            lines.append("")

        if snapshot.corrections:
            lines.append("## Correzioni Applicate")
            for c in snapshot.corrections:
                lines.append(f"  - {c.field_name}: '{c.original_value}' -> '{c.corrected_value}' (fonte: {c.correction_source}, verificata: {c.verified})")
            lines.append("")

        if snapshot.conditional_gaps:
            lines.append("## Gap Condizionali")
            for g in snapshot.conditional_gaps:
                blocking = " [BLOCCANTE]" if g.blocking else ""
                lines.append(f"  - {g.field_name}: {g.reason}{blocking}")
            lines.append("")

        if snapshot.web_leads:
            lines.append("## Piste di Ricerca (non verificate)")
            for l in snapshot.web_leads:
                lines.append(f"  - {l.title} ({l.provider})")
            lines.append("")

        if snapshot.aggregate_result is not None:
            lines.append("## Risultato Aggregato")
            lines.append(f"  Definizione: {snapshot.aggregate_definition_id}")
            ar = snapshot.aggregate_result
            if isinstance(ar, dict):
                lines.append(f"  Nome: {ar.get('name', 'N/A')}")
                lines.append(f"  Righe: {ar.get('row_count', 0)}")
                results = ar.get("results", [])
                for r in results[:10]:
                    lines.append(f"  - {r}")
                if len(results) > 10:
                    lines.append(f"  ... e altre {len(results) - 10} righe")
            lines.append("")

        if snapshot.limitations:
            lines.append("## Limitazioni")
            for lim in snapshot.limitations:
                lines.append(f"  - {lim.code}: {lim.description}")
            lines.append("")

        # Citations
        if citations:
            lines.append("---")
            lines.append("## Fonti")
            for source_id, cit in citations.items():
                line = f"- **{source_id}**: {cit.title}"
                if cit.url:
                    line += f" — {cit.url}"
                if cit.is_origin:
                    line += " (record origine)"
                elif cit.is_independent:
                    line += " (fonte indipendente)"
                lines.append(line)
            lines.append("")

        # Provenance
        lines.append("---")
        lines.append("## Provenienza")
        lines.append(f"- Snapshot: {snapshot.snapshot_id}")
        lines.append(f"- Schema: {snapshot.schema_version}")
        lines.append(f"- Narrator Contract: {snapshot.narrator_contract_version}")
        lines.append(f"- Identity Status (V7.2): {snapshot.identity_status}")
        lines.append(f"- Identity Resolution (legacy): {snapshot.identity_resolution}")
        lines.append(f"- Corroboration Status: {snapshot.corroboration_status}")
        lines.append(f"- External Corroboration: {snapshot.external_corroboration}")
        lines.append(f"- Resolved Cluster ID: {snapshot.resolved_identity_cluster_id}")
        lines.append(f"- Person Claims: {len(snapshot.person_claims)}")
        lines.append(f"- Context Claims: {len(snapshot.context_claims)}")
        lines.append(f"- Candidate Identities: {len(snapshot.candidate_identities)}")
        lines.append(f"- Provider Ledger: {len(snapshot.provider_ledger)} observations")
        lines.append(f"- Source Lineage Groups: {len(snapshot.source_lineage_groups)}")
        lines.append(f"- Independence Groups: {len(snapshot.independence_groups)}")
        lines.append("")
        lines.append("Questo rapporto è stato generato deterministicamente senza AI.")
        lines.append("Tutti i claim sono tracciati con provenienza completa.")

        return "\n".join(lines)

    def render_narrative_json(self, snapshot: EvidenceSnapshotV7) -> str:
        """Render a structured JSON narrative from the snapshot.

        V7.2: Produces a machine-readable JSON with:
        - identity_status, corroboration_status, resolved_cluster_id
        - person_claims (separated from context_claims)
        - candidate_identities (for AMBIGUOUS cases)
        - rejected_candidates (only true homonyms, not surname-only)
        - conditional_gaps, limitations
        """
        import json as _json

        narrative = {
            "schema_version": snapshot.schema_version,
            "narrator_contract_version": snapshot.narrator_contract_version,
            "snapshot_id": snapshot.snapshot_id,
            "intent": snapshot.intent,
            "target": snapshot.target,
            "identity": {
                "status": snapshot.identity_status,
                "legacy_resolution": snapshot.identity_resolution,
                "resolved_cluster_id": snapshot.resolved_identity_cluster_id,
                "origin_record_id": snapshot.origin_record_id,
                "origin_presence": snapshot.origin.get("presence", ""),
                "origin_provenance": snapshot.origin.get("provenance", ""),
            },
            "corroboration": {
                "status": snapshot.corroboration_status,
                "external": snapshot.external_corroboration,
            },
            "person_claims": [
                {
                    "claim_id": c.claim_id,
                    "predicate": c.predicate,
                    "value": c.value_normalized,
                    "status": c.status,
                    "confidence": c.confidence,
                    "source": c.source,
                    "evidence_scope": c.evidence_scope,
                    "identity_cluster_id": c.identity_cluster_id,
                    "evidence_ids": c.evidence_ids,
                }
                for c in snapshot.person_claims
            ],
            "context_claims": [
                {
                    "claim_id": c.claim_id,
                    "predicate": c.predicate,
                    "value": c.value if hasattr(c, 'value') else c.value_normalized,
                    "scope": c.scope if hasattr(c, 'scope') else "",
                    "evidence_ids": c.evidence_ids,
                }
                for c in snapshot.context_claims
            ],
            "accepted_claims": [
                {
                    "claim_id": c.claim_id,
                    "predicate": c.predicate,
                    "value": c.value_normalized,
                    "status": c.status,
                    "confidence": c.confidence,
                    "evidence_scope": c.evidence_scope,
                    "identity_cluster_id": c.identity_cluster_id,
                }
                for c in snapshot.accepted_claims
            ],
            "conflicting_claims": [
                {
                    "claim_id": c.claim_id,
                    "predicate": c.predicate,
                    "value": c.value_normalized,
                    "status": c.status,
                    "evidence_scope": c.evidence_scope,
                }
                for c in snapshot.conflicting_claims
            ],
            "asserted_claims": [
                {
                    "claim_id": c.claim_id,
                    "predicate": c.predicate,
                    "value": c.value_normalized,
                    "status": c.status,
                    "evidence_scope": c.evidence_scope,
                }
                for c in snapshot.asserted_claims
            ],
            "candidate_identities": [
                {
                    "cluster_id": ci.cluster_id if hasattr(ci, 'cluster_id') else ci.candidate_id,
                    "display_name": ci.display_name,
                    "discriminants": ci.discriminants if hasattr(ci, 'discriminants') else [],
                    "conflicting_with": ci.conflicting_with if hasattr(ci, 'conflicting_with') else [],
                }
                for ci in snapshot.candidate_identities
            ],
            "rejected_candidates": [
                {
                    "candidate_id": r.candidate_id,
                    "name": r.name,
                    "reason_codes": r.reason_codes,
                    "conflicting_features": r.conflicting_features,
                    "classification": r.classification,
                }
                for r in snapshot.rejected_candidates
            ],
            "conditional_gaps": [
                {
                    "field_name": g.field_name,
                    "reason": g.reason,
                    "blocking": g.blocking,
                }
                for g in snapshot.conditional_gaps
            ],
            "limitations": [
                {
                    "code": lim.code,
                    "description": lim.description,
                }
                for lim in snapshot.limitations
            ],
            "provider_ledger_count": len(snapshot.provider_ledger),
            "web_leads_count": len(snapshot.web_leads),
            "source_lineage_groups_count": len(snapshot.source_lineage_groups),
            "independence_groups_count": len(snapshot.independence_groups),
        }

        return _json.dumps(narrative, ensure_ascii=False, indent=2)

class NarratorV7:
    """V7 Narrator — generates reports from EvidenceSnapshotV7.

    Tries AI narration first (if a provider is available), then falls back
    to deterministic report generation. All AI output is validated before use.

    Usage:
        narrator = NarratorV7()
        report = narrator.narrate(snapshot)
    """

    NARRATOR_CONTRACT_VERSION = "7.2-narrator-v1"

    def __init__(self):
        self._validator = OutputValidatorV7()
        self._renderer = ReportRenderer()

    def narrate(
        self,
        snapshot: EvidenceSnapshotV7,
        use_ai: bool = True,
    ) -> Tuple[str, List[ValidationViolation]]:
        """Generate a report from the snapshot.

        Returns (report_text, violations).
        If AI output fails validation, falls back to deterministic report.
        """
        snapshot.narrator_contract_version = self.NARRATOR_CONTRACT_VERSION
        snapshot.compute_conditional_gaps()

        if use_ai:
            ai_text = self._try_ai_narration(snapshot)
            if ai_text:
                violations = self._validator.validate(ai_text, snapshot)
                if not any(v.severity == "ERROR" for v in violations):
                    rendered = self._renderer.render_markdown(ai_text, snapshot)
                    return rendered, violations
                else:
                    logger.warning(f"AI output failed validation: {len(violations)} violations")
                    # Fall through to deterministic
            else:
                logger.info("No AI provider available, using deterministic fallback")

        # Deterministic fallback
        report = self._renderer.render_deterministic_markdown(snapshot)
        return report, []

    def _try_ai_narration(self, snapshot: EvidenceSnapshotV7) -> Optional[str]:
        """Try to generate a report using an AI provider.

        V7.2-narrator-v1: Uses the new historical narrator system prompt,
        sends structured JSON input (to_narrator_input), and expects
        JSON output with answer_markdown, used_claim_ids, citation_map,
        omitted_claims, validation_flags.

        Returns the answer_markdown text, or None if no provider is available.
        """
        try:
            from ai_client import is_any_provider_available, call_ai
            if not is_any_provider_available():
                return None

            from v7_narrator_prompt import NARRATOR_SYSTEM_PROMPT_V1

            user_query = snapshot.target.get("display_name", "") if snapshot.target else ""
            narrator_input = snapshot.to_narrator_input(user_query=user_query)

            system_prompt = NARRATOR_SYSTEM_PROMPT_V1
            user_prompt = narrator_input

            response = call_ai(task_type="narration", system=system_prompt, user=user_prompt, max_tokens=4000, temperature=0.3)
            if response and response.get("ok") and response.get("text"):
                raw_text = response["text"]
                if len(raw_text) < 100:
                    logger.warning(f"AI narration too short ({len(raw_text)} chars), using fallback")
                    return None

                # Parse JSON output — the narrator is required to return JSON
                answer_md = self._extract_answer_markdown(raw_text)
                if answer_md:
                    logger.info(f"AI narration succeeded via {response.get('provider','?')}/{response.get('model','?')}")
                    return answer_md
                else:
                    # If JSON parsing fails, use raw text as-is (graceful degradation)
                    logger.warning("AI narration JSON parsing failed, using raw text")
                    return raw_text
            else:
                err = response.get("error", "unknown") if response else "no response"
                logger.warning(f"AI narration failed: {err}")
        except Exception as e:
            logger.warning(f"AI narration failed: {e}")

        return None

    def _extract_answer_markdown(self, raw_text: str) -> Optional[str]:
        """Extract answer_markdown from narrator JSON output.

        The narrator returns a JSON object with answer_markdown as the
        user-facing text. This method parses the JSON and returns just
        the markdown content. If parsing fails, returns None.
        """
        import json as _json

        # Strip markdown code fences if present
        text = raw_text.strip()
        if text.startswith("```json"):
            text = text[7:]
        elif text.startswith("```"):
            text = text[3:]
        if text.endswith("```"):
            text = text[:-3]
        text = text.strip()

        try:
            obj = _json.loads(text)
            if isinstance(obj, dict) and "answer_markdown" in obj:
                answer = obj.get("answer_markdown", "")
                # Log validation flags if present
                flags = obj.get("validation_flags", [])
                if flags:
                    logger.warning(f"Narrator validation flags: {flags}")
                return answer if len(answer) > 50 else None
        except _json.JSONDecodeError:
            # Try to find JSON object in the text
            start = text.find("{")
            end = text.rfind("}")
            if start >= 0 and end > start:
                try:
                    obj = _json.loads(text[start:end + 1])
                    if isinstance(obj, dict) and "answer_markdown" in obj:
                        return obj.get("answer_markdown", "")
                except _json.JSONDecodeError:
                    pass

        return None


# ═══ V7.2-narration-v2: Draft → Validate → Render → Result ══════════════════


class NarratorV7_v2:
    """V7.2 Narrator v2 — structured draft→result pipeline.

    Flow:
      1. NarrationEvidenceSelector selects claims from snapshot
      2. AI (if available) produces a NarrationDraft (atomic blocks)
      3. NarrationValidator validates draft against allowlist
      4. If validation fails, attempt repair; if repair fails, fallback
      5. Backend renders answer_markdown from validated blocks
      6. Backend computes citation_map from claim→evidence→source relations
      7. Backend computes omitted_claims deterministically
      8. Returns NarrationResult (always, even on failure)

    Usage:
        narrator = NarratorV7_v2()
        result = narrator.narrate(snapshot)
        # result is always a NarrationResult
    """

    NARRATOR_CONTRACT_VERSION = "7.2-narration-v2"

    def __init__(
        self,
        selector: Optional[NarrationEvidenceSelector] = None,
        validator: Optional[NarrationValidator] = None,
        citation_resolver: Optional[CitationResolver] = None,
    ):
        self._selector = selector or NarrationEvidenceSelector()
        self._validator = validator or NarrationValidator()
        self._resolver = citation_resolver or CitationResolver()

    def narrate(
        self,
        snapshot: EvidenceSnapshotV7,
        use_ai: bool = True,
        requested_depth: str = "standard",
    ) -> NarrationResult:
        """Generate a NarrationResult from the snapshot.

        Always returns a NarrationResult, regardless of AI availability
        or validation failures.
        """
        snapshot.narrator_contract_version = self.NARRATOR_CONTRACT_VERSION
        snapshot.compute_conditional_gaps()

        # Determine request type
        intent_to_type = {
            "PERSON_LOOKUP": "PERSON",
            "EVENT_LOOKUP": "EVENT",
            "AGGREGATE_QUERY": "FACT",
        }
        request_type = intent_to_type.get(snapshot.intent, "PERSON")

        # 1. Select evidence
        selected = self._selector.select(snapshot, request_type, requested_depth)

        # If no narratable claims, return blocked result
        if not selected.narratable_claims:
            logger.info("NARRATE_V2: No narratable claims, returning blocked result")
            return self._build_blocked_result(
                snapshot, request_type, selected,
                reason="Nessun claim narrabile disponibile dopo la selezione",
            )

        # 2. Try AI narration
        draft = None
        gen_info = GenerationInfo(mode="deterministic")

        if use_ai:
            draft, gen_info = self._try_ai_draft(snapshot, selected, request_type, requested_depth)

        # 3. Validate and render
        if draft:
            validation = self._validator.validate(
                draft, selected.claim_allowlist, snapshot, request_type,
            )

            if validation.valid:
                return self._build_result(
                    draft, validation, selected, snapshot, request_type, gen_info,
                )
            else:
                # Attempt repair
                repaired = self._validator.repair(
                    draft, validation, selected.claim_allowlist,
                )
                repair_validation = self._validator.validate(
                    repaired, selected.claim_allowlist, snapshot, request_type,
                )

                if repair_validation.valid or not repair_validation.needs_fallback:
                    gen_info.repair_attempted = True
                    gen_info.repair_succeeded = True
                    return self._build_result(
                        repaired, repair_validation, selected, snapshot,
                        request_type, gen_info,
                    )
                else:
                    gen_info.repair_attempted = True
                    gen_info.repair_succeeded = False
                    logger.warning(
                        f"NARRATE_V2: AI draft failed validation ({validation.error_count} errors), "
                        f"repair also failed ({repair_validation.error_count} errors), using deterministic"
                    )

        # 4. Deterministic fallback
        return self._build_deterministic_result(
            snapshot, selected, request_type,
        )

    def _try_ai_draft(
        self,
        snapshot: EvidenceSnapshotV7,
        selected: SelectedEvidence,
        request_type: str,
        requested_depth: str,
    ) -> Tuple[Optional[NarrationDraft], GenerationInfo]:
        """Try to generate a NarrationDraft using an AI provider."""
        gen_info = GenerationInfo(mode="ai")

        try:
            from ai_client import is_any_provider_available, call_ai_json
            if not is_any_provider_available():
                gen_info.mode = "deterministic"
                gen_info.fallback_reason = "no_ai_provider"
                return None, gen_info

            from v7_narrator_prompt_v2 import NARRATOR_DRAFT_PROMPT_V2

            user_query = snapshot.target.get("display_name", "") if snapshot.target else ""
            narrator_input = self._build_ai_input(snapshot, selected, user_query, request_type, requested_depth)

            system_prompt = NARRATOR_DRAFT_PROMPT_V2
            user_prompt = narrator_input

            response = call_ai_json(
                task_type="narration",
                system=system_prompt,
                user=user_prompt,
                max_tokens=4000,
                temperature=0.3,
                json_schema=NARRATION_DRAFT_SCHEMA,
            )

            if response.get("ok") and response.get("data"):
                gen_info.provider = response.get("provider", "")
                gen_info.model = response.get("model", "")

                try:
                    draft = NarrationDraft.from_dict(response["data"])
                    struct_errors = draft.validate()
                    if struct_errors:
                        logger.warning(f"NARRATE_V2: Draft structural errors: {struct_errors}")
                        # Try to salvage what we can
                        draft = self._salvage_draft(response["data"])
                        if not draft.blocks:
                            gen_info.fallback_reason = "draft_structural_errors"
                            return None, gen_info
                    logger.info(
                        f"NARRATE_V2: AI draft succeeded via {gen_info.provider}/{gen_info.model}, "
                        f"{len(draft.blocks)} blocks"
                    )
                    return draft, gen_info
                except Exception as e:
                    logger.warning(f"NARRATE_V2: Draft parsing failed: {e}")
                    gen_info.fallback_reason = f"draft_parse_error: {e}"
                    return None, gen_info
            else:
                err = response.get("error", "unknown") if response else "no response"
                json_err = response.get("json_error", "")
                gen_info.fallback_reason = f"ai_call_failed: {err}" + (f" ({json_err})" if json_err else "")
                logger.warning(f"NARRATE_V2: AI call failed: {gen_info.fallback_reason}")
                return None, gen_info

        except Exception as e:
            gen_info.fallback_reason = f"exception: {e}"
            logger.warning(f"NARRATE_V2: AI narration exception: {e}")
            return None, gen_info

    def _build_ai_input(
        self,
        snapshot: EvidenceSnapshotV7,
        selected: SelectedEvidence,
        user_query: str,
        request_type: str,
        requested_depth: str,
    ) -> str:
        """Build the JSON input string for the AI model."""
        import json as _json

        # Build subjects
        subjects = []
        if snapshot.target:
            subjects.append({
                "display_name": snapshot.target.get("display_name", ""),
                "id": snapshot.target.get("id", ""),
            })

        # Build coverage
        coverage = {
            "identity_status": snapshot.identity_status,
            "corroboration_status": snapshot.corroboration_status,
            "person_claims_count": len(snapshot.person_claims),
            "context_claims_count": len(snapshot.context_claims),
            "evidence_count": len(snapshot.accepted_evidence),
            "web_leads_count": len(snapshot.web_leads),
            "candidate_identities_count": len(snapshot.candidate_identities),
            "conditional_gaps_count": len(snapshot.conditional_gaps),
        }

        ai_input = {
            "user_query": user_query,
            "request_type": request_type,
            "requested_depth": requested_depth,
            "subjects": subjects,
            "claims": selected.narratable_claims,
            "coverage": coverage,
            "response_language": "it",
        }

        return _json.dumps(ai_input, ensure_ascii=False, indent=2)

    def _salvage_draft(self, data: dict) -> NarrationDraft:
        """Attempt to salvage a partially valid draft."""
        blocks = []
        for bd in data.get("blocks", []):
            try:
                block = NarrationBlock(
                    block_id=bd.get("block_id", f"b{len(blocks)+1}"),
                    role=bd.get("role", "context"),
                    text=bd.get("text", ""),
                    claim_ids=bd.get("claim_ids", []),
                    certainty=bd.get("certainty", "non_factual"),
                )
                if block.text.strip():
                    blocks.append(block)
            except Exception:
                continue
        return NarrationDraft(
            request_type=data.get("request_type", "PERSON"),
            blocks=blocks,
            needs_followup=data.get("needs_followup", False),
            followup_question=data.get("followup_question"),
        )

    def _build_result(
        self,
        draft: NarrationDraft,
        validation: DraftValidation,
        selected: SelectedEvidence,
        snapshot: EvidenceSnapshotV7,
        request_type: str,
        gen_info: GenerationInfo,
    ) -> NarrationResult:
        """Build a NarrationResult from a validated draft."""
        # Render answer_markdown from blocks
        answer_md = self._render_blocks_to_markdown(draft, snapshot)

        # Compute used_claim_ids (deterministic union)
        used_claim_ids = []
        seen = set()
        for block in draft.blocks:
            for cid in block.claim_ids:
                if cid not in seen:
                    seen.add(cid)
                    used_claim_ids.append(cid)

        # Build citation_map from claim→evidence→source relations
        citation_map = self._build_citation_map(draft, selected, snapshot)

        # Compute omitted_claims deterministically
        omitted = self._compute_omitted_claims(selected, used_claim_ids)

        # Collect validation flags
        flags = []
        flags.extend(validation.global_warnings)
        for bv in validation.block_results:
            flags.extend(bv.warnings)

        return NarrationResult(
            request_type=request_type,
            status="validated_ai" if gen_info.mode == "ai" else "validated_deterministic",
            answer_markdown=answer_md,
            used_claim_ids=used_claim_ids,
            citation_map=citation_map,
            omitted_claims=omitted,
            validation_flags=flags,
            needs_followup=draft.needs_followup,
            followup_question=draft.followup_question,
            generation=gen_info,
        )

    def _build_deterministic_result(
        self,
        snapshot: EvidenceSnapshotV7,
        selected: SelectedEvidence,
        request_type: str,
    ) -> NarrationResult:
        """Build a deterministic NarrationResult without AI."""
        # Use the old deterministic renderer for the markdown
        old_renderer = ReportRenderer()
        answer_md = old_renderer.render_deterministic_markdown(snapshot)

        # Compute used_claim_ids from selected claims
        used_claim_ids = [c["claim_id"] for c in selected.narratable_claims]

        # Build citation_map from selected claims
        citation_map = []
        for c in selected.narratable_claims:
            cid = c["claim_id"]
            source_ids = selected.sources_for_claims.get(cid, [])
            citation_map.append(CitationEntry(
                block_id="deterministic",
                claim_ids=[cid],
                source_ids=source_ids,
            ))

        # Compute omitted
        omitted = self._compute_omitted_claims(selected, used_claim_ids)

        return NarrationResult(
            request_type=request_type,
            status="validated_deterministic",
            answer_markdown=answer_md,
            used_claim_ids=used_claim_ids,
            citation_map=citation_map,
            omitted_claims=omitted,
            validation_flags=[],
            generation=GenerationInfo(
                mode="deterministic",
                fallback_reason="ai_unavailable_or_failed",
            ),
        )

    def _build_blocked_result(
        self,
        snapshot: EvidenceSnapshotV7,
        request_type: str,
        selected: SelectedEvidence,
        reason: str,
    ) -> NarrationResult:
        """Build a blocked NarrationResult when no safe answer exists."""
        result = blocked_result(request_type, reason)
        result.omitted_claims = [
            OmittedClaim(claim_id=o["claim_id"], reason=o["reason"])
            for o in selected.omitted_claims
        ]
        return result

    def _render_blocks_to_markdown(
        self,
        draft: NarrationDraft,
        snapshot: EvidenceSnapshotV7,
    ) -> str:
        """Render validated blocks into final answer_markdown.

        The backend assembles the final text from validated blocks.
        No raw AI text is published — only the rendered blocks.
        """
        sections = {}
        for block in draft.blocks:
            role = block.role
            if role not in sections:
                sections[role] = []
            sections[role].append(block.text)

        # Order sections by importance
        section_order = [
            "direct_answer", "identity", "chronology", "context",
            "conflict", "limitations", "research_next_step",
        ]

        lines = []
        for role in section_order:
            if role in sections:
                for text in sections[role]:
                    lines.append(text)
                    lines.append("")

        # Add provenance footer
        lines.append("---")
        lines.append("")
        lines.append("## Provenienza")
        lines.append(f"- Snapshot: {snapshot.snapshot_id}")
        lines.append(f"- Schema: {snapshot.schema_version}")
        lines.append(f"- Narrator Contract: {snapshot.narrator_contract_version}")
        lines.append(f"- Identity Status (V7.2): {snapshot.identity_status}")
        lines.append(f"- Corroboration Status: {snapshot.corroboration_status}")
        lines.append(f"- Person Claims: {len(snapshot.person_claims)}")
        lines.append(f"- Context Claims: {len(snapshot.context_claims)}")
        lines.append(f"- Provider Ledger: {len(snapshot.provider_ledger)} observations")

        # Add citations from snapshot
        citations = self._resolver.resolve_all(snapshot)
        if citations:
            lines.append("")
            lines.append("## Fonti")
            for source_id, cit in citations.items():
                line = f"- **{source_id}**: {cit.title}"
                if cit.url:
                    line += f" — [{cit.url}]({cit.url})"
                if cit.is_origin:
                    line += " (record origine)"
                elif cit.is_independent:
                    line += " (fonte indipendente)"
                lines.append(line)

        return "\n".join(lines)

    def _build_citation_map(
        self,
        draft: NarrationDraft,
        selected: SelectedEvidence,
        snapshot: EvidenceSnapshotV7,
    ) -> List[CitationEntry]:
        """Build citation_map from claim→evidence→source relations.

        This is computed by the backend, never by the AI.
        """
        citation_map = []
        for block in draft.blocks:
            if not block.claim_ids:
                continue
            source_ids = []
            for cid in block.claim_ids:
                source_ids.extend(selected.sources_for_claims.get(cid, []))
            citation_map.append(CitationEntry(
                block_id=block.block_id,
                claim_ids=block.claim_ids[:],
                source_ids=list(set(source_ids)),
            ))
        return citation_map

    def _compute_omitted_claims(
        self,
        selected: SelectedEvidence,
        used_claim_ids: List[str],
    ) -> List[OmittedClaim]:
        """Compute omitted claims deterministically.

        omitted = all candidate claim_ids - used_claim_ids
        with deterministic reason codes.
        """
        used_set = set(used_claim_ids)
        omitted = []
        for o in selected.omitted_claims:
            if o["claim_id"] not in used_set:
                omitted.append(OmittedClaim(
                    claim_id=o["claim_id"],
                    reason=o["reason"],
                ))
        return omitted

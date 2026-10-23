"""V7.2 Claim Rule Engine — rule-based claim validation and reclassification.

Inspired by the GPT manual pipeline's step 9: each claim is individually
validated against semantic rules, not just scored numerically.

Rules implemented:
  - DATE_PRECISION: if only year is known, reject generated day/month
  - SEMANTIC_ROLE: "sepolto a" → burial_place, not internment_place
  - SOURCE_FUNCTION: event context source cannot prove person identity
  - OCR_READABILITY: if OCR doesn't allow reading the name, needs_image_review
  - HOMONYM_GUARD: only name match without second identifier → reject auto link
  - ABSENCE_NOT_PROOF: no web results ≠ person doesn't exist
  - NO_CONTEXT_AS_PERSON: a page about an event cannot become person evidence

Each rule is applied independently and can:
  - Change claim status (ASSERTED → PROBABLE, REJECTED, etc.)
  - Reclassify predicate (sorte → buried_at)
  - Adjust confidence
  - Add rule_notes explaining the decision
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any


@dataclass
class ClaimRuleResult:
    """Result of applying a rule to a claim."""
    rule_name: str
    applied: bool
    original_status: str
    new_status: str
    original_predicate: str = ""
    new_predicate: str = ""
    confidence_adjusted: bool = False
    note: str = ""


# ─── Rule definitions ────────────────────────────────────────────────────────

def rule_date_precision(claim: Dict[str, Any]) -> Optional[ClaimRuleResult]:
    """RULE: If only year is known, reject generated day/month.

    Example: 1921-01-01 → keep 1921, reject 01-01 as synthetic.
    """
    predicate = claim.get("predicate", "")
    value = str(claim.get("value_normalized", ""))
    raw = str(claim.get("value_raw", ""))

    # Check for synthetic date pattern
    m = re.match(r"^(\d{4})-01-01$", value)
    if m:
        year = m.group(1)
        claim["value_raw"] = value
        claim["value_normalized"] = year
        claim["normalization_status"] = "year_only_from_synthetic"
        old_status = claim.get("status", "ASSERTED")
        claim["status"] = "REJECTED_PRECISION"
        claim["confidence"] = min(claim.get("confidence", 0.5), 0.3)
        return ClaimRuleResult(
            rule_name="DATE_PRECISION",
            applied=True,
            original_status=old_status,
            new_status="REJECTED_PRECISION",
            note=f"Data sintetica: {value} → mantenuto solo anno {year}",
        )

    return None


def rule_semantic_role_burial(claim: Dict[str, Any]) -> Optional[ClaimRuleResult]:
    """RULE: "sepolto a" → burial_place, not internment_place.

    If the source text says "sepolto a X", the predicate must be buried_at,
    not interned_at. The semantic role of the source text determines the
    predicate, not the field name in the DB.
    """
    predicate = claim.get("predicate", "")
    value = str(claim.get("value_normalized", "")).lower()
    raw = str(claim.get("value_raw", "")).lower()

    burial_indicators = ["sepolto a", "sepolta a", "sepolto nel", "tomba", "cimitero"]

    if predicate in ("interned_at", "had_fate", "event_location"):
        for indicator in burial_indicators:
            if indicator in value or indicator in raw:
                old_predicate = predicate
                claim["predicate"] = "buried_at"
                claim["value_raw"] = claim.get("value_raw") or claim.get("value_normalized", "")
                claim["normalization_status"] = "reclassified_from_semantic_role"
                old_status = claim.get("status", "ASSERTED")
                claim["status"] = "ASSERTED"
                return ClaimRuleResult(
                    rule_name="SEMANTIC_ROLE_BURIAL",
                    applied=True,
                    original_status=old_status,
                    new_status="ASSERTED",
                    original_predicate=old_predicate,
                    new_predicate="buried_at",
                    note=f"Riclassificato: '{indicator}' indica sepoltura, non {old_predicate}",
                )

    return None


def rule_source_function_guard(claim: Dict[str, Any]) -> Optional[ClaimRuleResult]:
    """RULE: A source that doesn't name the person cannot be person_evidence.

    If the source is classified as event_context or place_normalization,
    it cannot support a person_evidence claim.
    """
    evidence_scope = claim.get("evidence_scope", "")
    source_function = claim.get("source_function", "")

    if evidence_scope == "PERSON_EVIDENCE" and source_function in (
        "event_context", "place_normalization_evidence", "research_lead"
    ):
        old_status = claim.get("status", "ASSERTED")
        claim["status"] = "REJECTED"
        claim["confidence"] = 0.0
        return ClaimRuleResult(
            rule_name="SOURCE_FUNCTION_GUARD",
            applied=True,
            original_status=old_status,
            new_status="REJECTED",
            note=f"Fonte classificata come {source_function} non può supportare person_evidence",
        )

    return None


def rule_ocr_unreadable_name(claim: Dict[str, Any]) -> Optional[ClaimRuleResult]:
    """RULE: If OCR doesn't allow reading the name, mark needs_image_review."""
    predicate = claim.get("predicate", "")
    value = str(claim.get("value_normalized", ""))

    if predicate in ("has_name", "born_at") and value:
        # Check for OCR deformation patterns
        if re.search(r"[bcdfghjklmnpqrstvwxz]{5,}", value, re.I):
            old_status = claim.get("status", "ASSERTED")
            claim["status"] = "NEEDS_IMAGE_REVIEW"
            claim["confidence"] = 0.1
            return ClaimRuleResult(
                rule_name="OCR_UNREADABLE_NAME",
                applied=True,
                original_status=old_status,
                new_status="NEEDS_IMAGE_REVIEW",
                note=f"Nome con possibili deformazioni OCR: {value}",
            )

    return None


def rule_homonym_guard(claim: Dict[str, Any]) -> Optional[ClaimRuleResult]:
    """RULE: Name-only match without second identifier → reject auto link.

    If the only evidence is name coincidence (no date, place, paternity,
    matricola), the claim cannot be ASSERTED.
    """
    has_second_id = any(
        claim.get(f) for f in [
            "birth_year", "birth_place", "paternity", "service_number",
            "death_year", "death_place", "unit", "rank",
        ]
    )

    is_name_only = claim.get("predicate") in ("has_name", "born_at") and not has_second_id
    is_from_auto_link = claim.get("extraction_method", "") in ("auto_link", "keyword_match")

    if is_name_only and is_from_auto_link:
        old_status = claim.get("status", "ASSERTED")
        claim["status"] = "NEEDS_REVIEW"
        claim["confidence"] = min(claim.get("confidence", 0.5), 0.3)
        return ClaimRuleResult(
            rule_name="HOMONYM_GUARD",
            applied=True,
            original_status=old_status,
            new_status="NEEDS_REVIEW",
            note="Solo coincidenza nominale senza secondo identificatore",
        )

    return None


def rule_absence_not_proof(claims: List[Dict[str, Any]]) -> List[ClaimRuleResult]:
    """RULE: Absence of web results is not proof of non-existence.

    This is a meta-rule: if no web observations were collected but DB
    records exist, do not mark the person as 'not found'.
    """
    results = []
    has_db_evidence = any(
        c.get("source", "").startswith("local_db:") and c.get("status") not in ("REJECTED",)
        for c in claims
    )
    has_web_evidence = any(
        c.get("evidence_scope") == "CONTEXT_EVIDENCE" and c.get("source", "").startswith(("tavily", "brave", "serper"))
        for c in claims
    )

    if has_db_evidence and not has_web_evidence:
        # Don't downgrade DB claims just because web search returned nothing
        for claim in claims:
            if claim.get("source", "").startswith("local_db:") and claim.get("status") == "UNVERIFIED":
                if "no web evidence" in str(claim.get("anomaly_note", "")).lower():
                    old_status = claim["status"]
                    claim["status"] = "PROBABLE"
                    results.append(ClaimRuleResult(
                        rule_name="ABSENCE_NOT_PROOF",
                        applied=True,
                        original_status=old_status,
                        new_status="PROBABLE",
                        note="Assenza di risultati web non è prova di inesistenza",
                    ))

    return results


def rule_no_context_as_person(claim: Dict[str, Any]) -> Optional[ClaimRuleResult]:
    """RULE: A page about an event cannot become person evidence.

    If the observation snippet mentions an event but not the person by name,
    it can only be context, not person evidence.
    """
    evidence_scope = claim.get("evidence_scope", "")
    snippet = str(claim.get("value_normalized", "")).lower()
    target_name = str(claim.get("target_name", "")).lower()

    if evidence_scope == "PERSON_EVIDENCE" and target_name:
        # Check if the person's name actually appears in the snippet
        if target_name not in snippet and target_name.replace(" ", "") not in snippet.replace(" ", ""):
            old_status = claim.get("status", "ASSERTED")
            claim["status"] = "REJECTED"
            claim["evidence_scope"] = "CONTEXT_EVIDENCE"
            claim["confidence"] = 0.0
            return ClaimRuleResult(
                rule_name="NO_CONTEXT_AS_PERSON",
                applied=True,
                original_status=old_status,
                new_status="REJECTED",
                note="La fonte non nomina la persona — riclassificata come contesto",
            )

    return None


# ─── Engine ──────────────────────────────────────────────────────────────────

# Ordered list of rules to apply
_PERSON_RULES = [
    rule_date_precision,
    rule_semantic_role_burial,
    rule_ocr_unreadable_name,
    rule_homonym_guard,
    rule_source_function_guard,
    rule_no_context_as_person,
]

_EVENT_RULES = [
    rule_date_precision,
    rule_semantic_role_burial,
]


def apply_claim_rules(
    claims: List[Dict[str, Any]],
    intent: str = "PERSON_LOOKUP",
) -> List[ClaimRuleResult]:
    """Apply all applicable claim rules to a list of claims.

    Args:
        claims: List of claim dicts (modified in place)
        intent: PERSON_LOOKUP or EVENT_LOOKUP

    Returns:
        List of ClaimRuleResult for all rules that were applied
    """
    results = []
    rules = _PERSON_RULES if intent == "PERSON_LOOKUP" else _EVENT_RULES

    for claim in claims:
        for rule_fn in rules:
            result = rule_fn(claim)
            if result and result.applied:
                results.append(result)

    # Apply meta-rules (work on the full claim set)
    if intent == "PERSON_LOOKUP":
        results.extend(rule_absence_not_proof(claims))

    return results


def classify_claim_status(claim: Dict[str, Any]) -> str:
    """Classify a claim into APPROVED, PROBABLE, NEEDS_REVIEW, or REJECTED.

    Based on the GPT pipeline's approval taxonomy:
    - verified → APPROVED
    - probable → PROBABLE
    - possible → NEEDS_REVIEW
    - unverified → NEEDS_REVIEW
    - conflicting → NEEDS_REVIEW
    - rejected → REJECTED
    - needs_image_review → NEEDS_REVIEW
    - rejected_precision → REJECTED (for that precision level)
    """
    status = claim.get("status", "ASSERTED").upper()
    confidence = claim.get("confidence", 0.0)

    if status in ("REJECTED", "REJECTED_PRECISION"):
        return "REJECTED"
    elif status == "NEEDS_IMAGE_REVIEW":
        return "NEEDS_REVIEW"
    elif status == "NEEDS_REVIEW":
        return "NEEDS_REVIEW"
    elif status == "UNVERIFIED":
        return "NEEDS_REVIEW"
    elif status == "PROBABLE":
        return "PROBABLE"
    elif status in ("ASSERTED", "ACCEPTED") and confidence >= 0.7:
        return "APPROVED"
    elif status in ("ASSERTED", "ACCEPTED") and confidence >= 0.4:
        return "PROBABLE"
    elif status == "CONTEXT":
        return "CONTEXT"
    else:
        return "NEEDS_REVIEW"

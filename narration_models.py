"""Narration models for V7.2-narration-v2 contract.

Two distinct typed models:

1. NarrationDraft — the ONLY output accepted from the AI model.
   The model produces atomic narrative blocks, each referencing claim_ids
   from the allowlist. It does NOT produce source_ids, citation_map,
   used_claim_ids, or omitted_claims. Those are backend-computed.

2. NarrationResult — the ONLY output returned by the narration service.
   The backend always constructs this, regardless of AI success/failure.
   It contains the final answer_markdown (rendered from validated blocks),
   the citation_map (built from persisted claim→source relations),
   omitted_claims (computed deterministically), and validation_flags.

Key invariants:
- No code path returns a bare string instead of NarrationResult.
- answer_markdown is rendered by the backend from validated blocks.
- used_claim_ids is the deterministic union of claim_ids in validated blocks.
- citation_map is built by the backend from claim→evidence→source relations.
- omitted_claims = candidate_narratable_claim_ids - used_claim_ids.
- source_id is NEVER accepted from AI output.
- Raw provider text is NEVER published or passed to the renderer.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field, asdict
from typing import List, Optional, Dict, Any


# ─── Enums ──────────────────────────────────────────────────────────────────

NARRATION_STATUS = [
    "validated_ai",
    "validated_deterministic",
    "blocked_evidence_not_validated",
    "blocked_validation_failed",
]

BLOCK_ROLES = [
    "direct_answer",
    "identity",
    "chronology",
    "context",
    "conflict",
    "limitations",
    "research_next_step",
]

CERTAINTY_LEVELS = [
    "verified",
    "probable",
    "conflicting",
    "unverified_limit",
    "non_factual",
]

REQUEST_TYPES = ["PERSON", "FACT", "EVENT"]


# ─── NarrationDraft (AI output) ─────────────────────────────────────────────

@dataclass
class NarrationBlock:
    """A single atomic narrative block from the AI."""
    block_id: str
    role: str  # one of BLOCK_ROLES
    text: str
    claim_ids: List[str] = field(default_factory=list)
    certainty: str = "non_factual"  # one of CERTAINTY_LEVELS

    def validate(self) -> List[str]:
        """Return list of validation errors for this block."""
        errors = []
        if self.role not in BLOCK_ROLES:
            errors.append(f"INVALID_ROLE:{self.role}")
        if self.certainty not in CERTAINTY_LEVELS:
            errors.append(f"INVALID_CERTAINTY:{self.certainty}")
        if not self.block_id:
            errors.append("MISSING_BLOCK_ID")
        if not self.text or not self.text.strip():
            errors.append("EMPTY_TEXT")
        # Factual blocks must have claim_ids
        if self.certainty in ("verified", "probable", "conflicting", "unverified_limit"):
            if not self.claim_ids:
                errors.append("FACTUAL_BLOCK_WITHOUT_CLAIM_IDS")
        return errors


@dataclass
class NarrationDraft:
    """The ONLY output accepted from the AI model.

    The model returns atomic blocks, each referencing claim_ids from
    the allowlist. No source_ids, no citation_map, no omitted_claims.
    """
    schema_version: str = "7.2-narration-draft-v2"
    request_type: str = "PERSON"  # one of REQUEST_TYPES
    blocks: List[NarrationBlock] = field(default_factory=list)
    needs_followup: bool = False
    followup_question: Optional[str] = None

    def validate(self) -> List[str]:
        """Validate the draft structure. Returns list of error strings."""
        errors = []
        if self.schema_version != "7.2-narration-draft-v2":
            errors.append(f"INVALID_SCHEMA_VERSION:{self.schema_version}")
        if self.request_type not in REQUEST_TYPES:
            errors.append(f"INVALID_REQUEST_TYPE:{self.request_type}")
        if not self.blocks:
            errors.append("NO_BLOCKS")
        seen_ids = set()
        for b in self.blocks:
            if b.block_id in seen_ids:
                errors.append(f"DUPLICATE_BLOCK_ID:{b.block_id}")
            seen_ids.add(b.block_id)
            errors.extend(b.validate())
        return errors

    def to_dict(self) -> dict:
        return {
            "schema_version": self.schema_version,
            "request_type": self.request_type,
            "blocks": [
                {
                    "block_id": b.block_id,
                    "role": b.role,
                    "text": b.text,
                    "claim_ids": b.claim_ids,
                    "certainty": b.certainty,
                }
                for b in self.blocks
            ],
            "needs_followup": self.needs_followup,
            "followup_question": self.followup_question,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "NarrationDraft":
        blocks = []
        for bd in d.get("blocks", []):
            blocks.append(NarrationBlock(
                block_id=bd.get("block_id", ""),
                role=bd.get("role", "context"),
                text=bd.get("text", ""),
                claim_ids=bd.get("claim_ids", []),
                certainty=bd.get("certainty", "non_factual"),
            ))
        return cls(
            schema_version=d.get("schema_version", "7.2-narration-draft-v2"),
            request_type=d.get("request_type", "PERSON"),
            blocks=blocks,
            needs_followup=d.get("needs_followup", False),
            followup_question=d.get("followup_question"),
        )

    @classmethod
    def from_json(cls, raw: str) -> "NarrationDraft":
        """Parse a JSON string into a NarrationDraft.

        Strips markdown code fences if present.
        Raises json.JSONDecodeError if parsing fails.
        """
        text = raw.strip()
        if text.startswith("```json"):
            text = text[7:]
        elif text.startswith("```"):
            text = text[3:]
        if text.endswith("```"):
            text = text[:-3]
        text = text.strip()

        obj = json.loads(text)
        return cls.from_dict(obj)


# ─── NarrationResult (service output) ───────────────────────────────────────

@dataclass
class CitationEntry:
    """A single citation mapping a block to claims and sources."""
    block_id: str
    claim_ids: List[str]
    source_ids: List[str]


@dataclass
class OmittedClaim:
    """A claim that was available but not used in the narration."""
    claim_id: str
    reason: str  # deterministic reason code


@dataclass
class GenerationInfo:
    """Metadata about how the narration was generated."""
    mode: str = "ai"  # ai|deterministic|fallback
    provider: str = ""
    model: str = ""
    repair_attempted: bool = False
    repair_succeeded: bool = False
    fallback_reason: str = ""
    ai_validation: Optional[Dict[str, Any]] = None


@dataclass
class NarrationResult:
    """The ONLY output returned by the narration service.

    Always constructed by the backend, never by the AI.
    """
    schema_version: str = "7.2-narration-result-v2"
    request_type: str = "PERSON"
    status: str = "validated_ai"  # one of NARRATION_STATUS
    answer_markdown: str = ""
    used_claim_ids: List[str] = field(default_factory=list)
    citation_map: List[CitationEntry] = field(default_factory=list)
    omitted_claims: List[OmittedClaim] = field(default_factory=list)
    validation_flags: List[str] = field(default_factory=list)
    needs_followup: bool = False
    followup_question: Optional[str] = None
    generation: GenerationInfo = field(default_factory=GenerationInfo)

    def to_dict(self) -> dict:
        return {
            "schema_version": self.schema_version,
            "request_type": self.request_type,
            "status": self.status,
            "answer_markdown": self.answer_markdown,
            "used_claim_ids": self.used_claim_ids,
            "citation_map": [
                {
                    "block_id": c.block_id,
                    "claim_ids": c.claim_ids,
                    "source_ids": c.source_ids,
                }
                for c in self.citation_map
            ],
            "omitted_claims": [
                {"claim_id": o.claim_id, "reason": o.reason}
                for o in self.omitted_claims
            ],
            "validation_flags": self.validation_flags,
            "needs_followup": self.needs_followup,
            "followup_question": self.followup_question,
            "generation": {
                "mode": self.generation.mode,
                "provider": self.generation.provider,
                "model": self.generation.model,
                "repair_attempted": self.generation.repair_attempted,
                "repair_succeeded": self.generation.repair_succeeded,
                "fallback_reason": self.generation.fallback_reason,
            },
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=2)

    @classmethod
    def from_dict(cls, d: dict) -> "NarrationResult":
        citation_map = [
            CitationEntry(
                block_id=c.get("block_id", ""),
                claim_ids=c.get("claim_ids", []),
                source_ids=c.get("source_ids", []),
            )
            for c in d.get("citation_map", [])
        ]
        omitted = [
            OmittedClaim(claim_id=o.get("claim_id", ""), reason=o.get("reason", ""))
            for o in d.get("omitted_claims", [])
        ]
        gen = d.get("generation", {})
        generation = GenerationInfo(
            mode=gen.get("mode", "deterministic"),
            provider=gen.get("provider", ""),
            model=gen.get("model", ""),
            repair_attempted=gen.get("repair_attempted", False),
            repair_succeeded=gen.get("repair_succeeded", False),
            fallback_reason=gen.get("fallback_reason", ""),
        )
        return cls(
            schema_version=d.get("schema_version", "7.2-narration-result-v2"),
            request_type=d.get("request_type", "PERSON"),
            status=d.get("status", "validated_deterministic"),
            answer_markdown=d.get("answer_markdown", ""),
            used_claim_ids=d.get("used_claim_ids", []),
            citation_map=citation_map,
            omitted_claims=omitted,
            validation_flags=d.get("validation_flags", []),
            needs_followup=d.get("needs_followup", False),
            followup_question=d.get("followup_question"),
            generation=generation,
        )


# ─── JSON Schema for structured outputs ─────────────────────────────────────

NARRATION_DRAFT_SCHEMA: Dict[str, Any] = {
    "name": "narration_draft",
    "schema": {
        "type": "object",
        "properties": {
            "schema_version": {
                "type": "string",
                "const": "7.2-narration-draft-v2",
            },
            "request_type": {
                "type": "string",
                "enum": ["PERSON", "FACT", "EVENT"],
            },
            "blocks": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "block_id": {"type": "string"},
                        "role": {
                            "type": "string",
                            "enum": BLOCK_ROLES,
                        },
                        "text": {"type": "string"},
                        "claim_ids": {
                            "type": "array",
                            "items": {"type": "string"},
                        },
                        "certainty": {
                            "type": "string",
                            "enum": CERTAINTY_LEVELS,
                        },
                    },
                    "required": ["block_id", "role", "text", "claim_ids", "certainty"],
                    "additionalProperties": False,
                },
            },
            "needs_followup": {"type": "boolean"},
            "followup_question": {"type": ["string", "null"]},
        },
        "required": ["schema_version", "request_type", "blocks", "needs_followup", "followup_question"],
        "additionalProperties": False,
    },
    "strict": True,
}


# ─── Convenience: blocked result ────────────────────────────────────────────

def blocked_result(
    request_type: str,
    reason: str,
    flags: List[str] = None,
) -> NarrationResult:
    """Create a blocked NarrationResult when no safe answer exists."""
    return NarrationResult(
        request_type=request_type,
        status="blocked_validation_failed" if flags else "blocked_evidence_not_validated",
        answer_markdown=f"I dati disponibili non consentono di fornire una risposta verificabile. Motivo: {reason}",
        validation_flags=flags or [],
        generation=GenerationInfo(
            mode="fallback",
            fallback_reason=reason,
        ),
    )

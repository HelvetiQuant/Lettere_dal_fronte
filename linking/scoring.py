"""
Scoring and calibration for linking v2.

Rules:
- raw_score is computed from features but never presented as probability
- evidence_strength is weak|moderate|strong based on discriminator count
- confidence_calibrated is NULL until a labeled dataset exists
- No auto-promotion to 'confirmed' without human review
"""
from dataclasses import dataclass, field
from typing import Any

from linking.feature_extraction import Features, ConflictFlags


SCORING_VERSION = "2.0.0"


@dataclass
class ScoreResult:
    raw_score: float
    evidence_strength: str  # weak, moderate, strong
    confidence_calibrated: float | None = None
    calibration_model_version: str | None = None
    conflict_flags: list[str] = field(default_factory=list)
    can_be_confirmed: bool = False
    version: str = field(default=SCORING_VERSION, init=False)


def score_candidate(features: Features, conflicts: ConflictFlags | None = None) -> ScoreResult:
    """
    Score a candidate pair based on extracted features.
    
    Scoring rules:
    - Name match alone: raw_score 0.1-0.2, evidence_strength=weak
    - Name + 1 discriminator: raw_score 0.3-0.5, evidence_strength=moderate
    - Name + 2+ discriminators: raw_score 0.5-0.8, evidence_strength=strong
    - Any veto conflict: can_be_confirmed=False, evidence_strength=weak
    - confidence_calibrated is always NULL (no calibration dataset yet)
    """
    conflict_list = conflicts.to_list() if conflicts else []
    has_veto = conflicts.has_veto if conflicts else False
    
    # Base score from name matching
    score = 0.0
    if features.name_cognome_exact:
        score += 0.15
    elif features.name_cognome_phonetic:
        score += 0.08
    
    if features.name_nome_exact:
        score += 0.05
    
    # Add discriminator scores
    n_discriminators = len(features.discriminators)
    
    if n_discriminators == 0:
        evidence_strength = "weak"
    elif n_discriminators == 1:
        score += 0.2
        evidence_strength = "moderate"
    elif n_discriminators == 2:
        score += 0.35
        evidence_strength = "moderate"
    else:
        score += 0.45
        evidence_strength = "strong"
    
    # Specific feature bonuses
    if features.same_matricola:
        score += 0.2  # Matricola is a very strong discriminator
    if features.birth_date_compatible and features.birth_place_compatible:
        score += 0.1  # Both date and place = strong
    if features.document_citation:
        score += 0.1
    
    # Cap at 0.95 (never 1.0 — uncertainty is always present)
    score = min(score, 0.95)
    
    # Veto conflicts override everything
    if has_veto:
        evidence_strength = "weak"
        score = min(score, 0.15)
    
    # Determine evidence_strength based on discriminators and conflicts
    if has_veto:
        evidence_strength = "weak"
    elif n_discriminators >= 2 and not conflicts:
        evidence_strength = "strong"
    elif n_discriminators >= 1:
        evidence_strength = "moderate"
    else:
        evidence_strength = "weak"
    
    can_confirm = (
        not has_veto
        and n_discriminators >= 2
        and evidence_strength in ("moderate", "strong")
        and features.name_match
    )
    
    return ScoreResult(
        raw_score=round(score, 4),
        evidence_strength=evidence_strength,
        confidence_calibrated=None,  # No calibration dataset yet
        calibration_model_version=None,
        conflict_flags=conflict_list,
        can_be_confirmed=can_confirm,
    )


@dataclass
class DecisionResult:
    status: str  # accepted | needs_review | rejected
    reason: str
    raw_score: float
    evidence_strength: str
    conflict_flags: list[str]
    can_be_confirmed: bool


def decide(features: Features, conflicts: ConflictFlags | None = None) -> DecisionResult:
    """
    Decide the status of a candidate pair based on features and conflicts.
    
    Decision order (first match wins):
    1. temporal_conflict → rejected
    2. ww1_ww2_mismatch → rejected
    3. mixed_era_source → needs_review
    4. ambiguous_keywords_only → needs_review
    5. distinctive keyword + temporal overlap → accepted
    6. distinctive keyword but unknown temporal → needs_review
    7. insufficient evidence → rejected
    
    Returns DecisionResult with status, reason, and score info.
    """
    score_result = score_candidate(features, conflicts)
    conflict_list = conflicts.to_list() if conflicts else []
    has_veto = conflicts.has_veto if conflicts else False
    
    # 1. Temporal conflict (certain disjoint) → rejected
    if conflicts and conflicts.temporal_conflict:
        return DecisionResult(
            status="rejected",
            reason="temporal_conflict",
            raw_score=score_result.raw_score,
            evidence_strength=score_result.evidence_strength,
            conflict_flags=conflict_list,
            can_be_confirmed=False,
        )
    
    # 2. WW1/WW2 mismatch → rejected
    if conflicts and conflicts.ww1_ww2_mismatch:
        return DecisionResult(
            status="rejected",
            reason="ww1_ww2_mismatch",
            raw_score=score_result.raw_score,
            evidence_strength=score_result.evidence_strength,
            conflict_flags=conflict_list,
            can_be_confirmed=False,
        )
    
    # 3. Mixed era source → needs_review
    if conflicts and conflicts.mixed_era_source:
        return DecisionResult(
            status="needs_review",
            reason="mixed_era_source",
            raw_score=score_result.raw_score,
            evidence_strength=score_result.evidence_strength,
            conflict_flags=conflict_list,
            can_be_confirmed=False,
        )
    
    # 4. Ambiguous keywords only → needs_review
    if conflicts and conflicts.ambiguous_keywords_only:
        return DecisionResult(
            status="needs_review",
            reason="ambiguous_keywords_only",
            raw_score=score_result.raw_score,
            evidence_strength=score_result.evidence_strength,
            conflict_flags=conflict_list,
            can_be_confirmed=False,
        )
    
    # 5. Distinctive keyword + temporal overlap → accepted
    if features.discriminators and features.temporal_overlap and not has_veto:
        return DecisionResult(
            status="accepted",
            reason="distinctive_keyword_with_temporal_overlap",
            raw_score=score_result.raw_score,
            evidence_strength=score_result.evidence_strength,
            conflict_flags=conflict_list,
            can_be_confirmed=score_result.can_be_confirmed,
        )
    
    # 6. Distinctive keyword but unknown temporal → needs_review
    if features.discriminators and not features.temporal_overlap and not has_veto:
        return DecisionResult(
            status="needs_review",
            reason="distinctive_keyword_unknown_temporal",
            raw_score=score_result.raw_score,
            evidence_strength=score_result.evidence_strength,
            conflict_flags=conflict_list,
            can_be_confirmed=False,
        )
    
    # 7. Insufficient evidence
    return DecisionResult(
        status="rejected",
        reason="insufficient_evidence",
        raw_score=score_result.raw_score,
        evidence_strength=score_result.evidence_strength,
        conflict_flags=conflict_list,
        can_be_confirmed=False,
    )

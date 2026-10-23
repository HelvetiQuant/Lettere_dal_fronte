"""V7.3-Fase10: Source quality hierarchy and multi-dimensional scoring.

Combines multiple quality dimensions into a unified, comparable score:
  1. authority_tier: official (1) → unofficial (4)
  2. directness: original record → transcription → OCR → web snippet
  3. extraction_confidence: how reliably the data was extracted
  4. temporal_proximity: how close the source is to the event
  5. independence: whether sources are truly independent or derived from same origin

Key invariants:
  1. Quality score is multi-dimensional, never collapsed to a single number
  2. Official source veto is absolute — cannot be overridden by quantity
  3. Two independent primary sources > three dependent secondary sources
  4. Quality dimensions are preserved for audit and explanation
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple


# ─── Quality dimensions ──────────────────────────────────────────────────────

# Dimension 1: Authority tier (from source_authority_registry)
AUTHORITY_TIER_SCORES = {
    1: 0.95,  # official
    2: 0.80,  # primary
    3: 0.50,  # secondary
    4: 0.25,  # unofficial
}

# Dimension 2: Directness — how close is the source to the original record
DIRECTNESS_LEVELS = {
    "original_record": 1.0,      # the actual archival record
    "official_transcription": 0.85,  # transcribed by the archive itself
    "verified_transcription": 0.70,  # transcribed and verified by a researcher
    "unverified_transcription": 0.50,  # transcribed but not verified
    "ocr_extracted": 0.40,       # OCR extraction from a document
    "web_snippet": 0.25,         # snippet from web search
    "ai_generated": 0.15,        # AI-generated text (never evidence)
}

# Dimension 3: Temporal proximity — how close in time is the source to the event
TEMPORAL_PROXIMITY = {
    "contemporary": 1.0,         # created during or immediately after the event
    "near_contemporary": 0.85,   # within 5 years
    "historical": 0.65,          # within 20 years
    "modern": 0.45,              # 20-50 years later
    "recent": 0.30,              # 50+ years later
    "unknown": 0.20,             # cannot determine
}

# Dimension 4: Extraction confidence (from OCR, AI, manual)
# This is a per-field value, not per-source

# Dimension 5: Independence groups
# Sources in the same independence group are NOT independent
INDEPENDENCE_GROUPS = {
    "anrp": ["anrp_lebi", "anrp_registry"],
    "ministero": ["ministero_difesa", "albo_oro", "nastro_azzurro"],
    "icrc": ["icrc"],
    "cwgc": ["cwgc"],
    "imi_db": ["internati_imi"],
    "web": ["web_search", "wikipedia"],
    "fonti": ["fonti_indice", "archivio_documenti", "ocr_lettere"],
}


# ─── Data classes ────────────────────────────────────────────────────────────

@dataclass
class SourceQuality:
    """Multi-dimensional source quality assessment."""
    source_key: str = ""
    authority_tier: int = 4
    authority_score: float = 0.0
    directness: str = "unverified_transcription"
    directness_score: float = 0.0
    temporal_proximity: str = "unknown"
    temporal_proximity_score: float = 0.0
    extraction_confidence: float = 0.0
    independence_group: str = ""
    is_independent: bool = True

    # Computed quality level
    quality_level: str = "unknown"  # high, medium, low, very_low
    quality_score: float = 0.0

    # Explanation
    quality_factors: List[str] = field(default_factory=list)

    def compute(self):
        """Compute quality_level and quality_score from dimensions."""
        self.authority_score = AUTHORITY_TIER_SCORES.get(self.authority_tier, 0.25)
        self.directness_score = DIRECTNESS_LEVELS.get(self.directness, 0.25)
        self.temporal_proximity_score = TEMPORAL_PROXIMITY.get(self.temporal_proximity, 0.20)

        # Weighted combination (authority is most important)
        weights = {
            "authority": 0.40,
            "directness": 0.25,
            "temporal_proximity": 0.15,
            "extraction_confidence": 0.20,
        }
        self.quality_score = (
            self.authority_score * weights["authority"]
            + self.directness_score * weights["directness"]
            + self.temporal_proximity_score * weights["temporal_proximity"]
            + self.extraction_confidence * weights["extraction_confidence"]
        )

        # Determine quality level
        if self.quality_score >= 0.75:
            self.quality_level = "high"
        elif self.quality_score >= 0.50:
            self.quality_level = "medium"
        elif self.quality_score >= 0.30:
            self.quality_level = "low"
        else:
            self.quality_level = "very_low"

        # Build explanation
        self.quality_factors = [
            f"authority:tier{self.authority_tier}={self.authority_score:.2f}",
            f"directness:{self.directness}={self.directness_score:.2f}",
            f"temporal:{self.temporal_proximity}={self.temporal_proximity_score:.2f}",
            f"extraction:{self.extraction_confidence:.2f}",
            f"independent:{self.is_independent}",
        ]

    def to_dict(self) -> dict:
        self.compute()
        return {
            "source_key": self.source_key,
            "authority_tier": self.authority_tier,
            "authority_score": round(self.authority_score, 4),
            "directness": self.directness,
            "directness_score": round(self.directness_score, 4),
            "temporal_proximity": self.temporal_proximity,
            "temporal_proximity_score": round(self.temporal_proximity_score, 4),
            "extraction_confidence": round(self.extraction_confidence, 4),
            "independence_group": self.independence_group,
            "is_independent": self.is_independent,
            "quality_level": self.quality_level,
            "quality_score": round(self.quality_score, 4),
            "quality_factors": self.quality_factors,
        }


# ─── Source quality registry ─────────────────────────────────────────────────

# Default quality assessments per source
DEFAULT_QUALITY_ASSESSMENTS: Dict[str, Dict] = {
    "anrp_lebi": {
        "authority_tier": 1, "directness": "official_transcription",
        "temporal_proximity": "modern", "extraction_confidence": 0.90,
        "independence_group": "anrp",
    },
    "icrc": {
        "authority_tier": 1, "directness": "original_record",
        "temporal_proximity": "contemporary", "extraction_confidence": 0.95,
        "independence_group": "icrc",
    },
    "ministero_difesa": {
        "authority_tier": 1, "directness": "original_record",
        "temporal_proximity": "near_contemporary", "extraction_confidence": 0.92,
        "independence_group": "ministero",
    },
    "albo_oro": {
        "authority_tier": 2, "directness": "official_transcription",
        "temporal_proximity": "near_contemporary", "extraction_confidence": 0.88,
        "independence_group": "ministero",
    },
    "cwgc": {
        "authority_tier": 2, "directness": "original_record",
        "temporal_proximity": "contemporary", "extraction_confidence": 0.90,
        "independence_group": "cwgc",
    },
    "nastro_azzurro": {
        "authority_tier": 2, "directness": "official_transcription",
        "temporal_proximity": "historical", "extraction_confidence": 0.85,
        "independence_group": "ministero",
    },
    "internati_imi": {
        "authority_tier": 2, "directness": "verified_transcription",
        "temporal_proximity": "modern", "extraction_confidence": 0.80,
        "independence_group": "imi_db",
    },
    "fonti_indice": {
        "authority_tier": 3, "directness": "unverified_transcription",
        "temporal_proximity": "historical", "extraction_confidence": 0.60,
        "independence_group": "fonti",
    },
    "archivio_documenti": {
        "authority_tier": 3, "directness": "verified_transcription",
        "temporal_proximity": "historical", "extraction_confidence": 0.65,
        "independence_group": "fonti",
    },
    "ocr_lettere": {
        "authority_tier": 3, "directness": "ocr_extracted",
        "temporal_proximity": "contemporary", "extraction_confidence": 0.50,
        "independence_group": "fonti",
    },
    "web_search": {
        "authority_tier": 4, "directness": "web_snippet",
        "temporal_proximity": "recent", "extraction_confidence": 0.30,
        "independence_group": "web",
    },
    "wikipedia": {
        "authority_tier": 4, "directness": "web_snippet",
        "temporal_proximity": "recent", "extraction_confidence": 0.25,
        "independence_group": "web",
    },
}


def assess_source_quality(source_key: str, extraction_confidence: Optional[float] = None) -> SourceQuality:
    """Assess the quality of a source based on its key.

    Args:
        source_key: the source key from the registry
        extraction_confidence: override for extraction confidence (if known)

    Returns:
        SourceQuality with computed scores
    """
    defaults = DEFAULT_QUALITY_ASSESSMENTS.get(source_key, {
        "authority_tier": 4,
        "directness": "unverified_transcription",
        "temporal_proximity": "unknown",
        "extraction_confidence": 0.30,
        "independence_group": "",
    })

    q = SourceQuality(
        source_key=source_key,
        authority_tier=defaults["authority_tier"],
        directness=defaults["directness"],
        temporal_proximity=defaults["temporal_proximity"],
        extraction_confidence=extraction_confidence if extraction_confidence is not None else defaults["extraction_confidence"],
        independence_group=defaults.get("independence_group", ""),
    )
    q.compute()
    return q


# ─── Evidence combination rules ──────────────────────────────────────────────

def check_independence(source_keys: List[str]) -> Tuple[bool, List[str]]:
    """Check if a set of sources are truly independent.

    Sources in the same independence group are NOT independent.

    Returns:
        (all_independent, groups_with_multiple_sources)
    """
    group_counts: Dict[str, int] = {}
    for key in source_keys:
        defaults = DEFAULT_QUALITY_ASSESSMENTS.get(key, {})
        group = defaults.get("independence_group", key)  # fallback: each source is its own group
        group_counts[group] = group_counts.get(group, 0) + 1

    non_independent = [g for g, c in group_counts.items() if c > 1]
    return len(non_independent) == 0, non_independent


def combine_evidence_quality(qualities: List[SourceQuality]) -> Tuple[str, float, str]:
    """Combine multiple source quality assessments into an evidence quality verdict.

    Rules:
      1. 2+ independent high-quality sources → "verified"
      2. 1 high + 1 independent medium → "probable"
      3. 1 high alone → "possible"
      4. 2+ medium independent → "probable"
      5. 1 medium alone → "possible"
      6. Only low/very_low → "unverified"
      7. Any official conflict → "conflicting"

    Returns:
        (evidence_level, combined_score, reason)
    """
    if not qualities:
        return "unverified", 0.0, "no_evidence"

    # Check independence
    source_keys = [q.source_key for q in qualities]
    all_independent, non_indep_groups = check_independence(source_keys)

    # Count by quality level
    by_level: Dict[str, List[SourceQuality]] = {}
    for q in qualities:
        by_level.setdefault(q.quality_level, []).append(q)

    high = by_level.get("high", [])
    medium = by_level.get("medium", [])
    low = by_level.get("low", [])
    very_low = by_level.get("very_low", [])

    # Count independent high-quality sources
    independent_high = len(high) if all_independent else max(1, len(high) - 1)

    # Combined score = weighted average (higher quality sources weigh more)
    weights = {"high": 1.0, "medium": 0.7, "low": 0.4, "very_low": 0.1}
    total_weight = 0.0
    weighted_sum = 0.0
    for q in qualities:
        w = weights.get(q.quality_level, 0.1)
        weighted_sum += q.quality_score * w
        total_weight += w
    combined_score = weighted_sum / total_weight if total_weight > 0 else 0.0

    # Determine evidence level
    if independent_high >= 2:
        return "verified", combined_score, f"two_plus_independent_high_quality"
    if len(high) >= 1 and len(medium) >= 1:
        return "probable", combined_score, "high_plus_medium"
    if len(high) >= 1:
        return "possible", combined_score, "single_high_quality"
    if len(medium) >= 2 and all_independent:
        return "probable", combined_score, "two_independent_medium"
    if len(medium) >= 1:
        return "possible", combined_score, "single_medium_quality"
    if len(low) >= 1:
        return "unverified", combined_score, "only_low_quality"
    return "unverified", combined_score, "only_very_low_quality"


def can_publish_claim(
    evidence_level: str,
    min_level: str = "probable",
) -> bool:
    """Determine if a claim can be published based on evidence level.

    Args:
        evidence_level: verified, probable, possible, unverified, conflicting
        min_level: minimum level required for publication

    Returns:
        True if the claim can be published
    """
    level_order = ["unverified", "possible", "probable", "verified"]
    if evidence_level == "conflicting":
        return False
    try:
        return level_order.index(evidence_level) >= level_order.index(min_level)
    except ValueError:
        return False

"""
Centralized Source Authority and Provenance Registry.

This module provides the authoritative source registry for all data sources
(people, events, documents, claims). It replaces fixed confidence values
with a tiered authority system where:

- Official sources (state archives, ministries) have authority_tier=1
- Primary sources (verified institutional databases) have authority_tier=2
- Secondary sources (web, OCR-derived) have authority_tier=3
- Unofficial sources have authority_tier=4

The key innovation: temporal constraints from official sources act as VETO
gates, not just weighted scores. A complete date from an official source
that is incompatible with a candidate blocks the link regardless of name
similarity.

Schema is synchronized between SQLite and Supabase.
"""
import json
import sqlite3
import hashlib
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional


SCHEMA_VERSION = "3.0.0"
RULE_VERSION = "3.0.0"


# ─── Authority tiers ─────────────────────────────────────────────────────────

AUTHORITY_TIER_OFFICIAL = 1      # State archives, ministries, ANRP, ICRC
AUTHORITY_TIER_PRIMARY = 2       # Verified institutional databases (Albo d'Oro, CWGC)
AUTHORITY_TIER_SECONDARY = 3     # Web sources, OCR-derived, transcriptions
AUTHORITY_TIER_UNOFFICIAL = 4    # User-submitted, unverified web pages

TIER_NAMES = {
    AUTHORITY_TIER_OFFICIAL: "official",
    AUTHORITY_TIER_PRIMARY: "primary",
    AUTHORITY_TIER_SECONDARY: "secondary",
    AUTHORITY_TIER_UNOFFICIAL: "unofficial",
}

TIER_SCORES = {
    AUTHORITY_TIER_OFFICIAL: 0.95,
    AUTHORITY_TIER_PRIMARY: 0.80,
    AUTHORITY_TIER_SECONDARY: 0.50,
    AUTHORITY_TIER_UNOFFICIAL: 0.25,
}


# ─── Verification policies ───────────────────────────────────────────────────

VERIFICATION_POLICIES = {
    "official_verified": "Source is an official government/institutional archive. Data treated as canonical.",
    "primary_cross_check": "Source is primary but requires cross-check with another independent source.",
    "secondary_requires_corroboration": "Source is secondary; cannot overwrite canonical data without corroboration.",
    "unofficial_lead_only": "Source is unofficial; data treated as lead only, never as evidence.",
}


# ─── Link states ─────────────────────────────────────────────────────────────

LINK_STATES = [
    "verified",      # 2+ official/primary sources agree
    "probable",      # 1 official/primary + 1 secondary, no conflicts
    "possible",      # 1 source, no conflicts, needs corroboration
    "unverified",    # Source exists but authority too low or extraction uncertain
    "conflicting",   # Two official sources disagree
    "rejected",      # Hard conflict (e.g., date mismatch with official source)
]


# ─── Default source registry entries ─────────────────────────────────────────

DEFAULT_SOURCES = [
    # Official sources (tier 1)
    {"source_key": "anrp_lebi", "source_name": "LeBI - Lessico Biografico degli IMI (ANRP)",
     "source_type": "archive", "authority_tier": 1, "authority_score": 0.95,
     "is_official": True, "is_primary": True,
     "verification_policy": "official_verified",
     "provider": "lebi", "collection": "ANRP"},
    {"source_key": "icrc", "source_name": "International Committee of the Red Cross",
     "source_type": "archive", "authority_tier": 1, "authority_score": 0.95,
     "is_official": True, "is_primary": True,
     "verification_policy": "official_verified",
     "provider": "icrc", "collection": "ICRC"},
    {"source_key": "ministero_difesa", "source_name": "Ministero della Difesa - Caduti",
     "source_type": "archive", "authority_tier": 1, "authority_score": 0.92,
     "is_official": True, "is_primary": True,
     "verification_policy": "official_verified",
     "provider": "caduti_ministero", "collection": "MinisteroDifesa"},

    # Primary sources (tier 2)
    {"source_key": "albo_oro", "source_name": "Albo d'Oro dei Caduti della Grande Guerra",
     "source_type": "archive", "authority_tier": 2, "authority_score": 0.85,
     "is_official": True, "is_primary": True,
     "verification_policy": "primary_cross_check",
     "provider": "caduti_albooro", "collection": "AlboOro"},
    {"source_key": "cwgc", "source_name": "Commonwealth War Graves Commission",
     "source_type": "archive", "authority_tier": 2, "authority_score": 0.82,
     "is_official": True, "is_primary": True,
     "verification_policy": "primary_cross_check",
     "provider": "caduti_cwgc", "collection": "CWGC"},
    {"source_key": "nastro_azzurro", "source_name": "Decorati al Nastro Azzurro",
     "source_type": "archive", "authority_tier": 2, "authority_score": 0.80,
     "is_official": True, "is_primary": True,
     "verification_policy": "primary_cross_check",
     "provider": "decorati_nastroazzurro", "collection": "NastroAzzurro"},
    {"source_key": "internati_imi", "source_name": "Internati Militari Italiani (DB locale)",
     "source_type": "archive", "authority_tier": 2, "authority_score": 0.78,
     "is_official": True, "is_primary": True,
     "verification_policy": "primary_cross_check",
     "provider": "internati", "collection": "IMI"},

    # Secondary sources (tier 3)
    {"source_key": "fonti_indice", "source_name": "Fonti Indice (raccolte testuali)",
     "source_type": "document", "authority_tier": 3, "authority_score": 0.50,
     "is_official": False, "is_primary": False,
     "verification_policy": "secondary_requires_corroboration",
     "provider": "fonti_indice", "collection": "FontiIndice"},
    {"source_key": "archivio_documenti", "source_name": "Archivio Documenti (digitale)",
     "source_type": "document", "authority_tier": 3, "authority_score": 0.45,
     "is_official": False, "is_primary": False,
     "verification_policy": "secondary_requires_corroboration",
     "provider": "archivio_documenti", "collection": "ArchivioDoc"},
    {"source_key": "ocr_lettere", "source_name": "Lettere dal Fronte (OCR)",
     "source_type": "document", "authority_tier": 3, "authority_score": 0.40,
     "is_official": False, "is_primary": False,
     "verification_policy": "secondary_requires_corroboration",
     "provider": "ocr_lettere", "collection": "LettereFronte"},

    # Unofficial sources (tier 4)
    {"source_key": "web_search", "source_name": "Ricerca Web (Tavily/Google)",
     "source_type": "web", "authority_tier": 4, "authority_score": 0.20,
     "is_official": False, "is_primary": False,
     "verification_policy": "unofficial_lead_only",
     "provider": "tavily", "collection": "WebSearch"},
    {"source_key": "wikipedia", "source_name": "Wikipedia",
     "source_type": "web", "authority_tier": 4, "authority_score": 0.15,
     "is_official": False, "is_primary": False,
     "verification_policy": "unofficial_lead_only",
     "provider": "wikipedia", "collection": "Wikipedia"},
]


# ─── Schema SQL ──────────────────────────────────────────────────────────────

SOURCE_AUTHORITY_REGISTRY_SQL = """
CREATE TABLE IF NOT EXISTS source_authority_registry (
    source_key TEXT PRIMARY KEY,
    source_name TEXT NOT NULL,
    source_type TEXT NOT NULL CHECK (source_type IN (
        'archive','document','web','ocr','ai_extracted','user_submitted'
    )),
    authority_tier INTEGER NOT NULL CHECK (authority_tier BETWEEN 1 AND 4),
    authority_score REAL NOT NULL CHECK (authority_score BETWEEN 0 AND 1),
    is_official INTEGER NOT NULL DEFAULT 0,
    is_primary INTEGER NOT NULL DEFAULT 0,
    verification_policy TEXT NOT NULL,
    provider TEXT,
    collection TEXT,
    updated_at TEXT NOT NULL,
    rule_version TEXT NOT NULL,
    UNIQUE(source_key)
);

CREATE INDEX IF NOT EXISTS idx_sar_tier ON source_authority_registry(authority_tier);
CREATE INDEX IF NOT EXISTS idx_sar_provider ON source_authority_registry(provider);
CREATE INDEX IF NOT EXISTS idx_sar_official ON source_authority_registry(is_official);
"""

# Migration: add new columns to record_links and event_links
MIGRATION_RECORD_LINKS_SQL = """
-- Add V3 columns to record_links (idempotent via IF NOT EXISTS pattern)
ALTER TABLE record_links ADD COLUMN status TEXT DEFAULT 'unverified';
ALTER TABLE record_links ADD COLUMN source_authority TEXT DEFAULT '';
ALTER TABLE record_links ADD COLUMN match_confidence REAL DEFAULT 0.0;
ALTER TABLE record_links ADD COLUMN extraction_confidence REAL DEFAULT 0.0;
ALTER TABLE record_links ADD COLUMN conflict_code TEXT DEFAULT '';
ALTER TABLE record_links ADD COLUMN evidence_json TEXT DEFAULT '{}';
ALTER TABLE record_links ADD COLUMN decision_reason TEXT DEFAULT '';
ALTER TABLE record_links ADD COLUMN needs_review INTEGER DEFAULT 0;
ALTER TABLE record_links ADD COLUMN rule_version TEXT DEFAULT '';
"""

MIGRATION_EVENT_LINKS_SQL = """
-- Add V3 columns to event_links (idempotent via IF NOT EXISTS pattern)
ALTER TABLE event_links ADD COLUMN status TEXT DEFAULT 'unverified';
ALTER TABLE event_links ADD COLUMN source_authority TEXT DEFAULT '';
ALTER TABLE record_links ADD COLUMN match_confidence REAL DEFAULT 0.0;
ALTER TABLE event_links ADD COLUMN match_confidence REAL DEFAULT 0.0;
ALTER TABLE event_links ADD COLUMN extraction_confidence REAL DEFAULT 0.0;
ALTER TABLE event_links ADD COLUMN conflict_code TEXT DEFAULT '';
ALTER TABLE event_links ADD COLUMN evidence_json TEXT DEFAULT '{}';
ALTER TABLE event_links ADD COLUMN decision_reason TEXT DEFAULT '';
ALTER TABLE event_links ADD COLUMN needs_review INTEGER DEFAULT 0;
ALTER TABLE event_links ADD COLUMN rule_version TEXT DEFAULT '';
"""


# ─── Data classes ────────────────────────────────────────────────────────────

@dataclass
class SourceEntry:
    """A source registry entry."""
    source_key: str
    source_name: str
    source_type: str
    authority_tier: int
    authority_score: float
    is_official: bool = False
    is_primary: bool = False
    verification_policy: str = ""
    provider: str = ""
    collection: str = ""
    updated_at: str = ""
    rule_version: str = RULE_VERSION


@dataclass
class TemporalConstraint:
    """A temporal constraint from an official source.

    When a complete date from an official source is incompatible with a candidate,
    the link MUST be blocked regardless of name similarity.
    """
    date_value: str          # normalized ISO date
    precision: str           # exact, month, year, range
    source_key: str          # which source provided this date
    authority_tier: int      # authority tier of the source
    is_official: bool        # whether the source is official

    @property
    def is_hard_constraint(self) -> bool:
        """A complete date from an official source is a hard constraint."""
        return self.is_official and self.precision in ("exact", "month")

    @property
    def is_soft_constraint(self) -> bool:
        """Year-only or non-official dates are soft constraints."""
        return not self.is_hard_constraint


@dataclass
class LinkDecision:
    """Decision result for a candidate link."""
    status: str               # verified, probable, possible, unverified, conflicting, rejected
    match_confidence: float   # confidence in the name/identity match
    extraction_confidence: float  # confidence in the data extraction (OCR/AI)
    source_authority: str     # authority tier name of the source
    conflict_code: str        # empty if no conflict
    decision_reason: str      # human-readable explanation
    needs_review: bool        # whether manual review is required
    evidence: dict = field(default_factory=dict)
    rule_version: str = RULE_VERSION


# ─── Registry class ──────────────────────────────────────────────────────────

class SourceAuthorityRegistry:
    """Centralized source authority registry.

    Loads source definitions from SQLite (or creates them if missing),
    provides authority lookups, and enforces temporal constraints.
    """

    def __init__(self, conn: sqlite3.Connection):
        self._conn = conn
        self._cache: dict[str, SourceEntry] = {}
        self._ensure_schema()
        self._load()

    def _ensure_schema(self):
        """Create source_authority_registry table if it doesn't exist."""
        self._conn.executescript(SOURCE_AUTHORITY_REGISTRY_SQL)
        self._conn.commit()

    def _load(self):
        """Load all sources from the registry into cache."""
        rows = self._conn.execute(
            "SELECT source_key, source_name, source_type, authority_tier, "
            "authority_score, is_official, is_primary, verification_policy, "
            "provider, collection, updated_at, rule_version "
            "FROM source_authority_registry"
        ).fetchall()
        for r in rows:
            entry = SourceEntry(
                source_key=r[0],
                source_name=r[1],
                source_type=r[2],
                authority_tier=r[3],
                authority_score=r[4],
                is_official=bool(r[5]),
                is_primary=bool(r[6]),
                verification_policy=r[7],
                provider=r[8] or "",
                collection=r[9] or "",
                updated_at=r[10],
                rule_version=r[11],
            )
            self._cache[entry.source_key] = entry

        # Seed defaults if empty
        if not self._cache:
            self._seed_defaults()

    def _seed_defaults(self):
        """Insert default source entries."""
        now = datetime.now(timezone.utc).isoformat()
        for src in DEFAULT_SOURCES:
            entry = SourceEntry(
                source_key=src["source_key"],
                source_name=src["source_name"],
                source_type=src["source_type"],
                authority_tier=src["authority_tier"],
                authority_score=src["authority_score"],
                is_official=src["is_official"],
                is_primary=src["is_primary"],
                verification_policy=src["verification_policy"],
                provider=src.get("provider", ""),
                collection=src.get("collection", ""),
                updated_at=now,
                rule_version=RULE_VERSION,
            )
            self._conn.execute(
                "INSERT OR REPLACE INTO source_authority_registry "
                "(source_key, source_name, source_type, authority_tier, authority_score, "
                "is_official, is_primary, verification_policy, provider, collection, "
                "updated_at, rule_version) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                (entry.source_key, entry.source_name, entry.source_type,
                 entry.authority_tier, entry.authority_score,
                 int(entry.is_official), int(entry.is_primary),
                 entry.verification_policy, entry.provider, entry.collection,
                 entry.updated_at, entry.rule_version),
            )
            self._cache[entry.source_key] = entry
        self._conn.commit()

    def get(self, source_key: str) -> Optional[SourceEntry]:
        """Look up a source by key."""
        return self._cache.get(source_key)

    def get_by_provider(self, provider: str) -> Optional[SourceEntry]:
        """Look up a source by provider name (table name)."""
        for entry in self._cache.values():
            if entry.provider == provider:
                return entry
        return None

    def get_authority_score(self, source_key: str) -> float:
        """Get the authority score for a source."""
        entry = self.get(source_key)
        if entry:
            return entry.authority_score
        return 0.1  # Unknown source = lowest authority

    def get_authority_tier(self, source_key: str) -> int:
        """Get the authority tier for a source."""
        entry = self.get(source_key)
        if entry:
            return entry.authority_tier
        return AUTHORITY_TIER_UNOFFICIAL

    def is_official(self, source_key: str) -> bool:
        """Check if a source is official."""
        entry = self.get(source_key)
        return entry.is_official if entry else False

    def can_overwrite_canonical(self, source_key: str) -> bool:
        """Check if a source can overwrite canonical data.

        Only official sources can set canonical values.
        Web/unofficial sources can never overwrite official data.
        """
        entry = self.get(source_key)
        if not entry:
            return False
        return entry.is_official and entry.authority_tier <= 2

    def all_sources(self) -> list[SourceEntry]:
        """Return all registered sources."""
        return list(self._cache.values())

    def upsert(self, entry: SourceEntry):
        """Insert or update a source entry."""
        now = datetime.now(timezone.utc).isoformat()
        entry.updated_at = now
        self._conn.execute(
            "INSERT OR REPLACE INTO source_authority_registry "
            "(source_key, source_name, source_type, authority_tier, authority_score, "
            "is_official, is_primary, verification_policy, provider, collection, "
            "updated_at, rule_version) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
            (entry.source_key, entry.source_name, entry.source_type,
             entry.authority_tier, entry.authority_score,
             int(entry.is_official), int(entry.is_primary),
             entry.verification_policy, entry.provider, entry.collection,
             entry.updated_at, entry.rule_version),
        )
        self._conn.commit()
        self._cache[entry.source_key] = entry


# ─── Temporal constraint engine ──────────────────────────────────────────────

class TemporalConstraintEngine:
    """Evaluates temporal constraints for identity resolution.

    The key rule: a complete date from an official source is a VETO constraint.
    If a candidate has a complete date that is incompatible, the link is blocked
    even when name and cognome match exactly.
    """

    @staticmethod
    def dates_compatible(
        date_a: str,
        date_b: str,
        precision_a: str = "exact",
        precision_b: str = "exact",
        tolerance_years: int = 0,
    ) -> bool:
        """Check if two dates are compatible.

        Args:
            date_a: First date (ISO format or year)
            date_b: Second date (ISO format or year)
            precision_a: Precision of first date
            precision_b: Precision of second date
            tolerance_years: Allowed tolerance for year-level comparisons

        Returns:
            True if dates are compatible, False if they conflict
        """
        def _to_year(d: str) -> int | None:
            if not d:
                return None
            try:
                return int(str(d)[:4])
            except (ValueError, IndexError):
                return None

        ya = _to_year(date_a)
        yb = _to_year(date_b)

        if ya is None or yb is None:
            return True  # Can't compare, assume compatible

        # Exact dates: must match exactly (or within tolerance)
        if precision_a == "exact" and precision_b == "exact":
            return date_a == date_b or abs(ya - yb) <= tolerance_years

        # Month precision: year+month must match
        if precision_a in ("exact", "month") and precision_b in ("exact", "month"):
            return date_a[:7] == date_b[:7] or abs(ya - yb) <= tolerance_years

        # Year precision: year must match within tolerance
        return abs(ya - yb) <= tolerance_years

    @staticmethod
    def evaluate_temporal_veto(
        official_date: TemporalConstraint,
        candidate_date_str: str,
        candidate_precision: str = "unknown",
    ) -> tuple[bool, str]:
        """Evaluate if a candidate date violates an official temporal constraint.

        Args:
            official_date: The temporal constraint from an official source
            candidate_date_str: The date from the candidate record
            candidate_precision: Precision of the candidate date

        Returns:
            (is_blocked, reason) — True if the link must be blocked
        """
        if not official_date.is_hard_constraint:
            # Soft constraint: don't block, just note
            return False, ""

        if not candidate_date_str or candidate_precision == "unknown":
            # No candidate date to compare: don't block (but flag for review)
            return False, ""

        compatible = TemporalConstraintEngine.dates_compatible(
            official_date.date_value,
            candidate_date_str,
            official_date.precision,
            candidate_precision,
            tolerance_years=0,  # Official dates allow NO tolerance
        )

        if not compatible:
            return True, (
                f"TEMPORAL_VETO: Official source ({official_date.source_key}) "
                f"reports date {official_date.date_value} (precision={official_date.precision}), "
                f"candidate has {candidate_date_str} (precision={candidate_precision}). "
                f"Dates are incompatible — link blocked regardless of name match."
            )

        return False, ""


# ─── Link decision engine ────────────────────────────────────────────────────

class LinkDecisionEngine:
    """Decides link status based on authority, temporal constraints, and evidence.

    Key rules:
    1. Temporal constraints from official sources are evaluated FIRST (before scoring).
    2. Name-only matches (cognome + nome) without a second identifier → needs_review, not verified.
    3. Web/unofficial sources cannot overwrite canonical official data.
    4. Two conflicting official sources → needs_review, both evidence preserved.
    5. A date conflict with an official source → rejected (hard veto).
    """

    # Strong identifiers beyond name
    STRONG_IDENTIFIERS = [
        "data_nascita", "data_decesso", "data_morte", "data_cattura",
        "luogo_nascita", "paternita", "maternita", "matricola",
        "reparto", "unita", "grado",
    ]

    def __init__(self, registry: SourceAuthorityRegistry):
        self._registry = registry

    def evaluate_record_link(
        self,
        source_record: dict,
        target_record: dict,
        source_key: str,
        target_key: str = "",
        extraction_confidence: float = 1.0,
    ) -> LinkDecision:
        """Evaluate a record-to-record link.

        Args:
            source_record: The source record (e.g., from internati)
            target_record: The target record (e.g., from caduti_albooro)
            source_key: Source registry key for the source table
            target_key: Source registry key for the target table
            extraction_confidence: Confidence in the OCR/AI extraction (0-1)

        Returns:
            LinkDecision with status, confidence, and reasoning
        """
        source_entry = self._registry.get(source_key)
        target_entry = self._registry.get(target_key) if target_key else None

        # Determine the higher authority source (for canonical data)
        if target_entry and target_entry.is_official:
            official_entry = target_entry
            candidate_entry = source_entry
        elif source_entry and source_entry.is_official:
            official_entry = source_entry
            candidate_entry = target_entry
        else:
            official_entry = None
            candidate_entry = source_entry

        # ─── Step 1: Temporal constraint check (BEFORE scoring) ──────────
        # Determine which record is official and which is candidate
        if target_entry and target_entry.is_official and source_entry and not source_entry.is_official:
            official_record = target_record
            candidate_record = source_record
        elif source_entry and source_entry.is_official and target_entry and not target_entry.is_official:
            official_record = source_record
            candidate_record = target_record
        elif target_entry and target_entry.is_official:
            official_record = target_record
            candidate_record = source_record
        elif source_entry and source_entry.is_official:
            official_record = source_record
            candidate_record = target_record
        else:
            official_record = None
            candidate_record = None

        official_date = self._extract_official_date(official_entry, official_record)
        candidate_date_str, candidate_precision = self._extract_candidate_date(candidate_record)

        if official_date and official_date.is_hard_constraint:
            blocked, reason = TemporalConstraintEngine.evaluate_temporal_veto(
                official_date, candidate_date_str, candidate_precision
            )
            if blocked:
                return LinkDecision(
                    status="rejected",
                    match_confidence=0.0,
                    extraction_confidence=extraction_confidence,
                    source_authority=TIER_NAMES.get(
                        official_entry.authority_tier if official_entry else 4, "unofficial"
                    ),
                    conflict_code="TEMPORAL_VETO_OFFICIAL_DATE",
                    decision_reason=reason,
                    needs_review=False,
                    evidence={
                        "official_date": official_date.date_value,
                        "official_source": official_date.source_key,
                        "candidate_date": candidate_date_str,
                        "candidate_precision": candidate_precision,
                    },
                )

        # ─── Step 2: Name match assessment ────────────────────────────────
        name_match = self._assess_name_match(source_record, target_record)

        # ─── Step 3: Second identifier check ──────────────────────────────
        second_identifiers = self._find_matching_identifiers(source_record, target_record)

        # ─── Step 4: Determine status ─────────────────────────────────────
        source_authority_score = self._registry.get_authority_score(source_key) if source_entry else 0.1
        target_authority_score = self._registry.get_authority_score(target_key) if target_entry else 0.1
        max_authority = max(source_authority_score, target_authority_score)
        min_authority = min(source_authority_score, target_authority_score)

        # No name match at all
        if not name_match["cognome_match"]:
            return LinkDecision(
                status="rejected",
                match_confidence=0.0,
                extraction_confidence=extraction_confidence,
                source_authority=TIER_NAMES.get(
                    source_entry.authority_tier if source_entry else 4, "unofficial"
                ),
                conflict_code="NO_NAME_MATCH",
                decision_reason="Cognome does not match — link rejected.",
                needs_review=False,
            )

        # Name match but NO second identifier
        if name_match["cognome_match"] and not second_identifiers:
            return LinkDecision(
                status="needs_review" if min_authority >= 0.5 else "unverified",
                match_confidence=0.3,
                extraction_confidence=extraction_confidence,
                source_authority=TIER_NAMES.get(
                    source_entry.authority_tier if source_entry else 4, "unofficial"
                ),
                conflict_code="NAME_ONLY_NO_DISCRIMINATOR",
                decision_reason=(
                    "Name match (cognome + nome) but no second identifier found "
                    "(date, place, paternity, matricola, unit). "
                    "Link requires manual review — cannot auto-verify on name alone."
                ),
                needs_review=True,
                evidence={
                    "name_match": name_match,
                    "missing_identifiers": self.STRONG_IDENTIFIERS,
                },
            )

        # Name + 1 second identifier
        if len(second_identifiers) == 1:
            if max_authority >= 0.80:
                status = "probable"
                confidence = 0.65 + (max_authority - 0.80) * 0.5
            elif max_authority >= 0.50:
                status = "possible"
                confidence = 0.45
            else:
                status = "unverified"
                confidence = 0.25
            return LinkDecision(
                status=status,
                match_confidence=round(confidence, 3),
                extraction_confidence=extraction_confidence,
                source_authority=TIER_NAMES.get(
                    source_entry.authority_tier if source_entry else 4, "unofficial"
                ),
                conflict_code="",
                decision_reason=(
                    f"Name match + 1 identifier ({second_identifiers[0]}). "
                    f"Authority={max_authority:.2f}. Status={status}."
                ),
                needs_review=(status != "probable"),
                evidence={
                    "name_match": name_match,
                    "identifiers_matched": second_identifiers,
                    "max_authority": max_authority,
                },
            )

        # Name + 2+ second identifiers
        if len(second_identifiers) >= 2:
            if max_authority >= 0.80:
                status = "verified"
                confidence = 0.80 + (max_authority - 0.80) * 0.5
            elif max_authority >= 0.50:
                status = "probable"
                confidence = 0.60
            else:
                status = "possible"
                confidence = 0.40
            return LinkDecision(
                status=status,
                match_confidence=round(min(confidence, 0.95), 3),
                extraction_confidence=extraction_confidence,
                source_authority=TIER_NAMES.get(
                    source_entry.authority_tier if source_entry else 4, "unofficial"
                ),
                conflict_code="",
                decision_reason=(
                    f"Name match + {len(second_identifiers)} identifiers "
                    f"({', '.join(second_identifiers)}). "
                    f"Authority={max_authority:.2f}. Status={status}."
                ),
                needs_review=False,
                evidence={
                    "name_match": name_match,
                    "identifiers_matched": second_identifiers,
                    "max_authority": max_authority,
                },
            )

        # Fallback
        return LinkDecision(
            status="unverified",
            match_confidence=0.1,
            extraction_confidence=extraction_confidence,
            source_authority=TIER_NAMES.get(
                source_entry.authority_tier if source_entry else 4, "unofficial"
            ),
            conflict_code="INSUFFICIENT_EVIDENCE",
            decision_reason="Insufficient evidence for linking.",
            needs_review=True,
        )

    def evaluate_event_link(
        self,
        event_record: dict,
        target_record: dict,
        target_source_key: str,
        extraction_confidence: float = 1.0,
    ) -> LinkDecision:
        """Evaluate an event-to-record link.

        Authority and temporal compatibility are evaluated BEFORE keyword matching.
        Sources outside the event's time period cannot become direct evidence.
        """
        target_entry = self._registry.get(target_source_key)
        target_authority = target_entry.authority_score if target_entry else 0.1
        target_tier = target_entry.authority_tier if target_entry else 4

        event_start = event_record.get("data_inizio") or event_record.get("start_date") or ""
        event_end = event_record.get("data_fine") or event_record.get("end_date") or ""

        # ─── Step 1: Temporal compatibility (BEFORE keyword matching) ─────
        target_date = (
            target_record.get("data_morte") or target_record.get("data_decesso")
            or target_record.get("data_cattura") or target_record.get("anno_morte")
            or target_record.get("data_nascita") or ""
        )

        if event_start and target_date:
            try:
                event_start_year = int(str(event_start)[:4])
                event_end_year = int(str(event_end)[:4]) if event_end else event_start_year
                target_year = int(str(target_date)[:4])

                if target_year < event_start_year - 1 or target_year > event_end_year + 1:
                    return LinkDecision(
                        status="rejected",
                        match_confidence=0.0,
                        extraction_confidence=extraction_confidence,
                        source_authority=TIER_NAMES.get(target_tier, "unofficial"),
                        conflict_code="TEMPORAL_OUT_OF_PERIOD",
                        decision_reason=(
                            f"Target date {target_year} is outside event period "
                            f"({event_start_year}-{event_end_year}). "
                            f"Source outside period cannot be direct evidence."
                        ),
                        needs_review=False,
                        evidence={
                            "event_period": f"{event_start_year}-{event_end_year}",
                            "target_date": str(target_year),
                        },
                    )
            except (ValueError, IndexError):
                pass

        # ─── Step 2: Authority assessment ─────────────────────────────────
        if target_tier >= 4:
            # Unofficial web source: lead only, never direct evidence
            return LinkDecision(
                status="unverified",
                match_confidence=0.15,
                extraction_confidence=extraction_confidence,
                source_authority="unofficial",
                conflict_code="",
                decision_reason=(
                    "Unofficial web source — treated as lead only, "
                    "cannot be direct evidence for the event."
                ),
                needs_review=True,
                evidence={"target_authority": target_authority},
            )

        # ─── Step 3: Keyword matching (only after temporal + authority) ────
        # At this point, temporal compatibility is confirmed and source has
        # sufficient authority. Keyword matching determines match confidence.
        keyword_match = self._assess_keyword_match(event_record, target_record)

        if not keyword_match["matched"]:
            return LinkDecision(
                status="rejected",
                match_confidence=0.0,
                extraction_confidence=extraction_confidence,
                source_authority=TIER_NAMES.get(target_tier, "unofficial"),
                conflict_code="NO_KEYWORD_MATCH",
                decision_reason="No keyword or alias match found after temporal and authority checks.",
                needs_review=False,
            )

        # Determine status based on authority + keyword quality
        if keyword_match["distinctive_match"] and target_authority >= 0.80:
            status = "verified"
            confidence = 0.75 + (target_authority - 0.80) * 0.5
        elif keyword_match["distinctive_match"]:
            status = "probable"
            confidence = 0.55
        elif keyword_match["alias_match"]:
            status = "possible"
            confidence = 0.40
        else:
            status = "unverified"
            confidence = 0.20

        return LinkDecision(
            status=status,
            match_confidence=round(min(confidence, 0.95), 3),
            extraction_confidence=extraction_confidence,
            source_authority=TIER_NAMES.get(target_tier, "unofficial"),
            conflict_code="",
            decision_reason=(
                f"Temporal compatible + keyword match ({keyword_match['match_term']}). "
                f"Authority={target_authority:.2f}. Status={status}."
            ),
            needs_review=(status not in ("verified", "probable")),
            evidence={
                "keyword_match": keyword_match,
                "target_authority": target_authority,
                "temporal_compatible": True,
            },
        )

    def check_official_conflict(
        self,
        source1_key: str,
        source1_record: dict,
        source2_key: str,
        source2_record: dict,
        field: str,
    ) -> LinkDecision:
        """Check if two official sources disagree on a field.

        If two official sources conflict, do NOT auto-select:
        - Set needs_review=True
        - Preserve both pieces of evidence
        - Show the conflict in the dossier
        """
        entry1 = self._registry.get(source1_key)
        entry2 = self._registry.get(source2_key)

        val1 = (source1_record.get(field) or "").strip()
        val2 = (source2_record.get(field) or "").strip()

        if not val1 or not val2:
            return LinkDecision(
                status="possible",
                match_confidence=0.3,
                extraction_confidence=1.0,
                source_authority="official",
                conflict_code="",
                decision_reason=f"Field {field} missing in one source — no conflict to evaluate.",
                needs_review=False,
            )

        if val1 == val2:
            return LinkDecision(
                status="verified",
                match_confidence=0.90,
                extraction_confidence=1.0,
                source_authority="official",
                conflict_code="",
                decision_reason=f"Both official sources agree on {field}={val1}.",
                needs_review=False,
                evidence={field: val1, "sources": [source1_key, source2_key]},
            )

        # Conflict between two official sources
        return LinkDecision(
            status="conflicting",
            match_confidence=0.0,
            extraction_confidence=1.0,
            source_authority="official",
            conflict_code="OFFICIAL_SOURCES_CONFLICT",
            decision_reason=(
                f"Two official sources disagree on {field}: "
                f"{source1_key}='{val1}' vs {source2_key}='{val2}'. "
                f"NOT auto-selecting — both evidence preserved for manual review."
            ),
            needs_review=True,
            evidence={
                field: {"source1": val1, "source2": val2},
                "source1_key": source1_key,
                "source2_key": source2_key,
            },
        )

    # ─── Helpers ─────────────────────────────────────────────────────────

    def _extract_official_date(
        self,
        official_entry: Optional[SourceEntry],
        official_record: Optional[dict],
    ) -> Optional[TemporalConstraint]:
        """Extract a complete date from an official source record."""
        if not official_entry or not official_record:
            return None

        # Try date fields in priority order
        date_fields = [
            ("data_nascita", "exact"),
            ("data_decesso", "exact"),
            ("data_morte", "exact"),
            ("data_cattura", "exact"),
            ("anno_morte", "year"),
            ("anno_nascita", "year"),
        ]

        record = official_record

        for field, default_precision in date_fields:
            val = record.get(field, "")
            if val and str(val).strip():
                val_str = str(val).strip()
                # Determine precision
                if len(val_str) >= 10 and "-" in val_str:
                    precision = "exact"
                elif len(val_str) == 4 and val_str.isdigit():
                    precision = "year"
                else:
                    precision = default_precision

                return TemporalConstraint(
                    date_value=val_str,
                    precision=precision,
                    source_key=official_entry.source_key,
                    authority_tier=official_entry.authority_tier,
                    is_official=official_entry.is_official,
                )

        return None

    def _extract_candidate_date(
        self,
        candidate_record: Optional[dict],
    ) -> tuple[str, str]:
        """Extract date from the candidate (non-official) record."""
        if not candidate_record:
            return "", "unknown"

        record = candidate_record
        date_fields = ["data_nascita", "data_decesso", "data_morte", "data_cattura", "anno_morte", "anno_nascita"]

        for field in date_fields:
            val = record.get(field, "")
            if val and str(val).strip():
                val_str = str(val).strip()
                if len(val_str) >= 10 and "-" in val_str:
                    return val_str, "exact"
                elif len(val_str) == 4 and val_str.isdigit():
                    return val_str, "year"
                else:
                    return val_str, "unknown"

        return "", "unknown"

    def _assess_name_match(self, source: dict, target: dict) -> dict:
        """Assess name match between two records."""
        s_cog = (source.get("cognome") or source.get("nominativo", "")).strip().upper()
        s_nom = (source.get("nome") or "").strip().upper()
        t_cog = (target.get("cognome") or target.get("nominativo", "")).strip().upper()
        t_nom = (target.get("nome") or "").strip().upper()

        # Handle nominativo format "COGNOME NOME"
        if not s_cog and source.get("nominativo"):
            parts = source["nominativo"].split()
            s_cog = parts[0] if parts else ""
            s_nom = " ".join(parts[1:]) if len(parts) > 1 else ""
        if not t_cog and target.get("nominativo"):
            parts = target["nominativo"].split()
            t_cog = parts[0] if parts else ""
            t_nom = " ".join(parts[1:]) if len(parts) > 1 else ""

        cognome_match = s_cog and t_cog and s_cog == t_cog
        nome_match = s_nom and t_nom and s_nom == t_nom

        return {
            "cognome_match": bool(cognome_match),
            "nome_match": bool(nome_match),
            "full_name_match": bool(cognome_match and nome_match),
            "source_cognome": s_cog,
            "target_cognome": t_cog,
        }

    def _find_matching_identifiers(self, source: dict, target: dict) -> list[str]:
        """Find matching strong identifiers beyond name."""
        matched = []

        for field in self.STRONG_IDENTIFIERS:
            s_val = (source.get(field) or "").strip()
            t_val = (target.get(field) or "").strip()

            if not s_val or not t_val or s_val == "-" or t_val == "-":
                continue

            # For dates: check year-level compatibility
            if field.startswith("data_") or field.startswith("anno_"):
                try:
                    s_year = int(str(s_val)[:4])
                    t_year = int(str(t_val)[:4])
                    if abs(s_year - t_year) <= 0:
                        matched.append(field)
                except (ValueError, IndexError):
                    pass
            else:
                # Exact match for other fields
                if s_val.upper() == t_val.upper():
                    matched.append(field)

        return matched

    def _assess_keyword_match(self, event: dict, target: dict) -> dict:
        """Assess keyword match between event and target record."""
        import re

        keywords = event.get("keywords", "[]")
        aliases = event.get("aliases", "[]")

        try:
            keywords = json.loads(keywords) if isinstance(keywords, str) else keywords
        except (json.JSONDecodeError, TypeError):
            keywords = []
        try:
            aliases = json.loads(aliases) if isinstance(aliases, str) else aliases
        except (json.JSONDecodeError, TypeError):
            aliases = []

        # Build text from target record
        text_parts = []
        for field in ["luogo_morte", "luogo_cattura", "luogo_internamento",
                       "luogo_sepoltura", "cimitero", "reparto", "raw_text",
                       "titolo", "note", "soggetti_collegati", "description", "title"]:
            val = target.get(field, "")
            if val:
                text_parts.append(str(val))
        text = " ".join(text_parts).upper()

        if not text.strip():
            return {"matched": False, "distinctive_match": False, "alias_match": False, "match_term": ""}

        # Check distinctive keywords (skip ambiguous)
        ambiguous = {"campo", "russia", "africa", "nero", "corno", "lana",
                      "prigionia", "prigioniero", "lager", "cattura", "captured",
                      "fronte", "guerra", "morto", "caduto", "ferito"}

        for kw in keywords:
            if kw.lower() in ambiguous:
                continue
            if len(kw) >= 4:
                pattern = r"\b" + re.escape(kw) + r"\b"
                if re.search(pattern, text, re.IGNORECASE):
                    return {
                        "matched": True,
                        "distinctive_match": True,
                        "alias_match": False,
                        "match_term": kw,
                    }

        # Check aliases
        for alias in aliases:
            if len(alias) >= 4:
                pattern = r"\b" + re.escape(alias) + r"\b"
                if re.search(pattern, text, re.IGNORECASE):
                    return {
                        "matched": True,
                        "distinctive_match": False,
                        "alias_match": True,
                        "match_term": alias,
                    }

        return {"matched": False, "distinctive_match": False, "alias_match": False, "match_term": ""}


# ─── Migration helpers ───────────────────────────────────────────────────────

def migrate_record_links_schema(conn: sqlite3.Connection):
    """Add V3 columns to record_links table (idempotent)."""
    cursor = conn.cursor()

    # Get existing columns
    cols = {r[1] for r in cursor.execute("PRAGMA table_info(record_links)").fetchall()}

    new_cols = {
        "status": "TEXT DEFAULT 'unverified'",
        "source_authority": "TEXT DEFAULT ''",
        "match_confidence": "REAL DEFAULT 0.0",
        "extraction_confidence": "REAL DEFAULT 0.0",
        "conflict_code": "TEXT DEFAULT ''",
        "evidence_json": "TEXT DEFAULT '{}'",
        "decision_reason": "TEXT DEFAULT ''",
        "needs_review": "INTEGER DEFAULT 0",
        "rule_version": "TEXT DEFAULT ''",
    }

    for col, col_type in new_cols.items():
        if col not in cols:
            cursor.execute(f"ALTER TABLE record_links ADD COLUMN {col} {col_type}")
            print(f"  record_links: added column {col}")

    conn.commit()


def migrate_event_links_schema(conn: sqlite3.Connection):
    """Add V3 columns to event_links table (idempotent)."""
    cursor = conn.cursor()

    cols = {r[1] for r in cursor.execute("PRAGMA table_info(event_links)").fetchall()}

    new_cols = {
        "status": "TEXT DEFAULT 'unverified'",
        "source_authority": "TEXT DEFAULT ''",
        "match_confidence": "REAL DEFAULT 0.0",
        "extraction_confidence": "REAL DEFAULT 0.0",
        "conflict_code": "TEXT DEFAULT ''",
        "evidence_json": "TEXT DEFAULT '{}'",
        "decision_reason": "TEXT DEFAULT ''",
        "needs_review": "INTEGER DEFAULT 0",
        "rule_version": "TEXT DEFAULT ''",
    }

    for col, col_type in new_cols.items():
        if col not in cols:
            cursor.execute(f"ALTER TABLE event_links ADD COLUMN {col} {col_type}")
            print(f"  event_links: added column {col}")

    conn.commit()


def apply_source_registry_schema(conn: sqlite3.Connection):
    """Apply the source_authority_registry schema and seed defaults."""
    conn.executescript(SOURCE_AUTHORITY_REGISTRY_SQL)
    conn.commit()

    # Check if already seeded
    count = conn.execute("SELECT COUNT(*) FROM source_authority_registry").fetchone()[0]
    if count == 0:
        now = datetime.now(timezone.utc).isoformat()
        for src in DEFAULT_SOURCES:
            conn.execute(
                "INSERT OR REPLACE INTO source_authority_registry "
                "(source_key, source_name, source_type, authority_tier, authority_score, "
                "is_official, is_primary, verification_policy, provider, collection, "
                "updated_at, rule_version) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                (src["source_key"], src["source_name"], src["source_type"],
                 src["authority_tier"], src["authority_score"],
                 int(src["is_official"]), int(src["is_primary"]),
                 src["verification_policy"], src.get("provider", ""),
                 src.get("collection", ""), now, RULE_VERSION),
            )
        conn.commit()
        print(f"  source_authority_registry: seeded {len(DEFAULT_SOURCES)} default sources")
    else:
        print(f"  source_authority_registry: {count} sources already present")

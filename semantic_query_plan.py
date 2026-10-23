"""SemanticQueryPlan — immutable, versioned query plan for V7 pipeline.

The SemanticQueryPlan is created once per research request and never mutated.
It defines:
  - intent: what the user wants (PERSON_LOOKUP, EVENT_LOOKUP, AGGREGATE_QUERY, etc.)
  - target: canonical identity of the subject
  - required_claims: which claim fields must be resolved
  - provider_routing: which providers to query, in what order
  - fusion_strategy: how to combine results from multiple providers
  - manifest_hash: cryptographic binding to the QueryManifest

The plan is passed to every provider adapter. Providers cannot deviate from it.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field, asdict
from datetime import datetime
from typing import Dict, List, Optional, Any


# ─── Intent types ───────────────────────────────────────────────────────────

INTENT_TYPES = [
    "PERSON_LOOKUP",
    "EVENT_LOOKUP",
    "AGGREGATE_QUERY",
    "SOURCE_LOOKUP",
    "CONVERSATIONAL_FOLLOWUP",
    "ARCHIVE_SEARCH",
]


# ─── Claim field requirements ───────────────────────────────────────────────

PERSON_CLAIM_FIELDS = [
    "full_birth_date", "birth_year", "birth_place", "paternity",
    "rank", "unit", "service_number",
    "death_date", "death_year", "death_place", "death_cause",
    "captivity", "internment_place", "burial",
    "residence", "decoration_type", "decoration_year",
    "draft_class", "municipality",
    "capture_place", "capture_date", "fate",
]

EVENT_CLAIM_FIELDS = [
    "event_start_date", "event_end_date", "event_location",
    "event_description", "event_phase_count", "event_actors",
]

AGGREGATE_CLAIM_FIELDS = [
    "count", "breakdown", "temporal_distribution", "geographic_distribution",
]


# ─── Fusion strategies ──────────────────────────────────────────────────────

FUSION_STRATEGIES = [
    "MAJORITY_VOTE",
    "HIGHEST_CONFIDENCE",
    "PRESERVE_CONTRADICTIONS",
    "ORIGIN_PRIORITY",
]


# ─── Data classes ───────────────────────────────────────────────────────────

@dataclass
class ProviderRoute:
    """A single provider routing entry in the plan."""
    provider_name: str
    capability: str  # DISCOVERY_WEB|ARCHIVE_SEARCH|CONTENT_FETCH|REPORT_GENERATION|CONVERSATION
    priority: int = 0  # lower = higher priority
    max_results: int = 20
    timeout_ms: int = 30000
    enabled: bool = True
    fallback_only: bool = False


@dataclass
class TargetSpec:
    """Canonical target identity for the query."""
    target_type: str  # person|event|aggregate|source
    display_name: str = ""
    target_id: str = ""
    conflict: str = "UNKNOWN"  # ITALIAN_ONLY|AXIS_ONLY|CONFLICTING|UNKNOWN
    raw_input: str = ""
    parsed_fields: Dict[str, Any] = field(default_factory=dict)
    # V7.2: origin_record_id anchors the query to a specific known record
    # When set, the resolver should use ANCHORED_RECORD status if the record is found
    origin_record_id: str = ""  # e.g. "internati_12345" or "caduti_albooro_678"


@dataclass
class SemanticQueryPlan:
    """Immutable, versioned query plan.

    Created once per research request. Never mutated after creation.
    The manifest_hash binds this plan to the QueryManifest that was used
    to create it, ensuring provenance traceability.
    """
    plan_id: str = ""
    plan_hash: str = ""
    schema_version: str = "7.2"
    intent: str = ""  # PERSON_LOOKUP|EVENT_LOOKUP|AGGREGATE_QUERY|...
    target: TargetSpec = field(default_factory=TargetSpec)
    required_claims: List[str] = field(default_factory=list)
    provider_routes: List[ProviderRoute] = field(default_factory=list)
    fusion_strategy: str = "PRESERVE_CONTRADICTIONS"
    manifest_hash: str = ""
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    metadata: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        if not self.plan_id:
            raw = json.dumps(self._hash_payload(), sort_keys=True, ensure_ascii=False)
            self.plan_hash = hashlib.sha256(raw.encode()).hexdigest()
            self.plan_id = f"plan_v7_{self.plan_hash[:16]}"

    def _hash_payload(self) -> dict:
        d = asdict(self)
        d.pop("plan_id", None)
        d.pop("plan_hash", None)
        d.pop("created_at", None)
        return d

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "SemanticQueryPlan":
        target_d = d.pop("target", {})
        routes_d = d.pop("provider_routes", [])
        target = TargetSpec(**target_d) if isinstance(target_d, dict) else target_d
        routes = [ProviderRoute(**r) if isinstance(r, dict) else r for r in routes_d]
        return cls(target=target, provider_routes=routes, **d)

    def validate(self) -> List[str]:
        """Return list of validation errors. Empty = valid."""
        errors = []
        if self.intent not in INTENT_TYPES:
            errors.append(f"INVALID_INTENT: {self.intent}")
        if not self.target.target_type:
            errors.append("MISSING_TARGET_TYPE")
        if not self.target.display_name and not self.target.target_id:
            errors.append("MISSING_TARGET_IDENTITY")
        if not self.provider_routes:
            errors.append("NO_PROVIDER_ROUTES")
        if self.fusion_strategy not in FUSION_STRATEGIES:
            errors.append(f"INVALID_FUSION_STRATEGY: {self.fusion_strategy}")
        return errors

    def get_providers_for_capability(self, capability: str) -> List[ProviderRoute]:
        """Return enabled provider routes for a given capability, sorted by priority."""
        return sorted(
            [r for r in self.provider_routes if r.enabled and r.capability == capability],
            key=lambda r: r.priority,
        )


# ─── Plan builder ───────────────────────────────────────────────────────────

def build_plan(
    intent: str,
    target: TargetSpec,
    provider_capabilities: List[Dict[str, Any]],
    manifest_hash: str = "",
    fusion_strategy: str = "PRESERVE_CONTRADICTIONS",
    metadata: Optional[Dict[str, Any]] = None,
) -> SemanticQueryPlan:
    """Build a SemanticQueryPlan from intent, target, and available providers.

    Args:
        intent: One of INTENT_TYPES.
        target: Canonical target identity.
        provider_capabilities: List of provider capability dicts, each with:
            provider_name, capabilities (list), available (bool), priority (int).
        manifest_hash: Hash of the QueryManifest that triggered this plan.
        fusion_strategy: How to fuse results from multiple providers.
        metadata: Additional plan metadata.

    Returns:
        A validated SemanticQueryPlan.
    """
    # Determine required claims based on intent
    if intent == "PERSON_LOOKUP":
        required_claims = list(PERSON_CLAIM_FIELDS)
    elif intent == "EVENT_LOOKUP":
        required_claims = list(EVENT_CLAIM_FIELDS)
    elif intent == "AGGREGATE_QUERY":
        required_claims = list(AGGREGATE_CLAIM_FIELDS)
    else:
        required_claims = []

    # Build provider routes from capabilities
    routes: List[ProviderRoute] = []
    for cap in provider_capabilities:
        if not cap.get("available", False):
            continue
        name = cap.get("provider_name", "")
        capabilities = cap.get("capabilities", [])
        priority = cap.get("priority", 99)

        # Map intent to required capability
        if intent in ("PERSON_LOOKUP", "EVENT_LOOKUP", "SOURCE_LOOKUP", "ARCHIVE_SEARCH"):
            required_caps = ["DISCOVERY_WEB", "ARCHIVE_SEARCH", "CONTENT_FETCH"]
        elif intent == "AGGREGATE_QUERY":
            required_caps = ["DISCOVERY_WEB", "ARCHIVE_SEARCH"]
        elif intent == "CONVERSATIONAL_FOLLOWUP":
            required_caps = ["CONVERSATION", "REPORT_GENERATION"]
        else:
            required_caps = ["DISCOVERY_WEB"]

        for cap_type in required_caps:
            if cap_type in capabilities:
                routes.append(ProviderRoute(
                    provider_name=name,
                    capability=cap_type,
                    priority=priority,
                    max_results=cap.get("max_results", 20),
                    timeout_ms=cap.get("timeout_ms", 30000),
                    enabled=True,
                    fallback_only=cap.get("fallback_only", False),
                ))

    # Always include local_db as fallback
    has_local = any(r.provider_name == "local_db" for r in routes)
    if not has_local:
        routes.append(ProviderRoute(
            provider_name="local_db",
            capability="ARCHIVE_SEARCH",
            priority=50,
            max_results=50,
            timeout_ms=5000,
            enabled=True,
            fallback_only=True,
        ))

    plan = SemanticQueryPlan(
        intent=intent,
        target=target,
        required_claims=required_claims,
        provider_routes=routes,
        fusion_strategy=fusion_strategy,
        manifest_hash=manifest_hash,
        metadata=metadata or {},
    )

    errors = plan.validate()
    if errors:
        raise ValueError(f"Invalid query plan: {errors}")

    return plan

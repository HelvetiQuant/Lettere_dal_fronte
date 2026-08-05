"""UnifiedResearchOrchestratorV7 — single orchestrator for the entire V7 pipeline.

Unifies:
  - research_protocol.py (V4 discovery + evidence)
  - research_orchestrator.py (V6 agent loop)
  - report_conversation_provider.py (V6 narration)
  - ai_output_validator.py (V4 validation)

All public endpoints (/api/research-protocol, /api/research/*, /api/report/*)
must route through this orchestrator. No direct calls to V4/V6 modules.

Pipeline stages:
  1. PLAN     — Build SemanticQueryPlan from user input
  2. DISCOVER — Query providers per plan routes, collect ProviderObservations
  3. FETCH    — Open sources, extract content (OCR/metadata)
  4. EXTRACT  — Extract claims from fetched content
  5. RESOLVE  — Identity resolution, homonym rejection
  6. FUSE     — Multi-provider fusion with independence graph
  7. VALIDATE — Check invariants, detect contradictions
  8. NARRATE  — Generate report from snapshot (AI or deterministic)
  9. PERSIST  — Save snapshot + report to DB

Each stage is idempotent, observable, and non-destructive.
"""
from __future__ import annotations

import hashlib
import json
import time
import logging
from datetime import datetime
from typing import Dict, List, Optional, Any, Tuple

from semantic_query_plan import (
    SemanticQueryPlan, TargetSpec, ProviderRoute,
    build_plan, INTENT_TYPES,
)
from evidence_snapshot_v7 import (
    EvidenceSnapshotV7, ClaimV7, EvidenceItemV7,
    ProviderLedgerEntryV7, ConditionalGapV7, LimitationV7,
    SourceLineageGroup, IndependenceGroup, CorrectionLayer,
    ContextSourceV7, WebLeadV7, RejectedCandidateV7,
)
from provider_observation import (
    ProviderObservation, ProviderCapabilityRegistry, ProviderCapability,
    CAPABILITY_TYPES,
)
from v7_provider_adapters import V7AdapterRegistry
from v7_identity_model import IdentityResolver, CorrectionLedger, CanonicalIdentity
from v7_fusion_engine import SourceFamilyGraph, IndependenceAssessor, FusionEngine
from v7_event_aggregate import AggregateDefinitionRegistry, EventOntology
from v7_narrator import NarratorV7, OutputValidatorV7, ReportRenderer, CitationResolver, NarratorV7_v2
from narration_models import NarrationResult

logger = logging.getLogger(__name__)


# ─── Run context ────────────────────────────────────────────────────────────

class RunContext:
    """Per-run state container. Tracks all observations and intermediate results."""

    def __init__(self, run_id: str, plan: SemanticQueryPlan):
        self.run_id = run_id
        self.plan = plan
        self.observations: List[ProviderObservation] = []
        self.snapshot: Optional[EvidenceSnapshotV7] = None
        self.report: Optional[str] = None
        self.report_structured: Optional[Dict[str, Any]] = None
        self.started_at = datetime.now().isoformat()
        self.completed_at: Optional[str] = None
        self.errors: List[str] = []
        self.warnings: List[str] = []
        self.stage_timings: Dict[str, float] = {}
        self.identity_resolver = IdentityResolver()
        self.correction_ledger = CorrectionLedger()
        self.resolved_identity: Optional[CanonicalIdentity] = None
        self.rejected_homonyms: List = []
        self.narration_result = None

    def add_observation(self, obs: ProviderObservation):
        obs.run_id = self.run_id
        obs.manifest_hash = self.plan.manifest_hash
        self.observations.append(obs)

    def to_dict(self) -> dict:
        return {
            "run_id": self.run_id,
            "plan_id": self.plan.plan_id,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "observation_count": len(self.observations),
            "snapshot_id": self.snapshot.snapshot_id if self.snapshot else None,
            "has_report": self.report is not None,
            "errors": self.errors,
            "warnings": self.warnings,
            "stage_timings": self.stage_timings,
        }


# ─── Orchestrator ───────────────────────────────────────────────────────────

class UnifiedResearchOrchestratorV7:
    """Single entry point for all research, narration, and validation.

    Usage:
        orch = UnifiedResearchOrchestratorV7()
        result = orch.execute(user_input="Mario Rossi", intent="PERSON_LOOKUP")
    """

    SCHEMA_VERSION = "7.2"
    ORCHESTRATOR_CLASS = "UnifiedResearchOrchestratorV7"

    def __init__(self, capability_registry: Optional[ProviderCapabilityRegistry] = None):
        self._capability_registry = capability_registry or ProviderCapabilityRegistry()
        self._adapter_registry = V7AdapterRegistry(self._capability_registry)
        self._aggregate_registry = AggregateDefinitionRegistry()
        self._event_ontology = EventOntology()
        self._narrator = NarratorV7()
        self._narrator_v2 = NarratorV7_v2()
        self._runs: Dict[str, RunContext] = {}

    # ─── Public API ─────────────────────────────────────────────────────────

    def execute(
        self,
        user_input: str,
        intent: str = "PERSON_LOOKUP",
        target_id: str = "",
        conflict: str = "UNKNOWN",
        manifest_hash: str = "",
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Execute a full research pipeline.

        Returns a dict with:
          - run_id
          - plan_id
          - snapshot (dict or None)
          - report (str or None)
          - errors
          - warnings
        """
        t_start = time.time()

        # 1. PLAN
        t0 = time.time()
        plan = self._stage_plan(user_input, intent, target_id, conflict, manifest_hash, metadata)
        self._stage_timings_set("plan", time.time() - t0)

        run_id = f"run_v7_{int(time.time())}_{hashlib.sha256(user_input.encode()).hexdigest()[:8]}"
        ctx = RunContext(run_id, plan)
        self._runs[run_id] = ctx

        try:
            # 2. DISCOVER
            t0 = time.time()
            self._stage_discover(ctx)
            ctx.stage_timings["discover"] = time.time() - t0

            # 3. FETCH
            t0 = time.time()
            self._stage_fetch(ctx)
            ctx.stage_timings["fetch"] = time.time() - t0

            # 4. EXTRACT
            t0 = time.time()
            self._stage_extract(ctx)
            ctx.stage_timings["extract"] = time.time() - t0

            # 5. RESOLVE
            t0 = time.time()
            self._stage_resolve(ctx)
            ctx.stage_timings["resolve"] = time.time() - t0

            # 6. FUSE
            t0 = time.time()
            self._stage_fuse(ctx)
            ctx.stage_timings["fuse"] = time.time() - t0

            # 7. VALIDATE
            t0 = time.time()
            self._stage_validate(ctx)
            ctx.stage_timings["validate"] = time.time() - t0

            # 8. NARRATE
            t0 = time.time()
            self._stage_narrate(ctx)
            ctx.stage_timings["narrate"] = time.time() - t0

            # 9. PERSIST
            t0 = time.time()
            self._stage_persist(ctx)
            ctx.stage_timings["persist"] = time.time() - t0

        except Exception as e:
            ctx.errors.append(f"PIPELINE_ERROR: {e}")
            logger.exception(f"Pipeline error in run {run_id}")

        ctx.completed_at = datetime.now().isoformat()
        ctx.stage_timings["total"] = time.time() - t_start

        # V7.3-PERSON: Compute semantic counts
        semantic_counts = self._compute_semantic_counts(ctx)

        return {
            "run_id": run_id,
            "plan_id": plan.plan_id,
            "snapshot": ctx.snapshot.to_dict() if ctx.snapshot else None,
            "report": ctx.report,
            "report_structured": ctx.report_structured,
            "narration_result": ctx.narration_result.to_dict() if hasattr(ctx, 'narration_result') and ctx.narration_result else None,
            "errors": ctx.errors,
            "warnings": ctx.warnings,
            "stage_timings": ctx.stage_timings,
            "observation_count": len(ctx.observations),
            "semantic_counts": semantic_counts,
        }

    def get_run(self, run_id: str) -> Optional[RunContext]:
        return self._runs.get(run_id)

    def get_capabilities(self) -> Dict[str, Any]:
        """Return current capability snapshot for /api/system/capabilities."""
        return {
            "orchestrator_class": self.ORCHESTRATOR_CLASS,
            "schema_version": self.SCHEMA_VERSION,
            "narrator_contract_version": "7.2",
            "providers": {
                name: {
                    "capabilities": cap.capabilities,
                    "available": cap.available,
                    "contract_version": cap.contract_version,
                }
                for name, cap in self._capability_registry.all_providers().items()
            },
        }

    # ─── Stage implementations ──────────────────────────────────────────────

    def _lookup_origin_record(self, target: TargetSpec) -> Optional[Dict[str, Any]]:
        """Look up the origin DB record for a PERSON_LOOKUP target.

        Searches internati table by cognome+nome to provide context
        for query family construction and anomaly detection.
        """
        try:
            from database import get_conn
            conn = get_conn()
            name = target.display_name.strip()
            parts = name.split(None, 1)
            cognome = parts[0] if parts else name
            nome = parts[1] if len(parts) > 1 else ""

            if nome:
                row = conn.execute(
                    "SELECT * FROM internati WHERE cognome=? AND nome=? LIMIT 1",
                    (cognome, nome),
                ).fetchone()
            else:
                row = conn.execute(
                    "SELECT * FROM internati WHERE cognome=? LIMIT 1",
                    (cognome,),
                ).fetchone()

            conn.close()
            if row:
                cols = [d[0] for d in conn.execute("PRAGMA table_info(internati)").fetchall()] if row else []
                # Use Row keys if available (sqlite3.Row)
                try:
                    return dict(row)
                except Exception:
                    return dict(zip(cols, row)) if cols else {}
            return None
        except Exception as e:
            logger.debug(f"_lookup_origin_record failed: {e}")
            return None

    def _lookup_event_record(self, target: TargetSpec) -> Optional[Dict[str, Any]]:
        """Look up the event record from eventi_1gm for EVENT_LOOKUP target.

        Searches by nome (exact or LIKE) to provide keywords/aliases
        for query family construction.
        """
        try:
            from database import get_conn
            conn = get_conn()
            name = target.display_name.strip()

            row = conn.execute(
                "SELECT * FROM eventi_1gm WHERE nome = ? OR nome LIKE ? LIMIT 1",
                (name, f"%{name}%"),
            ).fetchone()

            conn.close()
            if row:
                try:
                    return dict(row)
                except Exception:
                    return None
            return None
        except Exception as e:
            logger.debug(f"_lookup_event_record failed: {e}")
            return None

    def _stage_plan(
        self,
        user_input: str,
        intent: str,
        target_id: str,
        conflict: str,
        manifest_hash: str,
        metadata: Optional[Dict[str, Any]],
    ) -> SemanticQueryPlan:
        """Stage 1: Build SemanticQueryPlan."""
        if intent not in INTENT_TYPES:
            raise ValueError(f"Invalid intent: {intent}. Must be one of {INTENT_TYPES}")

        target = TargetSpec(
            target_type=intent.split("_")[0].lower(),
            display_name=user_input,
            target_id=target_id,
            conflict=conflict,
            raw_input=user_input,
        )

        # Gather provider capabilities
        provider_caps = []
        for name, cap in self._capability_registry.all_providers().items():
            provider_caps.append({
                "provider_name": name,
                "capabilities": cap.capabilities,
                "available": cap.available,
                "priority": 10 if name == "local_db" else 20,
                "max_results": cap.max_results,
                "timeout_ms": cap.timeout_ms,
            })

        plan = build_plan(
            intent=intent,
            target=target,
            provider_capabilities=provider_caps,
            manifest_hash=manifest_hash,
            metadata=metadata or {},
        )

        return plan

    def _stage_discover(self, ctx: RunContext):
        """Stage 2: Query providers per plan routes, collect ProviderObservations.

        Uses V7AdapterRegistry to dispatch searches across all available
        providers (local_db, web search, federation) in a unified way.
        V7.2: Uses query families — multiple query variants (nominative,
        event-based, OCR variants, geographic) instead of a single query.
        For AGGREGATE_QUERY intent, executes registered aggregate definitions
        instead of provider searches.
        """
        plan = ctx.plan

        # Handle aggregate queries differently
        if plan.intent == "AGGREGATE_QUERY":
            agg_def = self._aggregate_registry.get_by_name(plan.target.display_name)
            if not agg_def:
                # Try to find a matching definition by keyword
                for d in self._aggregate_registry.all_definitions().values():
                    if plan.target.display_name.lower() in d.name.lower() or d.name.lower() in plan.target.display_name.lower():
                        agg_def = d
                        break

            if agg_def:
                result = self._aggregate_registry.execute(agg_def.definition_id)
                if result:
                    ctx._aggregate_result = result
                    ctx._aggregate_definition_id = agg_def.definition_id
                else:
                    ctx.warnings.append("AGGREGATE_QUERY_FAILED")
            else:
                ctx.warnings.append(f"NO_AGGREGATE_DEFINITION_FOR: {plan.target.display_name}")
            return

        # Check if any providers are available
        discovery_routes = plan.get_providers_for_capability("DISCOVERY_WEB")
        archive_routes = plan.get_providers_for_capability("ARCHIVE_SEARCH")

        if not discovery_routes and not archive_routes:
            ctx.warnings.append("NO_DISCOVERY_PROVIDERS_AVAILABLE")

        # V7.2: Build query family for multi-variant discovery
        from v7_query_family import build_query_family
        record_for_queries = None
        if plan.intent == "PERSON_LOOKUP":
            record_for_queries = self._lookup_origin_record(plan.target)
        elif plan.intent == "EVENT_LOOKUP":
            record_for_queries = self._lookup_event_record(plan.target)
        query_family = build_query_family(
            target_name=plan.target.display_name,
            record=record_for_queries,
            intent=plan.intent,
        )
        ctx._query_family = query_family

        # Execute primary query through adapter registry (includes local DB + web + federation)
        observations = self._adapter_registry.search_all(plan)

        for obs in observations:
            ctx.add_observation(obs)

        # V7.2: Execute additional query variants through web search adapters
        # (local DB already searched via primary query; web variants expand coverage)
        if discovery_routes:
            web_adapters = self._adapter_registry.get_discovery_adapters()
            primary_query = plan.target.display_name.lower()

            for variant in query_family.sorted_variants():
                # Skip variants that are just the primary query (already done)
                if variant.query_text.lower() == primary_query:
                    continue
                # Skip variants from families already covered by primary
                if variant.family == "NOMINATIVE" and variant.priority <= 2:
                    continue

                # Create a temporary plan variant for this query
                from semantic_query_plan import TargetSpec
                variant_target = TargetSpec(
                    target_type=plan.target.target_type,
                    display_name=variant.query_text,
                    target_id=plan.target.target_id,
                    conflict=plan.target.conflict,
                    raw_input=variant.query_text,
                    origin_record_id=plan.target.origin_record_id,
                )
                variant_plan = SemanticQueryPlan(
                    intent=plan.intent,
                    target=variant_target,
                    required_claims=plan.required_claims,
                    provider_routes=[r for r in plan.provider_routes if r.capability == "DISCOVERY_WEB"],
                    fusion_strategy=plan.fusion_strategy,
                    manifest_hash=plan.manifest_hash,
                    metadata={**plan.metadata, "query_family": variant.family, "query_purpose": variant.purpose},
                )

                for adapter in web_adapters:
                    try:
                        variant_obs = adapter.search(variant_plan)
                        for obs in variant_obs:
                            # Tag observation with its query family
                            obs.provider_metadata = obs.provider_metadata or {}
                            obs.provider_metadata["_query_family"] = variant.family
                            obs.provider_metadata["_query_purpose"] = variant.purpose
                            ctx.add_observation(obs)
                    except Exception as e:
                        logger.debug(f"Query variant '{variant.query_text}' failed on {adapter.provider_name}: {e}")

        if not ctx.observations:
            ctx.warnings.append("NO_OBSERVATIONS_COLLECTED")

    def _stage_fetch(self, ctx: RunContext):
        """Stage 3: Open sources, extract content.

        V7.2: Filters out search-page URLs (legacy _clean_bad_links.py logic).
        """
        try:
            from mass_index import _is_search_page_url
        except ImportError:
            _is_search_page_url = None

        for obs in ctx.observations:
            if obs.content_state == "NOT_OPENED":
                # V7.2: Reject search-page URLs
                if _is_search_page_url and obs.url_canonical and _is_search_page_url(obs.url_canonical):
                    obs.content_state = "FAILED"
                    obs.reason_codes.append("SEARCH_PAGE_URL")
                    obs.classification = "REJECTED"
                    continue

                if obs.snippet or obs.excerpt:
                    obs.content_state = "METADATA_ONLY"
                else:
                    obs.content_state = "FAILED"
                    obs.reason_codes.append("NO_CONTENT_AVAILABLE")

    def _stage_extract(self, ctx: RunContext):
        """Stage 4: Extract claims from fetched content.

        V7.2: Uses classify_observation to assign observations to identity clusters.
        Surname-only matches are classified as SURNAME_ONLY_NON_CANDIDATE and hidden.
        V7.2: For EVENT_LOOKUP, extracts event claims from DB records and web snippets.
        V7.2: Runs anomaly detection on raw DB records before extraction.
        V7.2: Applies claim-level rules after extraction.
        """
        plan = ctx.plan
        target_name = plan.target.display_name.strip()
        parts = target_name.split()
        cognome = parts[0] if parts else target_name
        nome = " ".join(parts[1:]) if len(parts) > 1 else ""

        ctx.identity_resolver.set_target(cognome, nome, origin_record_id=getattr(plan.target, 'origin_record_id', ''))

        # V7.2: Event claim extraction
        if plan.intent == "EVENT_LOOKUP":
            self._stage_extract_events(ctx)
            return

        # V7.2: Anomaly detection on origin record
        from v7_record_anomaly import detect_anomalies as _detect_anomalies
        anomaly_reports = []

        for obs in ctx.observations:
            if obs.content_state in ("NOT_OPENED", "FAILED"):
                continue

            meta = obs.provider_metadata
            if not meta or not isinstance(meta, dict):
                continue

            raw_record = meta.get("raw_record")
            if not raw_record or not isinstance(raw_record, dict):
                continue

            table = meta.get("table", "")

            # V7.2: Run anomaly detection on the raw record
            anomaly_report = _detect_anomalies(
                table=table,
                record=raw_record,
                record_id=str(raw_record.get("id", "")),
            )
            if anomaly_report.has_anomalies:
                anomaly_reports.append(anomaly_report)
                # Store on observation for downstream use
                obs.provider_metadata["_anomalies"] = anomaly_report.to_dict()
                for a in anomaly_report.anomalies:
                    ctx.warnings.append(f"ANOMALY: {a.anomaly_type} on {table}.{a.field_name}: {a.question}")

            # V7.2: classify observation using cluster-based resolver
            classification, cluster = ctx.identity_resolver.classify_observation(
                raw_record, provider=obs.provider, table=table,
            )

            if classification == "FULL_NAME_CANDIDATE" and cluster:
                obs.source_record_id = cluster.cluster_id
                obs.classification = "SOURCE_CANDIDATE"
            elif classification == "SURNAME_ONLY_NON_CANDIDATE":
                obs.classification = "SURNAME_ONLY_NON_CANDIDATE"
                obs.reason_codes.append("SURNAME_ONLY_NON_CANDIDATE")
            else:
                # Legacy fallback for non-person intents
                identity, reason_codes = ctx.identity_resolver.resolve_observation(
                    raw_record, provider=obs.provider, table=table,
                )
                if identity:
                    obs.source_record_id = identity.identity_id
                    obs.classification = "SOURCE_CANDIDATE"
                elif reason_codes:
                    obs.reason_codes.extend(reason_codes)

        # V7.3-PERSON: Extract claims from local DB records
        self._stage_extract_person_claims(ctx)

    def _stage_extract_person_claims(self, ctx: RunContext):
        """Extract claims from local DB records for PERSON pipeline.

        V7.3-PERSON-FIX: Uses person_source_schemas registry for mapping
        across all 5 PERSON tables (internati, caduti_albooro,
        decorati_nastroazzurro, caduti_cwgc, caduti_ministero).
        Separates claims from provenance — provenance items are NOT counted
        as person facts.
        """
        from evidence_snapshot_v7 import ClaimV7
        from person_source_schemas import (
            PERSON_SOURCE_SCHEMAS, extract_claims_from_record,
            get_war_period_for_table, get_name_fields_for_table,
        )
        from person_pipeline_models import (
            PersonCandidate, FactEvidence, SourceProvenance, PersonFact,
            ConflictSet, ConflictEntry,
        )
        import hashlib as _hashlib

        person_claims = []
        context_claims = []
        provenance_items = []
        person_candidates = []
        all_evidence = []

        for obs in ctx.observations:
            if obs.classification != "SOURCE_CANDIDATE":
                continue

            meta = obs.provider_metadata
            if not meta or not isinstance(meta, dict):
                continue

            raw_record = meta.get("raw_record")
            if not raw_record or not isinstance(raw_record, dict):
                continue

            table = meta.get("table", "")
            record_id = raw_record.get("id", "")

            # Extract from all 5 PERSON DB tables using schema registry
            if table not in PERSON_SOURCE_SCHEMAS:
                continue

            source_id = f"local_db:{table}:{record_id}"
            war_period = get_war_period_for_table(table)

            # Build PersonCandidate
            name_fields = get_name_fields_for_table(table)
            cognome_col, nome_col, nominativo_col = name_fields
            cand_cognome = raw_record.get(cognome_col, "") if cognome_col else ""
            cand_nome = raw_record.get(nome_col, "") if nome_col else ""
            cand_nominativo = raw_record.get(nominativo_col, "") if nominativo_col else ""

            candidate = PersonCandidate(
                candidate_id="",
                source_table=table,
                record_id=record_id,
                cognome=str(cand_cognome or "").strip(),
                nome=str(cand_nome or "").strip(),
                nominativo=str(cand_nominativo or "").strip(),
                war_period=war_period,
                authority_tier=PERSON_SOURCE_SCHEMAS[table].authority_tier,
                raw_record=raw_record,
            )
            person_candidates.append(candidate)

            # Extract claims and provenance using schema registry
            extracted_claims, extracted_provenance = extract_claims_from_record(table, raw_record, record_id)

            for ec in extracted_claims:
                if ec["validation_status"] == "invalid":
                    context_claims.append(ClaimV7(
                        claim_id=f"claim_invalid_{_hashlib.sha256((ec['predicate'] + '_' + source_id).encode()).hexdigest()[:12]}",
                        subject_id=obs.source_record_id or f"{table}_{record_id}",
                        predicate=ec["predicate"],
                        value_normalized=ec["value_normalized"],
                        value_raw=ec["value_raw"],
                        status="CONTEXT",
                        confidence=0.3,
                        source=source_id,
                        evidence_ids=[obs.observation_id],
                        evidence_scope="CONTEXT_EVIDENCE",
                        source_function="person_evidence",
                        normalization_status="invalid",
                    ))
                    continue

                claim_id = f"claim_person_{_hashlib.sha256((ec['predicate'] + '_' + source_id).encode()).hexdigest()[:12]}"
                person_claims.append(ClaimV7(
                    claim_id=claim_id,
                    subject_id=obs.source_record_id or f"{table}_{record_id}",
                    predicate=ec["predicate"],
                    value_normalized=ec["value_normalized"],
                    value_raw=ec["value_raw"],
                    status="ASSERTED",
                    confidence=0.85,
                    source=source_id,
                    evidence_ids=[obs.observation_id],
                    evidence_scope="PERSON_EVIDENCE",
                    source_function="person_evidence",
                    normalization_status="normalized" if ec["normalizer_note"] else "exact",
                ))

                # Build FactEvidence
                ev = FactEvidence(
                    evidence_id="",
                    candidate_id=candidate.candidate_id,
                    source_table=table,
                    record_id=record_id,
                    source_field=ec["source_field"],
                    value_raw=ec["value_raw"],
                    value_normalized=ec["value_normalized"],
                    normalizer_note=ec["normalizer_note"],
                    authority_tier=PERSON_SOURCE_SCHEMAS[table].authority_tier,
                    war_period=war_period,
                )
                all_evidence.append(ev)

            # Extract provenance (separate from claims)
            for ep in extracted_provenance:
                prov = SourceProvenance(
                    provenance_id="",
                    candidate_id=candidate.candidate_id,
                    source_table=table,
                    record_id=record_id,
                    predicate=ep["predicate"],
                    value_raw=ep["value_raw"],
                    value_normalized=ep["value_normalized"],
                    source_field=ep["source_field"],
                )
                provenance_items.append(prov)

                # Also add as context claim for narrator visibility
                claim_id = f"claim_prov_{_hashlib.sha256((ep['predicate'] + '_' + source_id).encode()).hexdigest()[:12]}"
                context_claims.append(ClaimV7(
                    claim_id=claim_id,
                    subject_id=obs.source_record_id or f"{table}_{record_id}",
                    predicate=ep["predicate"],
                    value_normalized=ep["value_normalized"],
                    value_raw=ep["value_raw"],
                    status="CONTEXT",
                    confidence=0.5,
                    source=source_id,
                    evidence_ids=[obs.observation_id],
                    evidence_scope="PROVENANCE",
                    source_function="provenance",
                    normalization_status="exact",
                ))

            # V7.3-PERSON-FIX: raw_text and needs_review (only for internati)
            raw_text = raw_record.get("raw_text", "")
            if raw_text and str(raw_text).strip():
                # Check if record has needs_review flag
                needs_review = raw_record.get("needs_review", 0)
                review_reason = raw_record.get("review_reason", "")
                text_preview = str(raw_text).strip()[:500]

                claim_id = f"claim_raw_{_hashlib.sha256(f'raw_text_{source_id}'.encode()).hexdigest()[:12]}"
                person_claims.append(ClaimV7(
                    claim_id=claim_id,
                    subject_id=obs.source_record_id or f"{table}_{record_id}",
                    predicate="source_text",
                    value_normalized=text_preview,
                    value_raw=str(raw_text).strip()[:1000],
                    status="ASSERTED" if not needs_review else "NEEDS_REVIEW",
                    confidence=0.70 if not needs_review else 0.40,
                    source=source_id,
                    evidence_ids=[obs.observation_id],
                    evidence_scope="PERSON_EVIDENCE",
                    source_function="person_evidence",
                    normalization_status="raw",
                ))

                if review_reason:
                    claim_id = f"claim_review_{_hashlib.sha256(f'review_{source_id}'.encode()).hexdigest()[:12]}"
                    person_claims.append(ClaimV7(
                        claim_id=claim_id,
                        subject_id=obs.source_record_id or f"{table}_{record_id}",
                        predicate="data_quality_note",
                        value_normalized=review_reason,
                        value_raw=review_reason,
                        status="ASSERTED",
                        confidence=0.95,
                        source=source_id,
                        evidence_ids=[obs.observation_id],
                        evidence_scope="PERSON_EVIDENCE",
                        source_function="person_evidence",
                        normalization_status="exact",
                    ))

        ctx._person_claims = person_claims
        ctx._context_claims = context_claims
        ctx._fused_accepted = []
        ctx._fused_conflicting = []
        ctx._fused_asserted = person_claims
        ctx._source_lineage_groups = []
        ctx._independence_groups = []
        # V7.3-PERSON-FIX: Store typed objects for semantic counts
        ctx._person_candidates = person_candidates
        ctx._person_evidence = all_evidence
        ctx._person_provenance = provenance_items

    def _stage_extract_events(self, ctx: RunContext):
        """Extract event claims from DB records and web search snippets.

        For each observation:
        - DB records (eventi_1gm): extract structured claims (dates, location, description)
        - Web search results: extract snippet-based context claims
        """
        from evidence_snapshot_v7 import ClaimV7
        import hashlib as _hashlib

        event_claims = []
        context_claims = []

        for obs in ctx.observations:
            if obs.content_state in ("NOT_OPENED", "FAILED"):
                continue

            meta = obs.provider_metadata
            if not meta or not isinstance(meta, dict):
                continue

            table = meta.get("table", "")

            # DB record from eventi_1gm → structured claims
            if table == "eventi_1gm":
                raw = meta.get("raw_record", {})
                if not raw:
                    continue

                obs.classification = "SOURCE_CANDIDATE"
                obs.source_record_id = f"eventi_1gm_{raw.get('id', '')}"

                claim_fields = {
                    "event_start_date": ("data_inizio", "data_inizio"),
                    "event_end_date": ("data_fine", "data_fine"),
                    "event_location": ("luogo", "luogo"),
                    "event_description": ("descrizione", "descrizione"),
                }

                # V7.2: Run anomaly detection on event record
                from v7_record_anomaly import detect_anomalies as _detect_anomalies
                anomaly_report = _detect_anomalies(table="eventi_1gm", record=raw, record_id=str(raw.get('id', '')))
                if anomaly_report.has_anomalies:
                    obs.provider_metadata["_anomalies"] = anomaly_report.to_dict()
                    for a in anomaly_report.anomalies:
                        ctx.warnings.append(f"ANOMALY: {a.anomaly_type} on eventi_1gm.{a.field_name}: {a.question}")

                for predicate, (field, source) in claim_fields.items():
                    val = raw.get(field, "")
                    if val and str(val).strip():
                        claim_id = f"claim_evt_{_hashlib.sha256(f'{predicate}_{obs.source_record_id}'.encode()).hexdigest()[:12]}"
                        event_claims.append(ClaimV7(
                            claim_id=claim_id,
                            subject_id=f"eventi_1gm_{raw.get('id', '')}",
                            predicate=predicate,
                            value_normalized=str(val).strip(),
                            value_raw=str(val).strip(),
                            status="ASSERTED",
                            confidence=0.85,
                            source=f"local_db:eventi_1gm:{raw.get('id','')}",
                            evidence_ids=[obs.observation_id],
                            evidence_scope="EVENT_EVIDENCE",
                            source_function="person_evidence",
                            normalization_status="exact",
                        ))

            # Web search results → context claims from snippets
            elif obs.classification == "SEARCH_RESULT" and obs.snippet:
                # V7.2: Classify source function based on query family
                query_family = meta.get("_query_family", "")
                if query_family == "GEOGRAPHIC_INVERSE":
                    src_func = "place_normalization_evidence"
                elif query_family == "EVENT_BASED":
                    src_func = "event_context"
                else:
                    src_func = "research_lead"

                claim_id = f"claim_ctx_{_hashlib.sha256(f'{obs.observation_id}_snippet'.encode()).hexdigest()[:12]}"
                context_claims.append(ClaimV7(
                    claim_id=claim_id,
                    subject_id=obs.observation_id,
                    predicate="web_context",
                    value_normalized=obs.snippet[:300],
                    value_raw=obs.snippet[:500],
                    status="CONTEXT",
                    confidence=0.3,
                    source=f"{obs.provider}:{obs.observation_id}",
                    evidence_ids=[obs.observation_id],
                    evidence_scope="CONTEXT_EVIDENCE",
                    source_function=src_func,
                    normalization_status="",
                ))

        ctx._fused_accepted = []
        ctx._fused_conflicting = []
        ctx._fused_asserted = event_claims
        ctx._person_claims = event_claims
        ctx._context_claims = context_claims
        ctx._source_lineage_groups = []
        ctx._independence_groups = []


    def _stage_resolve(self, ctx: RunContext):
        """Stage 5: Identity resolution via cluster-based discriminant analysis.

        V7.2: Uses IdentityResolver.resolve() to determine:
        - ANCHORED_RECORD: single cluster, query started from a known record
        - RESOLVED_IDENTITY: single cluster with discriminants, no conflicts
        - PARTIAL_IDENTITY: single cluster, no discriminants
        - AMBIGUOUS_IDENTITY: 2+ clusters that cannot be separated
        - UNRESOLVED_IDENTITY: 0 clusters

        Surname-only matches are NOT shown as rejected candidates.
        V7.2: For EVENT_LOOKUP, skips person resolution and sets event status.
        """
        plan = ctx.plan
        target_name = plan.target.display_name.strip()
        if not target_name:
            ctx.errors.append("RESOLVE_NO_TARGET_NAME")
            return

        # V7.2: Event lookup — skip person identity resolution
        if plan.intent == "EVENT_LOOKUP":
            has_db_match = any(
                obs.classification == "SOURCE_CANDIDATE"
                and obs.provider_metadata.get("table") == "eventi_1gm"
                for obs in ctx.observations
            )
            ctx.identity_status_v72 = "RESOLVED_IDENTITY" if has_db_match else "PARTIAL_IDENTITY"
            ctx.resolved_cluster = None
            ctx.candidate_clusters = []
            ctx.resolved_identity = None
            return

        # V7.2: cluster-based resolution
        identity_status, resolved_cluster, candidate_clusters = ctx.identity_resolver.resolve()

        ctx.identity_status_v72 = identity_status
        ctx.resolved_cluster = resolved_cluster
        ctx.candidate_clusters = candidate_clusters

        # Build rejected candidates only from true homonyms (full-name matches in other clusters)
        for other_cluster in candidate_clusters:
            if resolved_cluster and other_cluster.cluster_id == resolved_cluster.cluster_id:
                continue
            conflicting = other_cluster.conflicting_fields if other_cluster else []
            rejected = ctx.identity_resolver.reject_homonym(
                identity=None,
                candidate={
                    "nominativo": other_cluster.display_name,
                    "cognome": other_cluster.cognome,
                    "nome": other_cluster.nome,
                    **other_cluster.discriminant_values,
                },
                reason_codes=["HOMONYM_DIFFERENT_IDENTITY"] + conflicting,
                conflicting_features=conflicting,
            )
            ctx.rejected_homonyms.append(rejected)

        # Legacy compat: set resolved_identity for _build_snapshot
        if resolved_cluster:
            from v7_identity_model import CanonicalIdentity
            canonical_fields = {
                "cognome": resolved_cluster.cognome,
                "nome": resolved_cluster.nome,
                **resolved_cluster.discriminant_values,
            }
            conflict = plan.target.conflict
            ctx.resolved_identity = CanonicalIdentity(
                identity_type="person",
                display_name=resolved_cluster.display_name,
                canonical_fields=canonical_fields,
                provenance=",".join(resolved_cluster.source_tables),
                confidence=0.9 if identity_status in ("ANCHORED_RECORD", "RESOLVED_IDENTITY") else 0.5,
                conflict=conflict,
                source_record_ids=[r.get("id", "") for r in resolved_cluster.record_refs if isinstance(r, dict)],
            )
        else:
            ctx.resolved_identity = None

    def _stage_fuse(self, ctx: RunContext):
        """Stage 6: Multi-provider fusion with independence graph.

        V7.2: BLOCKED if identity_status is AMBIGUOUS_IDENTITY.
        Only fuses observations from the resolved identity cluster.
        Other clusters' observations are excluded from person claims.
        V7.2: For EVENT_LOOKUP, fusion is done in _stage_extract_events.
        V7.3-PERSON: Preserves person claims from local DB extraction.
        """
        # V7.2: Skip fusion for events — claims already extracted
        if ctx.plan.intent == "EVENT_LOOKUP":
            return

        # V7.3-PERSON: Preserve person claims from local DB extraction
        existing_person_claims = getattr(ctx, '_person_claims', [])

        # V7.2: Block fusion if identity is ambiguous
        identity_status = getattr(ctx, 'identity_status_v72', 'UNRESOLVED_IDENTITY')
        if identity_status == "AMBIGUOUS_IDENTITY":
            ctx.warnings.append("FUSE_BLOCKED_AMBIGUOUS_IDENTITY")
            ctx._fused_accepted = []
            ctx._fused_conflicting = []
            ctx._fused_asserted = existing_person_claims
            ctx._source_lineage_groups = []
            ctx._independence_groups = []
            ctx._person_claims = existing_person_claims
            ctx._context_claims = []
            return

        # V7.2: Filter observations to resolved cluster only
        resolved_cluster_id = ""
        if hasattr(ctx, 'resolved_cluster') and ctx.resolved_cluster:
            resolved_cluster_id = ctx.resolved_cluster.cluster_id

        cluster_obs = [
            obs for obs in ctx.observations
            if obs.classification == "SOURCE_CANDIDATE"
            and (not resolved_cluster_id or obs.source_record_id == resolved_cluster_id)
        ]

        # Build source family graph from cluster observations only
        graph = SourceFamilyGraph()

        for obs in cluster_obs:
            meta = obs.provider_metadata if isinstance(obs.provider_metadata, dict) else {}
            archive = meta.get("provider", "") or meta.get("archive", "")
            from v7_fusion_engine import SourceNode
            node = SourceNode(
                source_id=obs.source_record_id or obs.observation_id,
                provider=obs.provider,
                archive=archive,
                url=obs.url_canonical,
                title=obs.title,
                metadata=meta,
            )
            graph.add_source(node)

            # Detect same-archive relations
            for other_obs in cluster_obs:
                if other_obs.observation_id == obs.observation_id:
                    continue
                other_meta = other_obs.provider_metadata if isinstance(other_obs.provider_metadata, dict) else {}
                other_archive = other_meta.get("provider", "") or other_meta.get("archive", "")
                if archive and other_archive and archive == other_archive:
                    a_id = obs.source_record_id or obs.observation_id
                    b_id = other_obs.source_record_id or other_obs.observation_id
                    if not graph.are_related(a_id, b_id):
                        graph.add_edge(a_id, b_id, "SAME_ARCHIVE")

        # Run fusion engine on cluster observations only
        engine = FusionEngine(graph)
        accepted, conflicting, asserted = engine.fuse(
            cluster_obs,
            strategy=ctx.plan.fusion_strategy,
        )

        # V7.2: Tag claims with identity_cluster_id and evidence_scope
        for claim in accepted:
            claim.identity_cluster_id = resolved_cluster_id
            claim.evidence_scope = "PERSON_EVIDENCE"
        for claim in conflicting:
            claim.identity_cluster_id = resolved_cluster_id
            claim.evidence_scope = "PERSON_EVIDENCE"
        for claim in asserted:
            claim.identity_cluster_id = resolved_cluster_id
            claim.evidence_scope = "PERSON_EVIDENCE"

        # Store fused claims in context for _build_snapshot
        # V7.3-PERSON: Merge fused claims with existing local DB person claims
        ctx._fused_accepted = accepted
        ctx._fused_conflicting = conflicting
        ctx._fused_asserted = list(asserted) + list(existing_person_claims)
        ctx._person_claims = list(accepted) + list(asserted) + list(existing_person_claims)
        ctx._context_claims = []
        ctx._source_lineage_groups = graph.get_lineage_groups()

        # Build independence groups from source IDs
        source_ids = list(set(
            obs.source_record_id or obs.observation_id
            for obs in cluster_obs
            if obs.content_state not in ("NOT_OPENED", "FAILED")
        ))
        assessor = IndependenceAssessor(graph)
        ctx._independence_groups = assessor.build_independence_groups(source_ids)

    def _stage_validate(self, ctx: RunContext):
        """Stage 7: Check invariants, detect contradictions."""
        if ctx.snapshot:
            violations = ctx.snapshot.validate_invariants()
            for v in violations:
                ctx.errors.append(f"INVARIANT_VIOLATION: {v}")

    def _stage_narrate(self, ctx: RunContext):
        """Stage 8: Generate report from snapshot using NarratorV7_v2.

        V7.2-narration-v2: The narrator produces a NarrationResult
        (always structured, always validated). The AI produces only a
        NarrationDraft (atomic blocks); the backend validates, renders,
        and computes all metadata.
        """
        if not ctx.snapshot:
            ctx.snapshot = self._build_snapshot(ctx)

        if ctx.snapshot:
            ctx.snapshot.compute_conditional_gaps()
            violations = ctx.snapshot.validate_invariants()
            if violations:
                for v in violations:
                    ctx.errors.append(f"POST_NARRATE_INVARIANT: {v}")

            # Use V7.2 narrator v2 (draft→validate→render→result)
            result = self._narrator_v2.narrate(
                ctx.snapshot,
                use_ai=True,
            )
            ctx.report = result.answer_markdown
            ctx.report_structured = result.to_dict()
            ctx.narration_result = result

            # Collect validation flags as warnings
            for flag in result.validation_flags:
                ctx.warnings.append(f"NARRATION_FLAG: {flag}")

            # Log generation info
            gen = result.generation
            logger.info(
                f"NARRATE_V2: mode={gen.mode}, provider={gen.provider}, "
                f"status={result.status}, claims_used={len(result.used_claim_ids)}, "
                f"omitted={len(result.omitted_claims)}, "
                f"repair={'yes' if gen.repair_attempted else 'no'}"
            )
            if gen.fallback_reason:
                ctx.warnings.append(f"NARRATION_FALLBACK: {gen.fallback_reason}")
        else:
            ctx.errors.append("NO_SNAPSHOT_FOR_NARRATION")

    def _stage_persist(self, ctx: RunContext):
        """Stage 9: Save snapshot + report to DB."""
        # Persistence is done via the existing report_conversation_provider
        # or a new V7 persistence layer. For now, we keep it in-memory.
        pass

    def _compute_semantic_counts(self, ctx: RunContext) -> Dict[str, Any]:
        """V7.3-PERSON-FIX: Compute semantic counters with fact/evidence/provenance separation.

        Uses typed objects (PersonCandidate, FactEvidence, SourceProvenance)
        stored during extraction to produce accurate metrics:
        - unique_person_facts: deduped by predicate+normalized_value
        - supporting_evidence_records: total evidence items
        - unique_source_records: distinct candidate records
        - provenance_items: separate provenance count
        - conflict_sets: active conflicts
        - rejected_observations: rejected homonyms + observations
        """
        web_candidates = 0
        person_confirmed = 0
        person_probable = 0
        person_ambiguous = 0
        person_rejected = 0
        context_sources = 0

        for obs in ctx.observations:
            if obs.provider == "local_db" and obs.classification == "SOURCE_CANDIDATE":
                person_confirmed += 1
            elif obs.classification == "SOURCE_CANDIDATE":
                person_probable += 1
            elif obs.classification == "SURNAME_ONLY_NON_CANDIDATE":
                person_ambiguous += 1
            elif obs.classification in ("SEARCH_RESULT", "MODEL_LEAD"):
                web_candidates += 1
            elif obs.classification == "REJECTED":
                person_rejected += 1
            elif obs.classification == "CONTEXT":
                context_sources += 1

        # V7.3-PERSON-FIX: Use typed objects for accurate counts
        person_claims = getattr(ctx, '_person_claims', [])
        candidates = getattr(ctx, '_person_candidates', [])
        all_evidence = getattr(ctx, '_person_evidence', [])
        provenance_items = getattr(ctx, '_person_provenance', [])

        # Deduplicate claims by predicate + normalized_value (unique facts)
        seen_facts = set()
        unique_person_facts = 0
        for c in person_claims:
            if c.status in ("ASSERTED", "ACCEPTED", "VERIFIED"):
                key = (c.predicate, c.value_normalized)
                if key not in seen_facts:
                    seen_facts.add(key)
                    unique_person_facts += 1

        # Count provenance items separately (not as facts)
        provenance_count = len(provenance_items)

        # Evidence records (supporting evidence for facts)
        evidence_count = len(all_evidence)

        # Unique source records (candidates)
        unique_sources = len(candidates)

        # Rejected homonyms
        rejected_homonyms = len(getattr(ctx, 'rejected_homonyms', []))

        # Identity status
        identity_status = getattr(ctx, 'identity_status_v72', 'UNRESOLVED_IDENTITY')

        # War period from candidates
        war_periods = set(c.war_period for c in candidates if c.war_period)
        has_cross_war = len(war_periods) > 1

        return {
            # Observation-level counts (backward compatible)
            "web_candidates_seen": web_candidates,
            "person_sources_confirmed": person_confirmed,
            "person_sources_probable": person_probable,
            "person_sources_ambiguous": person_ambiguous,
            "person_candidates_rejected": person_rejected + rejected_homonyms,
            "context_sources": context_sources,
            # V7.3-PERSON-FIX: Fact/evidence/provenance separation
            "unique_person_facts": unique_person_facts,
            "supporting_evidence_records": evidence_count,
            "unique_source_records": unique_sources,
            "provenance_items": provenance_count,
            "conflict_sets": 0,  # populated after fusion
            "rejected_observations": person_rejected + rejected_homonyms,
            "candidate_clusters": len(getattr(ctx, 'candidate_clusters', [])),
            "identity_status": identity_status,
            "cross_war_contamination": has_cross_war,
            # Legacy compat
            "claims_accepted": unique_person_facts,
            "claims_rejected": len([c for c in person_claims if c.status == "REJECTED"]),
        }

    # ─── Helpers ────────────────────────────────────────────────────────────

    def _query_local_db(self, plan: SemanticQueryPlan) -> List[ProviderObservation]:
        """Query local SQLite database for initial observations.

        V7.3-PERSON: Uses exact cognome+nome match (not LIKE prefix).
        Includes raw_record in provider_metadata so observations get
        classified by IdentityResolver.classify_observation().
        """
        observations = []
        try:
            from database import get_conn
            conn = get_conn()

            if plan.intent == "PERSON_LOOKUP":
                name = plan.target.display_name.strip()
                parts = name.split(None, 1)
                cognome = parts[0] if parts else name
                nome = parts[1] if len(parts) > 1 else ""

                from person_source_schemas import PERSON_SOURCE_SCHEMAS, get_name_fields_for_table

                for table in PERSON_SOURCE_SCHEMAS:
                    try:
                        cognome_col, nome_col, nominativo_col = get_name_fields_for_table(table)

                        if nominativo_col and not cognome_col:
                            # Table uses single nominativo field (e.g., caduti_albooro)
                            rows = conn.execute(
                                f"SELECT * FROM {table} WHERE {nominativo_col} LIKE ? LIMIT 20",
                                (f"{cognome}%",)
                            ).fetchall()
                        elif nome:
                            rows = conn.execute(
                                f"SELECT * FROM {table} WHERE {cognome_col}=? AND {nome_col}=? LIMIT 20",
                                (cognome, nome)
                            ).fetchall()
                        else:
                            rows = conn.execute(
                                f"SELECT * FROM {table} WHERE {cognome_col}=? LIMIT 20",
                                (cognome,)
                            ).fetchall()
                        for r in rows:
                            r = dict(r)
                            obs = ProviderObservation(
                                provider="local_db",
                                capability="ARCHIVE_SEARCH",
                                title=r.get("nominativo") or f"{r.get('cognome','')} {r.get('nome','')}",
                                url_canonical="",
                                snippet=str(r)[:500],
                                content_state="METADATA_ONLY",
                                classification="SEARCH_RESULT",
                                provider_metadata={
                                    "table": table,
                                    "id": r.get("id"),
                                    "raw_record": r,
                                },
                            )
                            observations.append(obs)
                    except Exception:
                        pass

            conn.close()
        except Exception as e:
            logger.warning(f"Local DB query failed: {e}")

        return observations

    def _compute_limitations(self) -> list:
        """Compute snapshot limitations dynamically based on actual provider availability."""
        limitations = []
        try:
            from ai_client import is_any_provider_available
            if not is_any_provider_available():
                limitations.append(LimitationV7(
                    code="NO_AI_PROVIDER",
                    description="No AI provider available for narration. Using deterministic fallback.",
                ))
        except Exception:
            limitations.append(LimitationV7(
                code="NO_AI_PROVIDER",
                description="No AI provider available for narration. Using deterministic fallback.",
            ))
        return limitations

    def _build_snapshot(self, ctx: RunContext) -> EvidenceSnapshotV7:
        """Build EvidenceSnapshotV7 from run context.

        V7.2: Populates identity_status, corroboration_status, person_claims,
        context_claims, candidate_identities, resolved_identity_cluster_id.
        """
        plan = ctx.plan

        # Build provider ledger from observations
        ledger = [
            ProviderLedgerEntryV7(
                observation_id=obs.observation_id,
                provider=obs.provider,
                capability=obs.capability,
                classification=obs.classification,
                reason_codes=obs.reason_codes,
                accounted_for=True,
                raw_result_hash=obs.raw_response_hash,
            )
            for obs in ctx.observations
        ]

        # Build web leads from non-evidence observations
        web_leads = [
            WebLeadV7(
                lead_id=obs.observation_id,
                provider=obs.provider,
                url_canonical=obs.url_canonical,
                title=obs.title,
                snippet=obs.snippet,
                reason_codes=obs.reason_codes,
            )
            for obs in ctx.observations
            if obs.classification in ("MODEL_LEAD", "SEARCH_RESULT") and obs.url_canonical
        ]

        # V7.2: Identity status
        identity_status_v72 = getattr(ctx, 'identity_status_v72', 'UNRESOLVED_IDENTITY')
        resolved_cluster = getattr(ctx, 'resolved_cluster', None)
        candidate_clusters = getattr(ctx, 'candidate_clusters', [])

        # Legacy identity resolution mapping
        legacy_map = {
            "ANCHORED_RECORD": "RESOLVED",
            "RESOLVED_IDENTITY": "RESOLVED",
            "PARTIAL_IDENTITY": "PARTIAL",
            "AMBIGUOUS_IDENTITY": "UNRESOLVED",
            "UNRESOLVED_IDENTITY": "UNRESOLVED",
        }
        identity_status = legacy_map.get(identity_status_v72, "UNRESOLVED")
        origin_presence = "PRESENT" if resolved_cluster else "ABSENT"
        origin_source_id = resolved_cluster.cluster_id if resolved_cluster else ""
        origin_provenance = "VERIFIED" if identity_status_v72 in ("ANCHORED_RECORD", "RESOLVED_IDENTITY") else "UNVERIFIED"

        # V7.2: Build candidate identities for AMBIGUOUS cases
        from evidence_snapshot_v7 import CandidateIdentityV72
        candidate_identities = []
        for c in candidate_clusters:
            candidate_identities.append(CandidateIdentityV72(
                cluster_id=c.cluster_id,
                display_name=c.display_name,
                canonical_fields=c.discriminant_values,
                discriminants=list(c.discriminant_values.keys()),
                conflicting_with=[oc.cluster_id for oc in candidate_clusters if oc.cluster_id != c.cluster_id],
                source_record_ids=[str(r.get("id", "")) for r in c.record_refs if isinstance(r, dict)],
            ))

        # V7.2: Build rejected candidates only from true homonyms (not surname-only)
        rejected_candidates = []
        for i, rh in enumerate(ctx.rejected_homonyms):
            rejected_candidates.append(RejectedCandidateV7(
                candidate_id=f"rej_{i}",
                name=rh.candidate_name,
                reason_codes=rh.reason_codes,
                conflicting_features=rh.conflicting_features,
                birth_year=rh.candidate_fields.get("anno_nascita", ""),
                birth_place=rh.candidate_fields.get("luogo_nascita", ""),
                military_unit=rh.candidate_fields.get("reparto", ""),
                provider=rh.candidate_fields.get("provenance", ""),
                classification="HOMONYM",
            ))

        # Build corrections from ledger
        corrections = [
            CorrectionLayer(
                correction_id=c.correction_id,
                field_name=c.field_name,
                original_value=c.original_value,
                corrected_value=c.corrected_value,
                correction_source=c.correction_source,
                corrected_by=c.corrected_by,
                corrected_at=c.corrected_at,
                reason=c.reason,
                confidence=c.confidence,
                verified=c.verified,
            )
            for c in ctx.correction_ledger.all_corrections()
        ]

        # Determine external corroboration
        providers_with_evidence = set(
            obs.provider for obs in ctx.observations
            if obs.classification == "SOURCE_CANDIDATE" and obs.content_state != "NOT_OPENED"
        )
        if len(providers_with_evidence) >= 2:
            external_corroboration = "ACCEPTED"
            corroboration_status = "FULL"
        elif len(providers_with_evidence) == 1:
            external_corroboration = "PARTIAL"
            corroboration_status = "PARTIAL"
        else:
            external_corroboration = "NONE"
            corroboration_status = "NONE"

        # V7.2: Person claims and context claims
        person_claims = getattr(ctx, '_person_claims', [])
        context_claims = getattr(ctx, '_context_claims', [])

        # V7.2: Apply claim-level rules (date precision, semantic role, homonym guard, etc.)
        from v7_claim_rules import apply_claim_rules, classify_claim_status
        all_claim_dicts = []
        for c in person_claims + context_claims:
            cd = c.to_dict() if hasattr(c, 'to_dict') else dict(c.__dict__) if hasattr(c, '__dict__') else dict(c)
            all_claim_dicts.append(cd)
        rule_results = apply_claim_rules(all_claim_dicts, intent=plan.intent)
        for r in rule_results:
            if r.applied:
                ctx.warnings.append(f"CLAIM_RULE: {r.rule_name} — {r.note}")

        # V7.2: Store claim classifications for narrator (APPROVED/PROBABLE/NEEDS_REVIEW/REJECTED)
        ctx._claim_classifications = {cd.get("claim_id", ""): classify_claim_status(cd) for cd in all_claim_dicts}

        snapshot = EvidenceSnapshotV7(
            run_id=ctx.run_id,
            plan_id=plan.plan_id,
            manifest_hash=plan.manifest_hash,
            intent=plan.intent,
            target={
                "target_id": ctx.resolved_identity.identity_id if ctx.resolved_identity else plan.target.target_id,
                "display_name": plan.target.display_name,
                "conflict": ctx.resolved_identity.conflict if ctx.resolved_identity else plan.target.conflict,
                "target_type": plan.target.target_type,
            },
            origin={
                "presence": origin_presence,
                "provenance": origin_provenance,
                "source_id": origin_source_id,
            },
            identity_resolution=identity_status,
            external_corroboration=external_corroboration,
            identity_status=identity_status_v72,
            corroboration_status=corroboration_status,
            resolved_identity_cluster_id=resolved_cluster.cluster_id if resolved_cluster else "",
            origin_record_id=getattr(plan.target, 'origin_record_id', '') or plan.target.target_id,
            accepted_claims=getattr(ctx, '_fused_accepted', []),
            conflicting_claims=getattr(ctx, '_fused_conflicting', []),
            asserted_claims=getattr(ctx, '_fused_asserted', []),
            person_claims=person_claims,
            context_claims=context_claims,
            candidate_identities=candidate_identities,
            provider_ledger=ledger,
            web_leads=web_leads,
            rejected_candidates=rejected_candidates,
            corrections=corrections,
            source_lineage_groups=getattr(ctx, '_source_lineage_groups', []),
            independence_groups=getattr(ctx, '_independence_groups', []),
            aggregate_result=getattr(ctx, '_aggregate_result', None),
            aggregate_definition_id=getattr(ctx, '_aggregate_definition_id', ""),
            limitations=self._compute_limitations(),
        )

        return snapshot

    def _deterministic_fallback_report(self, snapshot: EvidenceSnapshotV7) -> str:
        """Generate a deterministic report without AI.

        V7.2: Shows identity_status, corroboration_status, person_claims,
        context_claims, candidate_identities. Hides surname-only candidates.
        """
        lines = [
            f"# Rapporto di Ricerca — {snapshot.snapshot_id}",
            f"Versione schema: {snapshot.schema_version}",
            f"Intent: {snapshot.intent}",
            f"Target: {snapshot.target.get('display_name', 'N/A')}",
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
            lines.append("## Claim Personali (attribuibili alla persona)")
            for c in snapshot.person_claims:
                lines.append(f"  - {c.predicate}: {c.value_normalized}")
            lines.append("")

        if snapshot.context_claims:
            lines.append("## Claim di Contesto (non attribuibili alla persona)")
            for c in snapshot.context_claims:
                lines.append(f"  - [{c.context_scope}] {c.predicate}: {c.value_normalized}")
            lines.append("")

        if snapshot.accepted_claims:
            lines.append("## Claim Accettati")
            for c in snapshot.accepted_claims:
                lines.append(f"  - {c.predicate}: {c.value_normalized}")
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
                lines.append(f"  - {g.field_name}: {g.reason}")
            lines.append("")

        if snapshot.web_leads:
            lines.append("## Piste di Ricerca (non verificate)")
            for l in snapshot.web_leads:
                lines.append(f"  - {l.title} ({l.provider})")
            lines.append("")

        if snapshot.limitations:
            lines.append("## Limitazioni")
            for lim in snapshot.limitations:
                lines.append(f"  - {lim.code}: {lim.description}")
            lines.append("")

        lines.append("---")
        lines.append("Questo rapporto e stato generato deterministicamente senza AI.")
        lines.append("Tutti i claim sono tracciati con provenienza completa.")

        return "\n".join(lines)

    def _stage_timings_set(self, stage: str, duration: float):
        """Helper for recording stage timing before RunContext exists."""
        pass

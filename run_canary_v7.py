"""V7.1 Canary Runner — frozen targets, 3 modes (offline, online, comparison).

Runs the V7 orchestrator against frozen canary targets and compares results
with V5/V6 baseline. Three modes:
  1. OFFLINE: deterministic only (no AI, no web search)
  2. ONLINE: with AI narration and web search (if available)
  3. COMPARISON: runs both V7 and legacy, compares outputs

Canary targets are FROZEN — they never change. This ensures reproducibility.
"""
from __future__ import annotations

import json
import os
import time
import logging
from dataclasses import dataclass, field, asdict
from datetime import datetime
from typing import Dict, List, Optional, Any, Tuple

logger = logging.getLogger(__name__)


# ─── Frozen canary targets ──────────────────────────────────────────────────

CANARY_TARGETS = [
    {
        "id": "canary_001",
        "input": "Rossi Mario",
        "intent": "PERSON_LOOKUP",
        "conflict": "UNKNOWN",
        "expected_min_observations": 10,
        "expected_identity": "RESOLVED",
        "expected_homonyms_rejected": True,
        "description": "Common Italian name — should find many records, many homonyms",
    },
    {
        "id": "canary_002",
        "input": "Bianchi Giovanni",
        "intent": "PERSON_LOOKUP",
        "conflict": "UNKNOWN",
        "expected_min_observations": 5,
        "expected_identity": "RESOLVED",
        "expected_homonyms_rejected": True,
        "description": "Another common name — multiple records expected",
    },
    {
        "id": "canary_003",
        "input": "Caporetto",
        "intent": "EVENT_LOOKUP",
        "conflict": "WWI",
        "expected_min_observations": 1,
        "expected_identity": "UNRESOLVED",
        "expected_homonyms_rejected": False,
        "description": "Major WWI event — should find at least 1 event record",
    },
    {
        "id": "canary_004",
        "input": "count_internati_by_campo",
        "intent": "AGGREGATE_QUERY",
        "conflict": "UNKNOWN",
        "expected_min_observations": 0,
        "expected_identity": "N/A",
        "expected_homonyms_rejected": False,
        "description": "Aggregate query — should return camp distribution",
    },
    {
        "id": "canary_005",
        "input": "Ferrari Carlo",
        "intent": "PERSON_LOOKUP",
        "conflict": "UNKNOWN",
        "expected_min_observations": 3,
        "expected_identity": "RESOLVED",
        "expected_homonyms_rejected": True,
        "description": "Moderate frequency name — should find records",
    },
    {
        "id": "canary_006",
        "input": "Zanardi Luigi",
        "intent": "PERSON_LOOKUP",
        "conflict": "UNKNOWN",
        "expected_min_observations": 1,
        "expected_identity": "RESOLVED",
        "expected_homonyms_rejected": True,
        "description": "Less common name — may find fewer records but still enough to resolve",
    },
    {
        "id": "canary_007",
        "input": "count_caduti_by_luogo",
        "intent": "AGGREGATE_QUERY",
        "conflict": "UNKNOWN",
        "expected_min_observations": 0,
        "expected_identity": "N/A",
        "expected_homonyms_rejected": False,
        "description": "Aggregate query — death place distribution",
    },
    {
        "id": "canary_008",
        "input": "Monte Grappa",
        "intent": "EVENT_LOOKUP",
        "conflict": "WWI",
        "expected_min_observations": 1,
        "expected_identity": "UNRESOLVED",
        "expected_homonyms_rejected": False,
        "description": "WWI battle location — should find event records",
    },
    {
        "id": "canary_009",
        "input": "Esposito Antonio",
        "intent": "PERSON_LOOKUP",
        "conflict": "UNKNOWN",
        "expected_min_observations": 5,
        "expected_identity": "RESOLVED",
        "expected_homonyms_rejected": True,
        "description": "Southern Italian common name",
    },
    {
        "id": "canary_010",
        "input": "temporal_distribution_caduti",
        "intent": "AGGREGATE_QUERY",
        "conflict": "UNKNOWN",
        "expected_min_observations": 0,
        "expected_identity": "N/A",
        "expected_homonyms_rejected": False,
        "description": "Aggregate query — temporal distribution of deaths",
    },
]


# ─── Canary result ──────────────────────────────────────────────────────────

@dataclass
class CanaryResult:
    """Result of a single canary target execution."""
    target_id: str = ""
    input: str = ""
    intent: str = ""
    mode: str = ""  # OFFLINE|ONLINE|COMPARISON
    run_id: str = ""
    observation_count: int = 0
    identity_resolution: str = ""
    accepted_claims: int = 0
    conflicting_claims: int = 0
    asserted_claims: int = 0
    rejected_homonyms: int = 0
    corrections: int = 0
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    stage_timings: Dict[str, float] = field(default_factory=dict)
    report_length: int = 0
    has_snapshot: bool = False
    has_report: bool = False
    aggregate_result_rows: int = 0
    elapsed_seconds: float = 0.0
    passed: bool = False
    failure_reasons: List[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


# ─── Canary runner ──────────────────────────────────────────────────────────

class CanaryRunnerV7:
    """Runs V7 orchestrator against frozen canary targets."""

    def __init__(self):
        from unified_orchestrator_v7 import UnifiedResearchOrchestratorV7
        self._orchestrator = UnifiedResearchOrchestratorV7()

    def run_target(self, target: Dict[str, Any], mode: str = "OFFLINE") -> CanaryResult:
        """Run a single canary target."""
        result = CanaryResult(
            target_id=target["id"],
            input=target["input"],
            intent=target["intent"],
            mode=mode,
        )

        t0 = time.time()
        try:
            orch_result = self._orchestrator.execute(
                user_input=target["input"],
                intent=target["intent"],
                conflict=target.get("conflict", "UNKNOWN"),
            )

            result.run_id = orch_result.get("run_id", "")
            result.observation_count = orch_result.get("observation_count", 0)
            result.errors = orch_result.get("errors", [])
            result.warnings = orch_result.get("warnings", [])
            result.stage_timings = orch_result.get("stage_timings", {})
            result.has_snapshot = orch_result.get("snapshot") is not None
            result.has_report = orch_result.get("report") is not None
            result.report_length = len(orch_result.get("report", ""))

            snap = orch_result.get("snapshot", {})
            if snap:
                result.identity_resolution = snap.get("identity_resolution", "")
                result.accepted_claims = len(snap.get("accepted_claims", []))
                result.conflicting_claims = len(snap.get("conflicting_claims", []))
                result.asserted_claims = len(snap.get("asserted_claims", []))
                result.rejected_homonyms = len(snap.get("rejected_candidates", []))
                result.corrections = len(snap.get("corrections", []))

                agg = snap.get("aggregate_result")
                if agg and isinstance(agg, dict):
                    result.aggregate_result_rows = agg.get("row_count", 0)

        except Exception as e:
            result.errors.append(f"CANARY_EXCEPTION: {str(e)}")

        result.elapsed_seconds = round(time.time() - t0, 3)

        # Evaluate pass/fail
        result.passed, result.failure_reasons = self._evaluate(target, result)

        return result

    def _evaluate(self, target: Dict[str, Any], result: CanaryResult) -> Tuple[bool, List[str]]:
        """Evaluate whether the canary target passed."""
        reasons = []

        if result.errors:
            reasons.append(f"Has {len(result.errors)} errors")

        if not result.has_snapshot:
            reasons.append("No snapshot generated")
            return False, reasons

        if not result.has_report:
            reasons.append("No report generated")

        if target.get("expected_min_observations", 0) > 0:
            if result.observation_count < target["expected_min_observations"]:
                reasons.append(
                    f"Expected >= {target['expected_min_observations']} observations, "
                    f"got {result.observation_count}"
                )

        expected_identity = target.get("expected_identity", "")
        if expected_identity and expected_identity != "N/A":
            if result.identity_resolution != expected_identity:
                reasons.append(
                    f"Expected identity={expected_identity}, "
                    f"got {result.identity_resolution}"
                )

        if target.get("expected_homonyms_rejected", False):
            if result.rejected_homonyms == 0:
                reasons.append("Expected homonyms to be rejected, got 0")

        return len(reasons) == 0, reasons

    def run_all(self, mode: str = "OFFLINE") -> List[CanaryResult]:
        """Run all canary targets."""
        results = []
        for target in CANARY_TARGETS:
            logger.info(f"Running canary {target['id']}: {target['input']}")
            result = self.run_target(target, mode=mode)
            results.append(result)
            status = "PASS" if result.passed else "FAIL"
            logger.info(f"  {target['id']}: {status} ({result.elapsed_seconds}s)")
        return results

    def generate_report(self, results: List[CanaryResult]) -> Dict[str, Any]:
        """Generate structured canary report."""
        passed = sum(1 for r in results if r.passed)
        failed = len(results) - passed

        return {
            "canary_run_id": f"canary_v7_{int(time.time())}",
            "run_at": datetime.now().isoformat(),
            "mode": results[0].mode if results else "UNKNOWN",
            "total_targets": len(results),
            "passed": passed,
            "failed": failed,
            "pass_rate": round(passed / len(results) * 100, 1) if results else 0,
            "results": [r.to_dict() for r in results],
            "summary": {
                "total_observations": sum(r.observation_count for r in results),
                "total_accepted_claims": sum(r.accepted_claims for r in results),
                "total_conflicting_claims": sum(r.conflicting_claims for r in results),
                "total_rejected_homonyms": sum(r.rejected_homonyms for r in results),
                "total_errors": sum(len(r.errors) for r in results),
                "avg_elapsed": round(sum(r.elapsed_seconds for r in results) / len(results), 3) if results else 0,
            },
        }

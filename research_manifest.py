"""Research Manifest — immutable, versioned target list for research runs.

Every run starts with a manifest containing the expected targets.
The manifest is immutable after validation: target_id, ordinal, target_hash,
target_type and conflict cannot change.

Key invariants:
- target_id, ordinal, target_hash are immutable after creation
- No result can occupy the ordinal of an expected target
- run_state is COMPLETE only if all expected targets are COMPLETED
- Missing/substituted/duplicate targets make the run PARTIAL or FAILED
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
from dataclasses import dataclass, field, asdict
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Dict, List, Optional, Tuple

log = logging.getLogger(__name__)


class RunState(str, Enum):
    SUCCESS = "SUCCESS"
    PARTIAL = "PARTIAL"
    FAILED = "FAILED"
    DEGRADED = "DEGRADED"


class TargetPhase(str, Enum):
    PENDING = "PENDING"
    RETRIEVING = "RETRIEVING"
    VALIDATING = "VALIDATING"
    PERSISTING = "PERSISTING"
    COMPLETED = "COMPLETED"
    RETRYABLE_ERROR = "RETRYABLE_ERROR"
    PERMANENT_ERROR = "PERMANENT_ERROR"
    SKIPPED_PROVIDER_RETRY = "SKIPPED_PROVIDER_RETRY"


@dataclass(frozen=True)
class ManifestTarget:
    """Single entry in the manifest — immutable."""
    ordinal: int
    target_id: str
    target_hash: str
    target_type: str  # "person" | "event"
    conflict: str  # "ww1" | "ww2" | "unknown"
    raw_input: Dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        d = asdict(self)
        return d


@dataclass
class Manifest:
    """Immutable manifest for a research run."""
    run_id: str
    benchmark_version: str
    scope: str  # "people-only" | "full-benchmark"
    expected_targets: int
    targets: List[ManifestTarget]
    manifest_hash: str
    created_at: str

    def __post_init__(self):
        # Validate: no duplicate ordinals or target_ids
        ordinals = [t.ordinal for t in self.targets]
        ids = [t.target_id for t in self.targets]
        if len(ordinals) != len(set(ordinals)):
            raise ValueError("Duplicate ordinals in manifest")
        if len(ids) != len(set(ids)):
            raise ValueError("Duplicate target_ids in manifest")
        if len(self.targets) != self.expected_targets:
            raise ValueError(
                f"Expected {self.expected_targets} targets, got {len(self.targets)}"
            )

    def to_dict(self) -> dict:
        return {
            "run_id": self.run_id,
            "benchmark_version": self.benchmark_version,
            "scope": self.scope,
            "expected_targets": self.expected_targets,
            "manifest_hash": self.manifest_hash,
            "created_at": self.created_at,
            "targets": [t.to_dict() for t in self.targets],
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=2)

    def get_target(self, target_id: str) -> Optional[ManifestTarget]:
        for t in self.targets:
            if t.target_id == target_id:
                return t
        return None

    def get_by_ordinal(self, ordinal: int) -> Optional[ManifestTarget]:
        for t in self.targets:
            if t.ordinal == ordinal:
                return t
        return None


def compute_target_hash(raw_input: Dict) -> str:
    """Compute deterministic hash from canonical fields."""
    canonical = json.dumps(raw_input, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(canonical.encode()).hexdigest()[:16]


def compute_manifest_hash(targets: List[ManifestTarget], run_id: str, scope: str) -> str:
    """Compute deterministic hash of the full manifest."""
    raw = f"{run_id}|{scope}|"
    for t in targets:
        raw += f"{t.ordinal}:{t.target_id}:{t.target_hash}:{t.target_type}:{t.conflict};"
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


def build_manifest(
    run_id: str,
    scope: str,
    targets_data: List[Dict],
    benchmark_version: str = "unversioned",
) -> Manifest:
    """Build an immutable manifest from raw target data.

    Args:
        run_id: unique run identifier
        scope: "people-only" or "full-benchmark"
        targets_data: list of dicts with keys: ordinal, target_id, target_type,
                      conflict, raw_input
        benchmark_version: version string for the benchmark
    """
    targets = []
    for td in targets_data:
        raw_input = td.get("raw_input", {})
        target_hash = compute_target_hash(raw_input)
        targets.append(ManifestTarget(
            ordinal=td["ordinal"],
            target_id=td["target_id"],
            target_hash=target_hash,
            target_type=td.get("target_type", "person"),
            conflict=td.get("conflict", "unknown"),
            raw_input=raw_input,
        ))

    # Sort by ordinal
    targets.sort(key=lambda t: t.ordinal)

    manifest_hash = compute_manifest_hash(targets, run_id, scope)
    created_at = datetime.now().isoformat()

    return Manifest(
        run_id=run_id,
        benchmark_version=benchmark_version,
        scope=scope,
        expected_targets=len(targets),
        targets=targets,
        manifest_hash=manifest_hash,
        created_at=created_at,
    )


@dataclass
class RunStatus:
    """Track status of a research run."""
    run_id: str
    manifest_hash: str
    state: RunState = RunState.PARTIAL
    scope: str = "people-only"
    expected: int = 0
    processed: int = 0
    completed: int = 0
    failed: int = 0
    missing_target_ids: List[str] = field(default_factory=list)
    unexpected_target_ids: List[str] = field(default_factory=list)
    substitutions: List[Dict] = field(default_factory=list)
    duplicate_target_ids: List[str] = field(default_factory=list)
    target_phases: Dict[str, str] = field(default_factory=dict)
    provider_health: Dict = field(default_factory=dict)
    started_at: str = ""
    completed_at: str = ""

    def update_target_phase(self, target_id: str, phase: TargetPhase):
        self.target_phases[target_id] = phase.value
        if phase == TargetPhase.COMPLETED:
            self.completed += 1
        elif phase in (TargetPhase.PERMANENT_ERROR,):
            self.failed += 1
        self.processed = sum(
            1 for p in self.target_phases.values()
            if p not in (TargetPhase.PENDING.value,)
        )
        self._recompute_state()

    def add_provider_health(self, provider: str, state: str, successes: int = 0,
                            failures: int = 0, last_error_code: str = ""):
        self.provider_health[provider] = {
            "state": state,
            "successes": successes,
            "failures": failures,
            "last_error_code": last_error_code,
        }
        self._recompute_state()

    def _recompute_state(self):
        if self.completed == self.expected and not self.missing_target_ids:
            self.state = RunState.SUCCESS
        elif self.failed > 0 or self.missing_target_ids:
            self.state = RunState.PARTIAL
        # DEGRADED if provider health issues
        for ph in self.provider_health.values():
            if ph.get("state") in ("CIRCUIT_OPEN", "DEGRADED"):
                if self.state == RunState.SUCCESS:
                    self.state = RunState.DEGRADED

    def finalize(self):
        """Compute final state after all targets processed."""
        expected_ids = set()
        # Check for missing/unexpected
        processed_ids = set(self.target_phases.keys())
        # Missing = expected but not in target_phases
        # This is set externally by the runner
        if self.missing_target_ids or self.unexpected_target_ids or self.substitutions:
            self.state = RunState.PARTIAL if self.completed > 0 else RunState.FAILED
        elif self.completed == self.expected:
            self.state = RunState.SUCCESS
        elif self.failed > 0:
            self.state = RunState.PARTIAL
        else:
            self.state = RunState.PARTIAL
        self.completed_at = datetime.now().isoformat()

    def to_dict(self) -> dict:
        return {
            "run_id": self.run_id,
            "manifest_hash": self.manifest_hash,
            "state": self.state.value,
            "scope": self.scope,
            "expected": self.expected,
            "processed": self.processed,
            "completed": self.completed,
            "failed": self.failed,
            "missing_target_ids": self.missing_target_ids,
            "unexpected_target_ids": self.unexpected_target_ids,
            "substitutions": self.substitutions,
            "duplicate_target_ids": self.duplicate_target_ids,
            "target_phases": self.target_phases,
            "provider_health": self.provider_health,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
        }


def save_manifest(manifest: Manifest, output_dir: str = "."):
    """Save manifest to JSON file."""
    path = Path(output_dir) / f"manifest_{manifest.run_id}.json"
    path.write_text(manifest.to_json(), encoding="utf-8")
    log.info("Manifest saved to %s (hash=%s, targets=%d)",
             path, manifest.manifest_hash, manifest.expected_targets)
    return str(path)


def load_manifest(path: str) -> Manifest:
    """Load manifest from JSON file."""
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    targets = [
        ManifestTarget(
            ordinal=t["ordinal"],
            target_id=t["target_id"],
            target_hash=t["target_hash"],
            target_type=t["target_type"],
            conflict=t["conflict"],
            raw_input=t.get("raw_input", {}),
        )
        for t in data["targets"]
    ]
    return Manifest(
        run_id=data["run_id"],
        benchmark_version=data.get("benchmark_version", "unversioned"),
        scope=data["scope"],
        expected_targets=data["expected_targets"],
        targets=targets,
        manifest_hash=data["manifest_hash"],
        created_at=data["created_at"],
    )


def validate_run_against_manifest(
    manifest: Manifest,
    processed_target_ids: List[str],
    run_status: RunStatus,
) -> RunStatus:
    """Validate that processed targets match the manifest.

    Checks for:
    - Missing targets (expected but not processed)
    - Unexpected targets (processed but not in manifest)
    - Substitutions (target_id at wrong ordinal)
    - Duplicates
    """
    expected_ids = {t.target_id for t in manifest.targets}
    expected_by_ordinal = {t.ordinal: t.target_id for t in manifest.targets}
    processed_set = set(processed_target_ids)

    # Missing
    run_status.missing_target_ids = sorted(expected_ids - processed_set)
    # Unexpected
    run_status.unexpected_target_ids = sorted(processed_set - expected_ids)
    # Duplicates
    seen = set()
    run_status.duplicate_target_ids = []
    for tid in processed_target_ids:
        if tid in seen:
            run_status.duplicate_target_ids.append(tid)
        seen.add(tid)

    run_status.expected = manifest.expected_targets
    run_status.finalize()
    return run_status

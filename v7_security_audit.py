"""V7 Legacy Security Audit — verifies side-effect-free imports, kill switch, raw immutability.

This module provides:
  - LegacySecurityAuditor: audits all legacy scripts for import safety
  - KillSwitchVerifier: verifies kill switch is enforced on all legacy jobs
  - RawImmutabilityChecker: checks that raw data tables are never modified by V7
  - SecurityReport: structured report of all security findings

Key principles:
  1. Legacy scripts must have zero side effects on import
  2. Legacy jobs must be gated by kill switch (LEGACY_JOB_<NAME>=true)
  3. Raw data tables (internati, caduti_*, decorati_*) must never be modified by V7
  4. All V7 corrections are overlays — raw data is immutable
"""
from __future__ import annotations

import importlib
import os
import sys
import time
import logging
from dataclasses import dataclass, field, asdict
from datetime import datetime
from typing import Dict, List, Optional, Any, Tuple

logger = logging.getLogger(__name__)


# ─── Security findings ──────────────────────────────────────────────────────

@dataclass
class SecurityFinding:
    """A single security finding."""
    code: str
    severity: str  # ERROR|WARNING|PASS|INFO
    module: str
    description: str
    evidence: str = ""


@dataclass
class SecurityReport:
    """Structured security audit report."""
    audit_id: str = ""
    audited_at: str = field(default_factory=lambda: datetime.now().isoformat())
    findings: List[SecurityFinding] = field(default_factory=list)
    total_modules: int = 0
    passed: int = 0
    warnings: int = 0
    errors: int = 0

    def __post_init__(self):
        if not self.audit_id:
            self.audit_id = f"sec_audit_{int(time.time())}"

    def add(self, finding: SecurityFinding):
        self.findings.append(finding)
        if finding.severity == "PASS":
            self.passed += 1
        elif finding.severity == "WARNING":
            self.warnings += 1
        elif finding.severity == "ERROR":
            self.errors += 1

    @property
    def ok(self) -> bool:
        return self.errors == 0

    def to_dict(self) -> dict:
        return {
            "audit_id": self.audit_id,
            "audited_at": self.audited_at,
            "total_modules": self.total_modules,
            "passed": self.passed,
            "warnings": self.warnings,
            "errors": self.errors,
            "ok": self.ok,
            "findings": [asdict(f) for f in self.findings],
        }


# ─── Legacy script inventory ────────────────────────────────────────────────

LEGACY_SCRIPTS = [
    "_check_keys.py",
    "_inspect_schema.py",
    "_schema_check.py",
    "_check_gaiaschi.py",
    "_status.py",
    "_status_check.py",
    "_find_best_candidates.py",
    "_fix_gaiaschi_db.py",
    "_gen_record_links.py",
    "_gen_event_links.py",
    "_clean_bad_links.py",
]

LEGACY_JOBS = [
    ("legacy_event_links", "EVENT_LINKS"),
    ("legacy_record_links", "RECORD_LINKS"),
    ("legacy_clean_bad_links", "CLEAN_BAD_LINKS"),
    ("legacy_fix_gaiaschi", "FIX_GAIASCHI"),
    ("legacy_sync_event_links_supabase", "SYNC_EVENT_LINKS_SUPABASE"),
    ("legacy_sync_record_links_supabase", "SYNC_RECORD_LINKS_SUPABASE"),
    ("legacy_mass_index", "MASS_INDEX"),
    ("legacy_mass_index_parallel", "MASS_INDEX_PARALLEL"),
    ("legacy_import_personal_sources", "IMPORT_PERSONAL_SOURCES"),
    ("legacy_ia_pipeline", "IA_PIPELINE"),
    ("legacy_research_to_index", "RESEARCH_TO_INDEX"),
    ("legacy_search_ww1_documents", "SEARCH_WW1_DOCUMENTS"),
    ("legacy_external_link_service", "EXTERNAL_LINK_SERVICE"),
]

RAW_DATA_TABLES = [
    "internati",
    "caduti_albooro",
    "caduti_bologna",
    "caduti_cwgc",
    "caduti_francia_ww1",
    "caduti_ministero",
    "caduti_sardi",
    "decorati_nastroazzurro",
    "decorati",
    "nara_t315",
    "nara_catalog",
    "archivio_fonti",
    "archivio_documenti",
    "fonti_indice",
]


# ─── Import safety auditor ──────────────────────────────────────────────────

class ImportSafetyAuditor:
    """Audits legacy scripts for import safety (zero side effects on import)."""

    def __init__(self, base_path: str = "."):
        self.base_path = base_path

    def audit_script(self, script_name: str) -> SecurityFinding:
        """Check if a script is import-safe by examining its source."""
        filepath = os.path.join(self.base_path, script_name)
        if not os.path.exists(filepath):
            return SecurityFinding(
                code="FILE_NOT_FOUND",
                severity="WARNING",
                module=script_name,
                description=f"Script not found: {filepath}",
            )

        with open(filepath, "r", encoding="utf-8", errors="replace") as f:
            source = f.read()

        has_main_guard = 'if __name__' in source and '__main__' in source
        has_main_func = 'def main(' in source or 'def run(' in source

        # Find the indentation level of def main() / def run()
        lines = source.split("\n")
        main_indent = -1
        for line in lines:
            stripped = line.lstrip()
            if stripped.startswith("def main(") or stripped.startswith("def run("):
                main_indent = len(line) - len(stripped)
                break

        # Check for top-level DB writes (outside functions)
        # A line is "inside a function" if its indentation > the function's def line
        top_level_writes = []
        in_triple_string = False

        for i, line in enumerate(lines, 1):
            stripped = line.lstrip()
            current_indent = len(line) - len(stripped)

            # Track triple-quoted strings
            if '"""' in stripped:
                count = stripped.count('"""')
                if count == 1:
                    in_triple_string = not in_triple_string
                # if count == 2, it opens and closes on same line — no state change
                continue
            if in_triple_string:
                continue

            # Skip comments, blank lines, imports, def/class lines
            if not stripped or stripped.startswith("#") or stripped.startswith("import ") or stripped.startswith("from ") or stripped.startswith("def ") or stripped.startswith("class "):
                continue

            # If we found def main(), any line with indent > main_indent is inside it
            if main_indent >= 0 and current_indent > main_indent:
                continue  # inside a function

            # This line is at or below the main_indent — it's top-level
            if any(kw in stripped for kw in ["conn.execute", "conn.commit", ".execute(", "INSERT ", "UPDATE ", "DELETE ", "CREATE TABLE", "ALTER "]):
                # Skip if it's inside an if __name__ block
                # Check if we're past the if __name__ guard
                if 'if __name__' in source:
                    # Find the line number of if __name__
                    guard_line = None
                    for j, l in enumerate(lines, 1):
                        if 'if __name__' in l:
                            guard_line = j
                            break
                    if guard_line and i > guard_line and current_indent > (len(lines[guard_line-1]) - len(lines[guard_line-1].lstrip())):
                        continue  # inside the __main__ block

                top_level_writes.append((i, stripped[:80]))

        if has_main_guard and has_main_func and not top_level_writes:
            return SecurityFinding(
                code="IMPORT_SAFE",
                severity="PASS",
                module=script_name,
                description="Script has main() guard and no top-level side effects",
            )
        elif not has_main_guard:
            return SecurityFinding(
                code="MISSING_MAIN_GUARD",
                severity="ERROR",
                module=script_name,
                description="Script lacks if __name__ == '__main__' guard",
                evidence=f"Has main func: {has_main_func}",
            )
        elif top_level_writes:
            return SecurityFinding(
                code="TOP_LEVEL_SIDE_EFFECTS",
                severity="ERROR",
                module=script_name,
                description=f"Found {len(top_level_writes)} top-level DB operations",
                evidence="; ".join([f"L{ln}: {s}" for ln, s in top_level_writes[:3]]),
            )
        else:
            return SecurityFinding(
                code="IMPORT_SAFE_NO_MAIN",
                severity="WARNING",
                module=script_name,
                description="Script has guard but no main() function",
            )


# ─── Kill switch verifier ───────────────────────────────────────────────────

class KillSwitchVerifier:
    """Verifies that legacy jobs are gated by the kill switch."""

    def __init__(self, base_path: str = "."):
        self.base_path = base_path

    def verify_job(self, job_value: str, job_enum_name: str) -> SecurityFinding:
        """Check if a legacy job is gated by the kill switch."""
        try:
            import sys
            base = os.path.abspath(self.base_path)
            if base not in sys.path:
                sys.path.insert(0, base)
            from linking.kill_switch import LegacyJob, is_legacy_job_enabled, is_force_execute_enabled

            job = LegacyJob[job_enum_name]
            enabled = is_legacy_job_enabled(job)
            force = is_force_execute_enabled()

            if not enabled:
                return SecurityFinding(
                    code="KILL_SWITCH_FROZEN",
                    severity="PASS",
                    module=f"legacy_job:{job_value}",
                    description=f"Job '{job_value}' is frozen (disabled by default)",
                )
            elif enabled and not force:
                return SecurityFinding(
                    code="KILL_SWITCH_AUDIT_ONLY",
                    severity="PASS",
                    module=f"legacy_job:{job_value}",
                    description=f"Job '{job_value}' is in audit-only mode",
                )
            else:
                return SecurityFinding(
                    code="KILL_SWITCH_FORCE_EXECUTE",
                    severity="WARNING",
                    module=f"legacy_job:{job_value}",
                    description=f"Job '{job_value}' has force_execute enabled — mutations allowed",
                )
        except ImportError:
            return SecurityFinding(
                code="KILL_SWITCH_MODULE_MISSING",
                severity="ERROR",
                module=f"legacy_job:{job_value}",
                description="kill_switch module not found",
            )
        except Exception as e:
            return SecurityFinding(
                code="KILL_SWITCH_ERROR",
                severity="WARNING",
                module=f"legacy_job:{job_value}",
                description=f"Kill switch check error: {e}",
            )


# ─── Raw immutability checker ───────────────────────────────────────────────

class RawImmutabilityChecker:
    """Checks that V7 modules never directly modify raw data tables."""

    V7_MODULES = [
        "unified_orchestrator_v7.py",
        "v7_provider_adapters.py",
        "v7_identity_model.py",
        "v7_fusion_engine.py",
        "v7_event_aggregate.py",
        "v7_narrator.py",
        "semantic_query_plan.py",
        "evidence_snapshot_v7.py",
    ]

    FORBIDDEN_PATTERNS = [
        "INSERT INTO",
        "UPDATE ",
        "DELETE FROM",
        "DROP TABLE",
        "ALTER TABLE",
    ]

    RAW_TABLE_PATTERN = "|".join(RAW_DATA_TABLES)

    def __init__(self, base_path: str = "."):
        self.base_path = base_path

    def check_module(self, module_file: str) -> SecurityFinding:
        """Check if a V7 module contains direct writes to raw data tables."""
        filepath = os.path.join(self.base_path, module_file)
        if not os.path.exists(filepath):
            return SecurityFinding(
                code="MODULE_NOT_FOUND",
                severity="WARNING",
                module=module_file,
                description=f"V7 module not found: {filepath}",
            )

        with open(filepath, "r", encoding="utf-8", errors="replace") as f:
            source = f.read()

        violations = []
        lines = source.split("\n")
        for i, line in enumerate(lines, 1):
            upper = line.upper()
            for pattern in self.FORBIDDEN_PATTERNS:
                if pattern.upper() in upper:
                    for table in RAW_DATA_TABLES:
                        if table.upper() in upper:
                            violations.append((i, line.strip()[:80]))
                            break

        if not violations:
            return SecurityFinding(
                code="RAW_IMMUTABLE",
                severity="PASS",
                module=module_file,
                description="No direct writes to raw data tables found",
            )
        else:
            return SecurityFinding(
                code="RAW_MUTATION_DETECTED",
                severity="ERROR",
                module=module_file,
                description=f"Found {len(violations)} direct writes to raw data tables",
                evidence="; ".join([f"L{ln}: {s}" for ln, s in violations[:3]]),
            )


# ─── Full security audit ────────────────────────────────────────────────────

class LegacySecurityAuditor:
    """Runs a full security audit of the V7 pipeline."""

    def __init__(self, base_path: str = "."):
        self.base_path = base_path
        self._import_auditor = ImportSafetyAuditor(base_path)
        self._kill_switch_verifier = KillSwitchVerifier(base_path)
        self._immutability_checker = RawImmutabilityChecker(base_path)

    def audit(self) -> SecurityReport:
        """Run full security audit and return structured report."""
        report = SecurityReport()

        # 1. Import safety audit
        for script in LEGACY_SCRIPTS:
            finding = self._import_auditor.audit_script(script)
            report.add(finding)
            report.total_modules += 1

        # 2. Kill switch verification
        for job_value, job_enum_name in LEGACY_JOBS:
            finding = self._kill_switch_verifier.verify_job(job_value, job_enum_name)
            report.add(finding)

        # 3. Raw immutability check
        for module in self._immutability_checker.V7_MODULES:
            finding = self._immutability_checker.check_module(module)
            report.add(finding)

        return report

"""LedgerReconciliation — reconcilable metrics for every research run.

For each provider and run, records:
  attempted_queries, completed_queries, failed_queries,
  raw_results, normalized_observations, unique_urls, duplicate_urls,
  opened_items, metadata_only_items, content_extracted,
  model_leads, context_sources, rejected_items,
  partial_evidence, accepted_evidence, accepted_claims, conflicting_claims

Invarianti:
  raw_results = normalized_observations + normalization_failures
  normalized_observations = unique_items + duplicates
  unique_items = unopened + opened + fetch_failed + metadata_only
  opened/content_extracted items = accepted + partial + context + rejected

If an invariant doesn't hold, the run is INCOMPLETE_LEDGER.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional


@dataclass
class ProviderMetrics:
    provider: str
    attempted_queries: int = 0
    completed_queries: int = 0
    failed_queries: int = 0
    raw_results: int = 0
    normalized_observations: int = 0
    normalization_failures: int = 0
    unique_urls: int = 0
    duplicate_urls: int = 0
    opened_items: int = 0
    metadata_only_items: int = 0
    content_extracted: int = 0
    fetch_failed: int = 0
    unopened: int = 0
    model_leads: int = 0
    context_sources: int = 0
    rejected_items: int = 0
    partial_evidence: int = 0
    accepted_evidence: int = 0
    accepted_claims: int = 0
    conflicting_claims: int = 0


@dataclass
class RunLedger:
    run_id: str
    manifest_hash: str
    provider_metrics: Dict[str, ProviderMetrics] = field(default_factory=dict)
    total_observations: int = 0
    total_unique: int = 0
    total_duplicates: int = 0
    total_accepted_evidence: int = 0
    total_accepted_claims: int = 0
    total_conflicting_claims: int = 0
    total_context_sources: int = 0
    total_web_leads: int = 0
    total_rejected: int = 0
    internal_markers_in_output: int = 0
    provider_version_mismatches: int = 0
    target_drifts: int = 0
    unaccounted_observations: int = 0
    ledger_state: str = "PENDING"  # PENDING|RECONCILED|INCOMPLETE_LEDGER

    def add_provider(self, metrics: ProviderMetrics):
        self.provider_metrics[metrics.provider] = metrics

    def reconcile(self) -> List[str]:
        """Check all invariants. Returns list of violations."""
        violations = []

        for provider, m in self.provider_metrics.items():
            # raw_results = normalized_observations + normalization_failures
            if m.raw_results != m.normalized_observations + m.normalization_failures:
                violations.append(
                    f"{provider}: raw_results({m.raw_results}) != normalized({m.normalized_observations}) + failures({m.normalization_failures})"
                )

            # normalized_observations = unique + duplicates
            unique_count = m.unique_urls
            if m.normalized_observations != unique_count + m.duplicate_urls:
                violations.append(
                    f"{provider}: normalized({m.normalized_observations}) != unique({unique_count}) + duplicates({m.duplicate_urls})"
                )

            # unique_items = unopened + opened + fetch_failed + metadata_only
            opened_total = m.opened_items + m.fetch_failed + m.metadata_only_items
            if unique_count != m.unopened + opened_total:
                violations.append(
                    f"{provider}: unique({unique_count}) != unopened({m.unopened}) + opened_total({opened_total})"
                )

            # opened items = accepted + partial + context + rejected
            classified = m.accepted_evidence + m.partial_evidence + m.context_sources + m.rejected_items
            if m.opened_items + m.content_extracted != classified:
                violations.append(
                    f"{provider}: opened+extracted({m.opened_items + m.content_extracted}) != classified({classified})"
                )

        # Global checks
        if self.internal_markers_in_output > 0:
            violations.append(f"INTERNAL_MARKERS_IN_OUTPUT: {self.internal_markers_in_output}")

        if self.provider_version_mismatches > 0:
            violations.append(f"PROVIDER_VERSION_MISMATCH: {self.provider_version_mismatches}")

        if self.target_drifts > 0:
            violations.append(f"TARGET_DRIFT: {self.target_drifts}")

        if self.unaccounted_observations > 0:
            violations.append(f"UNACCOUNTED_OBSERVATIONS: {self.unaccounted_observations}")

        self.ledger_state = "RECONCILED" if not violations else "INCOMPLETE_LEDGER"
        return violations

    def to_dict(self) -> dict:
        return {
            "run_id": self.run_id,
            "manifest_hash": self.manifest_hash,
            "provider_metrics": {k: v.__dict__ for k, v in self.provider_metrics.items()},
            "total_observations": self.total_observations,
            "total_unique": self.total_unique,
            "total_duplicates": self.total_duplicates,
            "total_accepted_evidence": self.total_accepted_evidence,
            "total_accepted_claims": self.total_accepted_claims,
            "total_conflicting_claims": self.total_conflicting_claims,
            "total_context_sources": self.total_context_sources,
            "total_web_leads": self.total_web_leads,
            "total_rejected": self.total_rejected,
            "internal_markers_in_output": self.internal_markers_in_output,
            "provider_version_mismatches": self.provider_version_mismatches,
            "target_drifts": self.target_drifts,
            "unaccounted_observations": self.unaccounted_observations,
            "ledger_state": self.ledger_state,
        }

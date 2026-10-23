"""
Kill switch centralizzato per pipeline legacy pericolose.

Tutti i job massivi (linking, sync, clean) devono controllare questo modulo
prima di eseguire. Default: tutti disabilitati.

Uso:
    from linking.kill_switch import is_legacy_job_enabled, LegacyJob
    
    if not is_legacy_job_enabled(LegacyJob.EVENT_LINKS):
        raise RuntimeError("Legacy event_links pipeline is frozen")
"""
import os
from enum import Enum
from pathlib import Path


class LegacyJob(Enum):
    EVENT_LINKS = "legacy_event_links"
    RECORD_LINKS = "legacy_record_links"
    CLEAN_BAD_LINKS = "legacy_clean_bad_links"
    FIX_GAIASCHI = "legacy_fix_gaiaschi"
    SYNC_EVENT_LINKS_SUPABASE = "legacy_sync_event_links_supabase"
    SYNC_RECORD_LINKS_SUPABASE = "legacy_sync_record_links_supabase"
    MASS_INDEX = "legacy_mass_index"
    MASS_INDEX_PARALLEL = "legacy_mass_index_parallel"
    IMPORT_PERSONAL_SOURCES = "legacy_import_personal_sources"
    IA_PIPELINE = "legacy_ia_pipeline"
    RESEARCH_TO_INDEX = "legacy_research_to_index"
    SEARCH_WW1_DOCUMENTS = "legacy_search_ww1_documents"
    EXTERNAL_LINK_SERVICE = "legacy_external_link_service"


_DEFAULT_DISABLED = {
    LegacyJob.EVENT_LINKS: False,
    LegacyJob.RECORD_LINKS: False,
    LegacyJob.CLEAN_BAD_LINKS: False,
    LegacyJob.FIX_GAIASCHI: False,
    LegacyJob.SYNC_EVENT_LINKS_SUPABASE: False,
    LegacyJob.SYNC_RECORD_LINKS_SUPABASE: False,
    LegacyJob.MASS_INDEX: False,
    LegacyJob.MASS_INDEX_PARALLEL: False,
    LegacyJob.IMPORT_PERSONAL_SOURCES: False,
    LegacyJob.IA_PIPELINE: False,
    LegacyJob.RESEARCH_TO_INDEX: False,
    LegacyJob.SEARCH_WW1_DOCUMENTS: False,
    LegacyJob.EXTERNAL_LINK_SERVICE: False,
}


def is_legacy_job_enabled(job: LegacyJob) -> bool:
    """
    Check if a legacy job is enabled.
    
    Jobs are disabled by default. They can be enabled via environment variable:
        LEGACY_JOB_<NAME>=true
    
    where <NAME> is the job's value uppercased.
    
    Even when enabled, jobs must run in --audit-only or --dry-run mode
    unless LEGACY_JOB_FORCE_EXECUTE=true is also set.
    """
    env_key = f"LEGACY_JOB_{job.value.upper()}"
    env_val = os.environ.get(env_key, "").lower().strip()
    return env_val in ("true", "1", "yes")


def is_force_execute_enabled() -> bool:
    """Check if force-execute is enabled (allows non-dry-run legacy jobs)."""
    return os.environ.get("LEGACY_JOB_FORCE_EXECUTE", "").lower().strip() in ("true", "1", "yes")


def assert_frozen(job: LegacyJob, context: str = ""):
    """
    Raise RuntimeError if a legacy job is not explicitly enabled.
    
    Use this at the top of legacy scripts to prevent accidental execution.
    """
    if not is_legacy_job_enabled(job):
        raise RuntimeError(
            f"Legacy job '{job.value}' is FROZEN. "
            f"This pipeline has been deprecated due to provenance and data integrity issues. "
            f"To run in audit-only mode, set {f'LEGACY_JOB_{job.value.upper()}=true'} in environment. "
            f"To execute mutations, also set LEGACY_JOB_FORCE_EXECUTE=true. "
            f"Context: {context}" if context else
            f"Legacy job '{job.value}' is FROZEN. "
            f"Set LEGACY_JOB_{job.value.upper()}=true to run in audit-only mode."
        )


def assert_audit_only(job: LegacyJob, context: str = ""):
    """
    Raise RuntimeError if force-execute is enabled without explicit audit-only override.
    In audit-only mode, jobs may run but must not mutate data.
    """
    if is_force_execute_enabled():
        raise RuntimeError(
            f"Legacy job '{job.value}' is in audit-only mode. "
            f"LEGACY_JOB_FORCE_EXECUTE is set but mutations are not permitted for this job. "
            f"Context: {context}"
        )


def list_jobs() -> dict:
    """Return status of all legacy jobs."""
    return {
        job.value: {
            "enabled": is_legacy_job_enabled(job),
            "force_execute": is_force_execute_enabled(),
            "default": _DEFAULT_DISABLED.get(job, False),
        }
        for job in LegacyJob
    }

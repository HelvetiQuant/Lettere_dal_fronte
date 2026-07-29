"""
Provider registry — loads provider metadata from archive_providers.yml
and populates archive.providers table on Supabase.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional

import yaml

from source_pipeline import (
    ProviderCapabilities,
    ProviderPolicy,
)

logger = logging.getLogger("source_pipeline.registry")


@dataclass
class ProviderConfig:
    code: str
    display_name: str
    authority_class: str = "DISCOVERY_ONLY"
    access_mode: str = "METADATA_ONLY"
    independence_group: str = ""
    rights_status: str = "UNKNOWN"
    terms_url: str = ""
    license_uri: str = ""
    holding_institution: str = ""
    collection_scope: str = ""
    personal_data_policy: str = "UNKNOWN"
    allowed_actions: List[str] = None
    rate_limit_delay: float = 1.0
    rate_limit_max_per_minute: int = 60
    provider_version: str = "1.0"
    enabled: bool = True
    capabilities: Dict[str, bool] = None
    notes: str = ""

    def __post_init__(self):
        if self.allowed_actions is None:
            self.allowed_actions = []
        if self.capabilities is None:
            self.capabilities = {}

    def to_caps(self) -> ProviderCapabilities:
        return ProviderCapabilities(
            search=self.capabilities.get("search", False),
            fetch_metadata=self.capabilities.get("fetch_metadata", False),
            download=self.capabilities.get("download", False),
            ocr=self.capabilities.get("ocr", False),
            caching=self.capabilities.get("caching", True),
            publishing=self.capabilities.get("publishing", False),
            local_storage=self.capabilities.get("local_storage", False),
            commercial_reuse=self.capabilities.get("commercial_reuse", False),
            personal_data=self.capabilities.get("personal_data", False),
        )

    def to_policy(self) -> ProviderPolicy:
        return ProviderPolicy(
            provider_code=self.code,
            authority_class=self.authority_class,
            access_mode=self.access_mode,
            rights_status=self.rights_status,
            terms_url=self.terms_url,
            license_uri=self.license_uri,
            holding_institution=self.holding_institution,
            collection_scope=self.collection_scope,
            personal_data_policy=self.personal_data_policy,
            allowed_actions=tuple(self.allowed_actions),
            rate_limit_delay_seconds=self.rate_limit_delay,
            rate_limit_max_per_minute=self.rate_limit_max_per_minute,
            independence_group=self.independence_group,
            provider_version=self.provider_version,
            enabled=self.enabled,
        )


_AUTHORITY_MAP = {
    "primary_archival": "PRIMARY_ARCHIVAL",
    "official_derived": "OFFICIAL_DERIVED",
    "scholarly_curated": "SCHOLARLY_CURATED",
    "aggregator": "AGGREGATOR",
    "discovery_only": "DISCOVERY_ONLY",
    "user_contributed": "USER_CONTRIBUTED",
}

_ACCESS_MAP = {
    "auto": "OPEN_API",
    "assisted": "TARGETED_SEARCH",
    "manual": "REQUEST_REQUIRED",
    "open_api": "OPEN_API",
    "open_download": "OPEN_DOWNLOAD",
    "metadata_only": "METADATA_ONLY",
    "targeted_search": "TARGETED_SEARCH",
    "request_required": "REQUEST_REQUIRED",
    "authorization_required": "AUTHORIZATION_REQUIRED",
    "unavailable": "UNAVAILABLE",
}

_RIGHTS_MAP = {
    "METADATA_ONLY": "METADATA_ONLY",
    "PUBLIC_VIEW": "PUBLIC_VIEW",
    "PUBLIC_DOWNLOAD": "PUBLIC_DOWNLOAD",
    "REQUEST_REQUIRED": "REQUEST_REQUIRED",
    "UNKNOWN": "UNKNOWN",
}


def load_providers(yaml_path: Path) -> Dict[str, ProviderConfig]:
    """Load provider configurations from YAML file."""
    with open(yaml_path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)

    providers = {}
    for entry in data.get("providers", []):
        code = entry.get("code", "")
        if not code:
            continue

        caps = entry.get("capabilities", [])
        cap_dict = {
            "search": "search" in caps,
            "fetch_metadata": "get_metadata" in caps or "metadata" in caps,
            "download": "get_document" in caps or "download" in caps,
            "ocr": "ocr" in caps or "full_text" in caps,
            "publishing": "publishing" in caps,
            "local_storage": "local_storage" in caps,
            "commercial_reuse": "commercial_reuse" in caps,
            "personal_data": "personal_data" in caps,
        }

        rights_default = entry.get("rights_default", "METADATA_ONLY")
        access_mode = _ACCESS_MAP.get(
            entry.get("access_mode", "assisted"), "METADATA_ONLY"
        )

        config_data = entry.get("config", {})
        rate_delay = float(config_data.get("rate_limit_delay", 1.0))

        # Infer authority_class if not explicitly set
        authority_class = entry.get("authority_class", "")
        if not authority_class:
            authority_score = float(entry.get("authority_score", 0.5))
            access_mode_raw = entry.get("access_mode", "assisted")
            rights = entry.get("rights_default", "METADATA_ONLY")
            if authority_score >= 0.90 and rights in ("METADATA_ONLY", "REQUEST_REQUIRED"):
                authority_class = "primary_archival"
            elif authority_score >= 0.85 and rights in ("PUBLIC_VIEW", "PUBLIC_DOWNLOAD"):
                authority_class = "primary_archival"
            elif authority_score >= 0.80:
                authority_class = "official_derived"
            elif authority_score >= 0.70:
                authority_class = "aggregator"
            else:
                authority_class = "discovery_only"

        providers[code] = ProviderConfig(
            code=code,
            display_name=entry.get("display_name", code),
            authority_class=_AUTHORITY_MAP.get(authority_class, "DISCOVERY_ONLY"),
            access_mode=access_mode,
            rights_status=_RIGHTS_MAP.get(rights_default, "UNKNOWN"),
            independence_group=entry.get("independence_group", ""),
            terms_url=config_data.get("terms_url", ""),
            license_uri=config_data.get("license_uri", ""),
            holding_institution=entry.get("holding_institution", entry.get("display_name", "")),
            collection_scope=", ".join(entry.get("geographic_areas", [])),
            personal_data_policy=config_data.get("personal_data_policy", "UNKNOWN"),
            allowed_actions=caps,
            rate_limit_delay=rate_delay,
            provider_version=entry.get("contract_version", "1.0"),
            enabled=True,
            capabilities=cap_dict,
            notes=config_data.get("notes", ""),
        )

    return providers


def sync_to_supabase(
    providers: Dict[str, ProviderConfig],
    execute_sql_fn,
) -> int:
    """Upsert providers into archive.providers table on Supabase. Returns count."""
    import json
    count = 0
    for code, cfg in providers.items():
        allowed_actions = "{" + ",".join(cfg.allowed_actions) + "}" if cfg.allowed_actions else "{}"
        rate_policy = json.dumps({
            "delay_seconds": cfg.rate_limit_delay,
            "max_per_minute": cfg.rate_limit_max_per_minute,
        })
        sql = f"""
        INSERT INTO archive.providers
            (provider_code, provider_name, authority_class, access_mode,
             rights_status, terms_url, license_uri, holding_institution,
             collection_scope, personal_data_policy, allowed_actions,
             rate_limit_policy, provider_version, enabled, notes)
        VALUES
            ('{code.replace("'", "''")}',
             '{cfg.display_name.replace("'", "''")}',
             '{cfg.authority_class}',
             '{cfg.access_mode}',
             '{cfg.rights_status}',
             '{cfg.terms_url.replace("'", "''")}',
             '{cfg.license_uri.replace("'", "''")}',
             '{cfg.holding_institution.replace("'", "''")}',
             '{cfg.collection_scope.replace("'", "''")}',
             '{cfg.personal_data_policy}',
             '{allowed_actions}',
             '{rate_policy.replace("'", "''")}',
             '{cfg.provider_version}',
             {str(cfg.enabled).lower()},
             '{cfg.notes.replace("'", "''")}')
        ON CONFLICT (provider_code) DO UPDATE SET
            provider_name = EXCLUDED.provider_name,
            authority_class = EXCLUDED.authority_class,
            access_mode = EXCLUDED.access_mode,
            rights_status = EXCLUDED.rights_status,
            terms_url = EXCLUDED.terms_url,
            license_uri = EXCLUDED.license_uri,
            holding_institution = EXCLUDED.holding_institution,
            collection_scope = EXCLUDED.collection_scope,
            personal_data_policy = EXCLUDED.personal_data_policy,
            allowed_actions = EXCLUDED.allowed_actions,
            rate_limit_policy = EXCLUDED.rate_limit_policy,
            provider_version = EXCLUDED.provider_version,
            enabled = EXCLUDED.enabled,
            notes = EXCLUDED.notes,
            updated_at = now();
        """
        try:
            result = execute_sql_fn(sql)
            if result.get("ok"):
                data = result.get("data") or {}
                if isinstance(data, dict) and data.get("ok") is False:
                    logger.error("Failed to sync provider %s: %s", code, data.get("error", ""))
                else:
                    count += 1
            else:
                logger.error("Failed to sync provider %s: %s", code, result.get("error", ""))
        except Exception as exc:
            logger.error("Failed to sync provider %s: %s", code, exc)
    return count

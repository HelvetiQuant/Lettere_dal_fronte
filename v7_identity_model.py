"""V7.2 Identity & Record Origin Model — identity clustering, 5 status states, discriminant-based resolution.

This module implements:
  - CanonicalIdentity: unique person/event/entity identity with provenance
  - RecordOrigin: where a record came from (archive, provider, fetch chain)
  - CorrectionLedger: layered corrections on immutable raw data
  - IdentityCluster: group of records that may belong to the same person
  - IdentityResolver: resolves observations to identity clusters with discriminant analysis

V7.2 key changes:
  1. Surname-only matches are SURNAME_ONLY_NON_CANDIDATE, not homonyms
  2. No arbitrary winner on score ties — AMBIGUOUS_IDENTITY instead
  3. 5 identity states: ANCHORED_RECORD, RESOLVED_IDENTITY, AMBIGUOUS_IDENTITY, PARTIAL_IDENTITY, UNRESOLVED_IDENTITY
  4. Discriminants: birth_year, birth_place, paternity, unit+period, death_year/place, matricola, grado
  5. Missing discriminant is NOT agreement
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field, asdict
from datetime import datetime
from typing import Dict, List, Optional, Any, Tuple


# ─── Identity types ─────────────────────────────────────────────────────────

IDENTITY_TYPES = ["person", "event", "place", "unit", "archive", "document"]

# V7.2: Identity status values
IDENTITY_STATUS_V72 = [
    "ANCHORED_RECORD",
    "RESOLVED_IDENTITY",
    "AMBIGUOUS_IDENTITY",
    "CONFLICTED_IDENTITY",
    "PARTIAL_IDENTITY",
    "UNRESOLVED_IDENTITY",
]

# V7.2: Discriminant fields (strong identity separators)
DISCRIMINANT_FIELDS = [
    "anno_nascita", "data_nascita", "luogo_nascita", "paternita", "maternita",
    "comune", "distretto", "matricola", "grado", "reparto",
    "anno_morte", "data_morte", "luogo_morte", "causa_morte",
    "provincia_nascita", "comune_nascita", "data_decesso",
    "nazione_decesso", "luogo_sepoltura",
    "service_number", "rank", "regiment", "nationality",
    "classe", "arma", "anno_decorazione",
]

# V7.2: Fields that indicate conflict between same-name records
CONFLICT_INDICATOR_FIELDS = [
    "reparto", "anno_morte", "luogo_morte", "causa_morte",
    "grado", "anno_nascita", "luogo_nascita",
    "data_nascita", "data_decesso", "paternita", "maternita",
    "matricola", "service_number", "rank", "regiment",
    "provincia_nascita", "comune_nascita",
    "nazione_decesso", "luogo_sepoltura",
]

# V7.3-FIX: Strong identifiers that MUST match for identity confirmation
STRONG_IDENTIFIERS = [
    "data_nascita", "data_decesso", "matricola", "service_number",
    "paternita", "maternita",
]

# V7.3-FIX: War period classification per table
TABLE_WAR_PERIOD = {
    "internati": "WWII",
    "lebi_records": "WWII",
    "caduti_albooro": "WWI",
    "decorati_nastroazzurro": "WWI",
    "caduti_cwgc": "BOTH",
    "caduti_ministero": "WWII",
}


@dataclass
class IdentityCluster:
    """A cluster of records that may belong to the same person.

    V7.2: replaces the single-winner approach with cluster-based identity.
    """
    cluster_id: str
    display_name: str
    cognome: str = ""
    nome: str = ""
    record_refs: List[Dict[str, Any]] = field(default_factory=list)
    discriminant_values: Dict[str, str] = field(default_factory=dict)
    conflicting_fields: List[str] = field(default_factory=list)
    has_full_name_match: bool = False
    has_discriminants: bool = False
    source_tables: List[str] = field(default_factory=list)

    def add_record(self, record: Dict[str, Any], table: str = ""):
        self.record_refs.append(record)
        if table and table not in self.source_tables:
            self.source_tables.append(table)
        for field_name in DISCRIMINANT_FIELDS:
            val = str(record.get(field_name, "")).strip()
            if val and val != "-":
                if field_name in self.discriminant_values:
                    if self.discriminant_values[field_name] != val:
                        if field_name not in self.conflicting_fields:
                            self.conflicting_fields.append(field_name)
                else:
                    self.discriminant_values[field_name] = val
        self.has_discriminants = len(self.discriminant_values) > 0

    @property
    def is_ambiguous(self) -> bool:
        return len(self.conflicting_fields) > 0

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class CanonicalIdentity:
    """A unique identity in the V7 system.

    Each identity has:
      - identity_id: stable hash-based ID
      - identity_type: person|event|place|unit|archive|document
      - display_name: human-readable name
      - canonical_fields: normalized fields (cognome, nome, anno_nascita, etc.)
      - provenance: where this identity was established
      - confidence: 0.0-1.0
      - conflict: ITALIAN_ONLY|AXIS_ONLY|CONFLICTING|UNKNOWN
    """
    identity_id: str = ""
    identity_type: str = "person"
    display_name: str = ""
    canonical_fields: Dict[str, Any] = field(default_factory=dict)
    provenance: str = ""  # internal_db|external|fused|manual
    confidence: float = 0.0
    conflict: str = "UNKNOWN"
    established_at: str = field(default_factory=lambda: datetime.now().isoformat())
    source_record_ids: List[str] = field(default_factory=list)

    def __post_init__(self):
        if not self.identity_id:
            raw = json.dumps({
                "type": self.identity_type,
                "name": self.display_name,
                "fields": self.canonical_fields,
            }, sort_keys=True, ensure_ascii=False)
            self.identity_id = f"id_{hashlib.sha256(raw.encode()).hexdigest()[:16]}"

    def to_dict(self) -> dict:
        return asdict(self)


# ─── Record origin ──────────────────────────────────────────────────────────

@dataclass
class RecordOrigin:
    """Provenance chain for a single record.

    Tracks the full lineage from raw observation to accepted evidence:
      - source_provider: which provider returned this record
      - source_table: which DB table (if local)
      - source_url: original URL (if web)
      - fetch_chain: list of steps from discovery to ingestion
      - raw_hash: hash of the raw record (immutability guarantee)
      - ingested_at: when the record was ingested
    """
    origin_id: str = ""
    source_provider: str = ""
    source_table: str = ""
    source_url: str = ""
    source_archive: str = ""
    fetch_chain: List[Dict[str, str]] = field(default_factory=list)
    raw_hash: str = ""
    ingested_at: str = field(default_factory=lambda: datetime.now().isoformat())
    access_mode: str = ""  # LINK_ONLY|METADATA_ONLY|API_METADATA|CONTENT_ALLOWED
    verified: bool = False

    def __post_init__(self):
        if not self.origin_id:
            raw = json.dumps({
                "provider": self.source_provider,
                "table": self.source_table,
                "url": self.source_url,
                "hash": self.raw_hash,
            }, sort_keys=True, ensure_ascii=False)
            self.origin_id = f"orig_{hashlib.sha256(raw.encode()).hexdigest()[:16]}"

    def to_dict(self) -> dict:
        return asdict(self)


# ─── Correction ledger ──────────────────────────────────────────────────────

@dataclass
class CorrectionEntry:
    """A single correction in the correction ledger.

    Corrections are layered overlays on immutable raw data.
    Each correction has:
      - correction_id: unique ID
      - target_identity_id: which identity this correction applies to
      - field_name: which field is corrected
      - original_value: the raw value (never modified)
      - corrected_value: the new value
      - correction_source: MANUAL|AI_SUGGESTED|CROSS_VALIDATED|AUTHORITY_FILE
      - corrected_by: who/what made the correction
      - reason: why the correction was made
      - confidence: 0.0-1.0
      - verified: whether this correction has been verified
      - supersedes: ID of a previous correction this one replaces
    """
    correction_id: str = ""
    target_identity_id: str = ""
    field_name: str = ""
    original_value: str = ""
    corrected_value: str = ""
    correction_source: str = "MANUAL"
    corrected_by: str = ""
    corrected_at: str = field(default_factory=lambda: datetime.now().isoformat())
    reason: str = ""
    confidence: float = 0.0
    verified: bool = False
    supersedes: str = ""

    def __post_init__(self):
        if not self.correction_id:
            raw = json.dumps({
                "identity": self.target_identity_id,
                "field": self.field_name,
                "original": self.original_value,
                "corrected": self.corrected_value,
                "source": self.correction_source,
            }, sort_keys=True, ensure_ascii=False)
            self.correction_id = f"corr_{hashlib.sha256(raw.encode()).hexdigest()[:16]}"

    def to_dict(self) -> dict:
        return asdict(self)


class CorrectionLedger:
    """Ledger of all corrections applied to raw data.

    Raw data is never modified. Corrections are stored as overlays.
    When reading a field, the ledger is consulted to find the latest
    verified correction for that field.

    Usage:
        ledger = CorrectionLedger()
        ledger.add(CorrectionEntry(
            target_identity_id="id_abc123",
            field_name="birth_year",
            original_value="1887",
            corrected_value="1886",
            correction_source="AUTHORITY_FILE",
            corrected_by="anrp_registry",
            reason="ANRP registry confirms 1886",
            confidence=0.95,
            verified=True,
        ))
        corrected = ledger.get_corrected_value("id_abc123", "birth_year", "1887")
        # Returns "1886"
    """

    def __init__(self):
        self._corrections: List[CorrectionEntry] = []
        self._by_identity: Dict[str, List[CorrectionEntry]] = {}

    def add(self, correction: CorrectionEntry):
        self._corrections.append(correction)
        if correction.target_identity_id not in self._by_identity:
            self._by_identity[correction.target_identity_id] = []
        self._by_identity[correction.target_identity_id].append(correction)

    def get_corrections_for_identity(self, identity_id: str) -> List[CorrectionEntry]:
        return self._by_identity.get(identity_id, [])

    def get_corrected_value(
        self,
        identity_id: str,
        field_name: str,
        raw_value: str,
    ) -> Tuple[str, Optional[CorrectionEntry]]:
        """Get the corrected value for a field, or the raw value if no correction.

        Returns (value, correction_entry_or_none).
        Only verified corrections are applied. If multiple corrections exist,
        the latest verified one is used.
        """
        corrections = self._by_identity.get(identity_id, [])
        relevant = [
            c for c in corrections
            if c.field_name == field_name and c.verified
        ]
        if not relevant:
            return raw_value, None

        # Sort by corrected_at descending (latest first)
        relevant.sort(key=lambda c: c.corrected_at, reverse=True)
        latest = relevant[0]
        return latest.corrected_value, latest

    def get_correction_chain(self, identity_id: str, field_name: str) -> List[CorrectionEntry]:
        """Get the full chain of corrections for a field, in order."""
        corrections = self._by_identity.get(identity_id, [])
        relevant = [c for c in corrections if c.field_name == field_name]
        relevant.sort(key=lambda c: c.corrected_at)
        return relevant

    def all_corrections(self) -> List[CorrectionEntry]:
        return list(self._corrections)

    def to_dict_list(self) -> List[dict]:
        return [c.to_dict() for c in self._corrections]


# ─── Identity resolver ──────────────────────────────────────────────────────

class IdentityResolver:
    """Resolves observations to identity clusters with discriminant analysis.

    V7.2: Replaces the single-winner scoring approach with cluster-based identity.
    - Surname-only matches → SURNAME_ONLY_NON_CANDIDATE (hidden from user)
    - Full-name matches → candidate clusters
    - If 1 cluster + origin record → ANCHORED_RECORD
    - If 1 cluster + discriminants, no conflicts → RESOLVED_IDENTITY
    - If 1 cluster + non-strong conflicts → CONFLICTED_IDENTITY
    - If 1 cluster + strong conflicts → AMBIGUOUS_IDENTITY
    - If 1 cluster, no discriminants → PARTIAL_IDENTITY
    - If 2+ clusters with conflicts → AMBIGUOUS_IDENTITY
    - If 0 clusters → UNRESOLVED_IDENTITY

    Key principle: identity resolution is decided by the BACKEND,
    never by the AI model. No destructive merge — all candidates preserved.
    """

    def __init__(self, correction_ledger: Optional[CorrectionLedger] = None):
        self._ledger = correction_ledger or CorrectionLedger()
        self._identities: Dict[str, CanonicalIdentity] = {}
        self._clusters: Dict[str, IdentityCluster] = {}
        self._surname_only: List[Dict[str, Any]] = []
        self._target_cognome: str = ""
        self._target_nome: str = ""
        self._origin_record_id: str = ""

    def set_target(self, cognome: str, nome: str, origin_record_id: str = ""):
        """Set the target name for this resolution session."""
        self._target_cognome = cognome.upper().strip()
        self._target_nome = nome.upper().strip()
        self._origin_record_id = origin_record_id

    def classify_observation(
        self,
        obs: Dict[str, Any],
        provider: str = "",
        table: str = "",
    ) -> Tuple[str, Optional[IdentityCluster]]:
        """Classify an observation as candidate, surname-only, or irrelevant.

        V7.3-FIX: Uses war_period from table to prevent cross-war homonym fusion.
        Records from different war periods are NEVER merged into the same cluster.

        Returns:
            (classification, cluster_or_none)
            classification: FULL_NAME_CANDIDATE | SURNAME_ONLY_NON_CANDIDATE | IRRELEVANT
        """
        obs_cognome = ""
        obs_nome = ""
        obs_nominativo = (obs.get("nominativo") or "").strip()

        if obs_nominativo:
            parts = obs_nominativo.split(None, 1)
            obs_cognome = parts[0].upper() if parts else ""
            obs_nome = parts[1].upper() if len(parts) > 1 else ""
        else:
            obs_cognome = (obs.get("cognome") or "").strip().upper()
            obs_nome = (obs.get("nome") or "").strip().upper()

        if not obs_cognome:
            return "IRRELEVANT", None

        target_cognome = self._target_cognome
        target_nome = self._target_nome

        if not target_cognome:
            return "IRRELEVANT", None

        cognome_match = obs_cognome == target_cognome
        nome_match = target_nome and obs_nome == target_nome

        # V7.3-FIX: Also try reversed name order (user may type "Nome Cognome")
        if not cognome_match or not nome_match:
            reversed_cognome_match = obs_cognome == target_nome
            reversed_nome_match = target_cognome and obs_nome == target_cognome
            if reversed_cognome_match and reversed_nome_match:
                cognome_match = True
                nome_match = True

        # V7.3-FIX: Get war period for this observation's table
        obs_war_period = TABLE_WAR_PERIOD.get(table, "UNKNOWN")

        if cognome_match and nome_match:
            cluster_id = self._make_cluster_id(obs_cognome, obs_nome, obs, table)
            if cluster_id not in self._clusters:
                self._clusters[cluster_id] = IdentityCluster(
                    cluster_id=cluster_id,
                    display_name=f"{obs_cognome} {obs_nome}".strip(),
                    cognome=obs_cognome,
                    nome=obs_nome,
                    has_full_name_match=True,
                )
            self._clusters[cluster_id].add_record(obs, table)
            return "FULL_NAME_CANDIDATE", self._clusters[cluster_id]

        if cognome_match and not nome_match:
            self._surname_only.append({
                "cognome": obs_cognome,
                "nome": obs_nome,
                "nominativo": obs_nominativo,
                "table": table,
                "provider": provider,
            })
            return "SURNAME_ONLY_NON_CANDIDATE", None

        return "IRRELEVANT", None

    def resolve(self) -> Tuple[str, Optional[IdentityCluster], List[IdentityCluster]]:
        """Determine identity status after all observations are classified.

        V7.3-FIX: Added strong-identifier conflict check. If a cluster has
        conflicting strong identifiers (data_nascita, paternita, etc.), it is
        marked AMBIGUOUS even if it's the only cluster.

        Returns:
            (identity_status, resolved_cluster, candidate_clusters)
        """
        candidate_clusters = list(self._clusters.values())

        if len(candidate_clusters) == 0:
            return "UNRESOLVED_IDENTITY", None, []

        if len(candidate_clusters) == 1:
            cluster = candidate_clusters[0]

            # V7.3-FIX: Check for strong-identifier conflicts within the cluster
            strong_conflicts = [f for f in cluster.conflicting_fields if f in STRONG_IDENTIFIERS]
            if strong_conflicts:
                # Strong identifier conflict = different people
                return "AMBIGUOUS_IDENTITY", None, candidate_clusters

            # V7.3-FASE5: Non-strong conflicts = CONFLICTED_IDENTITY
            # (e.g., different reparto but same birth date — same person, conflicting context)
            non_strong_conflicts = [f for f in cluster.conflicting_fields if f not in STRONG_IDENTIFIERS]
            if non_strong_conflicts and cluster.has_discriminants:
                return "CONFLICTED_IDENTITY", cluster, []

            if self._origin_record_id:
                return "ANCHORED_RECORD", cluster, []
            if cluster.has_discriminants and not cluster.is_ambiguous:
                return "RESOLVED_IDENTITY", cluster, []
            # V7.3-FIX: Single cluster with no discriminants and no strong IDs = PARTIAL
            return "PARTIAL_IDENTITY", cluster, []

        # 2+ clusters: check if they can be separated by discriminants
        separable = self._are_clusters_separable(candidate_clusters)
        if not separable:
            return "AMBIGUOUS_IDENTITY", None, candidate_clusters

        # If separable, try to find a unique match
        unique = self._find_unique_cluster(candidate_clusters)
        if unique:
            return "RESOLVED_IDENTITY", unique, [c for c in candidate_clusters if c.cluster_id != unique.cluster_id]

        return "AMBIGUOUS_IDENTITY", None, candidate_clusters

    def _are_clusters_separable(self, clusters: List[IdentityCluster]) -> bool:
        """Check if clusters can be separated by discriminant fields."""
        if len(clusters) < 2:
            return True
        for i in range(len(clusters)):
            for j in range(i + 1, len(clusters)):
                c1, c2 = clusters[i], clusters[j]
                for field_name in DISCRIMINANT_FIELDS:
                    v1 = c1.discriminant_values.get(field_name)
                    v2 = c2.discriminant_values.get(field_name)
                    if v1 and v2 and v1 != v2:
                        break
                else:
                    return False
        return True

    def _find_unique_cluster(self, clusters: List[IdentityCluster]) -> Optional[IdentityCluster]:
        """Find a cluster that is uniquely distinguishable from all others."""
        for cluster in clusters:
            unique = True
            for other in clusters:
                if other.cluster_id == cluster.cluster_id:
                    continue
                for field_name in DISCRIMINANT_FIELDS:
                    v1 = cluster.discriminant_values.get(field_name)
                    v2 = other.discriminant_values.get(field_name)
                    if v1 and v2 and v1 != v2:
                        break
                else:
                    unique = False
                    break
            if unique:
                return cluster
        return None

    def get_surname_only_records(self) -> List[Dict[str, Any]]:
        """Return surname-only records (to be hidden from user)."""
        return list(self._surname_only)

    def get_clusters(self) -> Dict[str, IdentityCluster]:
        return dict(self._clusters)

    def _make_cluster_id(self, cognome: str, nome: str, obs: Dict[str, Any], table: str = "") -> str:
        """V7.3-FIX: Cluster ID = name + war_period + table.

        Records with the same name from the same war period and table
        go into the same cluster. Strong identifiers are NOT part of the
        cluster ID — they are used for conflict detection within the cluster.
        This ensures that two "Rossi Mario" records with different birth dates
        from the same table end up in the same cluster, where the conflict
        is detected and the cluster is marked ambiguous.
        """
        war_period = TABLE_WAR_PERIOD.get(table, "UNKNOWN")
        raw = f"person|{cognome}|{nome}|war={war_period}|table={table}"
        return f"cluster_{hashlib.sha256(raw.encode()).hexdigest()[:12]}"

    # Legacy compat: keep resolve_observation for backward compat
    def resolve_observation(
        self,
        obs: Dict[str, Any],
        provider: str = "",
        table: str = "",
    ) -> Tuple[Optional[CanonicalIdentity], List[str]]:
        """Legacy: resolve an observation to a canonical identity."""
        reason_codes = []
        cognome = (obs.get("cognome") or obs.get("nominativo") or "").strip()
        nome = (obs.get("nome") or "").strip()
        if not cognome:
            reason_codes.append("NO_COGNOME")
            return None, reason_codes
        canonical_fields = {"cognome": cognome.upper(), "nome": nome.upper()}
        for field in ["anno_nascita", "luogo_nascita", "grado", "reparto", "anno_morte", "luogo_morte"]:
            val = obs.get(field)
            if val:
                canonical_fields[field] = str(val)
        conflict = "UNKNOWN"
        if table:
            if table in ("internati",):
                conflict = "AXIS_ONLY"
            elif table in ("caduti_albooro", "caduti_ministero", "decorati_nastroazzurro"):
                conflict = "ITALIAN_ONLY"
            elif table in ("caduti_cwgc",):
                conflict = "ALLIED_ONLY"
        display_name = f"{cognome} {nome}".strip()
        identity = CanonicalIdentity(
            identity_type="person",
            display_name=display_name,
            canonical_fields=canonical_fields,
            provenance=f"{provider}:{table}" if table else provider,
            confidence=0.8 if cognome and nome else 0.5,
            conflict=conflict,
            source_record_ids=[],
        )
        if identity.identity_id in self._identities:
            existing = self._identities[identity.identity_id]
            existing.source_record_ids.extend(identity.source_record_ids)
            return existing, reason_codes
        self._identities[identity.identity_id] = identity
        return identity, reason_codes

    def reject_homonym(
        self,
        identity: Optional[CanonicalIdentity],
        candidate: Dict[str, Any],
        reason_codes: List[str],
        conflicting_features: List[str],
    ) -> "RejectedHomonym":
        """Explicitly reject a homonym candidate with documented reasons."""
        return RejectedHomonym(
            candidate_name=candidate.get("nominativo") or f"{candidate.get('cognome','')} {candidate.get('nome','')}",
            target_identity_id=identity.identity_id if identity else "",
            reason_codes=reason_codes,
            conflicting_features=conflicting_features,
            candidate_fields=candidate,
        )

    def get_identity(self, identity_id: str) -> Optional[CanonicalIdentity]:
        return self._identities.get(identity_id)

    def all_identities(self) -> Dict[str, CanonicalIdentity]:
        return dict(self._identities)

    def _make_temp_id(self, cognome: str, nome: str) -> str:
        raw = f"person|{cognome.upper()}|{nome.upper()}"
        return f"id_{hashlib.sha256(raw.encode()).hexdigest()[:16]}"


@dataclass
class RejectedHomonym:
    """A homonym candidate that was explicitly rejected."""
    candidate_name: str
    target_identity_id: str
    reason_codes: List[str]
    conflicting_features: List[str]
    candidate_fields: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)

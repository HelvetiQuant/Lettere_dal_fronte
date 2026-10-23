"""QueryManifest — canonical, immutable, hashed research query contract.

Every research run starts by building a QueryManifest. All adapters receive
the same manifest and may only translate it into their provider syntax.
They cannot change target, conflict, or disambiguators.

The manifest is hashed and verified before and after every adapter.
Mutation → PROVIDER_CONTRACT_VIOLATION → results rejected.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field, asdict
from datetime import datetime
from typing import Dict, List, Optional, Any


@dataclass
class RunPolicy:
    max_results_per_provider: int = 20
    timeout_ms: int = 30000
    allow_live_web: bool = True
    allow_ocr: bool = False
    max_open_items: int = 5


@dataclass
class QueryManifest:
    manifest_id: str = ""
    manifest_hash: str = ""
    intent: str = ""  # PERSON_LOOKUP|EVENT_LOOKUP|AGGREGATE_QUERY|SOURCE_LOOKUP|CONVERSATIONAL_FOLLOWUP
    target: Dict[str, Any] = field(default_factory=dict)
    event_constraints: Dict[str, Any] = field(default_factory=dict)
    aggregate_constraints: Dict[str, Any] = field(default_factory=dict)
    allowed_source_classes: List[str] = field(default_factory=list)
    disallowed_source_classes: List[str] = field(default_factory=list)
    query_variants: List[str] = field(default_factory=list)
    identity_invariants: List[str] = field(default_factory=list)
    run_policy: RunPolicy = field(default_factory=RunPolicy)
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())

    def __post_init__(self):
        if not self.manifest_id:
            raw = json.dumps(self._hash_payload(), sort_keys=True, ensure_ascii=False)
            self.manifest_hash = hashlib.sha256(raw.encode()).hexdigest()
            self.manifest_id = f"manifest_{self.manifest_hash[:16]}"

    def _hash_payload(self) -> dict:
        d = asdict(self)
        d.pop("manifest_id", None)
        d.pop("manifest_hash", None)
        d.pop("created_at", None)
        return d

    def verify_hash(self) -> bool:
        raw = json.dumps(self._hash_payload(), sort_keys=True, ensure_ascii=False)
        return hashlib.sha256(raw.encode()).hexdigest() == self.manifest_hash

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "QueryManifest":
        rp = d.pop("run_policy", {})
        return cls(run_policy=RunPolicy(**rp) if isinstance(rp, dict) else rp, **d)

    @classmethod
    def for_person(
        cls,
        target_id: str,
        surname: str,
        given_names: List[str],
        display_name: str = "",
        source_order: str = "SURNAME_GIVEN",
        birth_date: Optional[str] = None,
        birth_year: Optional[str] = None,
        birth_place: Optional[str] = None,
        parentage: Optional[str] = None,
        service_number: Optional[str] = None,
        rank: Optional[str] = None,
        unit: Optional[str] = None,
        conflict: str = "UNKNOWN",
        run_policy: Optional[RunPolicy] = None,
    ) -> "QueryManifest":
        target = {
            "target_id": target_id,
            "surname": surname,
            "given_names": given_names,
            "display_name": display_name or f"{surname} {' '.join(given_names)}".strip(),
            "source_order": source_order,
            "birth_date": birth_date,
            "birth_year": birth_year,
            "birth_place": birth_place,
            "parentage": parentage,
            "service_number": service_number,
            "rank": rank,
            "unit": unit,
            "conflict": conflict,
        }
        variants = []
        if surname:
            variants.append(surname)
        if surname and given_names:
            variants.append(f"{surname} {' '.join(given_names)}")
            variants.append(f"{' '.join(given_names)} {surname}")
        invariants = []
        if birth_year:
            invariants.append(f"birth_year={birth_year}")
        if birth_place:
            invariants.append(f"birth_place={birth_place}")
        if parentage:
            invariants.append(f"parentage={parentage}")
        return cls(
            intent="PERSON_LOOKUP",
            target=target,
            query_variants=variants,
            identity_invariants=invariants,
            allowed_source_classes=["origin_record", "military_archive", "icrc", "lebi", "nara", "web_search"],
            run_policy=run_policy or RunPolicy(),
        )

    @classmethod
    def for_event(
        cls,
        event_id: str,
        event_name: str,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        location: Optional[str] = None,
        conflict: str = "WWI",
        run_policy: Optional[RunPolicy] = None,
    ) -> "QueryManifest":
        target = {
            "target_id": event_id,
            "display_name": event_name,
            "conflict": conflict,
        }
        constraints = {
            "start_date": start_date,
            "end_date": end_date,
            "location": location,
        }
        variants = [event_name]
        if location:
            variants.append(f"{event_name} {location}")
        return cls(
            intent="EVENT_LOOKUP",
            target=target,
            event_constraints=constraints,
            query_variants=variants,
            allowed_source_classes=["event_db", "military_archive", "web_search"],
            run_policy=run_policy or RunPolicy(),
        )

    @classmethod
    def for_aggregate(
        cls,
        query_id: str,
        description: str,
        filters: Dict[str, Any],
        conflict: str = "UNKNOWN",
        run_policy: Optional[RunPolicy] = None,
    ) -> "QueryManifest":
        target = {
            "target_id": query_id,
            "display_name": description,
            "conflict": conflict,
        }
        return cls(
            intent="AGGREGATE_QUERY",
            target=target,
            aggregate_constraints=filters,
            allowed_source_classes=["local_db", "canonical_db"],
            disallowed_source_classes=["web_search"],
            run_policy=run_policy or RunPolicy(allow_live_web=False),
        )

    @classmethod
    def for_source_lookup(
        cls,
        query_id: str,
        description: str,
        archive_type: str = "",
        conflict: str = "UNKNOWN",
        run_policy: Optional[RunPolicy] = None,
    ) -> "QueryManifest":
        target = {
            "target_id": query_id,
            "display_name": description,
            "conflict": conflict,
        }
        return cls(
            intent="SOURCE_LOOKUP",
            target=target,
            allowed_source_classes=["archive_catalog", "military_archive"],
            run_policy=run_policy or RunPolicy(allow_live_web=True),
        )

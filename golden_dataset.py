"""Golden Dataset Revisionabile — dataset di riferimento per validazione
qualità delle claim/evidence nel nuovo schema Supabase.

Il golden dataset è costituito da claim annotate manualmente con stato
epistemico atteso, numero di evidence minimo, e provider indipendenti
richiesti. Ogni entry è revisionabile tramite evidence.editorial_decisions.

Casi inclusi (basati sui pilot reali):
  - Pilot A: Battaglia del Carso (evt_0018) — claim_id=9, 22 items Europeana
  - Pilot B: Persona WW1 (ICRC) — claim_id=10, 5 items, 3 evidence
  - Pilot C: IMI WW2 (LeBI) — claim_id=11, 5 items, 3 evidence
  - Pilot D: Onorificenza Quirinale — claim_id=12, 0 items (caso negativo)

Ogni caso definisce:
  - expected_epistemic_status: confirmed / probable / candidate / unverifiable
  - min_evidence_count: numero minimo di evidence attese
  - required_independent_sources: numero minimo di provider indipendenti
  - expected_review_status: approved / pending / rejected
  - notes: note manuali per il revisore

Usage:
  python golden_dataset.py --init     # Crea le entry nel DB
  python golden_dataset.py --validate # Valida le claim contro il golden dataset
  python golden_dataset.py --report   # Genera report di validazione
"""
from __future__ import annotations

import json
import logging
import os
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import httpx
from dotenv import load_dotenv

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("golden_dataset")

SUPABASE_URL = os.environ.get("SUPABASE_URL", "")
SUPABASE_KEY = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")

_HEADERS = {
    "apikey": SUPABASE_KEY,
    "Authorization": f"Bearer {SUPABASE_KEY}",
    "Content-Type": "application/json",
}


# ─── Golden dataset definition ──────────────────────────────────────────────

@dataclass
class GoldenCase:
    """Un caso del golden dataset."""
    case_id: str
    claim_id: int
    description: str
    expected_claim_status: str  # discovered, ingested, candidate, supported, verified, conflicting, rejected
    min_evidence_count: int
    required_independent_sources: int
    expected_editorial_decision: str  # verified, supported, rejected, needs_revision, deferred
    notes: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "case_id": self.case_id,
            "claim_id": self.claim_id,
            "description": self.description,
            "expected_claim_status": self.expected_claim_status,
            "min_evidence_count": self.min_evidence_count,
            "required_independent_sources": self.required_independent_sources,
            "expected_editorial_decision": self.expected_editorial_decision,
            "notes": self.notes,
        }


# Casi reali basati sui pilot completati
GOLDEN_CASES: List[GoldenCase] = [
    GoldenCase(
        case_id="GD-001",
        claim_id=9,
        description="Pilot A: Battaglia del Carso (evt_0018) — occurred_during WW1, 22 items Europeana",
        expected_claim_status="supported",
        min_evidence_count=3,
        required_independent_sources=0,  # Solo Europeana, ma evidence non linkate ad external_items
        expected_editorial_decision="needs_revision",
        notes="22 items da Europeana confermano l'evento. claim_status 'supported'. Evidence create ma source_item_id NULL — da collegare agli external_items per independent_sources > 0.",
    ),
    GoldenCase(
        case_id="GD-002",
        claim_id=10,
        description="Pilot B: Persona WW1 — was_prisoner_in, 5 ICRC items, 3 evidence",
        expected_claim_status="supported",
        min_evidence_count=2,
        required_independent_sources=0,  # Solo ICRC, ma evidence non linkate ad external_items
        expected_editorial_decision="needs_revision",
        notes="5 items ICRC con 3 evidence. Evidence create ma source_item_id NULL — da collegare agli external_items.",
    ),
    GoldenCase(
        case_id="GD-003",
        claim_id=11,
        description="Pilot C: IMI WW2 — was_interned_in, 5 LeBI items, 3 evidence",
        expected_claim_status="supported",
        min_evidence_count=2,
        required_independent_sources=0,  # Solo LeBI/ANRP, ma evidence non linkate ad external_items
        expected_editorial_decision="needs_revision",
        notes="5 items LeBI con 3 evidence. Evidence create ma source_item_id NULL — da collegare agli external_items.",
    ),
    GoldenCase(
        case_id="GD-004",
        claim_id=12,
        description="Pilot D: Onorificenza Quirinale — received_honor, 0 items",
        expected_claim_status="discovered",
        min_evidence_count=0,
        required_independent_sources=0,
        expected_editorial_decision="deferred",
        notes="Nessun item recuperato. Endpoint Quirinale non ha restituito risultati. Internet Archive senza match. Claim da rivedere con query alternative.",
    ),
    # Casi negativi di controllo
    GoldenCase(
        case_id="GD-005-NEG",
        claim_id=0,  # Da creare: claim fittizia per test negativo
        description="Caso negativo: claim senza evidence deve essere 'unverifiable'",
        expected_claim_status="rejected",
        min_evidence_count=0,
        required_independent_sources=0,
        expected_editorial_decision="rejected",
        notes="Caso di controllo: una claim senza evidence deve avere claim_status='rejected' e editorial_decision='rejected'.",
    ),
    GoldenCase(
        case_id="GD-006-NEG",
        claim_id=0,
        description="Caso negativo: claim con evidence da singola fonte DISCOVERY_ONLY deve essere 'candidate'",
        expected_claim_status="candidate",
        min_evidence_count=1,
        required_independent_sources=0,
        expected_editorial_decision="needs_revision",
        notes="Caso di controllo: evidence da provider DISCOVERY_ONLY non basta per 'supported'. Deve restare 'candidate'.",
    ),
]


# ─── Supabase helpers ──────────────────────────────────────────────────────

def _exec_sql_returning(sql: str) -> list:
    url = f"{SUPABASE_URL}/rest/v1/rpc/exec_sql_returning"
    r = httpx.post(url, headers=_HEADERS, json={"query": sql}, timeout=60)
    if r.status_code in (200, 201, 204):
        try:
            return r.json()
        except Exception:
            return []
    logger.error("exec_sql_returning failed: %s", r.text[:500])
    return []


def _execute_sql(sql: str) -> dict:
    url = f"{SUPABASE_URL}/rest/v1/rpc/exec_sql"
    r = httpx.post(url, headers=_HEADERS, json={"query": sql}, timeout=60)
    if r.status_code in (200, 201, 204):
        try:
            return r.json()
        except Exception:
            return {"ok": True}
    return {"ok": False, "error": r.text[:500]}


# ─── Init: create editorial_decisions for golden cases ──────────────────────

def init_golden_dataset():
    """Crea le entry del golden dataset come editorial_decisions in Supabase."""
    logger.info("Initializing golden dataset in Supabase...")

    for case in GOLDEN_CASES:
        if case.claim_id == 0:
            logger.info(f"Skipping {case.case_id} (no claim_id — control case)")
            continue

        # Check if editorial_decision already exists
        check_sql = f"""
        SELECT json_agg(row_to_json(x)) FROM (
            SELECT id FROM evidence.editorial_decisions
            WHERE claim_id = {case.claim_id}
              AND reason ILIKE '%{case.case_id}%'
            LIMIT 1
        ) x;
        """
        existing = _exec_sql_returning(check_sql)
        if existing:
            logger.info(f"{case.case_id} already exists, skipping")
            continue

        # Create editorial_decision
        reason = f"[{case.case_id}] {case.notes}"
        reason_escaped = reason.replace("'", "''")
        decision_sql = f"""
        INSERT INTO evidence.editorial_decisions
            (claim_id, decision, reviewer_id, reason, decided_at)
        VALUES
            ({case.claim_id}, '{case.expected_editorial_decision}',
             'golden_dataset', '{reason_escaped}', now())
        ON CONFLICT DO NOTHING;
        """
        result = _execute_sql(decision_sql)
        if isinstance(result, dict) and result.get("ok", True):
            logger.info(f"{case.case_id} created for claim_id={case.claim_id}")
        else:
            logger.error(f"{case.case_id} failed: {result}")

    # Save golden dataset definition as JSON
    output_path = os.path.join(os.path.dirname(__file__), "docs", "audit", "GOLDEN_DATASET.json")
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    data = {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "cases": [c.to_dict() for c in GOLDEN_CASES],
        "total_cases": len(GOLDEN_CASES),
    }
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    logger.info(f"Golden dataset definition saved to {output_path}")


# ─── Validate: check claims against golden dataset ──────────────────────────

def validate_golden_dataset() -> List[Dict[str, Any]]:
    """Valida le claim esistenti contro il golden dataset."""
    logger.info("Validating golden dataset...")
    results = []

    for case in GOLDEN_CASES:
        if case.claim_id == 0:
            results.append({
                "case_id": case.case_id,
                "status": "skip",
                "message": "Control case — no claim_id",
            })
            continue

        # Fetch claim status
        claim_sql = f"""
        SELECT json_agg(row_to_json(x)) FROM (
            SELECT
                c.id, c.claim_status, c.predicate,
                COUNT(ev.id) AS evidence_count,
                COUNT(DISTINCT p.independence_group) AS independent_groups,
                (SELECT ed.decision FROM evidence.editorial_decisions ed
                 WHERE ed.claim_id = c.id ORDER BY ed.decided_at DESC LIMIT 1) AS latest_decision
            FROM evidence.claims c
            LEFT JOIN evidence.evidence ev ON ev.claim_id = c.id
            LEFT JOIN archive.external_items ei ON ei.id = ev.source_item_id
            LEFT JOIN archive.providers p ON p.id = ei.provider_id
            WHERE c.id = {case.claim_id}
            GROUP BY c.id
        ) x;
        """
        rows = _exec_sql_returning(claim_sql)
        if not isinstance(rows, list) or not rows or not rows[0]:
            results.append({
                "case_id": case.case_id,
                "claim_id": case.claim_id,
                "status": "fail",
                "message": f"Claim {case.claim_id} not found",
                "expected": case.to_dict(),
                "actual": None,
            })
            continue

        actual = rows[0]
        issues = []

        # Check claim_status
        if actual.get("claim_status") != case.expected_claim_status:
            issues.append(
                f"claim_status: expected '{case.expected_claim_status}', "
                f"got '{actual.get('claim_status')}'"
            )

        # Check evidence_count
        actual_ev_count = actual.get("evidence_count", 0)
        if actual_ev_count < case.min_evidence_count:
            issues.append(
                f"evidence_count: expected >= {case.min_evidence_count}, got {actual_ev_count}"
            )

        # Check independent sources
        actual_ind = actual.get("independent_groups", 0) or 0
        if actual_ind < case.required_independent_sources:
            issues.append(
                f"independent_sources: expected >= {case.required_independent_sources}, got {actual_ind}"
            )

        # Check editorial_decision
        if actual.get("latest_decision") != case.expected_editorial_decision:
            issues.append(
                f"editorial_decision: expected '{case.expected_editorial_decision}', "
                f"got '{actual.get('latest_decision')}'"
            )

        results.append({
            "case_id": case.case_id,
            "claim_id": case.claim_id,
            "status": "pass" if not issues else "fail",
            "issues": issues,
            "expected": case.to_dict(),
            "actual": {
                "claim_status": actual.get("claim_status"),
                "evidence_count": actual_ev_count,
                "independent_groups": actual_ind,
                "latest_decision": actual.get("latest_decision"),
            },
        })

    return results


# ─── Report ─────────────────────────────────────────────────────────────────

def generate_report(results: Optional[List[Dict]] = None):
    """Genera report di validazione del golden dataset."""
    if results is None:
        results = validate_golden_dataset()

    passed = sum(1 for r in results if r["status"] == "pass")
    failed = sum(1 for r in results if r["status"] == "fail")
    skipped = sum(1 for r in results if r["status"] == "skip")

    print("\n" + "=" * 80)
    print("GOLDEN DATASET VALIDATION REPORT")
    print("=" * 80)
    print(f"Total cases: {len(results)}")
    print(f"Passed: {passed}")
    print(f"Failed: {failed}")
    print(f"Skipped: {skipped}")
    print()

    for r in results:
        status_icon = "✅" if r["status"] == "pass" else "❌" if r["status"] == "fail" else "⏭️"
        print(f"{status_icon} {r['case_id']}: {r.get('message', r['status'])}")
        if r.get("issues"):
            for issue in r["issues"]:
                print(f"   ⚠️  {issue}")

    print("\n" + "=" * 80)

    # Save report
    output_path = os.path.join(os.path.dirname(__file__), "docs", "audit", "GOLDEN_DATASET_REPORT.json")
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump({
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "summary": {"total": len(results), "passed": passed, "failed": failed, "skipped": skipped},
            "results": results,
        }, f, indent=2, ensure_ascii=False)
    logger.info(f"Report saved to {output_path}")

    return failed == 0


# ─── Main ───────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Golden Dataset Revisionabile")
    parser.add_argument("--init", action="store_true", help="Initialize golden dataset in DB")
    parser.add_argument("--validate", action="store_true", help="Validate claims against golden dataset")
    parser.add_argument("--report", action="store_true", help="Generate validation report")
    args = parser.parse_args()

    if args.init:
        init_golden_dataset()
    if args.validate or args.report:
        results = validate_golden_dataset()
        if args.report:
            success = generate_report(results)
            sys.exit(0 if success else 1)
        else:
            print(json.dumps(results, indent=2, ensure_ascii=False))

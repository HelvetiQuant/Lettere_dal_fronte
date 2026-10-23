"""V7.3-Fase17: Acceptance metrics and before/after benchmark.

Measures the impact of V7.3 phases 1-16 on the system:
  1. Source quality distribution (high/medium/low/very_low)
  2. Claim state distribution (PUBLISHED / WITH_CAVEAT / REVIEW_PENDING / SUPPRESSED)
  3. Link migration statistics (record_links + event_links)
  4. Regression test pass rate (10 cases A-J)
  5. API endpoint count and health
  6. Module count and import health

Produces a JSON report at docs/v73_benchmark.json.
"""
from __future__ import annotations

import json
import os
import sys
import time
import sqlite3
from datetime import datetime
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from source_quality import assess_source_quality, combine_evidence_quality
from claim_lifecycle import determine_claim_state
from response_structure import ResponseBuilder, SECTION_IDS

DB_MAIN = Path(__file__).parent / "imi_internati.db"
DB_EVENTS = Path(__file__).parent / "eventi_1gm.db"


def measure_source_quality():
    """Measure source quality distribution across all registered sources."""
    from source_authority_registry import DEFAULT_SOURCES
    distribution = {"high": 0, "medium": 0, "low": 0, "very_low": 0}
    scores = []
    for src in DEFAULT_SOURCES:
        q = assess_source_quality(src["source_key"])
        distribution[q.quality_level] = distribution.get(q.quality_level, 0) + 1
        scores.append({"source": src["source_key"], "level": q.quality_level, "score": round(q.quality_score, 3)})
    return {"distribution": distribution, "sources": scores}


def measure_link_migration():
    """Measure V7.3 migration statistics from the database."""
    stats = {"record_links": {}, "event_links": {}}
    
    conn = sqlite3.connect(str(DB_MAIN))
    conn.row_factory = sqlite3.Row
    
    total = conn.execute("SELECT COUNT(*) as c FROM record_links").fetchone()["c"]
    migrated = conn.execute("SELECT COUNT(*) as c FROM record_links WHERE v73_rule_version = '7.3.0'").fetchone()["c"]
    
    state_dist = {}
    if migrated > 0:
        rows = conn.execute("SELECT v73_claim_state, COUNT(*) as c FROM record_links WHERE v73_rule_version = '7.3.0' GROUP BY v73_claim_state").fetchall()
        for r in rows:
            state_dist[r["v73_claim_state"] or "unknown"] = r["c"]
    
    stats["record_links"] = {"total": total, "migrated": migrated, "state_distribution": state_dist}
    conn.close()
    
    conn = sqlite3.connect(str(DB_EVENTS))
    conn.row_factory = sqlite3.Row
    
    total = conn.execute("SELECT COUNT(*) as c FROM event_links").fetchone()["c"]
    migrated = conn.execute("SELECT COUNT(*) as c FROM event_links WHERE v73_rule_version = '7.3.0'").fetchone()["c"]
    
    state_dist = {}
    if migrated > 0:
        rows = conn.execute("SELECT v73_claim_state, COUNT(*) as c FROM event_links WHERE v73_rule_version = '7.3.0' GROUP BY v73_claim_state").fetchall()
        for r in rows:
            state_dist[r["v73_claim_state"] or "unknown"] = r["c"]
    
    stats["event_links"] = {"total": total, "migrated": migrated, "state_distribution": state_dist}
    conn.close()
    
    return stats


def measure_regression():
    """Run the 10-case regression test and return pass rate."""
    import subprocess
    result = subprocess.run(
        [sys.executable, "test_v73_regression.py"],
        capture_output=True, text=True, cwd=str(Path(__file__).parent),
    )
    output = result.stdout + result.stderr
    passed = output.count(" PASS:")
    failed = output.count(" FAIL:")
    total = passed + failed
    return {
        "total": total,
        "passed": passed,
        "failed": failed,
        "pass_rate": round(passed / total * 100, 1) if total > 0 else 0,
        "exit_code": result.returncode,
    }


def measure_api_endpoints():
    """Count API endpoints in v7_api.py."""
    try:
        import v7_api
        routes = [r.path for r in v7_api.router.routes]
        v73_routes = [r for r in routes if any(
            kw in r for kw in ["source-quality", "validate", "claim-states", "build-response", "response-schema"]
        )]
        return {"total_v7_routes": len(routes), "v73_new_routes": len(v73_routes), "routes": routes}
    except Exception as e:
        return {"error": str(e)}


def measure_modules():
    """Count V7.3 modules and verify imports."""
    v73_modules = [
        "military_ontology", "source_quality", "semantic_validator",
        "claim_lifecycle", "response_structure", "geo_context",
        "migrate_v73_links",
    ]
    results = {}
    for mod in v73_modules:
        try:
            __import__(mod)
            results[mod] = "OK"
        except Exception as e:
            results[mod] = f"FAIL: {e}"
    return {"total": len(v73_modules), "importable": sum(1 for v in results.values() if v == "OK"), "details": results}


def measure_response_structure():
    """Verify the 11-section response structure."""
    builder = ResponseBuilder()
    response = builder.build(
        request_type="PERSON",
        query="Benchmark Test",
        identity_status="RESOLVED_IDENTITY",
        evidence_level="verified",
        claims=[],
        claim_states=[],
    )
    return {
        "schema_version": response.schema_version,
        "section_count": len(response.sections),
        "section_ids": [s.section_id for s in response.sections],
        "expected_sections": SECTION_IDS,
        "correct": len(response.sections) == 11,
    }


def main():
    print("=" * 70)
    print("V7.3 ACCEPTANCE METRICS — BENCHMARK")
    print("=" * 70)
    print()

    report = {
        "benchmark_id": f"v73_benchmark_{int(time.time())}",
        "timestamp": datetime.now().isoformat(),
        "version": "V7.3-Fase17",
    }

    # 1. Source quality
    print("1. Measuring source quality...")
    t0 = time.time()
    report["source_quality"] = measure_source_quality()
    print(f"   Done ({time.time()-t0:.1f}s)")

    # 2. Link migration
    print("2. Measuring link migration stats...")
    t0 = time.time()
    report["link_migration"] = measure_link_migration()
    print(f"   Done ({time.time()-t0:.1f}s)")

    # 3. Regression tests
    print("3. Running regression tests (10 cases A-J)...")
    t0 = time.time()
    report["regression"] = measure_regression()
    print(f"   Done ({time.time()-t0:.1f}s): {report['regression']['passed']}/{report['regression']['total']} PASS")

    # 4. API endpoints
    print("4. Counting API endpoints...")
    report["api"] = measure_api_endpoints()
    print(f"   V7 routes: {report['api'].get('total_v7_routes', 0)}, V7.3 new: {report['api'].get('v73_new_routes', 0)}")

    # 5. Module imports
    print("5. Verifying module imports...")
    report["modules"] = measure_modules()
    print(f"   {report['modules']['importable']}/{report['modules']['total']} modules importable")

    # 6. Response structure
    print("6. Verifying response structure...")
    report["response_structure"] = measure_response_structure()
    print(f"   Sections: {report['response_structure']['section_count']}, correct: {report['response_structure']['correct']}")

    # Summary
    print()
    print("=" * 70)
    print("SUMMARY")
    print("=" * 70)
    print(f"  Source quality: {report['source_quality']['distribution']}")
    print(f"  Record links: {report['link_migration']['record_links']['migrated']}/{report['link_migration']['record_links']['total']} migrated")
    print(f"  Event links: {report['link_migration']['event_links']['migrated']}/{report['link_migration']['event_links']['total']} migrated")
    print(f"  Regression: {report['regression']['passed']}/{report['regression']['total']} ({report['regression']['pass_rate']}%)")
    print(f"  API routes: {report['api'].get('total_v7_routes', 0)} total, {report['api'].get('v73_new_routes', 0)} new")
    print(f"  Modules: {report['modules']['importable']}/{report['modules']['total']} importable")
    print(f"  Response sections: {report['response_structure']['section_count']}/11")

    # Save report
    out_path = Path(__file__).parent / "docs" / "v73_benchmark.json"
    out_path.parent.mkdir(exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)
    print(f"\n  Report saved to: {out_path}")


if __name__ == "__main__":
    main()

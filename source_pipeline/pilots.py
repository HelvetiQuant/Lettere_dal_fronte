"""
Pilot runner — esegue i 4 pilot progettuali per validare la pipeline.

Pilot A: Battaglia del Carso (evt_0018) via Europeana
Pilot B: Persona WW1 con 2+ fonti (ICRC + Europeana)
Pilot C: IMI WW2 (LeBI + Arolsen)
Pilot D: Onorificenza Quirinale/Gazzetta

Per ogni pilot:
1. Discovery search sui provider pertinenti
2. Ingestion dei risultati in archive.external_items
3. Creazione claim in evidence.claims
4. Link evidenza in evidence.evidence
5. Report finale con metriche
"""
from __future__ import annotations

import json
import logging
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from source_pipeline.adapters import get_all_adapters
from source_pipeline.ingestion import (
    run_discovery,
    ingest_search_result,
    create_claim,
    add_evidence,
    _get_provider_id,
)

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("source_pipeline.pilots")


def _exec_sql_returning(sql: str) -> dict:
    """Execute SQL that returns rows via exec_sql_returning RPC."""
    import httpx
    import os
    from dotenv import load_dotenv
    load_dotenv()
    url = os.environ.get("SUPABASE_URL", "")
    key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")
    headers = {
        "apikey": key,
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
    }
    r = httpx.post(
        f"{url}/rest/v1/rpc/exec_sql_returning",
        headers=headers,
        json={"query": sql},
        timeout=120,
    )
    if r.status_code in (200, 201, 204):
        try:
            return r.json()
        except Exception:
            return {"ok": True}
    return {"ok": False, "error": r.text[:500]}


def _get_entity_id_by_name(name: str) -> int | None:
    """Look up a core.entities row by canonical_name."""
    from source_pipeline import compute_stable_id
    name_escaped = name.replace("'", "''")
    stable = compute_stable_id("entity", name)
    sql = f"SELECT json_agg(row_to_json(x)) FROM (SELECT id FROM core.entities WHERE stable_id = '{stable}' LIMIT 1) x;"
    result = _exec_sql_returning(sql)
    if isinstance(result, list) and result:
        return result[0].get("id")
    if isinstance(result, dict) and result.get("__error__"):
        logger.error("Query entity failed: %s", result.get("error", ""))
        return None
    return None


def _get_or_create_entity(name: str, entity_type: str = "event") -> int | None:
    """Get entity by name, or create if not exists."""
    from source_pipeline import compute_stable_id
    from source_pipeline.ingestion import _execute_sql

    stable = compute_stable_id("entity", name)
    existing = _get_entity_id_by_name(name)
    if existing:
        logger.info("Entity exists: id=%s name='%s'", existing, name)
        return existing

    name_escaped = name.replace("'", "''")
    sql = f"""
    WITH x AS (
        INSERT INTO core.entities (stable_id, entity_type, canonical_name, created_by_kind, source_system)
        VALUES ('{stable}', '{entity_type}', '{name_escaped}', 'pilot', 'source_pipeline_v2')
        ON CONFLICT (stable_id) DO UPDATE SET updated_at = now()
        RETURNING id
    )
    SELECT json_agg(row_to_json(x)) FROM x;
    """
    result = _exec_sql_returning(sql)
    if isinstance(result, list) and result:
        entity_id = result[0].get("id")
        logger.info("Entity created: id=%s name='%s'", entity_id, name)
        return entity_id
    if isinstance(result, dict) and result.get("__error__"):
        logger.error("Failed to create entity: %s", result.get("error", ""))
        return None

    # Fallback: try to query after insert
    return _get_entity_id_by_name(name)


def pilot_a_carso():
    """Pilot A: Battaglia del Carso (evt_0018) via Europeana."""
    print("\n" + "=" * 72)
    print("PILOT A: Battaglia del Carso (evt_0018) via Europeana")
    print("=" * 72)

    pipeline_run_id = f"pilot_a_carso_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}"

    # 1. Get or create entity for the battle
    entity_id = _get_or_create_entity("Battaglia del Carso", "event")
    if not entity_id:
        print("  FAIL: Could not get/create entity for Battaglia del Carso")
        return {"pilot": "A", "status": "failed", "reason": "entity creation failed"}

    print(f"  Entity: id={entity_id} name='Battaglia del Carso'")

    # 2. Discovery search on Europeana
    queries = [
        'Carso battle 1915 1916 1917',
        'Isonzo front Italian World War I',
        'Battaglia del Carso prima guerra mondiale',
    ]

    all_items = []
    for q in queries:
        print(f"\n  Discovery query: '{q}'")
        results = run_discovery("europeana", q, max_results=10)
        all_items.extend(results)
        time.sleep(1)

    print(f"\n  Total items discovered: {len(all_items)}")

    # 3. Create claim: "Battaglia del Carso" → occurred_during → WW1
    claim_id = create_claim(
        subject_entity_id=entity_id,
        predicate="occurred_during",
        object_value="WW1",
        claim_status="discovered",
        extraction_method="pilot_discovery",
        pipeline_run_id=pipeline_run_id,
        valid_from="1915-06-23",
        valid_to="1917-10-24",
        conflict_code="ww1",
    )
    if claim_id:
        print(f"  Claim created: id={claim_id} predicate='occurred_during' object='WW1'")

        # 4. Add evidence for each discovered source
        evidence_count = 0
        for item in all_items[:5]:
            ev_id = add_evidence(
                claim_id=claim_id,
                source_item_id=None,
                evidence_type="documentary",
                text_span=item.title[:200],
                independence_group="europeana",
                review_status="pending",
            )
            if ev_id:
                evidence_count += 1
                print(f"    Evidence: id={ev_id} source='{item.title[:50]}'")

        print(f"  Evidence added: {evidence_count}")

    return {
        "pilot": "A",
        "status": "completed",
        "entity_id": entity_id,
        "items_discovered": len(all_items),
        "claim_id": claim_id,
        "pipeline_run_id": pipeline_run_id,
    }


def pilot_b_ww1_person():
    """Pilot B: Persona WW1 con 2+ fonti (ICRC + Europeana)."""
    print("\n" + "=" * 72)
    print("PILOT B: Persona WW1 con 2+ fonti (ICRC + Europeana)")
    print("=" * 72)

    pipeline_run_id = f"pilot_b_ww1_person_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}"

    # Use a known WW1 soldier name from the database
    test_name = "Rossi Mario"
    entity_id = _get_or_create_entity(test_name, "person")
    if not entity_id:
        print(f"  FAIL: Could not get/create entity for '{test_name}'")
        return {"pilot": "B", "status": "failed", "reason": "entity creation failed"}

    print(f"  Entity: id={entity_id} name='{test_name}'")

    # Discovery on ICRC
    print(f"\n  Discovery on ICRC WW1...")
    icrc_results = run_discovery("icrc_ww1", test_name, max_results=5)
    print(f"  ICRC results: {len(icrc_results)}")

    time.sleep(2)

    # Discovery on Europeana
    print(f"\n  Discovery on Europeana...")
    eur_query = f'"{test_name}" prisoner war 1914-1918 Italy'
    eur_results = run_discovery("europeana", eur_query, max_results=5)
    print(f"  Europeana results: {len(eur_results)}")

    total_items = len(icrc_results) + len(eur_results)

    # Create claim: person → was_prisoner_in → WW1
    claim_id = create_claim(
        subject_entity_id=entity_id,
        predicate="was_prisoner_in",
        object_value="WW1",
        claim_status="discovered",
        extraction_method="pilot_discovery",
        pipeline_run_id=pipeline_run_id,
        conflict_code="ww1",
    )
    if claim_id:
        print(f"  Claim created: id={claim_id} predicate='was_prisoner_in'")

        # Add evidence from both providers
        evidence_count = 0
        for item in icrc_results[:3]:
            ev_id = add_evidence(
                claim_id=claim_id,
                evidence_type="official_record",
                text_span=item.title[:200],
                independence_group="icrc",
            )
            if ev_id:
                evidence_count += 1

        for item in eur_results[:3]:
            ev_id = add_evidence(
                claim_id=claim_id,
                evidence_type="documentary",
                text_span=item.title[:200],
                independence_group="europeana",
            )
            if ev_id:
                evidence_count += 1

        print(f"  Evidence from 2+ independent sources: {evidence_count}")

    return {
        "pilot": "B",
        "status": "completed",
        "entity_id": entity_id,
        "items_discovered": total_items,
        "icrc_results": len(icrc_results),
        "europeana_results": len(eur_results),
        "claim_id": claim_id,
        "independent_sources": 2 if icrc_results and eur_results else 1,
        "pipeline_run_id": pipeline_run_id,
    }


def pilot_c_imi_ww2():
    """Pilot C: IMI WW2 (LeBI + Internet Archive)."""
    print("\n" + "=" * 72)
    print("PILOT C: IMI WW2 (LeBI + Internet Archive)")
    print("=" * 72)

    pipeline_run_id = f"pilot_c_imi_ww2_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}"

    test_name = "Rossi Giovanni"
    entity_id = _get_or_create_entity(test_name, "person")
    if not entity_id:
        print(f"  FAIL: Could not get/create entity for '{test_name}'")
        return {"pilot": "C", "status": "failed", "reason": "entity creation failed"}

    print(f"  Entity: id={entity_id} name='{test_name}'")

    # Discovery on LeBI
    print(f"\n  Discovery on LeBI...")
    lebi_results = run_discovery("lebi", test_name, max_results=5)
    print(f"  LeBI results: {len(lebi_results)}")

    time.sleep(2)

    # Discovery on Internet Archive
    print(f"\n  Discovery on Internet Archive...")
    ia_query = f'{test_name} internato militare italiano 1943 1945'
    ia_results = run_discovery("internetarchive", ia_query, max_results=5)
    print(f"  Internet Archive results: {len(ia_results)}")

    total_items = len(lebi_results) + len(ia_results)

    # Create claim: person → was_interned_in → WW2
    claim_id = create_claim(
        subject_entity_id=entity_id,
        predicate="was_interned_in",
        object_value="WW2",
        claim_status="discovered",
        extraction_method="pilot_discovery",
        pipeline_run_id=pipeline_run_id,
        conflict_code="ww2",
    )
    if claim_id:
        print(f"  Claim created: id={claim_id} predicate='was_interned_in'")

        evidence_count = 0
        for item in lebi_results[:3]:
            ev_id = add_evidence(
                claim_id=claim_id,
                evidence_type="official_record",
                text_span=item.title[:200],
                independence_group="anrp",
            )
            if ev_id:
                evidence_count += 1

        for item in ia_results[:3]:
            ev_id = add_evidence(
                claim_id=claim_id,
                evidence_type="documentary",
                text_span=item.title[:200],
                independence_group="internetarchive",
            )
            if ev_id:
                evidence_count += 1

        print(f"  Evidence from independent sources: {evidence_count}")

    return {
        "pilot": "C",
        "status": "completed",
        "entity_id": entity_id,
        "items_discovered": total_items,
        "lebi_results": len(lebi_results),
        "ia_results": len(ia_results),
        "claim_id": claim_id,
        "pipeline_run_id": pipeline_run_id,
    }


def pilot_d_onorificenza():
    """Pilot D: Onorificenza Quirinale/Gazzetta."""
    print("\n" + "=" * 72)
    print("PILOT D: Onorificenza Quirinale/Gazzetta")
    print("=" * 72)

    pipeline_run_id = f"pilot_d_onorificenza_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}"

    test_name = "Garibaldi Giuseppe"
    entity_id = _get_or_create_entity(test_name, "person")
    if not entity_id:
        print(f"  FAIL: Could not get/create entity for '{test_name}'")
        return {"pilot": "D", "status": "failed", "reason": "entity creation failed"}

    print(f"  Entity: id={entity_id} name='{test_name}'")

    # Discovery on Quirinale
    print(f"\n  Discovery on Quirinale...")
    quir_results = run_discovery("quirinale", test_name, max_results=5)
    print(f"  Quirinale results: {len(quir_results)}")

    time.sleep(2)

    # Discovery on Internet Archive (Gazzetta Ufficiale)
    print(f"\n  Discovery on Internet Archive (Gazzetta Ufficiale)...")
    ia_query = f'Gazzetta Ufficiale onorificenza {test_name}'
    ia_results = run_discovery("internetarchive", ia_query, max_results=5)
    print(f"  Internet Archive results: {len(ia_results)}")

    total_items = len(quir_results) + len(ia_results)

    # Create claim: person → received_honor → ...
    claim_id = create_claim(
        subject_entity_id=entity_id,
        predicate="received_honor",
        object_value="medaglia",
        claim_status="discovered",
        extraction_method="pilot_discovery",
        pipeline_run_id=pipeline_run_id,
    )
    if claim_id:
        print(f"  Claim created: id={claim_id} predicate='received_honor'")

        evidence_count = 0
        for item in quir_results[:3]:
            ev_id = add_evidence(
                claim_id=claim_id,
                evidence_type="official_record",
                text_span=item.title[:200],
                independence_group="quirinale",
            )
            if ev_id:
                evidence_count += 1

        for item in ia_results[:3]:
            ev_id = add_evidence(
                claim_id=claim_id,
                evidence_type="documentary",
                text_span=item.title[:200],
                independence_group="internetarchive",
            )
            if ev_id:
                evidence_count += 1

        print(f"  Evidence from independent sources: {evidence_count}")

    return {
        "pilot": "D",
        "status": "completed",
        "entity_id": entity_id,
        "items_discovered": total_items,
        "quirinale_results": len(quir_results),
        "ia_results": len(ia_results),
        "claim_id": claim_id,
        "pipeline_run_id": pipeline_run_id,
    }


def main():
    """Run all 4 pilots and generate report."""
    print("\n" + "#" * 72)
    print("# SOURCE PIPELINE v2 — PILOT RUNNER")
    print(f"# Started: {datetime.now(timezone.utc).isoformat()}")
    print("#" * 72)

    results = []

    # Run pilots
    results.append(pilot_a_carso())
    results.append(pilot_b_ww1_person())
    results.append(pilot_c_imi_ww2())
    results.append(pilot_d_onorificenza())

    # Summary report
    print("\n" + "#" * 72)
    print("# PILOT RESULTS SUMMARY")
    print("#" * 72)

    report = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "pilots": results,
    }

    for r in results:
        pilot = r.get("pilot", "?")
        status = r.get("status", "?")
        items = r.get("items_discovered", 0)
        claim = r.get("claim_id", None)
        print(f"  Pilot {pilot}: {status} — items={items} claim_id={claim}")

    # Save report
    report_path = Path(__file__).parent.parent / "docs" / "audit" / "PILOT_RESULTS.json"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\n  Report saved: {report_path}")

    return report


if __name__ == "__main__":
    main()

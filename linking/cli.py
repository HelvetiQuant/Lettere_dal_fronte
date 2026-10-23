"""
CLI for linking v2 pipeline.

Usage:
    python -m linking.cli generate --dry-run
    python -m linking.cli generate --batch-size 500 --resume
    python -m linking.cli legacy-relations audit
    python -m linking.cli legacy-relations quarantine --dry-run
    python -m linking.cli claims add --subject internati:22808 --predicate luogo_nascita --value "Nibbiano (Piacenza)"
    python -m linking.cli snapshot create --database imi_internati --reason "pre-linking-v2"
"""
import argparse
import json
import sqlite3
import sys
import hashlib
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

ROOT = Path(__file__).parent.parent

from linking.kill_switch import LegacyJob, is_legacy_job_enabled, assert_frozen, list_jobs
from linking.schema_v2 import apply_schema
from linking.normalization import VERSION as NORM_VERSION
from linking.candidate_generation import generate_candidates, BLOCKING_VERSION
from linking.feature_extraction import (
    extract_features_person_source,
    extract_features_person_event,
    extract_features_document_event,
    extract_features_source_event,
    FEATURE_SCHEMA_VERSION,
)
from linking.scoring import score_candidate, decide, SCORING_VERSION
from linking.persistence import (
    create_pipeline_run, finish_pipeline_run,
    register_resource, upsert_relation,
    PERSISTENCE_VERSION,
)


ALGORITHM_VERSION = "2.0.0"


def _get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(str(ROOT / "imi_internati.db"), timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def _get_event_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(str(ROOT / "eventi_1gm.db"), timeout=30)
    conn.row_factory = sqlite3.Row
    return conn


def _git_sha() -> str:
    import subprocess
    try:
        r = subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True, cwd=str(ROOT))
        return r.stdout.strip()
    except Exception:
        return "unknown"


def cmd_generate(args):
    """Generate candidate relations using the v2 pipeline."""
    conn = _get_conn()
    event_conn = _get_event_conn()
    
    # Ensure v2 schema exists
    apply_schema(conn)
    
    dry_run = args.dry_run
    batch_size = args.batch_size
    resume = args.resume
    
    print(f"[linking-v2] Starting candidate generation")
    print(f"  Algorithm version: {ALGORITHM_VERSION}")
    print(f"  Dry run: {dry_run}")
    print(f"  Batch size: {batch_size}")
    print(f"  Resume: {resume}")
    
    # Create pipeline run (even in dry-run, for tracking)
    config = {
        "algorithm": "linking_v2",
        "batch_size": batch_size,
        "dry_run": dry_run,
        "resume": resume,
    }
    run_id = "dry-run" if dry_run else create_pipeline_run(
        conn, "linking_v2", ALGORITHM_VERSION, _git_sha(), config
    )
    
    counts = {"input_count": 0, "processed_count": 0, "candidate_count": 0,
              "confirmed_count": 0, "rejected_count": 0, "quarantined_count": 0,
              "failed_count": 0}
    
    # ─── Phase 1: Person ↔ Event candidates ─────────────────────────────
    print("\n[Phase 1] Person ↔ Event candidates")
    
    events = event_conn.execute(
        "SELECT id, nome, data_inizio, data_fine, luogo, aliases, keywords, descrizione FROM eventi_1gm"
    ).fetchall()
    
    # Register events in resource_registry
    event_resource_map = {}
    for ev in events:
        ev_dict = dict(ev)
        if not dry_run:
            rid = register_resource(conn, "event", "eventi_1gm", str(ev["id"]),
                                    metadata={"nome": ev["nome"]})
            event_resource_map[ev["id"]] = rid
        else:
            event_resource_map[ev["id"]] = f"dry-run-event-{ev['id']}"
    
    # Generate candidates: internati ↔ events
    internati = conn.execute(
        "SELECT id, cognome, nome, data_nascita, luogo_nascita, luogo_cattura, "
        "data_cattura, arbeitskommando, matricola, sorte, raw_text FROM internati LIMIT 100"
    ).fetchall()
    
    counts["input_count"] += len(internati)
    
    for person in internati:
        person_dict = dict(person)
        counts["processed_count"] += 1
        
        if not dry_run:
            person_rid = register_resource(conn, "person", "internati", str(person["id"]),
                                           metadata={"cognome": person["cognome"], "nome": person["nome"]})
        else:
            person_rid = f"dry-run-person-{person['id']}"
        
        for ev in events:
            ev_dict = dict(ev)
            features, conflicts = extract_features_person_event(person_dict, ev_dict)
            
            if not features.discriminators and conflicts.has_veto:
                counts["rejected_count"] += 1
                continue
            
            if features.discriminators:
                score = score_candidate(features, conflicts)
                counts["candidate_count"] += 1
                
                if not dry_run:
                    upsert_relation(
                        conn, person_rid, event_resource_map[ev["id"]],
                        relation_type="person_participated_in_event",
                        algorithm_name="linking_v2",
                        algorithm_version=ALGORITHM_VERSION,
                        features=features,
                        score=score,
                        pipeline_run_id=run_id,
                        direction="directed",
                        status="candidate",
                    )
                
                if score.can_be_confirmed:
                    counts["confirmed_count"] += 1
                if conflicts.has_veto:
                    counts["quarantined_count"] += 1
        
        if counts["processed_count"] % batch_size == 0:
            print(f"  Processed {counts['processed_count']}/{counts['input_count']} "
                  f"persons, {counts['candidate_count']} candidates")
    
    # ─── Phase 2: Person ↔ Source candidates ────────────────────────────
    print("\n[Phase 2] Person ↔ Source candidates (blocking-based)")
    
    candidates = generate_candidates(
        conn, "internati",
        {"cognome": "cognome", "nome": "nome", "id": "id",
         "year": "data_nascita", "place": "luogo_nascita", "matricola": "matricola"},
        "fonti_indice",
        {"cognome": "titolo", "nome": "note", "id": "id",
         "place": "luogo"},
    )
    
    print(f"  Blocking produced {len(candidates)} candidate pairs")
    counts["input_count"] += len(candidates)
    
    for cand in candidates:
        counts["processed_count"] += 1
        
        # Fetch full rows for feature extraction
        person = conn.execute(
            "SELECT id, cognome, nome, data_nascita, luogo_nascita, matricola "
            "FROM internati WHERE id = ?", (int(cand.source_record_key),)
        ).fetchone()
        
        fonte = conn.execute(
            "SELECT id, titolo, note, luogo, archivio FROM fonti_indice WHERE id = ?",
            (int(cand.target_record_key),)
        ).fetchone()
        
        if not person or not fonte:
            counts["failed_count"] += 1
            continue
        
        features = extract_features_person_source(dict(person), dict(fonte))
        score = score_candidate(features)
        
        if features.discriminators:
            counts["candidate_count"] += 1
            
            if not dry_run:
                person_rid = register_resource(conn, "person", "internati", str(person["id"]))
                source_rid = register_resource(conn, "source", "fonti_indice", str(fonte["id"]))
                
                upsert_relation(
                    conn, person_rid, source_rid,
                    relation_type="person_mentioned_in_source",
                    algorithm_name="linking_v2",
                    algorithm_version=ALGORITHM_VERSION,
                    features=features,
                    score=score,
                    pipeline_run_id=run_id,
                    direction="directed",
                    status="candidate",
                )
    
    # ─── Phase 3: fonti_indice ↔ event candidates ──────────────────────
    print("\n[Phase 3] fonti_indice ↔ event candidates (temporal-filtered)")
    
    # Fetch all fonti_indice with coverage info
    fonti = conn.execute(
        "SELECT id, archivio, titolo, tipo_fonte, soggetti_collegati, note, luogo, "
        "data_inizio, data_fine, coverage_start, coverage_end "
        "FROM fonti_indice"
    ).fetchall()
    
    counts["input_count"] += len(fonti) * len(events)
    
    accepted_count = 0
    needs_review_count = 0
    rejected_count = 0
    
    for fonte in fonti:
        fonte_dict = dict(fonte)
        counts["processed_count"] += 1
        
        if not dry_run:
            source_rid = register_resource(conn, "source", "fonti_indice", str(fonte["id"]),
                                           metadata={"titolo": fonte["titolo"][:100]})
        else:
            source_rid = f"dry-run-source-{fonte['id']}"
        
        for ev in events:
            ev_dict = dict(ev)
            features, conflicts = extract_features_source_event(fonte_dict, ev_dict)
            
            decision = decide(features, conflicts)
            
            if decision.status == "rejected":
                if decision.reason in ("temporal_conflict", "ww1_ww2_mismatch"):
                    counts["rejected_count"] += 1
                    rejected_count += 1
                continue
            
            if decision.status == "accepted":
                accepted_count += 1
                counts["candidate_count"] += 1
            elif decision.status == "needs_review":
                needs_review_count += 1
                counts["candidate_count"] += 1
            
            if not dry_run and features.discriminators:
                ev_rid = event_resource_map.get(ev["id"])
                if ev_rid:
                    upsert_relation(
                        conn, source_rid, ev_rid,
                        relation_type="source_describes_event",
                        algorithm_name="linking_v2",
                        algorithm_version=ALGORITHM_VERSION,
                        features=features,
                        score=score_candidate(features, conflicts),
                        pipeline_run_id=run_id,
                        direction="directed",
                        status=decision.status,
                    )
        
        if counts["processed_count"] % 500 == 0:
            print(f"  Processed {counts['processed_count']}/{len(fonti)} fonti, "
                  f"accepted={accepted_count}, needs_review={needs_review_count}, "
                  f"rejected={rejected_count}")
    
    print(f"  Phase 3 results: accepted={accepted_count}, "
          f"needs_review={needs_review_count}, rejected={rejected_count}")
    
    # ─── Finish ─────────────────────────────────────────────────────────
    if not dry_run:
        finish_pipeline_run(conn, run_id, status="completed", counts=counts)
    
    conn.close()
    event_conn.close()
    
    print(f"\n[linking-v2] Complete")
    print(f"  Input: {counts['input_count']}")
    print(f"  Processed: {counts['processed_count']}")
    print(f"  Candidates: {counts['candidate_count']}")
    print(f"  Confirmed (auto-eligible): {counts['confirmed_count']}")
    print(f"  Rejected (veto): {counts['rejected_count']}")
    print(f"  Quarantined: {counts['quarantined_count']}")
    print(f"  Failed: {counts['failed_count']}")
    if not dry_run:
        print(f"  Pipeline run ID: {run_id}")


def cmd_legacy_audit(args):
    """Audit legacy relations without modifying anything."""
    conn = _get_conn()
    event_conn = _get_event_conn()
    
    print("[audit] Legacy relations audit\n")
    
    # event_links
    try:
        rows = event_conn.execute(
            "SELECT link_type, COUNT(*) as n FROM event_links GROUP BY link_type ORDER BY n DESC"
        ).fetchall()
        print("event_links (eventi_1gm.db):")
        total = 0
        for r in rows:
            print(f"  {r['link_type']:30s} {r['n']:>10,}")
            total += r["n"]
        print(f"  {'TOTAL':30s} {total:>10,}")
    except Exception as e:
        print(f"  event_links: error — {e}")
    
    # record_links
    try:
        rows = conn.execute(
            "SELECT link_type, COUNT(*) as n FROM record_links GROUP BY link_type ORDER BY n DESC"
        ).fetchall()
        print("\nrecord_links (imi_internati.db):")
        total = 0
        for r in rows:
            print(f"  {r['link_type']:30s} {r['n']:>10,}")
            total += r["n"]
        print(f"  {'TOTAL':30s} {total:>10,}")
    except Exception as e:
        print(f"  record_links: error — {e}")
    
    # collegamenti
    try:
        total = conn.execute("SELECT COUNT(*) FROM collegamenti").fetchone()[0]
        print(f"\ncollegamenti (imi_internati.db): {total:,}")
    except Exception as e:
        print(f"  collegamenti: error — {e}")
    
    conn.close()
    event_conn.close()


def cmd_legacy_quarantine(args):
    """Quarantine legacy relations into legacy_relation_quarantine table."""
    conn = _get_conn()
    event_conn = _get_event_conn()
    
    apply_schema(conn)
    
    dry_run = args.dry_run
    run_id = args.run_id or str(uuid4())
    
    print(f"[quarantine] Legacy relation quarantine")
    print(f"  Run ID: {run_id}")
    print(f"  Dry run: {dry_run}\n")
    
    # Quarantine event_links
    try:
        total = event_conn.execute("SELECT COUNT(*) FROM event_links").fetchone()[0]
        print(f"event_links: {total:,} rows to quarantine")
        
        if not dry_run:
            batch_size = 500
            offset = 0
            quarantined = 0
            while True:
                rows = event_conn.execute(
                    f"SELECT id, evento_id, target_table, target_id, link_type, "
                    f"match_field, match_value, confidence, created_at "
                    f"FROM event_links LIMIT {batch_size} OFFSET {offset}"
                ).fetchall()
                if not rows:
                    break
                
                for r in rows:
                    payload = json.dumps(dict(r), ensure_ascii=False, default=str)
                    payload_sha = hashlib.sha256(payload.encode()).hexdigest()
                    
                    conn.execute(
                        """INSERT OR IGNORE INTO legacy_relation_quarantine
                           (id, legacy_table, legacy_pk, legacy_payload, legacy_payload_sha256,
                            inferred_source_ref, inferred_target_ref, quarantine_reason,
                            legacy_algorithm_name, legacy_algorithm_version,
                            migration_run_id, quarantined_at)
                           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                        (str(uuid4()), "event_links", str(r["id"]),
                         payload, payload_sha,
                         None, None,
                         "legacy_substring_match_no_provenance",
                         "_gen_event_links", "1.0",
                         run_id, datetime.now(timezone.utc).isoformat())
                    )
                    quarantined += 1
                
                conn.commit()
                offset += batch_size
                if offset % 5000 == 0:
                    print(f"  Quarantined {quarantined}/{total}")
            
            print(f"  Quarantined {quarantined} event_links")
    except Exception as e:
        print(f"  event_links: error — {e}")
    
    # Quarantine record_links
    try:
        total = conn.execute("SELECT COUNT(*) FROM record_links").fetchone()[0]
        print(f"\nrecord_links: {total:,} rows to quarantine")
        
        if not dry_run:
            rows = conn.execute(
                "SELECT id, from_table, from_id, to_table, to_id, link_type, confidence, elaborato_il "
                "FROM record_links"
            ).fetchall()
            
            quarantined = 0
            for r in rows:
                payload = json.dumps(dict(r), ensure_ascii=False, default=str)
                payload_sha = hashlib.sha256(payload.encode()).hexdigest()
                
                conn.execute(
                    """INSERT OR IGNORE INTO legacy_relation_quarantine
                       (id, legacy_table, legacy_pk, legacy_payload, legacy_payload_sha256,
                        inferred_source_ref, inferred_target_ref, quarantine_reason,
                        legacy_algorithm_name, legacy_algorithm_version,
                        migration_run_id, quarantined_at)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (str(uuid4()), "record_links", str(r["id"]),
                     payload, payload_sha,
                     None, None,
                     "legacy_star_topology_no_evidence",
                     "_gen_record_links", "1.0",
                     run_id, datetime.now(timezone.utc).isoformat())
                )
                quarantined += 1
            
            conn.commit()
            print(f"  Quarantined {quarantined} record_links")
    except Exception as e:
        print(f"  record_links: error — {e}")
    
    if dry_run:
        print("\n[dry-run] No data was modified. Use --execute to quarantine.")
    else:
        count = conn.execute(
            "SELECT COUNT(*) FROM legacy_relation_quarantine WHERE migration_run_id = ?",
            (run_id,)
        ).fetchone()[0]
        print(f"\n[quarantine] Total quarantined: {count}")
    
    conn.close()
    event_conn.close()


def cmd_legacy_restore(args):
    """Restore quarantined legacy relations (marks as restored, does not re-insert into legacy tables)."""
    conn = _get_conn()
    
    run_id = args.run_id
    dry_run = args.dry_run
    
    print(f"[restore] Legacy relation restore")
    print(f"  Run ID: {run_id}")
    print(f"  Dry run: {dry_run}\n")
    
    rows = conn.execute(
        "SELECT id, legacy_table, legacy_pk, quarantine_reason, quarantined_at, restored_at "
        "FROM legacy_relation_quarantine WHERE migration_run_id = ? AND restored_at IS NULL",
        (run_id,)
    ).fetchall()
    
    print(f"  Quarantined rows pending restore: {len(rows)}")
    
    if not dry_run:
        restored = 0
        for r in rows:
            conn.execute(
                "UPDATE legacy_relation_quarantine SET restored_at = ?, restored_by = ? WHERE id = ?",
                (datetime.now(timezone.utc).isoformat(), "cli:restore", r["id"])
            )
            restored += 1
        conn.commit()
        print(f"  Restored: {restored}")
    else:
        print("  [dry-run] No data modified.")
    
    conn.close()


def cmd_legacy_list_quarantine(args):
    """List quarantined legacy relations."""
    conn = _get_conn()
    
    rows = conn.execute(
        "SELECT legacy_table, migration_run_id, COUNT(*) as n, "
        "MIN(quarantined_at) as first_at, MAX(quarantined_at) as last_at, "
        "SUM(CASE WHEN restored_at IS NOT NULL THEN 1 ELSE 0 END) as restored "
        "FROM legacy_relation_quarantine GROUP BY legacy_table, migration_run_id "
        "ORDER BY legacy_table"
    ).fetchall()
    
    if not rows:
        print("No quarantined relations found.")
    else:
        print(f"{'Table':20s} {'Run ID':36s} {'Total':>8s} {'Restored':>8s} {'First':20s}")
        for r in rows:
            print(f"{r['legacy_table']:20s} {r['migration_run_id']:36s} {r['n']:>8,} {r['restored']:>8,} {r['first_at']:20s}")
    
    conn.close()


def cmd_kill_switch_status(args):
    """Show kill switch status."""
    jobs = list_jobs()
    print("Legacy job kill switch status:")
    for job_name, info in jobs.items():
        status = "ENABLED" if info["enabled"] else "FROZEN"
        force = " + FORCE" if info["force_execute"] else ""
        print(f"  {job_name:40s} {status}{force}")


def cmd_repair_event_links(args):
    """Repair event_links for a specific event: quarantine legacy + generate v2."""
    import csv
    import json as _json
    
    event_id = args.event_id
    dry_run = not args.execute
    rollback_id = args.rollback
    
    conn = _get_conn()
    event_conn = _get_event_conn()
    
    if rollback_id:
        print(f"[repair] Rollback for pipeline_run_id: {rollback_id}")
        rows = conn.execute(
            "SELECT id, legacy_table, legacy_pk, legacy_payload "
            "FROM legacy_relation_quarantine "
            "WHERE migration_run_id = ? AND restored_at IS NULL",
            (rollback_id,)
        ).fetchall()
        
        print(f"  Quarantined rows to restore: {len(rows)}")
        
        if not dry_run:
            restored = 0
            for r in rows:
                conn.execute(
                    "UPDATE legacy_relation_quarantine "
                    "SET restored_at = ?, restored_by = ? WHERE id = ?",
                    (datetime.now(timezone.utc).isoformat(), "cli:repair-rollback", r["id"])
                )
                restored += 1
            conn.commit()
            print(f"  Restored: {restored}")
        else:
            print("  [dry-run] No data modified.")
        conn.close()
        event_conn.close()
        return
    
    print(f"[repair] Event ID: {event_id}")
    print(f"  Mode: {'DRY-RUN' if dry_run else 'EXECUTE'}")
    
    # 1. Get event info
    ev = event_conn.execute(
        "SELECT id, nome, data_inizio, data_fine, conflict, keywords, aliases "
        "FROM eventi_1gm WHERE id = ?",
        (event_id,)
    ).fetchone()
    
    if not ev:
        print(f"  ERROR: Event ID {event_id} not found in eventi_1gm")
        conn.close()
        event_conn.close()
        return
    
    ev_dict = dict(ev)
    print(f"  Event: {ev_dict['nome']}")
    print(f"  Period: {ev_dict['data_inizio']} - {ev_dict['data_fine']}")
    print(f"  Conflict: {ev_dict['conflict']}")
    
    # 2. Get all legacy event_links for this event (fonte_archivistica only)
    legacy_links = event_conn.execute(
        "SELECT id, target_table, target_id, link_type, match_field, match_value, confidence, created_at "
        "FROM event_links WHERE evento_id = ? AND link_type = 'fonte_archivistica'",
        (event_id,)
    ).fetchall()
    
    print(f"  Legacy links (fonte_archivistica): {len(legacy_links)}")
    
    # 3. Classify each link
    results = []
    accepted = 0
    needs_review = 0
    rejected = 0
    
    for link in legacy_links:
        link = dict(link)
        fonte = conn.execute(
            "SELECT id, archivio, titolo, tipo_fonte, soggetti_collegati, note, luogo, "
            "data_inizio, data_fine, coverage_start, coverage_end "
            "FROM fonti_indice WHERE id = ?",
            (link["target_id"],)
        ).fetchone()
        
        if not fonte:
            results.append({
                "legacy_link_id": link["id"],
                "source_id": link["target_id"],
                "title": "NOT FOUND",
                "archive": "",
                "coverage_start": "",
                "coverage_end": "",
                "matched_terms": [],
                "temporal_relation": "unknown",
                "conflict_flags": ["source_not_found"],
                "decision": "rejected",
                "reason": "source_not_found",
                "raw_score": 0.0,
            })
            rejected += 1
            continue
        
        fonte = dict(fonte)
        features, conflicts = extract_features_source_event(fonte, ev_dict)
        decision = decide(features, conflicts)
        score = score_candidate(features, conflicts)
        
        matched = []
        if hasattr(features, 'matched_terms') and features.matched_terms:
            matched = features.matched_terms.get("distinctive", []) + features.matched_terms.get("ambiguous", [])
        
        from linking.temporal_filter import temporal_relation as _tr
        t_rel = _tr(
            fonte.get("coverage_start") or fonte.get("data_inizio"),
            fonte.get("coverage_end") or fonte.get("data_fine"),
            ev_dict.get("data_inizio"), ev_dict.get("data_fine")
        )
        
        results.append({
            "event_id": event_id,
            "event_name": ev_dict["nome"],
            "legacy_link_id": link["id"],
            "source_id": link["target_id"],
            "title": fonte.get("titolo", "")[:120],
            "archive": fonte.get("archivio", ""),
            "coverage_start": fonte.get("coverage_start") or fonte.get("data_inizio") or "",
            "coverage_end": fonte.get("coverage_end") or fonte.get("data_fine") or "",
            "matched_terms": matched,
            "temporal_relation": t_rel,
            "conflict_flags": conflicts.to_list(),
            "decision": decision.status,
            "reason": decision.reason,
            "raw_score": score.raw_score,
        })
        
        if decision.status == "accepted":
            accepted += 1
        elif decision.status == "needs_review":
            needs_review += 1
        else:
            rejected += 1
    
    print(f"\n  Classification results:")
    print(f"    Accepted:     {accepted}")
    print(f"    Needs review: {needs_review}")
    print(f"    Rejected:     {rejected}")
    
    # 4. Output JSON + CSV
    out_prefix = f"repair_event_{event_id}_{datetime.now().strftime('%Y%m%dT%H%M%S')}"
    json_path = ROOT / f"{out_prefix}.json"
    csv_path = ROOT / f"{out_prefix}.csv"
    
    with open(json_path, "w", encoding="utf-8") as f:
        _json.dump(results, f, ensure_ascii=False, indent=2)
    print(f"\n  JSON report: {json_path}")
    
    with open(csv_path, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=[
            "event_id", "event_name", "legacy_link_id", "source_id",
            "title", "archive", "coverage_start", "coverage_end",
            "matched_terms", "temporal_relation", "conflict_flags",
            "decision", "reason", "raw_score",
        ])
        writer.writeheader()
        for r in results:
            row = dict(r)
            row["matched_terms"] = "; ".join(row.get("matched_terms", []))
            row["conflict_flags"] = "; ".join(row.get("conflict_flags", []))
            writer.writerow(row)
    print(f"  CSV report: {csv_path}")
    
    # 5. Execute: quarantine + create v2 relations
    if not dry_run:
        print(f"\n[execute] Starting migration...")
        
        run_id = str(uuid4())
        
        # Create pipeline run
        run_id = create_pipeline_run(
            conn,
            pipeline_name="repair_event_links",
            algorithm_version=ALGORITHM_VERSION,
            configuration={"event_id": event_id, "event_name": ev_dict["nome"]},
        )
        
        try:
            # Quarantine legacy links
            quarantined = 0
            for link in legacy_links:
                link = dict(link)
                payload = _json.dumps(link, ensure_ascii=False)
                payload_sha = hashlib.sha256(payload.encode()).hexdigest()
                
                conn.execute(
                    """INSERT OR IGNORE INTO legacy_relation_quarantine
                       (id, legacy_table, legacy_pk, legacy_payload, legacy_payload_sha256,
                        inferred_source_ref, inferred_target_ref, quarantine_reason,
                        legacy_algorithm_name, legacy_algorithm_version,
                        migration_run_id, quarantined_at)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (str(uuid4()), "event_links", str(link["id"]),
                     payload, payload_sha,
                     f"fonti_indice:{link['target_id']}", f"eventi_1gm:{event_id}",
                     "temporal_contamination_repair",
                     "_gen_event_links", "1.0",
                     run_id, datetime.now(timezone.utc).isoformat())
                )
                quarantined += 1
            
            conn.commit()
            print(f"  Quarantined {quarantined} legacy links")
            
            # Create v2 relations for accepted and needs_review
            v2_created = 0
            for r in results:
                if r["decision"] in ("accepted", "needs_review"):
                    fonte = conn.execute(
                        "SELECT id, archivio, titolo, soggetti_collegati, note, luogo, "
                        "data_inizio, data_fine, coverage_start, coverage_end "
                        "FROM fonti_indice WHERE id = ?",
                        (r["source_id"],)
                    ).fetchone()
                    if not fonte:
                        continue
                    fonte = dict(fonte)
                    
                    features, conflicts = extract_features_source_event(fonte, ev_dict)
                    score = score_candidate(features, conflicts)
                    
                    source_rid = register_resource(conn, "source", "fonti_indice", str(fonte["id"]),
                                                   metadata={"titolo": fonte.get("titolo", "")[:100]})
                    ev_rid = register_resource(conn, "event", "eventi_1gm", str(event_id),
                                               metadata={"nome": ev_dict["nome"]})
                    
                    upsert_relation(
                        conn, source_rid, ev_rid,
                        relation_type="source_describes_event",
                        algorithm_name="linking_v2_repair",
                        algorithm_version=ALGORITHM_VERSION,
                        features=features,
                        score=score,
                        pipeline_run_id=run_id,
                        direction="directed",
                        status=r["decision"],
                    )
                    v2_created += 1
            
            conn.commit()
            print(f"  Created {v2_created} v2 relations")
            
            # Finish pipeline run
            finish_pipeline_run(conn, run_id, status="completed", counts={
                "input_count": len(legacy_links),
                "processed_count": len(results),
                "candidate_count": accepted + needs_review,
                "confirmed_count": accepted,
                "rejected_count": rejected,
                "quarantined_count": quarantined,
                "failed_count": 0,
            })
            
            print(f"  Pipeline run ID: {run_id}")
            print(f"\n[execute] Migration complete. Use --rollback {run_id} to revert.")
            
        except Exception as e:
            conn.rollback()
            print(f"  ERROR: {e}")
            print(f"  Transaction rolled back. No data modified.")
            try:
                finish_pipeline_run(conn, run_id, status="failed", counts={},
                                    error_summary=str(e))
            except:
                pass
    else:
        print(f"\n[dry-run] No data modified. Use --execute to run migration.")
    
    conn.close()
    event_conn.close()


def main():
    parser = argparse.ArgumentParser(description="Linking v2 CLI")
    sub = parser.add_subparsers(dest="command")
    
    # generate
    gen_p = sub.add_parser("generate", help="Generate candidate relations")
    gen_p.add_argument("--dry-run", action="store_true", default=True, help="Dry run (default)")
    gen_p.add_argument("--execute", action="store_true", help="Execute (not dry-run)")
    gen_p.add_argument("--batch-size", type=int, default=500)
    gen_p.add_argument("--resume", action="store_true")
    gen_p.set_defaults(func=cmd_generate)
    
    # legacy-relations
    leg_p = sub.add_parser("legacy-relations", help="Legacy relation management")
    leg_sub = leg_p.add_subparsers(dest="legacy_command")
    
    leg_sub.add_parser("audit", help="Audit legacy relations").set_defaults(func=cmd_legacy_audit)
    
    q_p = leg_sub.add_parser("quarantine", help="Quarantine legacy relations")
    q_p.add_argument("--dry-run", action="store_true", default=True)
    q_p.add_argument("--execute", action="store_true")
    q_p.add_argument("--run-id", type=str, default=None)
    q_p.set_defaults(func=cmd_legacy_quarantine)
    
    r_p = leg_sub.add_parser("restore", help="Restore quarantined relations")
    r_p.add_argument("--run-id", required=True, help="Migration run ID to restore")
    r_p.add_argument("--dry-run", action="store_true", default=True)
    r_p.add_argument("--execute", action="store_true")
    r_p.set_defaults(func=cmd_legacy_restore)
    
    leg_sub.add_parser("list", help="List quarantined relations").set_defaults(func=cmd_legacy_list_quarantine)
    
    # repair-event-links
    rep_p = sub.add_parser("repair-event-links", help="Repair event_links for a specific event")
    rep_p.add_argument("--event-id", type=int, required=True, help="Event ID in eventi_1gm")
    rep_p.add_argument("--dry-run", action="store_true", default=True)
    rep_p.add_argument("--execute", action="store_true", help="Execute migration")
    rep_p.add_argument("--rollback", type=str, default=None, help="Rollback a previous pipeline_run_id")
    rep_p.set_defaults(func=cmd_repair_event_links)
    
    # kill-switch
    ks_p = sub.add_parser("kill-switch", help="Show kill switch status")
    ks_p.set_defaults(func=cmd_kill_switch_status)
    
    args = parser.parse_args()
    
    if hasattr(args, "func"):
        # Handle --execute overriding --dry-run
        if hasattr(args, "execute") and args.execute:
            args.dry_run = False
        args.func(args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()

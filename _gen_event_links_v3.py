"""V3 Event Linking Pipeline — Authority-first, temporal-constraint-enforced.

Replaces the legacy _gen_event_links.py which used keyword matching without
checking temporal compatibility or source authority. This version:

1. Evaluates source authority and temporal compatibility BEFORE keyword matching.
2. Sources outside the event's time period cannot become direct evidence.
3. Unofficial web sources are treated as leads only, never direct evidence.
4. All links get: status, source_authority, match_confidence,
   extraction_confidence, conflict_code, evidence_json, decision_reason,
   needs_review, rule_version.

Usage:
    python _gen_event_links_v3.py --dry-run
    python _gen_event_links_v3.py --execute
    python _gen_event_links_v3.py --re-evaluate
"""
import sys
import os
import json
import time
import sqlite3
import argparse
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from source_authority_registry import (
    SourceAuthorityRegistry,
    LinkDecisionEngine,
    LinkDecision,
    RULE_VERSION,
    TIER_NAMES,
)


DB = os.path.join(os.path.dirname(__file__), "imi_internati.db")
EDB = os.path.join(os.path.dirname(__file__), "eventi_1gm.db")


def _utc_now():
    return datetime.now(timezone.utc).isoformat()


TABLE_TO_SOURCE_KEY = {
    "internati": "internati_imi",
    "caduti_albooro": "albo_oro",
    "caduti_ministero": "ministero_difesa",
    "caduti_cwgc": "cwgc",
    "decorati_nastroazzurro": "nastro_azzurro",
    "fonti_indice": "fonti_indice",
    "archivio_documenti": "archivio_documenti",
}


def _add_event_link_v3(conn, existing_keys, event_id, target_table, target_id,
                       link_type, match_field, match_value, decision):
    """Add a V3 event link with full provenance."""
    k = (event_id, target_table, target_id, link_type)
    if k in existing_keys:
        return False

    existing_keys.add(k)
    conn.execute(
        """INSERT OR IGNORE INTO event_links
           (evento_id, target_table, target_id, link_type, match_field, match_value,
            confidence, status, source_authority, match_confidence,
            extraction_confidence, conflict_code, evidence_json,
            decision_reason, needs_review, rule_version, created_at)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (event_id, target_table, target_id, link_type, match_field, match_value,
         decision.match_confidence, decision.status, decision.source_authority,
         decision.match_confidence, decision.extraction_confidence,
         decision.conflict_code, json.dumps(decision.evidence, ensure_ascii=False),
         decision.decision_reason, int(decision.needs_review),
         decision.rule_version, _utc_now()),
    )
    return True


def _update_event_link_v3(conn, link_id, decision):
    """Update an existing event link with V3 decision metadata."""
    conn.execute(
        """UPDATE event_links SET
           confidence = ?, status = ?, source_authority = ?,
           match_confidence = ?, extraction_confidence = ?,
           conflict_code = ?, evidence_json = ?,
           decision_reason = ?, needs_review = ?,
           rule_version = ? WHERE id = ?""",
        (decision.match_confidence, decision.status, decision.source_authority,
         decision.match_confidence, decision.extraction_confidence,
         decision.conflict_code, json.dumps(decision.evidence, ensure_ascii=False),
         decision.decision_reason, int(decision.needs_review),
         decision.rule_version, link_id),
    )


def run_generate(dry_run=True):
    """Generate new event links using V3 authority-aware logic."""
    conn_ro = sqlite3.connect(DB, timeout=30)
    conn_ro.row_factory = sqlite3.Row
    conn_ro.execute("PRAGMA journal_mode=WAL")
    conn_ro.execute("PRAGMA query_only=ON")

    conn_ev = sqlite3.connect(EDB, timeout=30)
    conn_ev.row_factory = sqlite3.Row
    conn_ev.execute("PRAGMA journal_mode=WAL")

    registry = SourceAuthorityRegistry(conn_ev)
    engine = LinkDecisionEngine(registry)

    print(f"[V3 EVENT LINKS] Starting generation (dry_run={dry_run})")
    print(f"  Rule version: {RULE_VERSION}")

    # Load events
    events = conn_ev.execute(
        "SELECT id, nome, data_inizio, data_fine, luogo, aliases, keywords, descrizione FROM eventi_1gm"
    ).fetchall()
    print(f"  Events: {len(events)}")

    # Load existing link keys
    existing = set()
    try:
        for r in conn_ev.execute("SELECT evento_id, target_table, target_id, link_type FROM event_links").fetchall():
            existing.add((r["evento_id"], r["target_table"], r["target_id"], r["link_type"]))
        print(f"  Existing event_links: {len(existing)}")
    except sqlite3.OperationalError:
        print("  event_links table empty or missing")

    stats = {"added": 0, "rejected": 0, "needs_review": 0, "skipped": 0}

    # ─── PASS 1: caduti_albooro → events (luogo_morte) ───────────────────
    print("\n[PASS 1] caduti_albooro → events (luogo_morte + temporal check)")
    t0 = time.time()

    caduti = conn_ro.execute(
        "SELECT id, luogo_morte, anno_morte, grado, reparto FROM caduti_albooro LIMIT 10000"
    ).fetchall()
    print(f"  Caduti to process: {len(caduti)}")

    for c in caduti:
        c_dict = dict(c)
        c_dict["data_morte"] = c_dict.get("anno_morte", "")

        for ev in events:
            ev_dict = dict(ev)
            decision = engine.evaluate_event_link(
                ev_dict, c_dict,
                target_source_key="albo_oro",
                extraction_confidence=0.90,
            )

            if decision.status == "rejected":
                stats["rejected"] += 1
                continue

            if not dry_run:
                added = _add_event_link_v3(
                    conn_ev, existing,
                    ev["id"], "caduti_albooro", c["id"],
                    "soldato_caduto", "luogo_morte",
                    c_dict.get("luogo_morte", ""), decision,
                )
                if added:
                    stats["added"] += 1
                    if decision.needs_review:
                        stats["needs_review"] += 1
            else:
                stats["added"] += 1

    if not dry_run:
        conn_ev.commit()
    print(f"  DONE: {stats['added']} added, {stats['rejected']} rejected ({time.time()-t0:.0f}s)")

    # ─── PASS 2: archivio_documenti → events (keyword + temporal) ────────
    print("\n[PASS 2] archivio_documenti → events (keyword + temporal)")
    t0 = time.time()
    stats2 = {"added": 0, "rejected": 0, "needs_review": 0}

    docs = conn_ro.execute(
        "SELECT rowid as id, title, description, place, creator, date_text, "
        "year_start, provider, doc_type FROM archivio_documenti LIMIT 5000"
    ).fetchall()
    print(f"  Documents to process: {len(docs)}")

    for d in docs:
        d_dict = dict(d)
        d_dict["titolo"] = d_dict.get("title", "")
        d_dict["note"] = d_dict.get("description", "")

        for ev in events:
            ev_dict = dict(ev)
            decision = engine.evaluate_event_link(
                ev_dict, d_dict,
                target_source_key="archivio_documenti",
                extraction_confidence=0.80,
            )

            if decision.status == "rejected":
                stats2["rejected"] += 1
                continue

            if not dry_run:
                added = _add_event_link_v3(
                    conn_ev, existing,
                    ev["id"], "archivio_documenti", d["id"],
                    "documento", "text_match",
                    decision.evidence.get("keyword_match", {}).get("match_term", ""),
                    decision,
                )
                if added:
                    stats2["added"] += 1
                    if decision.needs_review:
                        stats2["needs_review"] += 1
            else:
                stats2["added"] += 1

    if not dry_run:
        conn_ev.commit()
    print(f"  DONE: {stats2['added']} added, {stats2['rejected']} rejected ({time.time()-t0:.0f}s)")

    # ─── PASS 3: internati → events WW2 (luogo_cattura/internamento) ─────
    print("\n[PASS 3] internati → events WW2 (luogo + temporal)")
    t0 = time.time()
    stats3 = {"added": 0, "rejected": 0, "needs_review": 0}

    internati = conn_ro.execute(
        "SELECT id, luogo_cattura, luogo_internamento, arbeitskommando, "
        "sorte, data_cattura, raw_text FROM internati LIMIT 10000"
    ).fetchall()
    print(f"  Internati to process: {len(internati)}")

    for i in internati:
        i_dict = dict(i)

        for ev in events:
            ev_dict = dict(ev)
            decision = engine.evaluate_event_link(
                ev_dict, i_dict,
                target_source_key="internati_imi",
                extraction_confidence=0.85,
            )

            if decision.status == "rejected":
                stats3["rejected"] += 1
                continue

            if not dry_run:
                added = _add_event_link_v3(
                    conn_ev, existing,
                    ev["id"], "internati", i["id"],
                    "internato_ww2", "luogo_text",
                    decision.evidence.get("keyword_match", {}).get("match_term", ""),
                    decision,
                )
                if added:
                    stats3["added"] += 1
                    if decision.needs_review:
                        stats3["needs_review"] += 1
            else:
                stats3["added"] += 1

    if not dry_run:
        conn_ev.commit()
    print(f"  DONE: {stats3['added']} added, {stats3['rejected']} rejected ({time.time()-t0:.0f}s)")

    # ─── Summary ─────────────────────────────────────────────────────────
    total = sum(s.get("added", 0) for s in [stats, stats2, stats3])
    total_rej = sum(s.get("rejected", 0) for s in [stats, stats2, stats3])

    print(f"\n{'='*60}")
    print(f"V3 EVENT LINKS SUMMARY")
    print(f"{'='*60}")
    print(f"  Total added: {total}")
    print(f"  Total rejected: {total_rej}")
    print(f"  Dry run: {dry_run}")

    if not dry_run:
        db_total = conn_ev.execute("SELECT COUNT(*) FROM event_links").fetchone()[0]
        print(f"  DB total event_links: {db_total}")

        for r in conn_ev.execute("SELECT status, COUNT(*) as n FROM event_links GROUP BY status ORDER BY n DESC").fetchall():
            print(f"    {r['status'] or 'NULL':20s} {r['n']:>8}")

    conn_ro.close()
    conn_ev.close()
    print("DONE")


def run_re_evaluate(dry_run=True):
    """Re-evaluate existing event_links with V3 logic."""
    conn_ro = sqlite3.connect(DB, timeout=30)
    conn_ro.row_factory = sqlite3.Row
    conn_ro.execute("PRAGMA query_only=ON")

    conn_ev = sqlite3.connect(EDB, timeout=30)
    conn_ev.row_factory = sqlite3.Row

    registry = SourceAuthorityRegistry(conn_ev)
    engine = LinkDecisionEngine(registry)

    print(f"[V3 EVENT LINKS RE-EVALUATE] (dry_run={dry_run})")

    links = conn_ev.execute(
        "SELECT id, evento_id, target_table, target_id, link_type, match_field, match_value, confidence "
        "FROM event_links WHERE rule_version IS NULL OR rule_version = '' OR rule_version != ?",
        (RULE_VERSION,),
    ).fetchall()
    print(f"  Links to re-evaluate: {len(links)}")

    stats = {"verified": 0, "probable": 0, "possible": 0, "unverified": 0,
             "conflicting": 0, "rejected": 0, "needs_review": 0, "skipped": 0}

    # Load events for lookup
    events_by_id = {}
    for ev in conn_ev.execute("SELECT * FROM eventi_1gm").fetchall():
        events_by_id[ev["id"]] = dict(ev)

    for link in links:
        ev_dict = events_by_id.get(link["evento_id"])
        if not ev_dict:
            stats["skipped"] += 1
            continue

        target_table = link["target_table"]
        target_id = link["target_id"]

        # Fetch target record from main DB
        try:
            target_row = conn_ro.execute(
                f"SELECT * FROM {target_table} WHERE id = ?", (target_id,)
            ).fetchone()
        except (sqlite3.OperationalError, ValueError):
            stats["skipped"] += 1
            continue

        if not target_row:
            stats["skipped"] += 1
            continue

        target_dict = dict(target_row)
        target_source_key = TABLE_TO_SOURCE_KEY.get(target_table, "")

        if not target_source_key:
            if not dry_run:
                conn_ev.execute(
                    "UPDATE event_links SET status='unverified', rule_version=? WHERE id=?",
                    (RULE_VERSION, link["id"]),
                )
            stats["unverified"] += 1
            continue

        decision = engine.evaluate_event_link(
            ev_dict, target_dict,
            target_source_key=target_source_key,
            extraction_confidence=0.85,
        )

        if not dry_run:
            _update_event_link_v3(conn_ev, link["id"], decision)

        stats[decision.status] = stats.get(decision.status, 0) + 1
        if decision.needs_review:
            stats["needs_review"] += 1

    if not dry_run:
        conn_ev.commit()

    print(f"\n{'='*60}")
    print(f"RE-EVALUATION SUMMARY")
    print(f"{'='*60}")
    for status, count in sorted(stats.items()):
        print(f"  {status:20s} {count:>8}")
    print(f"  Dry run: {dry_run}")

    conn_ro.close()
    conn_ev.close()
    print("DONE")


def main():
    parser = argparse.ArgumentParser(description="V3 Event Linking Pipeline")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--re-evaluate", action="store_true")
    args = parser.parse_args()

    if args.re_evaluate:
        run_re_evaluate(dry_run=not args.execute)
    else:
        run_generate(dry_run=not args.execute)


if __name__ == "__main__":
    main()

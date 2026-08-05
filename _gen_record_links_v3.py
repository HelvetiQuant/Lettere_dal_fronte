"""V3 Record Linking Pipeline — Authority-aware, temporal-constraint-enforced.

Replaces the legacy _gen_record_links.py which used fixed confidence 0.8
for name-only matches. This version:

1. Uses SourceAuthorityRegistry to determine source authority tiers.
2. Requires at least a second identifier (date, place, paternity, matricola,
   unit) beyond cognome+nome to create a verified link.
3. Enforces temporal constraints: a complete date from an official source
   that is incompatible with a candidate BLOCKS the link, regardless of
   name similarity.
4. Web/unofficial sources cannot overwrite canonical official data.
5. Two conflicting official sources → needs_review, both evidence preserved.
6. All links get: status, source_authority, match_confidence,
   extraction_confidence, conflict_code, evidence_json, decision_reason,
   needs_review, rule_version.

States: verified, probable, possible, unverified, conflicting, rejected.

Usage:
    python _gen_record_links_v3.py --dry-run
    python _gen_record_links_v3.py --execute
    python _gen_record_links_v3.py --re-evaluate  # re-evaluate existing links
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


def _utc_now():
    return datetime.now(timezone.utc).isoformat()


def _get_conn():
    conn = sqlite3.connect(DB, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


# ─── Provider-to-source-key mapping ──────────────────────────────────────────

TABLE_TO_SOURCE_KEY = {
    "internati": "internati_imi",
    "caduti_albooro": "albo_oro",
    "caduti_ministero": "ministero_difesa",
    "caduti_cwgc": "cwgc",
    "decorati_nastroazzurro": "nastro_azzurro",
    "fonti_indice": "fonti_indice",
    "archivio_documenti": "archivio_documenti",
}


def _get_record(conn, table, record_id):
    """Fetch a record by id from a table."""
    try:
        row = conn.execute(f"SELECT * FROM {table} WHERE id = ?", (record_id,)).fetchone()
        return dict(row) if row else None
    except sqlite3.OperationalError:
        return None


def _add_link_v3(conn, existing_keys, ft, fi, tt, ti, lt, decision, source_key, target_key):
    """Add a V3 link with full provenance metadata."""
    k = (ft, fi, tt, ti, lt)
    if k in existing_keys:
        return False

    existing_keys.add(k)
    conn.execute(
        """INSERT OR IGNORE INTO record_links
           (from_table, from_id, to_table, to_id, link_type, confidence,
            status, source_authority, match_confidence, extraction_confidence,
            conflict_code, evidence_json, decision_reason, needs_review,
            rule_version, elaborato_il)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (ft, fi, tt, ti, lt, decision.match_confidence,
         decision.status, decision.source_authority,
         decision.match_confidence, decision.extraction_confidence,
         decision.conflict_code, json.dumps(decision.evidence, ensure_ascii=False),
         decision.decision_reason, int(decision.needs_review),
         decision.rule_version, _utc_now()),
    )
    return True


def _update_link_v3(conn, link_id, decision):
    """Update an existing link with V3 decision metadata."""
    conn.execute(
        """UPDATE record_links SET
           confidence = ?, status = ?, source_authority = ?,
           match_confidence = ?, extraction_confidence = ?,
           conflict_code = ?, evidence_json = ?,
           decision_reason = ?, needs_review = ?,
           rule_version = ?, elaborato_il = ?
           WHERE id = ?""",
        (decision.match_confidence, decision.status, decision.source_authority,
         decision.match_confidence, decision.extraction_confidence,
         decision.conflict_code, json.dumps(decision.evidence, ensure_ascii=False),
         decision.decision_reason, int(decision.needs_review),
         decision.rule_version, _utc_now(), link_id),
    )


def run_generate(dry_run=True, batch_size=5000):
    """Generate new record links using V3 authority-aware logic."""
    conn = _get_conn()
    registry = SourceAuthorityRegistry(conn)
    engine = LinkDecisionEngine(registry)

    now = _utc_now()
    print(f"[V3 RECORD LINKS] Starting generation (dry_run={dry_run})")
    print(f"  Rule version: {RULE_VERSION}")

    # Load existing link keys
    existing = set()
    for r in conn.execute("SELECT from_table, from_id, to_table, to_id, link_type FROM record_links").fetchall():
        existing.add((r["from_table"], r["from_id"], r["to_table"], r["to_id"], r["link_type"]))
    print(f"  Existing links: {len(existing)}")

    stats = {"added": 0, "rejected": 0, "needs_review": 0, "skipped": 0}

    # ─── PASS 1: Cross-albo person linking (internati ↔ caduti) ──────────
    print("\n[PASS 1] Cross-albo: internati ↔ caduti_albooro")
    t0 = time.time()

    internati = conn.execute(
        "SELECT id, cognome, nome, data_nascita, luogo_nascita, matricola, "
        "reparto, grado, luogo_cattura, data_cattura FROM internati "
        "WHERE cognome IS NOT NULL AND cognome != '' LIMIT 5000"
    ).fetchall()
    print(f"  Internati to process: {len(internati)}")

    for person in internati:
        person_dict = dict(person)
        cognome = (person_dict.get("cognome") or "").strip().upper()
        nome = (person_dict.get("nome") or "").strip().upper()

        if not cognome or len(cognome) < 3:
            stats["skipped"] += 1
            continue

        # Find candidates in caduti_albooro by cognome + nome
        if nome:
            candidates = conn.execute(
                "SELECT id, nominativo, anno_morte, luogo_morte, grado, reparto "
                "FROM caduti_albooro WHERE nominativo LIKE ? LIMIT 20",
                (f"{cognome} {nome}%",),
            ).fetchall()
        else:
            candidates = []

        for cand in candidates:
            cand_dict = dict(cand)
            # Parse nominativo
            nom_parts = (cand_dict.get("nominativo") or "").split()
            cand_dict["cognome"] = nom_parts[0] if nom_parts else ""
            cand_dict["nome"] = " ".join(nom_parts[1:]) if len(nom_parts) > 1 else ""
            cand_dict["anno_nascita"] = ""  # Not in caduti_albooro

            decision = engine.evaluate_record_link(
                person_dict, cand_dict,
                source_key="internati_imi",
                target_key="albo_oro",
                extraction_confidence=0.90,
            )

            if decision.status == "rejected":
                stats["rejected"] += 1
                continue

            if not dry_run:
                added = _add_link_v3(
                    conn, existing,
                    "internati", person["id"],
                    "caduti_albooro", cand["id"],
                    "cross_albo_person", decision,
                    "internati_imi", "albo_oro",
                )
                if added:
                    stats["added"] += 1
                    if decision.needs_review:
                        stats["needs_review"] += 1
            else:
                stats["added"] += 1

        if (stats["added"] + stats["rejected"]) % batch_size == 0 and stats["added"] > 0:
            if not dry_run:
                conn.commit()
            print(f"    {stats['added']} added, {stats['rejected']} rejected ({time.time()-t0:.0f}s)")

    if not dry_run:
        conn.commit()
    print(f"  DONE: {stats['added']} added, {stats['rejected']} rejected ({time.time()-t0:.0f}s)")

    # ─── PASS 2: caduti_albooro ↔ caduti_ministero ───────────────────────
    print("\n[PASS 2] Cross-albo: caduti_albooro ↔ caduti_ministero")
    t0 = time.time()
    stats2 = {"added": 0, "rejected": 0, "needs_review": 0, "skipped": 0}

    # For each caduto_ministero, find matching caduti_albooro by name
    minist = conn.execute(
        "SELECT id, cognome, nome, data_nascita, data_decesso, "
        "comune_nascita, paternita, matricola "
        "FROM caduti_ministero WHERE cognome IS NOT NULL AND cognome != '' LIMIT 5000"
    ).fetchall()
    print(f"  Caduti ministero to process: {len(minist)}")

    for m in minist:
        m_dict = dict(m)
        cognome = (m_dict.get("cognome") or "").strip().upper()
        nome = (m_dict.get("nome") or "").strip().upper()

        if not cognome or len(cognome) < 3:
            stats2["skipped"] += 1
            continue

        # Find candidates in caduti_albooro
        if nome:
            candidates = conn.execute(
                "SELECT id, nominativo, anno_morte, luogo_morte, classe, grado, reparto "
                "FROM caduti_albooro WHERE nominativo LIKE ? LIMIT 20",
                (f"{cognome} {nome}%",),
            ).fetchall()
        else:
            candidates = []

        for cand in candidates:
            cand_dict = dict(cand)
            nom_parts = (cand_dict.get("nominativo") or "").split()
            cand_dict["cognome"] = nom_parts[0] if nom_parts else ""
            cand_dict["nome"] = " ".join(nom_parts[1:]) if len(nom_parts) > 1 else ""
            cand_dict["data_nascita"] = cand_dict.get("classe", "")  # classe = birth year
            cand_dict["data_decesso"] = cand_dict.get("anno_morte", "")

            decision = engine.evaluate_record_link(
                m_dict, cand_dict,
                source_key="ministero_difesa",
                target_key="albo_oro",
                extraction_confidence=0.90,
            )

            if decision.status == "rejected":
                stats2["rejected"] += 1
                continue

            if not dry_run:
                added = _add_link_v3(
                    conn, existing,
                    "caduti_ministero", m["id"],
                    "caduti_albooro", cand["id"],
                    "cross_albo_person", decision,
                    "ministero_difesa", "albo_oro",
                )
                if added:
                    stats2["added"] += 1
                    if decision.needs_review:
                        stats2["needs_review"] += 1
            else:
                stats2["added"] += 1

    if not dry_run:
        conn.commit()
    print(f"  DONE: {stats2['added']} added, {stats2['rejected']} rejected ({time.time()-t0:.0f}s)")

    # ─── PASS 3: Same-event soldier grouping (anno_morte + luogo_morte) ───
    print("\n[PASS 3] caduti_albooro: same-event grouping (anno+luogo)")
    t0 = time.time()
    stats3 = {"added": 0, "rejected": 0}

    groups = conn.execute("""
        SELECT anno_morte, luogo_morte, COUNT(*) as n, GROUP_CONCAT(id) as ids
        FROM caduti_albooro
        WHERE anno_morte IS NOT NULL AND anno_morte != '' AND luogo_morte IS NOT NULL AND luogo_morte != '-'
        GROUP BY anno_morte, luogo_morte
        HAVING n > 1 AND n <= 500
    """).fetchall()
    print(f"  Groups (anno+luogo): {len(groups)}")

    for g in groups:
        ids = [int(x) for x in g["ids"].split(",") if x]
        # This is a context link (same event), not a person identity link
        # Use moderate confidence since the grouping is by event, not identity
        hub = ids[0]
        for sid in ids[1:]:
            decision = LinkDecision(
                status="possible",
                match_confidence=0.0,  # Not a person match
                extraction_confidence=0.95,
                source_authority="primary",
                conflict_code="",
                decision_reason=f"Same event group (anno={g['anno_morte']}, luogo={g['luogo_morte']})",
                needs_review=False,
                evidence={"group_type": "same_event", "anno_morte": g["anno_morte"], "luogo_morte": g["luogo_morte"]},
            )
            if not dry_run:
                added = _add_link_v3(
                    conn, existing,
                    "caduti_albooro", sid, "caduti_albooro", hub,
                    "stesso_evento_luogo", decision,
                    "albo_oro", "albo_oro",
                )
                if added:
                    stats3["added"] += 1
            else:
                stats3["added"] += 1

    if not dry_run:
        conn.commit()
    print(f"  DONE: {stats3['added']} same-event links ({time.time()-t0:.0f}s)")

    # ─── Summary ─────────────────────────────────────────────────────────
    total = sum(s.get("added", 0) for s in [stats, stats2, stats3])
    total_rej = sum(s.get("rejected", 0) for s in [stats, stats2, stats3])
    total_review = sum(s.get("needs_review", 0) for s in [stats, stats2, stats3])

    print(f"\n{'='*60}")
    print(f"V3 RECORD LINKS SUMMARY")
    print(f"{'='*60}")
    print(f"  Total added: {total}")
    print(f"  Total rejected: {total_rej}")
    print(f"  Needs review: {total_review}")
    print(f"  Dry run: {dry_run}")

    if not dry_run:
        db_total = conn.execute("SELECT COUNT(*) FROM record_links").fetchone()[0]
        print(f"  DB total record_links: {db_total}")

        # Status breakdown
        for r in conn.execute("SELECT status, COUNT(*) as n FROM record_links GROUP BY status ORDER BY n DESC").fetchall():
            print(f"    {r['status'] or 'NULL':20s} {r['n']:>8}")

    conn.close()
    print("DONE")


def run_re_evaluate(dry_run=True):
    """Re-evaluate existing record_links with V3 logic.

    Links that were created with name-only matching (confidence 0.8)
    are re-evaluated. Those without a second identifier are moved to
    needs_review or rejected.
    """
    conn = _get_conn()
    registry = SourceAuthorityRegistry(conn)
    engine = LinkDecisionEngine(registry)

    print(f"[V3 RE-EVALUATE] Starting re-evaluation of existing links (dry_run={dry_run})")

    # Fetch all links that don't have V3 metadata yet (rule_version is empty or old)
    links = conn.execute(
        "SELECT id, from_table, from_id, to_table, to_id, link_type, confidence "
        "FROM record_links WHERE rule_version IS NULL OR rule_version = '' OR rule_version != ?",
        (RULE_VERSION,),
    ).fetchall()
    print(f"  Links to re-evaluate: {len(links)}")

    stats = {"verified": 0, "probable": 0, "possible": 0, "unverified": 0,
             "conflicting": 0, "rejected": 0, "needs_review": 0, "skipped": 0}

    for link in links:
        ft, fi, tt, ti = link["from_table"], link["from_id"], link["to_table"], link["to_id"]
        lt = link["link_type"]

        # Skip non-person links (same-event grouping, document links)
        if lt in ("stesso_evento_luogo", "stesso_anno_decorizione", "documento_evento", "documento_luogo"):
            # These are context links, not person identity links
            # Just update the rule_version and set appropriate status
            if not dry_run:
                conn.execute(
                    "UPDATE record_links SET status='possible', rule_version=?, "
                    "decision_reason='Context link (same event/group), not person identity' WHERE id=?",
                    (RULE_VERSION, link["id"]),
                )
            stats["possible"] += 1
            continue

        # Fetch both records
        source_record = _get_record(conn, ft, fi)
        target_record = _get_record(conn, tt, ti)

        if not source_record or not target_record:
            stats["skipped"] += 1
            continue

        source_key = TABLE_TO_SOURCE_KEY.get(ft, "")
        target_key = TABLE_TO_SOURCE_KEY.get(tt, "")

        if not source_key or not target_key:
            # Unknown table — mark as unverified
            if not dry_run:
                conn.execute(
                    "UPDATE record_links SET status='unverified', rule_version=?, "
                    "decision_reason='Unknown source table — cannot evaluate authority' WHERE id=?",
                    (RULE_VERSION, link["id"]),
                )
            stats["unverified"] += 1
            continue

        # Evaluate with V3 engine
        decision = engine.evaluate_record_link(
            source_record, target_record,
            source_key=source_key, target_key=target_key,
            extraction_confidence=0.90,
        )

        if not dry_run:
            _update_link_v3(conn, link["id"], decision)

        stats[decision.status] = stats.get(decision.status, 0) + 1
        if decision.needs_review:
            stats["needs_review"] += 1

    if not dry_run:
        conn.commit()

    print(f"\n{'='*60}")
    print(f"RE-EVALUATION SUMMARY")
    print(f"{'='*60}")
    for status, count in sorted(stats.items()):
        print(f"  {status:20s} {count:>8}")
    print(f"  Dry run: {dry_run}")

    conn.close()
    print("DONE")


def main():
    parser = argparse.ArgumentParser(description="V3 Record Linking Pipeline")
    parser.add_argument("--dry-run", action="store_true", help="Don't write to DB")
    parser.add_argument("--execute", action="store_true", help="Write to DB")
    parser.add_argument("--re-evaluate", action="store_true", help="Re-evaluate existing links")
    args = parser.parse_args()

    if args.re_evaluate:
        run_re_evaluate(dry_run=not args.execute)
    else:
        run_generate(dry_run=not args.execute)


if __name__ == "__main__":
    main()

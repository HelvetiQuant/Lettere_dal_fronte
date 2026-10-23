"""Validation Campaign — Section 3: Stratified Pilot Dataset.

Creates a stratified sample from real legacy data for adversarial testing.
Output: docs/validation/pilot_dataset.json

Stratification dimensions:
  - event_links: by link_type, confidence band, target_table, cross-war contamination
  - record_links: by from_table/to_table, confidence band
  - internati: by cross_link_audit status (active/reverted/none)

NO data modification. Read-only on original DBs.
"""
import json
import sqlite3
import random
from datetime import datetime, timezone
from pathlib import Path

CAMPAIGN_ID = "validation_20260817_v1"
RUN_ID = f"pilot_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S')}"
random.seed(42)  # reproducibility

IMI_DB = "imi_internati.db"
EVENTS_DB = "eventi_1gm.db"
OUTPUT = Path("docs/validation/pilot_dataset.json")


def confidence_band(c):
    if c is None:
        return "unknown"
    c = float(c)
    if c >= 0.9:
        return "high_0.9+"
    elif c >= 0.7:
        return "medium_0.7-0.9"
    elif c >= 0.5:
        return "low_0.5-0.7"
    elif c > 0:
        return "very_low_<0.5"
    return "zero"


def stratify_event_links(conn, target_per_stratum=500):
    """Stratified sample from event_links."""
    results = []

    # Stratum 1: by link_type
    link_types = conn.execute(
        "SELECT link_type, COUNT(*) as c FROM event_links GROUP BY link_type ORDER BY c DESC"
    ).fetchall()

    for lt in link_types:
        lt_name = lt["link_type"]
        total = lt["c"]
        n = min(target_per_stratum, total)
        rows = conn.execute(
            """SELECT * FROM event_links WHERE link_type=? ORDER BY RANDOM() LIMIT ?""",
            (lt_name, n)
        ).fetchall()
        for row in rows:
            r = dict(row)
            results.append({
                "source_db": EVENTS_DB,
                "source_table": "event_links",
                "row_id": r["id"],
                "stratum": f"link_type:{lt_name}",
                "evento_id": r["evento_id"],
                "target_table": r["target_table"],
                "target_id": r["target_id"],
                "link_type": r["link_type"],
                "match_field": r.get("match_field"),
                "match_value": r.get("match_value"),
                "confidence": r.get("confidence"),
                "confidence_band": confidence_band(r.get("confidence")),
                "usable_as_evidence": r.get("usable_as_evidence"),
                "origin": r.get("origin"),
                "war_period": r.get("war_period"),
                "semantic_role": r.get("semantic_role"),
                "cross_war_suspect": lt_name == "internato_ww2",
            })

    # Stratum 2: cross-war contamination (internato_ww2 in WWI events DB)
    ww2_links = conn.execute(
        """SELECT * FROM event_links WHERE link_type='internato_ww2' ORDER BY RANDOM() LIMIT 200"""
    ).fetchall()
    for row in ww2_links:
        r = dict(row)
        # Check if evento is WWI
        evt = conn.execute(
            "SELECT nome, data_inizio, data_fine, conflict FROM eventi_1gm WHERE id=?",
            (r["evento_id"],)
        ).fetchone()
        results.append({
            "source_db": EVENTS_DB,
            "source_table": "event_links",
            "row_id": r["id"],
            "stratum": "cross_war_contamination",
            "evento_id": r["evento_id"],
            "evento_nome": dict(evt)["nome"] if evt else None,
            "evento_data_inizio": dict(evt)["data_inizio"] if evt else None,
            "evento_data_fine": dict(evt)["data_fine"] if evt else None,
            "target_table": r["target_table"],
            "target_id": r["target_id"],
            "link_type": r["link_type"],
            "confidence": r.get("confidence"),
            "confidence_band": confidence_band(r.get("confidence")),
            "usable_as_evidence": r.get("usable_as_evidence"),
            "cross_war_suspect": True,
            "note": "WWII internment link in WWI events DB",
        })

    # Stratum 3: high-confidence legacy links (most likely to bypass gating)
    high_conf = conn.execute(
        """SELECT * FROM event_links WHERE confidence >= 0.9 AND link_type != 'internato_ww2'
           ORDER BY RANDOM() LIMIT 500"""
    ).fetchall()
    for row in high_conf:
        r = dict(row)
        results.append({
            "source_db": EVENTS_DB,
            "source_table": "event_links",
            "row_id": r["id"],
            "stratum": "high_confidence_legacy",
            "evento_id": r["evento_id"],
            "target_table": r["target_table"],
            "target_id": r["target_id"],
            "link_type": r["link_type"],
            "match_field": r.get("match_field"),
            "confidence": r.get("confidence"),
            "confidence_band": "high_0.9+",
            "usable_as_evidence": r.get("usable_as_evidence"),
            "cross_war_suspect": False,
            "note": "High-confidence legacy link — likely to bypass gating",
        })

    return results


def stratify_record_links(conn, target_per_stratum=500):
    """Stratified sample from record_links."""
    results = []

    # Stratum 1: by from_table / to_table combination
    combos = conn.execute(
        """SELECT from_table, to_table, COUNT(*) as c
           FROM record_links GROUP BY from_table, to_table ORDER BY c DESC LIMIT 20"""
    ).fetchall()

    for combo in combos:
        ft = combo["from_table"]
        tt = combo["to_table"]
        total = combo["c"]
        n = min(target_per_stratum, total)
        rows = conn.execute(
            """SELECT * FROM record_links WHERE from_table=? AND to_table=?
               ORDER BY RANDOM() LIMIT ?""",
            (ft, tt, n)
        ).fetchall()
        for row in rows:
            r = dict(row)
            results.append({
                "source_db": IMI_DB,
                "source_table": "record_links",
                "row_id": r["id"],
                "stratum": f"from_to:{ft}->{tt}",
                "from_table": r["from_table"],
                "from_id": r["from_id"],
                "to_table": r["to_table"],
                "to_id": r["to_id"],
                "link_type": r.get("link_type"),
                "match_method": r.get("match_method"),
                "confidence": r.get("confidence"),
                "confidence_band": confidence_band(r.get("confidence")),
                "usable_as_evidence": r.get("usable_as_evidence"),
                "algorithm_version": r.get("algorithm_version"),
                "origin": r.get("origin"),
                "war_period": r.get("war_period"),
            })

    # Stratum 2: by confidence band
    for band_range, band_name in [(0.9, "high"), (0.7, "medium"), (0.0, "low")]:
        rows = conn.execute(
            """SELECT * FROM record_links WHERE confidence >= ? AND confidence < ?
               ORDER BY RANDOM() LIMIT 200""",
            (band_range, band_range + 0.2)
        ).fetchall()
        for row in rows:
            r = dict(row)
            results.append({
                "source_db": IMI_DB,
                "source_table": "record_links",
                "row_id": r["id"],
                "stratum": f"confidence_band:{band_name}",
                "from_table": r["from_table"],
                "from_id": r["from_id"],
                "to_table": r["to_table"],
                "to_id": r["to_id"],
                "link_type": r.get("link_type"),
                "confidence": r.get("confidence"),
                "confidence_band": band_name,
                "usable_as_evidence": r.get("usable_as_evidence"),
                "algorithm_version": r.get("algorithm_version"),
            })

    return results


def stratify_internati_crosslink(conn, target=200):
    """Sample internati records with cross-link audit info."""
    results = []

    # Active cross-linked internati
    active = conn.execute(
        """SELECT i.id, i.cognome, i.nome, cla.column_name, cla.source_table,
                  cla.match_method, cla.match_score, cla.old_value, cla.new_value
           FROM internati i
           JOIN cross_link_audit cla ON i.id = cla.internati_id
           WHERE cla.reverted = 0 AND cla.match_method != 'PRE_CROSS_LINK_BASELINE'
           ORDER BY RANDOM() LIMIT ?""",
        (target,)
    ).fetchall()
    for row in active:
        r = dict(row)
        results.append({
            "source_db": IMI_DB,
            "source_table": "internati",
            "stratum": "crosslink_active",
            "internati_id": r["id"],
            "cognome": r["cognome"],
            "nome": r["nome"],
            "column_name": r["column_name"],
            "source_table_origin": r["source_table"],
            "match_method": r["match_method"],
            "match_score": r["match_score"],
            "old_value": r["old_value"],
            "new_value": r["new_value"],
            "reverted": False,
            "note": "Active cross-link from external source",
        })

    # Reverted cross-linked internati
    reverted = conn.execute(
        """SELECT i.id, i.cognome, i.nome, cla.column_name, cla.source_table,
                  cla.match_method, cla.match_score, cla.old_value, cla.new_value
           FROM internati i
           JOIN cross_link_audit cla ON i.id = cla.internati_id
           WHERE cla.reverted = 1 AND cla.match_method != 'PRE_CROSS_LINK_BASELINE'
           ORDER BY RANDOM() LIMIT ?""",
        (target,)
    ).fetchall()
    for row in reverted:
        r = dict(row)
        results.append({
            "source_db": IMI_DB,
            "source_table": "internati",
            "stratum": "crosslink_reverted",
            "internati_id": r["id"],
            "cognome": r["cognome"],
            "nome": r["nome"],
            "column_name": r["column_name"],
            "source_table_origin": r["source_table"],
            "match_method": r["match_method"],
            "match_score": r["match_score"],
            "old_value": r["old_value"],
            "new_value": r["new_value"],
            "reverted": True,
            "note": "Reverted cross-link — value restored to original",
        })

    # Internati with no cross-link
    no_link = conn.execute(
        """SELECT i.id, i.cognome, i.nome FROM internati i
           WHERE i.id NOT IN (SELECT DISTINCT internati_id FROM cross_link_audit)
           ORDER BY RANDOM() LIMIT ?""",
        (target,)
    ).fetchall()
    for row in no_link:
        r = dict(row)
        results.append({
            "source_db": IMI_DB,
            "source_table": "internati",
            "stratum": "no_crosslink",
            "internati_id": r["id"],
            "cognome": r["cognome"],
            "nome": r["nome"],
            "reverted": None,
            "note": "No cross-link audit record — original data only",
        })

    return results


def main():
    print(f"=== Pilot Dataset Creation ===")
    print(f"Campaign: {CAMPAIGN_ID}")
    print(f"Run ID: {RUN_ID}")
    print()

    imi = sqlite3.connect(IMI_DB)
    imi.row_factory = sqlite3.Row
    events = sqlite3.connect(EVENTS_DB)
    events.row_factory = sqlite3.Row

    all_items = []

    print("Stratifying event_links...")
    el_items = stratify_event_links(events)
    print(f"  {len(el_items)} items")
    all_items.extend(el_items)

    print("Stratifying record_links...")
    rl_items = stratify_record_links(imi)
    print(f"  {len(rl_items)} items")
    all_items.extend(rl_items)

    print("Stratifying internati cross-link...")
    cl_items = stratify_internati_crosslink(imi)
    print(f"  {len(cl_items)} items")
    all_items.extend(cl_items)

    # Summary stats
    strata = {}
    for item in all_items:
        s = item["stratum"]
        strata[s] = strata.get(s, 0) + 1

    print(f"\n=== Strata Summary ===")
    for s in sorted(strata.keys()):
        print(f"  {s}: {strata[s]}")
    print(f"\n  TOTAL: {len(all_items)}")

    # Cross-war contamination count
    cross_war = [i for i in all_items if i.get("cross_war_suspect")]
    print(f"  Cross-war suspects: {len(cross_war)}")

    # Write output
    output = {
        "campaign_id": CAMPAIGN_ID,
        "run_id": RUN_ID,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "total_items": len(all_items),
        "strata": strata,
        "cross_war_suspects": len(cross_war),
        "items": all_items,
    }

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print(f"\nWritten to {OUTPUT}")

    imi.close()
    events.close()


if __name__ == "__main__":
    main()

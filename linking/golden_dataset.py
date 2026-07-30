"""
Golden dataset schema and mandatory test cases for linking v2 calibration.

Each case is a labeled pair (positive, negative, or uncertain) that the
linking engine must handle correctly. Cases are stored in
golden_dataset_labels table and can be used for:

1. Calibration of raw_score → confidence_calibrated
2. Regression testing
3. Algorithm comparison (A/B scoring)
"""
import json
import sqlite3
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

ROOT = Path(__file__).resolve().parent.parent


MANDATORY_CASES = [
    {
        "case_id": "GOLD-001",
        "description": "Same person, same matricola, different sources — must be positive",
        "source_namespace": "internati",
        "source_record_key": "22808",
        "target_namespace": "fonti_indice",
        "target_record_key": "test_source_1",
        "relation_type": "person_mentioned_in_source",
        "label": "positive",
        "evidence": "Same matricola, same cognome+nome, same luogo_nascita",
        "reviewer": "system:golden",
    },
    {
        "case_id": "GOLD-002",
        "description": "WW1 soldier linked to WW2 event — must be negative (veto)",
        "source_namespace": "internati",
        "source_record_key": "test_ww1_soldier",
        "target_namespace": "eventi_1gm",
        "target_record_key": "test_ww2_event",
        "relation_type": "person_participated_in_event",
        "label": "negative",
        "evidence": "ww1_ww2_mismatch conflict flag",
        "reviewer": "system:golden",
    },
    {
        "case_id": "GOLD-003",
        "description": "Person born after event ended — must be negative (veto)",
        "source_namespace": "internati",
        "source_record_key": "test_born_late",
        "target_namespace": "eventi_1gm",
        "target_record_key": "1",
        "relation_type": "person_participated_in_event",
        "label": "negative",
        "evidence": "born_after_event conflict flag",
        "reviewer": "system:golden",
    },
    {
        "case_id": "GOLD-004",
        "description": "Ambiguous keyword 'campo' only match — must be negative",
        "source_namespace": "archivio_documenti",
        "source_record_key": "test_doc_campo",
        "target_namespace": "eventi_1gm",
        "target_record_key": "test_event_prigionia",
        "relation_type": "document_about_event",
        "label": "negative",
        "evidence": "Only ambiguous keyword 'campo', no discriminators",
        "reviewer": "system:golden",
    },
    {
        "case_id": "GOLD-005",
        "description": "Same cognome, different nome, no other discriminator — must be uncertain",
        "source_namespace": "internati",
        "source_record_key": "test_omonimo_1",
        "target_namespace": "fonti_indice",
        "target_record_key": "test_omonimo_2",
        "relation_type": "person_mentioned_in_source",
        "label": "uncertain",
        "evidence": "Same cognome but different nome, no date/place/matricola",
        "reviewer": "system:golden",
    },
    {
        "case_id": "GOLD-006",
        "description": "Same cognome+nome+birth_date+birth_place — must be positive",
        "source_namespace": "internati",
        "source_record_key": "test_full_match_1",
        "target_namespace": "caduti_albooro",
        "target_record_key": "test_full_match_2",
        "relation_type": "person_same_person",
        "label": "positive",
        "evidence": "4 discriminators: name, date, place, all match",
        "reviewer": "system:golden",
    },
    {
        "case_id": "GOLD-007",
        "description": "Document with event name in title + date in range — must be positive",
        "source_namespace": "archivio_documenti",
        "source_record_key": "test_doc_carso",
        "target_namespace": "eventi_1gm",
        "target_record_key": "test_event_carso",
        "relation_type": "document_about_event",
        "label": "positive",
        "evidence": "Event name in title (word boundary), year 1917 in event range",
        "reviewer": "system:golden",
    },
    {
        "case_id": "GOLD-008",
        "description": "Search page URL as source — must be negative",
        "source_namespace": "fonti_indice",
        "source_record_key": "test_search_page",
        "target_namespace": "internati",
        "target_record_key": "1",
        "relation_type": "person_mentioned_in_source",
        "label": "negative",
        "evidence": "Source URL is a search page, not a direct document",
        "reviewer": "system:golden",
    },
]


def seed_golden_dataset(conn: sqlite3.Connection, dataset_version: str = "1.0.0"):
    """Insert mandatory golden dataset cases if not already present."""
    inserted = 0
    for case in MANDATORY_CASES:
        existing = conn.execute(
            "SELECT id FROM golden_dataset_labels WHERE case_id = ?",
            (case["case_id"],)
        ).fetchone()
        
        if existing:
            continue
        
        # Register resources
        from linking.persistence import register_resource
        
        source_rid = register_resource(
            conn, "person", case["source_namespace"], case["source_record_key"]
        )
        target_rid = register_resource(
            conn, "person", case["target_namespace"], case["target_record_key"]
        )
        
        conn.execute(
            """INSERT INTO golden_dataset_labels
               (id, case_id, source_resource_id, target_resource_id,
                relation_type, label, evidence_ids, reviewer_id, reviewed_at,
                review_notes, source_family_ids, dataset_version, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (str(uuid4()), case["case_id"], source_rid, target_rid,
             case["relation_type"], case["label"], None,
             case["reviewer"], datetime.now(timezone.utc).isoformat(),
             case["evidence"], None, dataset_version,
             datetime.now(timezone.utc).isoformat())
        )
        inserted += 1
    
    conn.commit()
    return inserted


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Golden dataset management")
    sub = parser.add_subparsers(dest="command")
    
    sub.add_parser("seed", help="Seed mandatory golden cases")
    sub.add_parser("list", help="List golden cases")
    
    args = parser.parse_args()
    conn = sqlite3.connect(str(ROOT / "imi_internati.db"), timeout=30)
    conn.row_factory = sqlite3.Row
    
    from linking.schema_v2 import apply_schema
    apply_schema(conn)
    
    if args.command == "seed":
        n = seed_golden_dataset(conn)
        print(f"Seeded {n} golden dataset cases")
    elif args.command == "list":
        rows = conn.execute(
            "SELECT case_id, relation_type, label, review_notes, dataset_version "
            "FROM golden_dataset_labels ORDER BY case_id"
        ).fetchall()
        for r in rows:
            print(f"  {r['case_id']:10s} {r['relation_type']:35s} {r['label']:10s} {r['review_notes']}")
        print(f"\nTotal: {len(rows)} cases")
    else:
        parser.print_help()
    
    conn.close()


if __name__ == "__main__":
    main()

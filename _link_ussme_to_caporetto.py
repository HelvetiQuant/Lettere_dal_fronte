"""_link_ussme_to_caporetto.py — Link USSME documents to Caporetto event (event_id=16)."""
import sqlite3
from datetime import datetime, timezone

EVENT_ID = 16
DB_PATH = "eventi_1gm.db"

def main():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        # Get USSME document rowids from imi_internati.db
        conn2 = sqlite3.connect("imi_internati.db")
        conn2.row_factory = sqlite3.Row
        cursor2 = conn2.execute(
            "SELECT rowid, external_id, title, doc_type, provider "
            "FROM archivio_documenti WHERE provider LIKE 'USSME%' "
            "ORDER BY doc_type, title"
        )
        docs = cursor2.fetchall()
        print(f"Found {len(docs)} USSME documents in imi_internati.db")
        conn2.close()

        caporetto_keywords = [
            "caporetto", "isonzo", "piave", "1917", "commissione d'inchiesta",
            "ripeggamento", "grande guerra", "assalto", "arditi",
            "communication intelligence", "fondo h-4",
        ]

        now = datetime.now(timezone.utc).isoformat()
        linked = 0
        skipped = 0

        for doc in docs:
            rowid = doc["rowid"]
            title = doc["title"] or ""
            doc_type = doc["doc_type"] or ""
            title_lower = title.lower()

            matches = [kw for kw in caporetto_keywords if kw in title_lower]
            if "vol. iv" in title_lower or "vol iv" in title_lower:
                matches.append("vol_iv_1917")

            if not matches:
                continue

            existing = conn.execute(
                "SELECT 1 FROM event_links WHERE evento_id=? AND target_table=? AND target_id=?",
                (EVENT_ID, "archivio_documenti", rowid)
            ).fetchone()

            if existing:
                print(f"  SKIP (exists): [{rowid}] {title[:60]}")
                skipped += 1
                continue

            if "vol. iv" in title_lower:
                match_field, match_value, confidence = "volume", "IV (1917)", 0.95
            elif "commissione" in title_lower or "h-4" in title_lower:
                match_field, match_value, confidence = "document_type", "commissione_inchiesta", 0.95
            elif "caporetto" in title_lower:
                match_field, match_value, confidence = "keyword", "caporetto", 0.90
            elif "isonzo" in title_lower:
                match_field, match_value, confidence = "keyword", "isonzo", 0.85
            elif "piave" in title_lower:
                match_field, match_value, confidence = "keyword", "piave", 0.80
            elif "1917" in title_lower:
                match_field, match_value, confidence = "year", "1917", 0.75
            elif "grande guerra" in title_lower:
                match_field, match_value, confidence = "collection", "grande_guerra", 0.70
            elif "assalto" in title_lower:
                match_field, match_value, confidence = "topic", "reparti_assalto", 0.70
            elif "communication intelligence" in title_lower:
                match_field, match_value, confidence = "topic", "intelligence", 0.75
            else:
                match_field, match_value, confidence = "collection", "ussme", 0.60

            conn.execute(
                """INSERT INTO event_links
                   (evento_id, target_table, target_id, link_type,
                    match_field, match_value, confidence, created_at,
                    status, origin, usable_as_evidence, war_period, semantic_role,
                    quarantined_at, quarantine_reason)
                   VALUES (?, 'archivio_documenti', ?, 'metadata_match',
                           ?, ?, ?, ?,
                           'VERIFIED', 'ussme_import', 1, 'WWI', 'documentary_source',
                           '', '')""",
                (EVENT_ID, rowid, match_field, match_value, confidence, now)
            )
            linked += 1
            print(f"  LINKED [{match_field}={match_value} conf={confidence:.2f}]: [{rowid}] {title[:60]}")

        conn.commit()
        print(f"\nTotal linked: {linked}")
        print(f"Skipped (existing): {skipped}")

        # Verify
        cursor = conn.execute(
            "SELECT COUNT(*) FROM event_links WHERE evento_id=? AND target_table='archivio_documenti'",
            (EVENT_ID,)
        )
        total_el = cursor.fetchone()[0]
        print(f"Total event_links for event {EVENT_ID} with archivio_documenti: {total_el}")

    finally:
        conn.close()

if __name__ == "__main__":
    main()

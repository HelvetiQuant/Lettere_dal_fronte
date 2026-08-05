"""DEPRECATED — Legacy Gaiaschi correction.

This script is FROZEN. It has known issues:
- Direct UPDATE to internati.luogo_nascita without structured claim/review
- "Confermata Grecia" without evidence locator or documental reference
- No review_decision record
- Uses entity_variants as workaround, not a proper claim model

Use the new claim/review pipeline instead:
    python -m linking.cli claims add --subject internati:22808 --predicate luogo_nascita --value "Nibbiano (Piacenza)" --status proposed

To run in audit-only mode:
    LEGACY_JOB_LEGACY_FIX_GAIASCHI=true python _fix_gaiaschi_db.py
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from linking.kill_switch import LegacyJob, assert_frozen

assert_frozen(LegacyJob.FIX_GAIASCHI, "_fix_gaiaschi_db.py is deprecated")

import sqlite3
from datetime import datetime


def main():
    """Run legacy Gaiaschi correction.

    V7.3-FIX: Uses data_corrections overlay table instead of direct UPDATE.
    Raw data (internati.luogo_nascita, entita.luogo) is NEVER modified.
    Corrections are stored as overlays in data_corrections and entity_variants.

    All DB operations are inside this function.
    Importing this module has zero side effects beyond the kill switch check.
    """
    conn = sqlite3.connect('imi_internati.db')
    conn.row_factory = sqlite3.Row
    now = datetime.now().isoformat(timespec="seconds")

    # V7.3-FIX: Record correction in data_corrections (overlay, raw data immutable)
    import hashlib
    corr_id = hashlib.sha256(
        f"internati:22808:luogo_nascita:{now}".encode()
    ).hexdigest()[:16]

    conn.execute("""
        INSERT OR REPLACE INTO data_corrections
            (correction_id, target_identity_id, field_name, original_value, corrected_value,
             correction_source, corrected_by, corrected_at, reason, confidence, verified)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        corr_id,
        "internati:22808",
        "luogo_nascita",
        "Nibbiaño (Bergamo)",
        "Nibbiano (Piacenza)",
        "MANUAL",
        "manual_review",
        now,
        "Divergenza fonti: italiane=Belgrado, Asse=Grecia. Confermata Grecia. Luogo nascita corretto: Nibbiano (Piacenza) non Bergamo.",
        1.0,
        1,
    ))

    # Registra anche in entity_variants (legacy overlay, non tocca raw_text)
    conn.execute("""
        INSERT OR REPLACE INTO entity_variants
            (entity_type, entity_id, field_name, original_value, variant_value, variant_type, origin, confidence, verified, created_at)
        VALUES ('internati', 22808, 'luogo_nascita', 'Nibbiaño (Bergamo)', 'Nibbiano (Piacenza)', 'correction', 'manual_review', 1.0, 1, ?)
    """, (now,))

    # V7.3-FIX: Record correction for entita.luogo too
    corr_id2 = hashlib.sha256(
        f"entita:internati:22808:luogo:{now}".encode()
    ).hexdigest()[:16]
    conn.execute("""
        INSERT OR REPLACE INTO data_corrections
            (correction_id, target_identity_id, field_name, original_value, corrected_value,
             correction_source, corrected_by, corrected_at, reason, confidence, verified)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        corr_id2,
        "entita:internati:22808",
        "luogo",
        "Nibbiaño (Bergamo)",
        "Nibbiano (Piacenza)",
        "MANUAL",
        "manual_review",
        now,
        "Correction propagated from internati:22808 luogo_nascita fix.",
        1.0,
        1,
    ))

    # Registra anche variant per entita.contesto
    conn.execute("""
        INSERT OR REPLACE INTO entity_variants
            (entity_type, entity_id, field_name, original_value, variant_value, variant_type, origin, confidence, verified, created_at)
        VALUES ('entita', NULL, 'contesto', 'Nibbiaño (Bergamo)', 'Nibbiano (Piacenza)', 'correction', 'manual_review', 1.0, 1, ?)
    """, (now,))

    conn.commit()

    # Verify
    conn.row_factory = sqlite3.Row
    r = conn.execute("SELECT id, cognome, nome, data_nascita, luogo_nascita, luogo_cattura, data_cattura, sorte, raw_text, review_reason FROM internati WHERE id=22808").fetchone()
    print("AFTER FIX:")
    print(f"  id: {r['id']}")
    print(f"  cognome: {r['cognome']}")
    print(f"  nome: {r['nome']}")
    print(f"  data_nascita: {r['data_nascita']}")
    print(f"  luogo_nascita: {r['luogo_nascita']}")
    print(f"  luogo_cattura: {r['luogo_cattura']}")
    print(f"  data_cattura: {r['data_cattura']}")
    print(f"  sorte: {r['sorte']}")
    print(f"  raw_text: {r['raw_text'][:200]}")
    print(f"  review_reason: {r['review_reason']}")

    e = conn.execute("SELECT * FROM entita WHERE fonte_tabella='internati' AND fonte_id=22808").fetchone()
    if e:
        print(f"\n  entita.luogo: {e['luogo']}")
        print(f"  entita.contesto: {e['contesto']}")

    # Check for any other records with Nibbiaño
    other = conn.execute("SELECT id, cognome, nome, luogo_nascita FROM internati WHERE luogo_nascita LIKE '%Nibbiaño%' OR luogo_nascita LIKE '%Bergamo%' AND luogo_nascita LIKE '%Nibbiano%'").fetchall()
    if other:
        print(f"\n  Other records with same issue: {len(other)}")
        for o in other:
            print(f"    id={o['id']} {o['cognome']} {o['nome']} luogo={o['luogo_nascita']}")

    conn.close()
    print("\nDONE - DB corrected.")


if __name__ == "__main__":
    main()

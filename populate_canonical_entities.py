"""V7.3 — Popola canonical_entities dai record internati.

Importa tutti i record della tabella `internati` in `canonical_entities`,
normalizzando i nomi e creando entity_id stabili.

Idempotente: se l'entity esiste già (stesso source_table + source_id),
viene saltato.
"""
import sys
import os
import sqlite3
import uuid
import json
from pathlib import Path
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from text_matching_v73 import normalize_text, parse_name

DB_MAIN = Path(__file__).parent / "imi_internati.db"


def generate_entity_id(source_table: str, source_id: int) -> str:
    """Generate a stable entity_id from source table and ID."""
    return f"ent_{source_table}_{source_id}"


def populate_canonical_entities(dry_run: bool = False):
    """Populate canonical_entities from internati table."""
    conn = sqlite3.connect(str(DB_MAIN))
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    # Get all internati records
    cur.execute("SELECT * FROM internati WHERE cognome IS NOT NULL AND cognome != ''")
    rows = cur.fetchall()

    inserted = 0
    skipped = 0
    errors = 0

    for row in rows:
        r = dict(row)
        entity_id = generate_entity_id("internati", r["id"])

        # Check if already exists
        cur.execute("SELECT entity_id FROM canonical_entities WHERE entity_id = ?", (entity_id,))
        if cur.fetchone():
            skipped += 1
            continue

        # Parse name
        raw_name = f"{r.get('cognome', '')} {r.get('nome', '')}".strip()
        cognome, nome = parse_name(raw_name)
        normalized = normalize_text(raw_name)

        # Determine entity type
        entity_type = "person"

        # Build metadata
        metadata = {}
        if r.get("grado"):
            metadata["grado"] = r["grado"]
        if r.get("matricola"):
            metadata["matricola"] = r["matricola"]
        if r.get("luogo_nascita"):
            metadata["luogo_nascita"] = r["luogo_nascita"]
        if r.get("data_nascita"):
            metadata["data_nascita"] = r["data_nascita"]
        if r.get("residenza"):
            metadata["residenza"] = r["residenza"]
        if r.get("luogo_cattura"):
            metadata["luogo_cattura"] = r["luogo_cattura"]
        if r.get("data_cattura"):
            metadata["data_cattura"] = r["data_cattura"]
        if r.get("luogo_internamento"):
            metadata["luogo_internamento"] = r["luogo_internamento"]
        if r.get("arbeitskommando"):
            metadata["arbeitskommando"] = r["arbeitskommando"]
        if r.get("sorte"):
            metadata["sorte"] = r["sorte"]
        if r.get("data"):
            metadata["data_evento"] = r["data"]

        # Determine war period from data
        war_period = "UNKNOWN"
        data_str = r.get("data", "") or r.get("data_cattura", "")
        if data_str:
            try:
                year = int(data_str[:4])
                if year >= 1939:
                    war_period = "WWII"
                elif year >= 1914:
                    war_period = "WWI"
            except (ValueError, TypeError):
                pass

        if not dry_run:
            try:
                cur.execute("""
                    INSERT INTO canonical_entities (
                        entity_id, entity_type, canonical_name, normalized_name,
                        cognome, nome, data_nascita, luogo_nascita,
                        matricola, grado, war_period,
                        source_table, source_id, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    entity_id,
                    entity_type,
                    raw_name,
                    normalized,
                    cognome,
                    nome,
                    r.get("data_nascita") or "",
                    r.get("luogo_nascita") or "",
                    r.get("matricola") or "",
                    r.get("grado") or "",
                    war_period,
                    "internati",
                    r["id"],
                    datetime.now().isoformat(timespec="seconds"),
                    datetime.now().isoformat(timespec="seconds"),
                ))
                inserted += 1
            except sqlite3.IntegrityError as e:
                print(f"  SKIP (integrity): {entity_id} — {e}")
                skipped += 1
            except Exception as e:
                print(f"  ERROR: {entity_id} — {e}")
                errors += 1
        else:
            inserted += 1

    if not dry_run:
        conn.commit()

    conn.close()

    print(f"\nResults: {inserted} inserted, {skipped} skipped (already exist), {errors} errors")
    return inserted, skipped, errors


if __name__ == "__main__":
    dry = "--dry-run" in sys.argv
    print(f"Populating canonical_entities from internati (dry_run={dry})...")
    populate_canonical_entities(dry_run=dry)

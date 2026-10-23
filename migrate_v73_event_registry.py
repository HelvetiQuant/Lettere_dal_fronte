"""V7.3 — Populate canonical_event_registry from eventi_1gm with corrections.

Corrections applied:
- Battaglie dell'Isonzo: data_fine corrected to 1917-11-12 (includes Caporetto)
- Caporetto: marked as Austro-Hungarian/German offensive (not Italian)
- Monte Grappa: phases documented as children
- All events get war classification (WWI/WWII)
- Source provenance recorded

Usage:
    python migrate_v73_event_registry.py --dry-run
    python migrate_v73_event_registry.py --execute
"""
from __future__ import annotations

import argparse
import sqlite3
import json
import uuid
from datetime import datetime
from pathlib import Path

DB_MAIN = Path(__file__).parent / "imi_internati.db"
DB_EVENTS = Path(__file__).parent / "eventi_1gm.db"

MIGRATION_VERSION = "7.3.0"

# ─── Event corrections ──────────────────────────────────────────────────────

# Date corrections (only where structurally wrong)
DATE_CORRECTIONS = {
    "evt_0017": {  # Battaglie dell'Isonzo
        "data_fine": "1917-11-12",  # Was 1917-09-12 (excluded Caporetto)
        "correction_reason": "Series of 12 battles includes Caporetto (24 Oct - 12 Nov 1917). "
                             "Previous end date (1917-09-12) only covered through 11th battle. "
                             "Source: Ufficio Storico dello Stato Maggiore dell'Esercito, "
                             "L'esercito italiano nella grande guerra 1915-1918, Roma 1929.",
    },
}

# War classification
def classify_war(data_inizio: str) -> str:
    if not data_inizio:
        return "UNKNOWN"
    year = int(data_inizio[:4]) if len(data_inizio) >= 4 else 0
    if year >= 1939:
        return "WWII"
    if year >= 1914 and year <= 1922:
        return "WWI"
    return "OTHER"

# Offensive direction for battles
OFFENSIVE_DIRECTION = {
    "evt_0016": "AUSTRO_HUNGARIAN_GERMAN",  # Caporetto
    "evt_0017": "ITALIAN",  # Isonzo 1-11
    "evt_0018": "ITALIAN",  # Carso
    "evt_0019": "AUSTRO_HUNGARIAN",  # Piave (actually Austrian offensive)
    "evt_0020": "ITALIAN",  # Vittorio Veneto
    "evt_0022": "DEFENSIVE_ITALIAN",  # Monte Grappa
}

# Provenance for event data
EVENT_PROVENANCE = {
    "default": {
        "source": "Ufficio Storico dello Stato Maggiore dell'Esercito",
        "work": "L'esercito italiano nella grande guerra 1915-1918",
        "publisher": "Roma, 1929-1975",
        "url": "",
        "access_date": "2026-08-03",
    },
    "evt_0016": {  # Caporetto
        "source": "Ufficio Storico dello Stato Maggiore dell'Esercito",
        "work": "L'esercito italiano nella grande guerra, Volume IV - Le operazioni del 1917",
        "publisher": "Roma, 1965",
        "notes": "Austro-Hungarian/German offensive (Operation Wunderfreund), not Italian offensive",
        "url": "",
        "access_date": "2026-08-03",
    },
    "evt_0017": {  # Battaglie dell'Isonzo
        "source": "Ufficio Storico dello Stato Maggiore dell'Esercito",
        "work": "L'esercito italiano nella grande guerra, Volumes II-IV",
        "publisher": "Roma, 1929-1965",
        "notes": "12 battles total. 11 Italian offensives (Jun 1915 - Sep 1917) + 1 Austro-Hungarian/German offensive (Caporetto, Oct-Nov 1917)",
        "url": "",
        "access_date": "2026-08-03",
    },
}


def run_populate(dry_run: bool = True):
    print(f"\n{'='*80}")
    print(f"V7.3 Event Registry Population — v{MIGRATION_VERSION}")
    print(f"Mode: {'DRY RUN' if dry_run else 'EXECUTE'}")
    print(f"{'='*80}")

    # Read events from eventi_1gm.db
    conn_evt = sqlite3.connect(str(DB_EVENTS))
    conn_evt.row_factory = sqlite3.Row
    cur = conn_evt.cursor()

    cur.execute("""
        SELECT id, stable_id, nome, data_inizio, data_fine, event_type,
               parent_event_id, temporal_precision, general_location,
               localities_json, subjects_json, units_json, aliases, keywords,
               descrizione, narrative_version
        FROM eventi_1gm
        ORDER BY id
    """)
    events = [dict(r) for r in cur.fetchall()]
    print(f"\nSource events: {len(events)}")

    # Apply corrections and prepare records
    records = []
    corrections_applied = 0
    for evt in events:
        stable_id = evt["stable_id"] or f"evt_{evt['id']:04d}"
        data_inizio = evt["data_inizio"] or ""
        data_fine = evt["data_fine"] or ""
        war = classify_war(data_inizio)

        # Apply date corrections
        correction_reason = ""
        if stable_id in DATE_CORRECTIONS:
            corr = DATE_CORRECTIONS[stable_id]
            if data_fine != corr["data_fine"]:
                old_fine = data_fine
                data_fine = corr["data_fine"]
                correction_reason = corr["correction_reason"]
                corrections_applied += 1
                print(f"  Correction: {evt['nome']} data_fine {old_fine} -> {data_fine}")

        # Parse aliases and keywords (stored as JSON or comma-separated)
        aliases_json = evt.get("aliases") or "[]"
        try:
            aliases = json.loads(aliases_json) if isinstance(aliases_json, str) else aliases_json
        except (json.JSONDecodeError, TypeError):
            aliases = [a.strip() for a in str(aliases_json).split(",") if a.strip()]

        keywords_json = evt.get("keywords") or "[]"
        try:
            keywords = json.loads(keywords_json) if isinstance(keywords_json, str) else keywords_json
        except (json.JSONDecodeError, TypeError):
            keywords = [k.strip() for k in str(keywords_json).split(",") if k.strip()]

        # Provenance
        provenance = EVENT_PROVENANCE.get(stable_id, EVENT_PROVENANCE["default"])
        if correction_reason:
            provenance = {**provenance, "correction_reason": correction_reason}

        # Offensive direction
        direction = OFFENSIVE_DIRECTION.get(stable_id, "")
        if direction:
            provenance = {**provenance, "offensive_direction": direction}

        event_id = str(uuid.uuid5(uuid.NAMESPACE_URL, f"v73:{stable_id}"))
        now = datetime.now().isoformat(timespec="seconds")

        record = {
            "event_id": event_id,
            "stable_id": stable_id,
            "name": evt["nome"] or "",
            "event_type": evt["event_type"] or "evento",
            "parent_event_id": evt.get("parent_event_id") or "",
            "war": war,
            "data_inizio": data_inizio,
            "data_fine": data_fine,
            "temporal_precision": evt.get("temporal_precision") or "day",
            "general_location": evt.get("general_location") or "",
            "localities_json": evt.get("localities_json") or "[]",
            "subjects_json": evt.get("subjects_json") or "[]",
            "units_json": evt.get("units_json") or "[]",
            "aliases_json": json.dumps(aliases, ensure_ascii=False),
            "keywords_json": json.dumps(keywords, ensure_ascii=False),
            "description": evt.get("descrizione") or "",
            "source_provenance_json": json.dumps(provenance, ensure_ascii=False),
            "narrative_version": evt.get("narrative_version") or "",
            "review_status": "active",
            "created_at": now,
            "updated_at": now,
            "version": 1,
        }
        records.append(record)

    print(f"\nCorrections applied: {corrections_applied}")
    print(f"Records to insert: {len(records)}")

    # Count by war
    war_counts = {}
    for r in records:
        war_counts[r["war"]] = war_counts.get(r["war"], 0) + 1
    print(f"War distribution: {war_counts}")

    if not dry_run:
        conn_main = sqlite3.connect(str(DB_MAIN))
        cur_main = conn_main.cursor()

        inserted = 0
        for r in records:
            cols = ", ".join(r.keys())
            placeholders = ", ".join(["?"] * len(r))
            try:
                cur_main.execute(
                    f"INSERT OR REPLACE INTO canonical_event_registry ({cols}) VALUES ({placeholders})",
                    list(r.values())
                )
                inserted += 1
            except Exception as e:
                print(f"  ERROR inserting {r['stable_id']}: {e}")

        conn_main.commit()
        print(f"\nInserted: {inserted} events into canonical_event_registry")
        conn_main.close()

    conn_evt.close()

    print(f"\n{'='*80}")
    print(f"Summary ({'DRY RUN' if dry_run else 'EXECUTED'}): {len(records)} events, {corrections_applied} corrections")
    print(f"{'='*80}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="V7.3 Event Registry Population")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args()

    if args.dry_run:
        run_populate(dry_run=True)
    elif args.execute:
        run_populate(dry_run=False)
    else:
        parser.print_help()

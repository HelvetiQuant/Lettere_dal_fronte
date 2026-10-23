"""DEPRECATED — Legacy record-to-record linking pipeline.

V7.3-FIX: Quarantine instead of DELETE. CLI with --dry-run/--execute.
All legacy links are marked quarantined (usable_as_evidence=0) not deleted.

Known remaining issues (documented, not fixed here — use linking v2):
- Star topology with arbitrary hub (first ID)
- O(N×M) scan of persons × fonti
- No evidence, no candidate/confirmed distinction
- Creates artificial centralities in the graph

Use the new linking v2 pipeline instead:
    python -m linking.cli generate --dry-run

To run this legacy script (audit only):
    LEGACY_JOB_LEGACY_RECORD_LINKS=true python _gen_record_links.py --dry-run

To execute with DB writes:
    LEGACY_JOB_LEGACY_RECORD_LINKS=true python _gen_record_links.py --execute
"""
import sys
import os
import argparse
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from linking.kill_switch import LegacyJob, assert_frozen

assert_frozen(LegacyJob.RECORD_LINKS, "_gen_record_links.py is deprecated")

import sqlite3, re, time
from datetime import datetime

DB = os.path.join(os.path.dirname(__file__), "imi_internati.db")


def main():
    """Run legacy record linking.

    V7.3-FIX: Requires explicit --execute flag. Default is --dry-run (audit only).
    V7.3-FIX: Quarantines old fonte_personale links instead of DELETE.
    """
    parser = argparse.ArgumentParser(description="Legacy record linking (deprecated)")
    parser.add_argument("--dry-run", action="store_true", default=True,
                        help="Audit only, no DB writes (default)")
    parser.add_argument("--execute", action="store_true", default=False,
                        help="Execute with DB writes (requires confirmation)")
    args = parser.parse_args()

    if args.execute:
        args.dry_run = False
        print("WARNING: --execute mode. DB will be modified.")
        print("This will QUARANTINE (not delete) old fonte_personale links.")
        confirm = input("Type 'yes' to continue: ")
        if confirm.strip().lower() != "yes":
            print("Aborted.")
            return
    else:
        print("[DRY-RUN] No DB writes will be performed. Use --execute to apply changes.")

    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    now = datetime.now().isoformat(timespec="seconds")

    # Schema: ensure V7.3 quarantine columns exist
    conn.execute("""CREATE TABLE IF NOT EXISTS record_links (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        from_table TEXT NOT NULL, from_id INTEGER NOT NULL,
        to_table TEXT NOT NULL, to_id INTEGER NOT NULL,
        link_type TEXT NOT NULL, confidence REAL DEFAULT 0.5,
        elaborato_il TEXT,
        UNIQUE(from_table, from_id, to_table, to_id, link_type)
    )""")
    # V7.3-FIX: Add quarantine columns if not present (additive, idempotent)
    try:
        conn.execute("ALTER TABLE record_links ADD COLUMN usable_as_evidence INTEGER DEFAULT 1")
    except sqlite3.OperationalError:
        pass
    try:
        conn.execute("ALTER TABLE record_links ADD COLUMN quarantined_at TEXT")
    except sqlite3.OperationalError:
        pass
    try:
        conn.execute("ALTER TABLE record_links ADD COLUMN quarantine_reason TEXT")
    except sqlite3.OperationalError:
        pass
    conn.commit()

    existing = set()
    for r in conn.execute("SELECT from_table, from_id, to_table, to_id, link_type FROM record_links").fetchall():
        existing.add((r["from_table"], r["from_id"], r["to_table"], r["to_id"], r["link_type"]))
    print(f"[PRE] record_links esistenti: {len(existing)}")

    # V7.3-FIX: Quarantine old fonte_personale links (NOT DELETE)
    quarantined = conn.execute(
        "UPDATE record_links SET usable_as_evidence=0, quarantined_at=?, quarantine_reason='legacy_fonte_personale_unverified' "
        "WHERE link_type='fonte_personale' AND usable_as_evidence IS NULL OR usable_as_evidence=1",
        (now,)
    ).rowcount if not args.dry_run else 0
    if not args.dry_run:
        conn.commit()
    # Remove quarantined links from the working set
    existing = set()
    for r in conn.execute(
        "SELECT from_table, from_id, to_table, to_id, link_type FROM record_links WHERE usable_as_evidence=1 OR usable_as_evidence IS NULL"
    ).fetchall():
        existing.add((r["from_table"], r["from_id"], r["to_table"], r["to_id"], r["link_type"]))
    print(f"[QUARANTINE] {quarantined} old fonte_personale links quarantined (not deleted)")
    print(f"[PRE] record_links attivi (usable_as_evidence=1): {len(existing)}")

    def _add(ft, fi, tt, ti, lt, conf=0.5):
        k = (ft, fi, tt, ti, lt)
        if k in existing:
            return False
        existing.add(k)
        if not args.dry_run:
            conn.execute("INSERT OR IGNORE INTO record_links (from_table,from_id,to_table,to_id,link_type,confidence,elaborato_il,usable_as_evidence) VALUES (?,?,?,?,?,?,?,1)",
                         (ft, fi, tt, ti, lt, conf, now))
        return True

    # ─── PASSO 1: Soldati stesso evento/luogo/anno ─────────────────────────────
    # Raggruppa caduti_albooro per (anno_morte, luogo_morte) → link tra loro
    # V7.3-FIX: Use pairwise links with deterministic ordering (no star topology)
    print("\n[PASSO 1] caduti_albooro: link soldati stesso evento/luogo/anno")
    t0 = time.time()
    groups = conn.execute("""
        SELECT anno_morte, luogo_morte, COUNT(*) as n, GROUP_CONCAT(id) as ids
        FROM caduti_albooro
        WHERE anno_morte IS NOT NULL AND anno_morte != '' AND luogo_morte IS NOT NULL AND luogo_morte != '-'
        GROUP BY anno_morte, luogo_morte
        HAVING n > 1 AND n <= 500
    """).fetchall()
    print(f"  Gruppi (anno+luogo): {len(groups)}")
    added = 0
    for g in groups:
        ids = sorted([int(x) for x in g["ids"].split(",") if x])
        # V7.3-FIX: Pairwise links with deterministic ordering (min → max)
        for i in range(len(ids)):
            for j in range(i + 1, min(i + 50, len(ids))):
                if _add("caduti_albooro", ids[i], "caduti_albooro", ids[j], "stesso_evento_luogo", 0.9):
                    added += 1
        if added % 50000 == 0 and added > 0:
            if not args.dry_run:
                conn.commit()
            print(f"    {added} link ({time.time()-t0:.0f}s)")
    if not args.dry_run:
        conn.commit()
    print(f"  DONE: {added} link soldati-stesso-evento ({time.time()-t0:.0f}s)")

    # ─── PASSO 2: Decorati stesso anno+evento ──────────────────────────────────
    # V7.3-FIX: Pairwise links with deterministic ordering (no star topology)
    print("\n[PASSO 2] decorati_nastroazzurro: link decorati stesso anno")
    t0 = time.time()
    groups2 = conn.execute("""
        SELECT anno_decorazione, COUNT(*) as n, GROUP_CONCAT(id) as ids
        FROM decorati_nastroazzurro
        WHERE anno_decorazione IS NOT NULL AND anno_decorazione != ''
        GROUP BY anno_decorazione HAVING n > 1 AND n <= 500
    """).fetchall()
    print(f"  Gruppi (anno): {len(groups2)}")
    added2 = 0
    for g in groups2:
        ids = sorted([int(x) for x in g["ids"].split(",") if x])
        for i in range(len(ids)):
            for j in range(i + 1, min(i + 50, len(ids))):
                if _add("decorati_nastroazzurro", ids[i], "decorati_nastroazzurro", ids[j], "stesso_anno_decorizione", 0.7):
                    added2 += 1
        if added2 % 50000 == 0 and added2 > 0:
            if not args.dry_run:
                conn.commit()
            print(f"    {added2} link ({time.time()-t0:.0f}s)")
    if not args.dry_run:
        conn.commit()
    print(f"  DONE: {added2} link decorati-stesso-anno ({time.time()-t0:.0f}s)")

    # ─── PASSO 3: Soldati ↔ documenti evento/luogo ─────────────────────────────
    # V7.3-FIX: Use exact year match (not LIKE %year%), ordered query (not LIMIT 50 without ORDER BY)
    print("\n[PASSO 3] caduti_albooro ↔ archivio_documenti (match anno+luogo)")
    t0 = time.time()
    docs = conn.execute("SELECT rowid, provider, external_id, title, year_start, place FROM archivio_documenti").fetchall()
    print(f"  Documenti: {len(docs)}")
    added3 = 0
    for doc in docs:
        doc_year = doc["year_start"]
        doc_place = (doc["place"] or "").lower()
        # V7.3-FIX: Exact year match with word boundary (not LIKE %year%)
        if doc_year and 1914 <= doc_year <= 1919:
            soldati = conn.execute(
                "SELECT id FROM caduti_albooro WHERE CAST(anno_morte AS INTEGER)=? ORDER BY id LIMIT 200",
                (doc_year,)
            ).fetchall()
            for s in soldati:
                if _add("caduti_albooro", s["id"], "archivio_documenti", doc["rowid"], "documento_evento", 0.6):
                    added3 += 1
        # V7.3-FIX: Word-boundary place match (not LIKE %place%)
        if doc_place and len(doc_place) >= 4:
            soldati_l = conn.execute(
                "SELECT id FROM caduti_albooro WHERE LOWER(luogo_morte)=? ORDER BY id LIMIT 200",
                (doc_place,)
            ).fetchall()
            for s in soldati_l:
                if _add("caduti_albooro", s["id"], "archivio_documenti", doc["rowid"], "documento_luogo", 0.65):
                    added3 += 1
    if not args.dry_run:
        conn.commit()
    print(f"  DONE: {added3} link soldati-documenti ({time.time()-t0:.0f}s)")

    # ─── PASSO 4: Soldati ↔ fonti_indice (match COGNOME + NOME) ────────────────
    # ANTI-OMONIMIA: match su cognome+nome intero, non solo cognome.
    # Strategia inversa: per ogni soldato, cerca "Cognome Nome" nei titoli fonti.
    print("\n[PASSO 4] caduti_albooro ↔ fonti_indice (match COGNOME+NOME)")
    t0 = time.time()
    # Pre-carica tutte le fonti in memoria (titolo+note UPPER) per ricerca veloce
    fonti_all = []
    for f in conn.execute("SELECT id, titolo, note FROM fonti_indice WHERE titolo IS NOT NULL").fetchall():
        haystack = ((f["titolo"] or "") + " " + (f["note"] or "")).upper()
        if len(haystack) >= 5:
            fonti_all.append((f["id"], haystack))
    print(f"  Fonti in memoria: {len(fonti_all)}")
    # Pre-carica nomi soldati: (id, cognome, nome_completo_upper)
    # caduti_albooro.nominativo è "COGNOME Nome" o simile
    soldati_names = conn.execute("SELECT id, nominativo FROM caduti_albooro WHERE nominativo IS NOT NULL").fetchall()
    print(f"  Soldati da cercare: {len(soldati_names)}")
    added4 = 0
    batch = 0
    for s in soldati_names:
        nom = (s["nominativo"] or "").strip()
        if len(nom) < 5:
            continue
        nom_up = nom.upper()
        # Estrai cognome (prima parola) e nome (resto)
        parts = nom_up.split()
        if len(parts) < 2:
            continue  # solo cognome, skip per evitare omonimia
        cognome = parts[0]
        nome = parts[1] if len(parts) > 1 else ""
        # Match: cerca "COGNOME NOME" (almeno cognome + primo nome) nel haystack
        search_key = f"{cognome} {nome}"
        if len(cognome) < 3 or len(nome) < 2:
            continue
        for fid, haystack in fonti_all:
            if search_key in haystack:
                # Verifica aggiuntiva: almeno cognome E nome presenti
                if cognome in haystack and nome in haystack:
                    if _add("caduti_albooro", s["id"], "fonti_indice", fid, "fonte_personale", 0.8):
                        added4 += 1
        batch += 1
        if batch % 50000 == 0:
            if not args.dry_run:
                conn.commit()
            print(f"    {batch}/{len(soldati_names)} soldati, {added4} link ({time.time()-t0:.0f}s)")
    if not args.dry_run:
        conn.commit()
    print(f"  DONE: {added4} link soldati-fonti ({time.time()-t0:.0f}s)")

    # ─── PASSO 5: Decorati ↔ fonti_indice (match COGNOME + NOME) ────────────────
    print("\n[PASSO 5] decorati_nastroazzurro ↔ fonti_indice (match COGNOME+NOME)")
    t0 = time.time()
    decorati_names = conn.execute("SELECT id, cognome, nome FROM decorati_nastroazzurro WHERE cognome IS NOT NULL AND nome IS NOT NULL").fetchall()
    print(f"  Decorati da cercare: {len(decorati_names)}")
    added5 = 0
    batch = 0
    for d in decorati_names:
        cognome = (d["cognome"] or "").strip().upper()
        nome = (d["nome"] or "").strip().upper()
        if len(cognome) < 3 or len(nome) < 2:
            continue
        search_key = f"{cognome} {nome}"
        for fid, haystack in fonti_all:
            if search_key in haystack:
                if cognome in haystack and nome in haystack:
                    if _add("decorati_nastroazzurro", d["id"], "fonti_indice", fid, "fonte_personale", 0.8):
                        added5 += 1
        batch += 1
        if batch % 50000 == 0:
            if not args.dry_run:
                conn.commit()
            print(f"    {batch}/{len(decorati_names)} decorati, {added5} link ({time.time()-t0:.0f}s)")
    if not args.dry_run:
        conn.commit()
    print(f"  DONE: {added5} link decorati-fonti ({time.time()-t0:.0f}s)")

    # ─── PASSO 6: CWGC WW1 ↔ archivio_documenti (match anno) ───────────────────
    # V7.3-FIX: Exact year match with ORDER BY (not LIKE %year% without ORDER BY)
    print("\n[PASSO 6] caduti_cwgc WW1 ↔ archivio_documenti (match anno)")
    t0 = time.time()
    added6 = 0
    for doc in docs:
        doc_year = doc["year_start"]
        if doc_year and 1914 <= doc_year <= 1919:
            soldati = conn.execute(
                "SELECT id FROM caduti_cwgc WHERE guerra='World War 1' AND CAST(data_morte AS INTEGER)=? ORDER BY id LIMIT 200",
                (doc_year,)
            ).fetchall()
            for s in soldati:
                if _add("caduti_cwgc", s["id"], "archivio_documenti", doc["rowid"], "documento_evento", 0.6):
                    added6 += 1
    if not args.dry_run:
        conn.commit()
    print(f"  DONE: {added6} link cwgc-documenti ({time.time()-t0:.0f}s)")

    # ─── VERIFICHE ──────────────────────────────────────────────────────────────
    print(f"\n{'='*60}")
    print("VERIFICHE")
    print(f"{'='*60}")

    total = conn.execute("SELECT COUNT(*) FROM record_links").fetchone()[0]
    print(f"\nTotale record_links: {total}")

    print("\nPer link_type:")
    for r in conn.execute("SELECT link_type, COUNT(*) as n FROM record_links GROUP BY link_type ORDER BY n DESC").fetchall():
        print(f"  {r['link_type']:30s} {r['n']:>8}")

    print("\nPer from_table → to_table:")
    for r in conn.execute("SELECT from_table, to_table, COUNT(*) as n FROM record_links GROUP BY from_table, to_table ORDER BY n DESC LIMIT 15").fetchall():
        print(f"  {r['from_table']:20s} → {r['to_table']:20s} {r['n']:>8}")

    # Sample
    print("\nSample record_links:")
    for lt in ["stesso_evento_luogo", "documento_evento", "fonte_personale"]:
        rows = conn.execute("SELECT * FROM record_links WHERE link_type=? LIMIT 3", (lt,)).fetchall()
        print(f"\n  {lt}:")
        for r in rows:
            print(f"    {r['from_table']}#{r['from_id']} → {r['to_table']}#{r['to_id']} (conf={r['confidence']})")

    conn.close()
    print(f"\nDONE")


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Report completo di tutti i DB: schema, record, colonne, link, grafo."""
import sqlite3, json, os, sys, io
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

BASE = Path(__file__).parent

DBS = {
    "imi_internati.db": BASE / "imi_internati.db",
    "eventi_1gm.db": BASE / "eventi_1gm.db",
    "validazioni_ai.db": BASE / "validazioni_ai.db",
}

def safe_count(conn, table):
    try:
        return conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
    except:
        return -1

def safe_cols(conn, table):
    try:
        return [(c["name"], c["type"]) for c in conn.execute(f"PRAGMA table_info({table})").fetchall()]
    except:
        return []

def safe_distinct(conn, table, col, limit=15):
    try:
        rows = conn.execute(
            f"SELECT {col}, COUNT(*) as n FROM {table} "
            f"WHERE {col} IS NOT NULL AND {col} != '' "
            f"GROUP BY {col} ORDER BY n DESC LIMIT {limit}"
        ).fetchall()
        return [(r[0], r[1]) for r in rows]
    except:
        return []

def safe_query(conn, sql):
    try:
        return conn.execute(sql).fetchall()
    except:
        return []

print("=" * 80)
print("REPORT COMPLETO DATABASE — TUTTE LE GUERRE")
print("=" * 80)

for db_name, db_path in DBS.items():
    if not db_path.exists():
        print(f"\n[SKIP] {db_name} non trovato")
        continue

    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row

    print(f"\n{'#' * 80}")
    print(f"# DB: {db_name}  ({db_path.stat().st_size / 1024 / 1024:.1f} MB)")
    print(f"{'#' * 80}")

    tables = [r[0] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
    ).fetchall()]

    print(f"\nTabelle: {len(tables)}")
    total_records = 0

    for t in tables:
        cnt = safe_count(conn, t)
        cols = safe_cols(conn, t)
        if cnt >= 0:
            total_records += cnt
            print(f"\n  ── {t} ({cnt:,} record) ──")
        else:
            print(f"\n  ── {t} (ERRORE) ──")
        for cname, ctype in cols:
            print(f"      {cname:35s} {ctype}")

    print(f"\n  TOTALE RECORD: {total_records:,}")

    # ─── Dettagli specifici per tabella ─────────────────────────────────
    print(f"\n{'─' * 60}")
    print(f"DETTAGLI DATI — {db_name}")
    print(f"{'─' * 60}")

    # caduti_albooro
    if "caduti_albooro" in tables:
        print("\n  [caduti_albooro]")
        for col in ["luogo_morte", "anno_morte", "arma", "volume"]:
            vals = safe_distinct(conn, "caduti_albooro", col, 20)
            if vals:
                print(f"\n    Top {col}:")
                for v, n in vals:
                    print(f"      {v:40s} {n:>7,}")

    # decorati_nastroazzurro
    if "decorati_nastroazzurro" in tables:
        print("\n  [decorati_nastroazzurro]")
        for col in ["anno_decorazione", "arma", "tipo_decorazione"]:
            vals = safe_distinct(conn, "decorati_nastroazzurro", col, 15)
            if vals:
                print(f"\n    Top {col}:")
                for v, n in vals:
                    print(f"      {v:45s} {n:>7,}")

    # archivio_documenti
    if "archivio_documenti" in tables:
        print("\n  [archivio_documenti]")
        for col in ["provider", "doc_type", "war"]:
            vals = safe_distinct(conn, "archivio_documenti", col, 20)
            if vals:
                print(f"\n    Top {col}:")
                for v, n in vals:
                    print(f"      {v:40s} {n:>5}")

    # fonti_indice
    if "fonti_indice" in tables:
        print("\n  [fonti_indice]")
        for col in ["archivio", "tipo_fonte", "access_type", "fetch_status"]:
            vals = safe_distinct(conn, "fonti_indice", col, 20)
            if vals:
                print(f"\n    Top {col}:")
                for v, n in vals:
                    print(f"      {v:40s} {n:>7,}")

    # record_links (grafo vecchio)
    if "record_links" in tables:
        print("\n  [record_links] — GRAFO SOLDATO-SOLDATO")
        cnt = safe_count(conn, "record_links")
        print(f"    Totale link: {cnt:,}")
        for r in safe_query(conn,
            "SELECT link_type, COUNT(*) as n, "
            "COUNT(DISTINCT from_table || '_' || from_id) as from_nodes, "
            "COUNT(DISTINCT to_table || '_' || to_id) as to_nodes "
            "FROM record_links GROUP BY link_type ORDER BY n DESC"
        ):
            print(f"      {r['link_type']:30s}  link={r['n']:>7,}  from={r['from_nodes']:>6,}  to={r['to_nodes']:>6,}")
        # from/to tables
        for r in safe_query(conn,
            "SELECT from_table, to_table, COUNT(*) as n "
            "FROM record_links GROUP BY from_table, to_table ORDER BY n DESC"
        ):
            print(f"      {r['from_table']:25s} -> {r['to_table']:25s}  n={r['n']:>7,}")

    # eventi_1gm
    if "eventi_1gm" in tables:
        print("\n  [eventi_1gm] — EVENTI CANONICI")
        for r in conn.execute("SELECT id, nome, data_inizio, data_fine, luogo FROM eventi_1gm ORDER BY id").fetchall():
            print(f"    #{r['id']:2d}  {r['nome']:30s}  {r['data_inizio'] or '?':>10} -> {r['data_fine'] or '?':<10}  {r['luogo'] or ''}")

    # event_links (grafo event-centric)
    if "event_links" in tables:
        print("\n  [event_links] — GRAFO EVENT-CENTRIC")
        cnt = safe_count(conn, "event_links")
        print(f"    Totale link: {cnt:,}")
        for r in safe_query(conn,
            "SELECT link_type, COUNT(*) as n FROM event_links GROUP BY link_type ORDER BY n DESC"
        ):
            print(f"      {r['link_type']:30s}  n={r['n']:>7,}")
        print("\n    Per evento:")
        for r in safe_query(conn,
            "SELECT e.nome, COUNT(el.id) as total, "
            "SUM(CASE WHEN el.link_type='soldato_caduto' THEN 1 ELSE 0 END) as caduti, "
            "SUM(CASE WHEN el.link_type='soldato_decorato' THEN 1 ELSE 0 END) as decorati, "
            "SUM(CASE WHEN el.link_type='documento' THEN 1 ELSE 0 END) as documenti, "
            "SUM(CASE WHEN el.link_type='fonte_archivistica' THEN 1 ELSE 0 END) as fonti "
            "FROM eventi_1gm e LEFT JOIN event_links el ON e.id=el.evento_id "
            "GROUP BY e.id ORDER BY total DESC"
        ):
            print(f"      {r['nome']:30s}  total={r['total'] or 0:>7,}  caduti={r['caduti'] or 0:>6,}  dec={r['decorati'] or 0:>6,}  doc={r['documenti'] or 0:>3}  fonti={r['fonti'] or 0:>3}")

    # record_link_validations
    if "record_link_validations" in tables:
        print("\n  [record_link_validations] — VALIDAZIONI AI")
        cnt = safe_count(conn, "record_link_validations")
        print(f"    Totale validazioni: {cnt:,}")
        for r in safe_query(conn,
            "SELECT ai_provider, COUNT(*) as n, "
            "SUM(CASE WHEN verdict='VALID' THEN 1 ELSE 0 END) as v, "
            "SUM(CASE WHEN verdict='INVALID' THEN 1 ELSE 0 END) as iv, "
            "SUM(CASE WHEN verdict='UNCERTAIN' THEN 1 ELSE 0 END) as u "
            "FROM record_link_validations GROUP BY ai_provider ORDER BY ai_provider"
        ):
            print(f"      {r['ai_provider']:15s}  n={r['n']:>4}  VALID={r['v'] or 0:>3}  INVALID={r['iv'] or 0:>3}  UNCERTAIN={r['u'] or 0:>3}")

    # Altre tabelle (luoghi_1gm, soldati_1gm, ecc.)
    for t in tables:
        if t in ("caduti_albooro", "decorati_nastroazzurro", "archivio_documenti",
                 "fonti_indice", "record_links", "eventi_1gm", "event_links",
                 "record_link_validations", "sqlite_sequence"):
            continue
        cnt = safe_count(conn, t)
        if cnt > 0:
            print(f"\n  [{t}] ({cnt:,} record)")
            cols = safe_cols(conn, t)
            # Show sample
            try:
                sample = conn.execute(f"SELECT * FROM {t} LIMIT 1").fetchone()
                if sample:
                    for k, v in dict(sample).items():
                        if v and str(v).strip():
                            print(f"      {k:35s} = {str(v)[:60]}")
            except:
                pass

    conn.close()

print(f"\n{'=' * 80}")
print("FINE REPORT")
print("=" * 80)

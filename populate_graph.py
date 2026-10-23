"""Populate graph_nodes/graph_edges from legacy link tables.

Materializes the canonical graph (graph_schema.py) from:
  - entita            -> nodes  ent:{id}          (namespace 'entita')
  - collegamenti      -> edges  ent:{eid} -> rec:{table}:{rid}
  - record_links      -> edges  rec:{from} -> rec:{to}
  - eventi_1gm.event_links (db eventi_1gm.db) -> evt:{eid} -> rec:{table}:{rid}

Record nodes rec:{table}:{id} are created for every (table,id) referenced
by any edge, with a best-effort label from the source table.

Idempotent: INSERT OR IGNORE, safe to re-run.

Usage:
  python populate_graph.py            # full run
  python populate_graph.py --dry      # counts only
"""
import sqlite3, json, sys, time, hashlib
from datetime import datetime

DB = 'imi_internati.db'
EDB = 'eventi_1gm.db'
NOW = datetime.now().isoformat()
ALGO_VER = 'graph_v1_materialize_2026-10-12'

# label expression per source table
LABEL_EXPR = {
    'internati': "cognome || ' ' || COALESCE(nome,'')",
    'lebi_records': "cognome || ' ' || COALESCE(nome,'')",
    'caduti_albooro': "nominativo",
    'caduti_cwgc': "cognome || ' ' || COALESCE(nome,'')",
    'caduti_ministero': "cognome || ' ' || COALESCE(nome,'')",
    'caduti_sardi': "cognome || ' ' || COALESCE(nome,'')",
    'caduti_bologna': "nome",
    'decorati_nastroazzurro': "cognome || ' ' || COALESCE(nome,'')",
    'decorati': "cognome || ' ' || COALESCE(nome,'')",
    'menzioni': "cognome || ' ' || COALESCE(nome,'')",
    'fondi_archivistici': "titolo",
    'fonti_narrative': "titolo",
    'eventi_1gm': "nome",
    'entita': "valore",
}
NODE_TYPE = {
    'internati': 'persona', 'lebi_records': 'persona', 'caduti_albooro': 'persona',
    'caduti_cwgc': 'persona', 'caduti_ministero': 'persona', 'caduti_sardi': 'persona',
    'caduti_bologna': 'persona', 'decorati_nastroazzurro': 'persona', 'decorati': 'persona',
    'menzioni': 'persona', 'fondi_archivistici': 'fondo', 'fonti_narrative': 'documento',
    'eventi_1gm': 'evento', 'entita': 'entita',
}


def node_id_rec(table, rid):
    return f'rec:{table}:{rid}'


def batch(conn, sql, rows, size=10000):
    for i in range(0, len(rows), size):
        conn.executemany(sql, rows[i:i + size])


def main():
    dry = '--dry' in sys.argv
    t0 = time.time()
    conn = sqlite3.connect(DB)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=OFF")
    conn.execute(f"ATTACH DATABASE '{EDB}' AS ev")

    # register pipeline run
    run_id = None
    if not dry:
        cur = conn.execute("""
            INSERT INTO graph_pipeline_runs (pipeline, algorithm_version, mode, status, started_at)
            VALUES ('materialize', ?, 'execute', 'running', ?)
        """, (ALGO_VER, NOW))
        run_id = cur.lastrowid
        conn.commit()

    stats = {'nodes': 0, 'edges': 0}

    # ── 1. NODES: entita ────────────────────────────────────────────────
    print('=== 1. Nodes: entita ===')
    rows = conn.execute("""
        SELECT id, tipo, valore, cognome, nome, data, luogo, fonte_tabella, fonte_id
        FROM entita
    """).fetchall()
    if not dry:
        batch(conn, """
            INSERT OR IGNORE INTO graph_nodes
            (id, namespace, node_type, label, source_table, source_id, external_id,
             attributes_json, status, algorithm_version, first_seen_at, updated_at)
            VALUES (?, 'entita', ?, ?, 'entita', ?, NULL, ?, 'active', ?, ?, ?)
        """, [
            (f'ent:{r[0]}', r[1] or 'entita', r[2] or '', r[0],
             json.dumps({'cognome': r[3], 'nome': r[4], 'data': r[5], 'luogo': r[6],
                         'fonte_tabella': r[7], 'fonte_id': r[8]}, ensure_ascii=False),
             ALGO_VER, NOW, NOW)
            for r in rows
        ])
        conn.commit()
    stats['nodes'] += len(rows)
    print(f'  {len(rows)} nodi entita')

    # ── 2. Collect record refs from all edge sources ────────────────────
    print('=== 2. Collect record refs ===')
    recs = set()
    for table, rid in conn.execute("SELECT tabella_origine, record_id FROM collegamenti"):
        recs.add((table, rid))
    for ft, fid, tt, tid in conn.execute("SELECT from_table, from_id, to_table, to_id FROM record_links"):
        recs.add((ft, fid)); recs.add((tt, tid))
    for tt, tid in conn.execute("SELECT target_table, target_id FROM ev.event_links"):
        recs.add((tt, tid))
    print(f'  {len(recs)} record refs unici')

    # ── 3. NODES: records (labels per table, chunked) ───────────────────
    print('=== 3. Nodes: records ===')
    by_table = {}
    for t, rid in recs:
        by_table.setdefault(t, []).append(rid)

    n_written = 0
    for table, ids in sorted(by_table.items()):
        expr = LABEL_EXPR.get(table)
        label_map = {}
        if expr:
            try:
                for i in range(0, len(ids), 20000):
                    chunk = ids[i:i + 20000]
                    ph = ','.join('?' * len(chunk))
                    for rid, lab in conn.execute(
                            f"SELECT id, {expr} FROM {table} WHERE id IN ({ph})", chunk):
                        label_map[rid] = lab
            except Exception as e:
                print(f'    label {table}: ERR {e} (uso id)')
        rows = [
            (node_id_rec(table, rid), 'record', NODE_TYPE.get(table, 'record'),
             str(label_map.get(rid) or f'{table}#{rid}'), table, rid,
             '{}', 'active', ALGO_VER, NOW, NOW)
            for rid in ids
        ]
        if not dry:
            batch(conn, """
                INSERT OR IGNORE INTO graph_nodes
                (id, namespace, node_type, label, source_table, source_id, external_id,
                 attributes_json, status, algorithm_version, first_seen_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, NULL, ?, ?, ?, ?, ?)
            """, rows)
            conn.commit()
        n_written += len(rows)
    stats['nodes'] += n_written
    print(f'  {n_written} nodi record')

    # ── 4. NODES: events ────────────────────────────────────────────────
    print('=== 4. Nodes: events ===')
    ev_rows = conn.execute("SELECT id, nome FROM ev.eventi_1gm").fetchall()
    if not dry:
        batch(conn, """
            INSERT OR IGNORE INTO graph_nodes
            (id, namespace, node_type, label, source_table, source_id, external_id,
             attributes_json, status, algorithm_version, first_seen_at, updated_at)
            VALUES (?, 'evento', 'evento', ?, 'eventi_1gm', ?, NULL, '{}', 'active', ?, ?, ?)
        """, [(f'evt:{r[0]}', r[1] or '', r[0], ALGO_VER, NOW, NOW) for r in ev_rows])
        conn.commit()
    stats['nodes'] += len(ev_rows)
    print(f'  {len(ev_rows)} nodi evento')

    # ── 5. EDGES: collegamenti ──────────────────────────────────────────
    print('=== 5. Edges: collegamenti ===')
    n = 0
    cur = conn.execute("SELECT id, entita_id, tabella_origine, record_id, tipo_collegamento, confidenza FROM collegamenti")
    buf = []
    for eid, ent, tab, rid, tipo, conf in cur:
        buf.append((
            f'col:{eid}', f'ent:{ent}', node_id_rec(tab, rid),
            tipo or 'collegato_a', tipo or 'collegato_a', 'directed', 'active',
            conf if conf is not None else 1.0,
            f'Collegamento legacy entita#{ent} -> {tab}#{rid}',
            '[]', '[]', 'collegamenti_materialize', ALGO_VER,
            'collegamenti', str(eid), NOW, NOW, 1))
        n += 1
        if len(buf) >= 10000:
            if not dry:
                conn.executemany("""
                    INSERT OR IGNORE INTO graph_edges
                    (id, source_node_id, target_node_id, relation_type, relation_label,
                     direction, status, confidence, explanation, evidence_json,
                     contrary_signals_json, algorithm, algorithm_version, source_system,
                     source_edge_id, first_seen_at, last_seen_at, active)
                    VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""", buf)
                conn.commit()
            buf = []
        if n % 500000 == 0:
            print(f'    {n}...')
    if buf and not dry:
        conn.executemany("""
            INSERT OR IGNORE INTO graph_edges
            (id, source_node_id, target_node_id, relation_type, relation_label,
             direction, status, confidence, explanation, evidence_json,
             contrary_signals_json, algorithm, algorithm_version, source_system,
             source_edge_id, first_seen_at, last_seen_at, active)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""", buf)
        conn.commit()
    stats['edges'] += n
    print(f'  {n} archi collegamenti')

    # ── 6. EDGES: record_links ──────────────────────────────────────────
    print('=== 6. Edges: record_links ===')
    rows = conn.execute("""
        SELECT id, from_table, from_id, to_table, to_id, link_type, confidence,
               status, match_status, evidence_json, explanation
        FROM record_links
    """).fetchall()
    if not dry:
        batch(conn, """
            INSERT OR IGNORE INTO graph_edges
            (id, source_node_id, target_node_id, relation_type, relation_label,
             direction, status, confidence, explanation, evidence_json,
             contrary_signals_json, algorithm, algorithm_version, source_system,
             source_edge_id, first_seen_at, last_seen_at, active)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        """, [
            (f'rl:{r[0]}', node_id_rec(r[1], r[2]), node_id_rec(r[3], r[4]),
             r[5] or 'linked', r[5] or 'linked', 'undirected',
             (r[7] or r[8] or 'candidate'), r[6] if r[6] is not None else 0.5,
             r[10] or f'Record link {r[1]}#{r[2]} <-> {r[3]}#{r[4]}',
             r[9] or '[]', '[]', 'record_links_materialize', ALGO_VER,
             'record_links', str(r[0]), NOW, NOW, 1)
            for r in rows
        ])
        conn.commit()
    stats['edges'] += len(rows)
    print(f'  {len(rows)} archi record_links')

    # ── 7. EDGES: event_links (eventi_1gm.db) ───────────────────────────
    print('=== 7. Edges: event_links ===')
    n = 0
    cur = conn.execute("""
        SELECT id, evento_id, target_table, target_id, link_type, confidence, status, evidence_json
        FROM ev.event_links
    """)
    buf = []
    for eid, ev_id, tab, rid, ltype, conf, status, evj in cur:
        buf.append((
            f'el:{eid}', f'evt:{ev_id}', node_id_rec(tab, rid),
            ltype or 'linked_to_event', ltype or 'linked_to_event', 'directed',
            status or 'candidate', conf if conf is not None else 0.5,
            f'Event link evt#{ev_id} -> {tab}#{rid}',
            evj or '[]', '[]', 'event_links_materialize', ALGO_VER,
            'event_links', str(eid), NOW, NOW, 1))
        n += 1
        if len(buf) >= 10000:
            if not dry:
                conn.executemany("""
                    INSERT OR IGNORE INTO graph_edges
                    (id, source_node_id, target_node_id, relation_type, relation_label,
                     direction, status, confidence, explanation, evidence_json,
                     contrary_signals_json, algorithm, algorithm_version, source_system,
                     source_edge_id, first_seen_at, last_seen_at, active)
                    VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""", buf)
                conn.commit()
            buf = []
        if n % 500000 == 0:
            print(f'    {n}...')
    if buf and not dry:
        conn.executemany("""
            INSERT OR IGNORE INTO graph_edges
            (id, source_node_id, target_node_id, relation_type, relation_label,
             direction, status, confidence, explanation, evidence_json,
             contrary_signals_json, algorithm, algorithm_version, source_system,
             source_edge_id, first_seen_at, last_seen_at, active)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""", buf)
        conn.commit()
    stats['edges'] += n
    print(f'  {len(n and [n] or []) and n} archi event_links')

    # ── Finalize ────────────────────────────────────────────────────────
    if not dry and run_id:
        conn.execute("""
            UPDATE graph_pipeline_runs
            SET status='completed', nodes_written=?, edges_written=?, finished_at=?
            WHERE id=?
        """, (stats['nodes'], stats['edges'], datetime.now().isoformat(), run_id))
        conn.commit()
        fn = conn.execute('SELECT COUNT(*) FROM graph_nodes').fetchone()[0]
        fe = conn.execute('SELECT COUNT(*) FROM graph_edges').fetchone()[0]
        print(f'\nFINALE — graph_nodes: {fn} | graph_edges: {fe}')
    print(f'Tempo: {time.time()-t0:.0f}s')


if __name__ == '__main__':
    main()

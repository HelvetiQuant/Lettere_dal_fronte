"""Sync graph_nodes/graph_edges SQLite -> Supabase (batch upsert con checkpoint).

Usage: python sync_graph_to_supabase.py
Resume: riprende da .graph_sync_checkpoint.json
"""
import sqlite3, os, json, time, sys
import httpx
from dotenv import load_dotenv

load_dotenv()
URL = os.environ['SUPABASE_URL'].rstrip('/')
KEY = os.environ['SUPABASE_SERVICE_ROLE_KEY']
CKPT = '.graph_sync_checkpoint.json'
BATCH = 1000

HDR = {
    'apikey': KEY, 'Authorization': f'Bearer {KEY}',
    'Content-Type': 'application/json',
    'Prefer': 'resolution=merge-duplicates',
}


def load_ckpt():
    try:
        return json.load(open(CKPT))
    except Exception:
        return {}


def save_ckpt(d):
    json.dump(d, open(CKPT, 'w'))


def sync_table(client, conn, table, id_col, start):
    cols = [c[1] for c in conn.execute(f'PRAGMA table_info({table})')]
    total = conn.execute(f'SELECT COUNT(*) FROM {table}').fetchone()[0]
    print(f'=== {table}: {total} righe, resume da {start} ===')
    offset = start
    errs = 0
    while True:
        rows = conn.execute(
            f"SELECT {', '.join(cols)} FROM {table} ORDER BY rowid LIMIT ? OFFSET ?",
            (BATCH, offset)).fetchall()
        if not rows:
            break
        payload = [{k: r[k] for k in cols} for r in rows]
        for attempt in range(3):
            resp = client.post(f'{URL}/rest/v1/{table}?on_conflict={id_col}',
                               headers=HDR, json=payload)
            if resp.status_code < 300:
                break
            time.sleep(2 * (attempt + 1))
        if resp.status_code >= 300:
            errs += len(rows)
            print(f'ERR @{offset}: {resp.status_code} {resp.text[:150]}')
        offset += len(rows)
        if offset % 50000 < BATCH:
            print(f'  {offset}/{total} ({time.strftime("%H:%M:%S")})')
            save_ckpt({table: offset, 'errors': errs})
    save_ckpt({table: offset, 'errors': errs})
    print(f'{table} FATTO: {offset}/{total}, errori {errs}')
    return errs


def main():
    ck = load_ckpt()
    conn = sqlite3.connect('imi_internati.db')
    conn.row_factory = sqlite3.Row
    client = httpx.Client(timeout=120)
    errs = 0
    errs += sync_table(client, conn, 'graph_nodes', 'id', ck.get('graph_nodes', 0))
    errs += sync_table(client, conn, 'graph_edges', 'id', ck.get('graph_edges', 0))
    print(f'TOTALE ERRORI: {errs}')


if __name__ == '__main__':
    main()

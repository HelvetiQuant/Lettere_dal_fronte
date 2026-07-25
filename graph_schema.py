"""Schema additivo del grafo canonico.

La migrazione non cancella né riscrive ``collegamenti``, ``record_links``,
``event_links`` o ``external_record_links``. I servizi possono leggerli tramite
adattatori; le nuove tabelle conservano materializzazioni, revisioni e
metadati senza alterare la provenienza legacy.

Usage:
    python -m graph_schema              # deploy (additive, safe)
    python -m graph_schema --dry-run    # show what would be created
    python -m graph_schema --rollback   # drop graph tables (reversible)
"""
from __future__ import annotations

import argparse
import sys
from typing import Optional

from database import get_conn


SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS graph_nodes (
    id TEXT PRIMARY KEY,
    namespace TEXT NOT NULL,
    node_type TEXT NOT NULL,
    label TEXT NOT NULL,
    source_table TEXT NOT NULL,
    source_id INTEGER NOT NULL,
    external_id TEXT,
    attributes_json TEXT NOT NULL DEFAULT '{}',
    status TEXT NOT NULL DEFAULT 'active',
    algorithm_version TEXT NOT NULL,
    first_seen_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE(namespace, source_table, source_id)
);

CREATE TABLE IF NOT EXISTS graph_edges (
    id TEXT PRIMARY KEY,
    source_node_id TEXT NOT NULL,
    target_node_id TEXT NOT NULL,
    relation_type TEXT NOT NULL,
    relation_label TEXT NOT NULL,
    direction TEXT NOT NULL DEFAULT 'directed',
    status TEXT NOT NULL DEFAULT 'candidate',
    confidence REAL,
    explanation TEXT NOT NULL,
    evidence_json TEXT NOT NULL DEFAULT '[]',
    contrary_signals_json TEXT NOT NULL DEFAULT '[]',
    algorithm TEXT NOT NULL,
    algorithm_version TEXT NOT NULL,
    source_system TEXT NOT NULL,
    source_edge_id TEXT,
    first_seen_at TEXT NOT NULL,
    last_seen_at TEXT NOT NULL,
    active INTEGER NOT NULL DEFAULT 1,
    FOREIGN KEY (source_node_id) REFERENCES graph_nodes(id),
    FOREIGN KEY (target_node_id) REFERENCES graph_nodes(id),
    UNIQUE(source_system, source_edge_id, algorithm_version)
);

CREATE TABLE IF NOT EXISTS graph_edge_reviews (
    edge_id TEXT PRIMARY KEY,
    decision TEXT NOT NULL,
    status TEXT NOT NULL,
    note TEXT,
    reviewed_by TEXT NOT NULL,
    reviewed_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS graph_pipeline_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    pipeline TEXT NOT NULL,
    algorithm_version TEXT NOT NULL,
    mode TEXT NOT NULL,
    status TEXT NOT NULL,
    scanned INTEGER NOT NULL DEFAULT 0,
    nodes_written INTEGER NOT NULL DEFAULT 0,
    edges_written INTEGER NOT NULL DEFAULT 0,
    issues_found INTEGER NOT NULL DEFAULT 0,
    checkpoint_json TEXT,
    started_at TEXT NOT NULL,
    finished_at TEXT,
    error TEXT
);

CREATE TABLE IF NOT EXISTS graph_integrity_issues (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id INTEGER,
    issue_key TEXT NOT NULL UNIQUE,
    code TEXT NOT NULL,
    severity TEXT NOT NULL,
    source_system TEXT,
    source_edge_id TEXT,
    message TEXT NOT NULL,
    details_json TEXT,
    status TEXT NOT NULL DEFAULT 'open',
    created_at TEXT NOT NULL,
    resolved_at TEXT,
    FOREIGN KEY (run_id) REFERENCES graph_pipeline_runs(id)
);

CREATE TABLE IF NOT EXISTS archival_metadata (
    stable_id TEXT PRIMARY KEY,
    source_table TEXT NOT NULL,
    source_id INTEGER NOT NULL,
    metadata_standard TEXT NOT NULL,
    title TEXT NOT NULL,
    metadata_json TEXT NOT NULL,
    checksum TEXT,
    status TEXT NOT NULL DEFAULT 'generated',
    algorithm_version TEXT NOT NULL,
    generated_at TEXT NOT NULL,
    reviewed_by TEXT,
    reviewed_at TEXT,
    UNIQUE(source_table, source_id, metadata_standard)
);

CREATE INDEX IF NOT EXISTS idx_graph_nodes_label ON graph_nodes(label);
CREATE INDEX IF NOT EXISTS idx_graph_nodes_type ON graph_nodes(node_type);
CREATE INDEX IF NOT EXISTS idx_graph_nodes_source
    ON graph_nodes(namespace, source_table, source_id);
CREATE INDEX IF NOT EXISTS idx_graph_edges_source
    ON graph_edges(source_node_id, active);
CREATE INDEX IF NOT EXISTS idx_graph_edges_target
    ON graph_edges(target_node_id, active);
CREATE INDEX IF NOT EXISTS idx_graph_edges_status
    ON graph_edges(status, active);
CREATE INDEX IF NOT EXISTS idx_graph_edges_origin
    ON graph_edges(source_system, source_edge_id);
CREATE INDEX IF NOT EXISTS idx_graph_issues_status
    ON graph_integrity_issues(status, severity);
CREATE INDEX IF NOT EXISTS idx_archival_metadata_source
    ON archival_metadata(source_table, source_id);
"""

ROLLBACK_SQL = """
DROP TABLE IF EXISTS archival_metadata;
DROP TABLE IF EXISTS graph_integrity_issues;
DROP TABLE IF EXISTS graph_pipeline_runs;
DROP TABLE IF EXISTS graph_edge_reviews;
DROP TABLE IF EXISTS graph_edges;
DROP TABLE IF EXISTS graph_nodes;
"""


def init_graph_schema(conn=None) -> None:
    own_connection = conn is None
    conn = conn or get_conn()
    try:
        conn.executescript(SCHEMA_SQL)
        conn.commit()
    finally:
        if own_connection:
            conn.close()


def graph_schema_available(conn) -> bool:
    row = conn.execute(
        "SELECT COUNT(*) AS n FROM sqlite_master "
        "WHERE type='table' AND name IN "
        "('graph_nodes','graph_edges','graph_edge_reviews','archival_metadata')"
    ).fetchone()
    return bool(row and row["n"] == 4)


def rollback_graph_schema(conn=None) -> None:
    own_connection = conn is None
    conn = conn or get_conn()
    try:
        conn.executescript(ROLLBACK_SQL)
        conn.commit()
    finally:
        if own_connection:
            conn.close()


def main():
    parser = argparse.ArgumentParser(description="Graph schema migration")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be created")
    parser.add_argument("--rollback", action="store_true", help="Drop graph tables (reversible)")
    args = parser.parse_args()

    if args.dry_run:
        existing = []
        conn = get_conn()
        for table in ["graph_nodes", "graph_edges", "graph_edge_reviews",
                       "graph_pipeline_runs", "graph_integrity_issues", "archival_metadata"]:
            row = conn.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)
            ).fetchone()
            if row:
                existing.append(table)
        conn.close()
        if existing:
            print(f"Already exists: {', '.join(existing)}")
            print("Schema is already deployed. Use --rollback to remove.")
        else:
            print("Would create 6 tables + 8 indexes:")
            for t in ["graph_nodes", "graph_edges", "graph_edge_reviews",
                       "graph_pipeline_runs", "graph_integrity_issues", "archival_metadata"]:
                print(f"  - {t}")
        return

    if args.rollback:
        print("Rolling back graph schema (dropping tables)...")
        rollback_graph_schema()
        print("Done. Graph tables removed. Legacy tables (record_links, event_links) untouched.")
        return

    print("Deploying graph schema (additive, safe)...")
    init_graph_schema()
    conn = get_conn()
    if graph_schema_available(conn):
        print("OK: graph schema deployed successfully.")
    else:
        print("ERROR: schema deployment failed verification.")
        sys.exit(1)
    conn.close()


if __name__ == "__main__":
    main()

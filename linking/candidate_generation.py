"""
Candidate generation via blocking indexes.

Eliminates O(N*M) scans by using blocking keys:
- Phonetic prefix of cognome + initial of nome
- Birth year bucket
- Normalized place
- Unit/reparto
- Matricola
- Camp/Stalag
- Provider/external ID

Each block produces candidate pairs that are then scored by feature_extraction.
"""
import sqlite3
from dataclasses import dataclass, field
from typing import Iterable

from linking.normalization import normalize_name, normalize_place, VERSION


BLOCKING_VERSION = "2.0.0"


@dataclass
class CandidatePair:
    source_namespace: str
    source_record_key: str
    target_namespace: str
    target_record_key: str
    block_key: str
    block_type: str
    version: str = field(default=BLOCKING_VERSION, init=False)


def _phonetic_prefix(s: str, length: int = 3) -> str:
    """Simple phonetic prefix: first N consonants + vowels as fallback."""
    if not s:
        return ""
    s = s.lower().strip()
    consonants = "".join(c for c in s if c in "bcdfghjklmnpqrstvwz")
    if len(consonants) >= length:
        return consonants[:length]
    return s[:length]


def build_blocking_index(conn: sqlite3.Connection, table: str, columns: dict) -> list[dict]:
    """
    Build blocking index entries for a table.
    
    Args:
        conn: SQLite connection
        table: Source table name (e.g. 'internati', 'caduti_albooro')
        columns: Dict mapping block_type to column name(s)
    
    Returns:
        List of {block_key, block_type, record_key} dicts
    """
    entries = []
    
    # Name-based blocking
    if "cognome" in columns and "nome" in columns:
        cog_col = columns["cognome"]
        nom_col = columns["nome"]
        id_col = columns.get("id", "id")
        rows = conn.execute(
            f"SELECT {id_col}, {cog_col}, {nom_col} FROM {table} "
            f"WHERE {cog_col} IS NOT NULL AND {cog_col} != ''"
        ).fetchall()
        for r in rows:
            norm = normalize_name(r[1] or "", r[2] or "")
            if norm.cognome_normalized:
                key = _phonetic_prefix(norm.cognome_normalized, 3)
                if key:
                    entries.append({
                        "block_key": f"name:{key}",
                        "block_type": "phonetic_cognome",
                        "record_key": str(r[0]),
                        "namespace": table,
                    })
                # Also block on full normalized name
                if norm.nome_normalized:
                    key2 = f"{norm.cognome_normalized[:4]}{norm.nome_normalized[:1]}"
                    entries.append({
                        "block_key": f"name:{key2}",
                        "block_type": "name_initial",
                        "record_key": str(r[0]),
                        "namespace": table,
                    })
    
    # Year-based blocking
    if "year" in columns:
        year_col = columns["year"]
        id_col = columns.get("id", "id")
        rows = conn.execute(
            f"SELECT {id_col}, {year_col} FROM {table} "
            f"WHERE {year_col} IS NOT NULL AND {year_col} != ''"
        ).fetchall()
        for r in rows:
            year_str = str(r[1]).strip()[:4]
            if year_str.isdigit():
                entries.append({
                    "block_key": f"year:{year_str}",
                    "block_type": "birth_year",
                    "record_key": str(r[0]),
                    "namespace": table,
                })
    
    # Place-based blocking
    if "place" in columns:
        place_col = columns["place"]
        id_col = columns.get("id", "id")
        rows = conn.execute(
            f"SELECT {id_col}, {place_col} FROM {table} "
            f"WHERE {place_col} IS NOT NULL AND {place_col} != ''"
        ).fetchall()
        for r in rows:
            norm = normalize_place(r[1] or "")
            if norm.normalized:
                key = norm.normalized.lower()[:6]
                entries.append({
                    "block_key": f"place:{key}",
                    "block_type": "place_prefix",
                    "record_key": str(r[0]),
                    "namespace": table,
                })
    
    # Matricola blocking (exact match)
    if "matricola" in columns:
        mat_col = columns["matricola"]
        id_col = columns.get("id", "id")
        rows = conn.execute(
            f"SELECT {id_col}, {mat_col} FROM {table} "
            f"WHERE {mat_col} IS NOT NULL AND {mat_col} != ''"
        ).fetchall()
        for r in rows:
            mat = str(r[1]).strip()
            if mat:
                entries.append({
                    "block_key": f"mat:{mat}",
                    "block_type": "matricola",
                    "record_key": str(r[0]),
                    "namespace": table,
                })
    
    return entries


def generate_candidates(
    conn: sqlite3.Connection,
    source_table: str,
    source_columns: dict,
    target_table: str,
    target_columns: dict,
) -> list[CandidatePair]:
    """
    Generate candidate pairs by building blocking indexes for both tables
    and finding records that share at least one block key.
    
    This replaces O(N*M) scans with O(N+M) index building + O(matches) lookup.
    """
    source_entries = build_blocking_index(conn, source_table, source_columns)
    target_entries = build_blocking_index(conn, target_table, target_columns)
    
    # Group target entries by block_key
    target_by_key: dict[str, list[dict]] = {}
    for e in target_entries:
        target_by_key.setdefault(e["block_key"], []).append(e)
    
    candidates = []
    seen = set()
    
    for se in source_entries:
        key = se["block_key"]
        if key not in target_by_key:
            continue
        for te in target_by_key[key]:
            # Skip self-matches
            if se["record_key"] == te["record_key"] and se["namespace"] == te["namespace"]:
                continue
            # Deduplicate
            pair_key = (
                se["namespace"], se["record_key"],
                te["namespace"], te["record_key"],
                se["block_type"],
            )
            if pair_key in seen:
                continue
            seen.add(pair_key)
            
            candidates.append(CandidatePair(
                source_namespace=se["namespace"],
                source_record_key=se["record_key"],
                target_namespace=te["namespace"],
                target_record_key=te["record_key"],
                block_key=key,
                block_type=se["block_type"],
            ))
    
    return candidates

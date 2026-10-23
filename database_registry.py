"""Registro canonico dei database e delle tabelle storiche.

Il progetto conserva dati in più database SQLite. Questo modulo evita che ogni
servizio reinventi percorsi, nomi di colonne e query dinamiche. Le tabelle sono
esplicitamente autorizzate: un valore proveniente dal database non viene mai
interpolato in SQL senza essere prima risolto nel registro.
"""
from __future__ import annotations

import os
import re
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping, Optional
from urllib.parse import urlparse


ROOT = Path(__file__).resolve().parent
MAIN_DB_PATH = Path(os.environ.get("IMI_DATABASE_PATH", ROOT / "imi_internati.db"))
EVENTS_DB_PATH = Path(os.environ.get("EVENTS_DATABASE_PATH", ROOT / "eventi_1gm.db"))


@dataclass(frozen=True)
class TableSpec:
    database: str
    node_type: str
    label_fields: tuple[str, ...]
    description_fields: tuple[str, ...] = ()
    date_fields: tuple[str, ...] = ()
    place_fields: tuple[str, ...] = ()
    url_fields: tuple[str, ...] = ()


TABLE_SPECS: dict[str, TableSpec] = {
    "internati": TableSpec(
        "main", "persona", ("cognome", "nome"),
        ("grado", "reparto", "luogo_internamento", "sorte"),
        ("data_nascita", "data_cattura"), ("luogo_nascita", "luogo_cattura"),
    ),
    "caduti_albooro": TableSpec(
        "main", "persona", ("nominativo",), ("grado", "reparto", "causa_morte"),
        ("anno_morte",), ("comune_attuale", "luogo_morte"),
        ("detail_url", "img_url"),
    ),
    "caduti_bologna": TableSpec(
        "main", "persona", ("nome",), ("grado", "reparto", "causa_morte"),
        ("data_morte", "anno_nascita"), ("luogo_nascita", "luogo_morte"),
    ),
    "caduti_cwgc": TableSpec(
        "main", "persona", ("cognome", "nome"), ("rank", "regiment", "service_number"),
        ("data_nascita", "data_morte"), ("cimitero", "paese_cimitero"),
    ),
    "caduti_ministero": TableSpec(
        "main", "persona", ("cognome", "nome"), ("nominativo_paternita",),
        ("data_nascita", "data_decesso"), ("comune_nascita", "luogo_sepoltura"),
        ("scheda_url",),
    ),
    "caduti_sardi": TableSpec(
        "main", "persona", ("cognome", "nome"), ("grado", "reparto", "causa_morte"),
        ("data_nascita", "data_morte"), ("luogo_nascita", "luogo_morte"),
        ("scheda_url",),
    ),
    "caduti_francia_ww1": TableSpec(
        "main", "persona", ("nom",), ("grade", "unite"),
        ("naissance", "date_deces"), ("lieu_naissance", "lieu_deces"),
        ("images_href",),
    ),
    "decorati": TableSpec(
        "main", "persona", ("cognome", "nome"), ("grado", "reparto", "decorazione"),
        ("data_nascita", "data_morte"), ("comune_nascita", "luogo_morte"),
        ("url_scheda",),
    ),
    "decorati_nastroazzurro": TableSpec(
        "main", "persona", ("cognome", "nome"), ("tipo_decorazione", "arma"),
        ("anno_decorazione",),
    ),
    "menzioni": TableSpec(
        "main", "menzione", ("cognome", "nome", "testo_originale"),
        ("tipo", "grado", "reparto", "contesto"), ("data",), ("luogo",),
        ("file_pdf",),
    ),
    "fondi_archivistici": TableSpec(
        "main", "fondo_archivistico", ("titolo", "codice_fondo"),
        ("descrizione", "periodo", "busta", "fascicolo"), (), ("luoghi",),
        ("url", "file_pdf"),
    ),
    "fonti_indice": TableSpec(
        "main", "fonte", ("titolo", "segnatura"), ("archivio", "fondo", "serie", "note"),
        ("data_inizio", "data_fine"), ("luogo",), ("url_file", "url_catalogo", "iiif_manifest"),
    ),
    "fonti_narrative": TableSpec(
        "main", "fonte", ("titolo", "nome_file"), ("autore", "archivio", "descrizione"),
        ("data_documento",), (), ("path_locale",),
    ),
    "lettere_personali": TableSpec(
        "main", "documento", ("mittente", "destinatario", "filename"),
        ("oggetto",), ("data_lettera",), ("luogo",), ("file_path",),
    ),
    "archivio_documenti": TableSpec(
        "main", "documento", ("title", "external_id"), ("description", "provider", "doc_type"),
        ("date_text",), ("place",), ("source_url", "thumbnail_url"),
    ),
    "archivio_fonti": TableSpec(
        "main", "fonte", ("titolo_documento", "segnatura"),
        ("archivio", "fondo", "serie", "unita_principale", "note"),
        ("data_inizio", "data_fine"), ("teatro_operazioni", "luoghi_citati"),
        ("iiif_manifest_url", "url_catalogo", "path_storage", "path_originale"),
    ),
    "research_subjects": TableSpec(
        "main", "soggetto_ricerca", ("name",), ("subject_type", "status"),
    ),
    "rc_candidates": TableSpec(
        "main", "persona", ("cognome", "nome"), ("grado", "reparto", "conflitto"),
        ("data_nascita",), ("luogo_nascita",),
    ),
    "entita": TableSpec(
        "main", "entita", ("valore",), ("tipo", "contesto"), ("data",), ("luogo",),
    ),
    "external_source_records": TableSpec(
        "main", "fonte_esterna", ("title", "reference_code", "external_id"),
        ("provider", "archive_name", "description"), ("date_from", "date_to"),
        (), ("digital_object_url", "canonical_record_url", "parent_record_url"),
    ),
    "eventi_1gm": TableSpec(
        "events", "evento", ("nome",), ("descrizione", "aliases", "keywords"),
        ("data_inizio", "data_fine"), ("luogo",),
    ),
}


def get_table_spec(table: str) -> TableSpec:
    try:
        return TABLE_SPECS[table]
    except KeyError as exc:
        raise ValueError(f"Tabella non autorizzata: {table}") from exc


def connect_sqlite(path: Path, *, read_only: bool = True) -> sqlite3.Connection:
    path = Path(path).resolve()
    if read_only:
        if not path.exists():
            raise FileNotFoundError(path)
        uri = f"{path.as_uri()}?mode=ro"
        conn = sqlite3.connect(uri, uri=True, timeout=30)
        conn.execute("PRAGMA query_only=ON")
    else:
        conn = sqlite3.connect(str(path), timeout=60)
        conn.execute("PRAGMA foreign_keys=ON")
        conn.execute("PRAGMA busy_timeout=60000")
    conn.row_factory = sqlite3.Row
    return conn


def connect_database(database: str, *, read_only: bool = True) -> sqlite3.Connection:
    if database == "main":
        return connect_sqlite(MAIN_DB_PATH, read_only=read_only)
    if database == "events":
        return connect_sqlite(EVENTS_DB_PATH, read_only=read_only)
    raise ValueError(f"Database non autorizzato: {database}")


def table_exists(conn: sqlite3.Connection, table: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type IN ('table','view') AND name=?",
        (table,),
    ).fetchone()
    return bool(row)


def table_columns(conn: sqlite3.Connection, table: str) -> set[str]:
    get_table_spec(table)
    if not table_exists(conn, table):
        return set()
    return {str(row["name"]) for row in conn.execute(f'PRAGMA table_info("{table}")')}


def fetch_record(
    table: str,
    record_id: int,
    *,
    connections: Optional[Mapping[str, sqlite3.Connection]] = None,
) -> Optional[dict[str, Any]]:
    spec = get_table_spec(table)
    own_connection = connections is None or spec.database not in connections
    conn = connect_database(spec.database, read_only=True) if own_connection else connections[spec.database]
    try:
        if not table_exists(conn, table):
            return None
        row = conn.execute(f'SELECT * FROM "{table}" WHERE id=?', (int(record_id),)).fetchone()
        return dict(row) if row else None
    finally:
        if own_connection:
            conn.close()


def first_text(record: Mapping[str, Any], fields: Iterable[str]) -> Optional[str]:
    for field in fields:
        value = record.get(field)
        if value is not None and str(value).strip():
            return str(value).strip()
    return None


def record_label(table: str, record: Mapping[str, Any]) -> str:
    spec = get_table_spec(table)
    values: list[str] = []
    for field in spec.label_fields:
        value = record.get(field)
        if value is not None and str(value).strip():
            text = " ".join(str(value).split())
            if text not in values:
                values.append(text)
    label = " ".join(values).strip()
    if not label:
        label = f"{table} #{record.get('id', '?')}"
    return label


def record_description(table: str, record: Mapping[str, Any]) -> Optional[str]:
    spec = get_table_spec(table)
    parts = []
    for field in spec.description_fields:
        value = record.get(field)
        if value is not None and str(value).strip():
            parts.append(f"{field.replace('_', ' ')}: {' '.join(str(value).split())}")
    return "; ".join(parts[:4]) or None


def record_urls(table: str, record: Mapping[str, Any]) -> list[dict[str, str]]:
    spec = get_table_spec(table)
    urls: list[dict[str, str]] = []
    seen: set[str] = set()
    for field in spec.url_fields:
        value = record.get(field)
        if not value:
            continue
        url = str(value).strip()
        if not url or url in seen:
            continue
        kind = "file" if field in {
            "url_file", "digital_object_url", "iiif_manifest", "iiif_manifest_url",
        } else "record"
        if field in {
            "path_locale", "file_path", "file_pdf", "path_storage", "path_originale",
        } and not url.startswith(("http://", "https://")):
            kind = "local_reference"
        elif url.startswith(("http://", "https://")) and kind != "file":
            from research_orchestrator import classify_url
            kind = classify_url(url)
        urls.append({"field": field, "url": url, "kind": kind})
        seen.add(url)
    return urls

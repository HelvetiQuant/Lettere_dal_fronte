"""Read-only integrity and source-link audit across the historical datasets."""
from __future__ import annotations

import argparse
import html
import json
import re
import sqlite3
import sys
import time
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parent
OCR_ROOT = ROOT.parent / "ocr_lettere"
DEFAULT_DATABASES = {
    "imi_internati": ROOT / "imi_internati.db",
    "eventi_1gm": ROOT / "eventi_1gm.db",
    "archivio_fonti": ROOT / "archivio_fonti.db",
    "fonti_risorse": ROOT / "fonti_risorse.db",
    "albo_oro": ROOT / "albo_oro.db",
    "imi_data": ROOT / "imi_data.db",
    "validazioni_ai": ROOT / "validazioni_ai.db",
    "ocr_lettere": OCR_ROOT / "ocr_lettere.db",
}
NAME_COLUMNS = {"nome", "cognome", "nominativo", "mittente", "destinatario", "nom"}
PLACE_COLUMNS = {"luogo", "luogo_nascita", "comune_nascita", "luogo_morte", "luogo_cattura", "luogo_internamento", "residenza", "place"}
DATE_COLUMNS = {"data", "data_nascita", "data_morte", "data_cattura", "data_lettera", "anno_morte", "anno_decorazione", "year_start"}
URL_COLUMNS = {"url", "url_catalogo", "url_file", "url_pagina", "url_documento", "source_url", "detail_url", "scheda_url", "iiif_manifest"}
RELATION_TABLES = {"collegamenti", "record_links", "event_links"}
PLACEHOLDERS = {"", "-", "n/d", "nd", "n.a.", "na", "n/a", "unknown", "sconosciuto", "null"}


def normalize_text(value: object) -> str:
    if value is None:
        return ""
    value = str(value).strip().lower()
    value = re.sub(r"[\u2010-\u2015\-_/,:;.]+", " ", value)
    return re.sub(r"\s+", " ", value).strip()


def normalize_name(value: object) -> str:
    return normalize_text(value)


def is_empty(value: object) -> bool:
    return normalize_text(value) in PLACEHOLDERS


def severity_counts(findings: list[dict]) -> dict[str, int]:
    counts = Counter(f["severity"] for f in findings)
    return {level: counts.get(level, 0) for level in ("info", "warning", "error", "critical")}


def connect_readonly(path: Path) -> sqlite3.Connection:
    uri = f"file:{path.resolve().as_posix()}?mode=ro"
    conn = sqlite3.connect(uri, uri=True, timeout=10)
    conn.row_factory = sqlite3.Row
    return conn


def table_names(conn: sqlite3.Connection) -> list[str]:
    return [r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name")]


def table_columns(conn: sqlite3.Connection, table: str) -> list[str]:
    return [r[1] for r in conn.execute(f'PRAGMA table_info("{table}")')]


def schema_inventory(databases: dict[str, Path], findings: list[dict]) -> list[dict]:
    inventory = []
    for name, path in databases.items():
        item = {"name": name, "path": str(path), "exists": path.exists(), "size_bytes": path.stat().st_size if path.exists() else 0, "tables": []}
        if not path.exists():
            findings.append({"severity": "warning", "code": "database_missing", "database": name, "message": "Database configurato ma non presente", "path": str(path)})
            inventory.append(item)
            continue
        try:
            with connect_readonly(path) as conn:
                for table in table_names(conn):
                    columns = table_columns(conn, table)
                    count = conn.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0]
                    item["tables"].append({"name": table, "columns": columns, "row_count": count})
        except Exception as exc:
            item["error"] = str(exc)
            findings.append({"severity": "critical", "code": "database_unreadable", "database": name, "message": str(exc), "path": str(path)})
        inventory.append(item)
    return inventory


def row_dict(row: sqlite3.Row) -> dict:
    return {k: row[k] for k in row.keys()}


def candidate_identity_rows(databases: dict[str, Path], subject: str | None, findings: list[dict]) -> list[dict]:
    rows = []
    target = normalize_name(subject) if subject else ""
    for db_name, path in databases.items():
        if not path.exists():
            continue
        try:
            with connect_readonly(path) as conn:
                for table in table_names(conn):
                    columns = table_columns(conn, table)
                    name_cols = [c for c in columns if c.lower() in NAME_COLUMNS]
                    if not name_cols:
                        continue
                    select_cols = [c for c in columns if c.lower() in NAME_COLUMNS | PLACE_COLUMNS | DATE_COLUMNS or c.lower() in {"id", "rowid", "title", "filename"}]
                    select_cols = list(dict.fromkeys(select_cols))[:30]
                    if not select_cols:
                        continue
                    quoted = ", ".join(f'"{c}"' for c in select_cols)
                    for row in conn.execute(f'SELECT rowid AS __rowid, {quoted} FROM "{table}" LIMIT 100000'):
                        data = row_dict(row)
                        pieces = [data.get(c) for c in name_cols if data.get(c)]
                        candidate = normalize_name(" ".join(str(v) for v in pieces))
                        if not candidate:
                            continue
                        if target:
                            target_tokens = set(target.split())
                            candidate_tokens = set(candidate.split())
                            if not target_tokens <= candidate_tokens:
                                continue
                        rows.append({"database": db_name, "table": table, "row_id": data.pop("__rowid"), "identity": candidate, "record": data})
        except Exception as exc:
            findings.append({"severity": "error", "code": "identity_scan_failed", "database": db_name, "message": str(exc)})
    return rows


def audit_identity_groups(rows: list[dict], findings: list[dict]) -> list[dict]:
    groups = defaultdict(list)
    for row in rows:
        groups[row["identity"]].append(row)
    result = []
    for identity, members in sorted(groups.items()):
        datasets = sorted({f"{r['database']}:{r['table']}" for r in members})
        places = sorted({normalize_text(v) for r in members for k, v in r["record"].items() if k.lower() in PLACE_COLUMNS and not is_empty(v)})
        dates = sorted({normalize_text(v) for r in members for k, v in r["record"].items() if k.lower() in DATE_COLUMNS and not is_empty(v)})
        conflicts = False
        conflict_details: list[dict] = []
        for col_type, col_set in (("place", PLACE_COLUMNS), ("date", DATE_COLUMNS)):
            by_col: dict[str, set[str]] = defaultdict(set)
            for r in members:
                for k, v in r["record"].items():
                    if k.lower() in col_set and not is_empty(v):
                        by_col[k.lower()].add(normalize_text(v))
            for col, vals in by_col.items():
                if len(vals) > 1:
                    conflicts = True
                    conflict_details.append({"column": col, "values": sorted(vals)})
        if len(members) > 1:
            findings.append({"severity": "warning" if conflicts else "info", "code": "identity_multi_dataset", "identity": identity, "message": "Identità presente in più record/dataset", "datasets": datasets, "places": places, "dates": dates, "conflict": conflicts})
        if conflicts:
            findings.append({"severity": "critical", "code": "identity_attribute_conflict", "identity": identity, "message": "Stesso nominativo con valori discordanti per la stessa colonna: possibile omonimia", "datasets": datasets, "places": places, "dates": dates, "conflicts": conflict_details})
        result.append({"identity": identity, "records": members, "datasets": datasets, "places": places, "dates": dates, "conflict": conflicts, "conflict_details": conflict_details})
    return result


def validate_local_links(databases: dict[str, Path], findings: list[dict]) -> dict:
    result = {"relations": [], "orphan_count": 0, "duplicate_count": 0}
    referenced_tables = set()
    for path in databases.values():
        if not path.exists():
            continue
        try:
            with connect_readonly(path) as conn:
                for relation in RELATION_TABLES & set(table_names(conn)):
                    columns = set(table_columns(conn, relation))
                    for row in conn.execute(f'SELECT * FROM "{relation}" LIMIT 200000'):
                        data = row_dict(row)
                        if {"from_table", "from_id"} <= columns:
                            referenced_tables.add(data.get("from_table"))
                        if {"to_table", "to_id"} <= columns:
                            referenced_tables.add(data.get("to_table"))
                        if {"target_table", "target_id"} <= columns:
                            referenced_tables.add(data.get("target_table"))
                        if {"tabella_origine", "record_id"} <= columns:
                            referenced_tables.add(data.get("tabella_origine"))
        except Exception:
            continue
    global_ids = defaultdict(set)
    for path in databases.values():
        if not path.exists():
            continue
        try:
            with connect_readonly(path) as conn:
                for table in referenced_tables:
                    if table not in table_names(conn):
                        continue
                    try:
                        for row in conn.execute(f'SELECT rowid, * FROM "{table}" LIMIT 200000'):
                            global_ids[table].add(row[0])
                            if "id" in row.keys() and row["id"] is not None:
                                global_ids[table].add(row["id"])
                    except sqlite3.OperationalError:
                        continue
        except Exception:
            continue
    for db_name, path in databases.items():
        if not path.exists():
            continue
        try:
            with connect_readonly(path) as conn:
                tables = set(table_names(conn))
                for relation in sorted(RELATION_TABLES & tables):
                    columns = set(table_columns(conn, relation))
                    rows = conn.execute(f'SELECT rowid AS __rowid, * FROM "{relation}" LIMIT 200000').fetchall()
                    keys = Counter()
                    relation_summary = {"database": db_name, "table": relation, "rows": len(rows), "orphans": 0, "duplicates": 0}
                    for row in rows:
                        data = row_dict(row)
                        key = tuple(data.get(c) for c in ("from_table", "from_id", "to_table", "to_id", "link_type") if c in columns)
                        if key:
                            keys[key] += 1
                        pairs = []
                        if {"from_table", "from_id"} <= columns:
                            pairs.append((data["from_table"], data["from_id"], "from"))
                        if {"to_table", "to_id"} <= columns:
                            pairs.append((data["to_table"], data["to_id"], "to"))
                        if {"target_table", "target_id"} <= columns:
                            pairs.append((data["target_table"], data["target_id"], "target"))
                        if {"tabella_origine", "record_id"} <= columns:
                            pairs.append((data["tabella_origine"], data["record_id"], "source"))
                        for target_table, target_id, side in pairs:
                            if not target_table or target_id is None:
                                relation_summary["orphans"] += 1
                                findings.append({"severity": "error", "code": "relation_target_invalid", "database": db_name, "relation": relation, "row_id": data.get("__rowid"), "side": side, "target_table": target_table, "target_id": target_id})
                                continue
                            if target_table not in global_ids or target_id not in global_ids[target_table]:
                                relation_summary["orphans"] += 1
                                findings.append({"severity": "error", "code": "relation_target_missing", "database": db_name, "relation": relation, "row_id": data.get("__rowid"), "side": side, "target_table": target_table, "target_id": target_id})
                    for key, count in keys.items():
                        if count > 1:
                            relation_summary["duplicates"] += count - 1
                            findings.append({"severity": "warning", "code": "relation_duplicate", "database": db_name, "relation": relation, "key": list(key), "count": count})
                    result["orphan_count"] += relation_summary["orphans"]
                    result["duplicate_count"] += relation_summary["duplicates"]
                    result["relations"].append(relation_summary)
        except Exception as exc:
            findings.append({"severity": "error", "code": "relation_scan_failed", "database": db_name, "message": str(exc)})
    return result


def collect_urls(databases: dict[str, Path], findings: list[dict]) -> list[dict]:
    urls = []
    for db_name, path in databases.items():
        if not path.exists():
            continue
        try:
            with connect_readonly(path) as conn:
                for table in table_names(conn):
                    columns = table_columns(conn, table)
                    url_cols = [c for c in columns if c.lower() in URL_COLUMNS]
                    if not url_cols:
                        continue
                    select_cols = ", ".join(f'"{c}"' for c in ["id"] + url_cols if c in columns)
                    for row in conn.execute(f'SELECT rowid AS __rowid, {select_cols} FROM "{table}" LIMIT 200000'):
                        data = row_dict(row)
                        for col in url_cols:
                            url = data.get(col)
                            if not is_empty(url):
                                urls.append({"database": db_name, "table": table, "row_id": data.get("id", data.get("__rowid")), "column": col, "url": str(url).strip()})
        except Exception as exc:
            findings.append({"severity": "error", "code": "url_scan_failed", "database": db_name, "message": str(exc)})
    return urls


def classify_url(item: dict) -> dict:
    url = item["url"]
    parsed = urlparse(url)
    status = "candidate"
    reason = ""
    if not parsed.scheme and parsed.path and (parsed.path.startswith(("/", "./", "../")) or "/" in parsed.path or ".aspx" in parsed.path.lower()):
        status, reason = "relative_unresolved", "URL relativo: manca il dominio originale"
    elif parsed.scheme not in {"http", "https"} or not parsed.netloc:
        status, reason = "invalid", "URL privo di schema HTTP(S) o host"
    elif parsed.hostname in {"open-data.bundesarchiv.de"} and parsed.path.rstrip("/") == "/ddb-bestand":
        status, reason = "catalog_landing", "Landing page ufficiale Bundesarchiv; non è un record diretto"
    elif any(token in parsed.path.lower() for token in ("search", "suche", "query")):
        status, reason = "search_page", "URL di ricerca, non record diretto"
    elif parsed.path.lower().endswith((".pdf", ".jpg", ".jpeg", ".png", ".tif", ".tiff")):
        status, reason = "document", "URL con estensione documento"
    else:
        status, reason = "catalog_or_record", "URL HTTP(S) da verificare online"
    return {**item, "host": parsed.hostname or "", "status": status, "reason": reason}


def verify_urls_online(urls: list[dict], findings: list[dict], enabled: bool) -> list[dict]:
    result = []
    seen = set()
    for item in urls:
        classified = classify_url(item)
        if item["url"] in seen:
            classified["status"] = "duplicate_url"
            result.append(classified)
            continue
        seen.add(item["url"])
        if classified["status"] == "invalid":
            findings.append({"severity": "error", "code": "invalid_url", **item, "message": classified["reason"]})
        elif classified["status"] == "relative_unresolved":
            findings.append({"severity": "warning", "code": "relative_url_unresolved", **item, "message": classified["reason"]})
        if not enabled or classified["status"] in {"invalid", "relative_unresolved"}:
            result.append(classified)
            continue
        try:
            request = Request(item["url"], method="HEAD", headers={"User-Agent": "IMI-cross-db-audit/1.0"})
            with urlopen(request, timeout=15) as response:
                classified.update({"online_status": response.status, "final_url": response.geturl(), "content_type": response.headers.get("Content-Type", "")})
                if response.status >= 400:
                    classified["status"] = "not_reachable"
                    findings.append({"severity": "error", "code": "url_http_error", **item, "http_status": response.status})
                else:
                    classified["status"] = "verified"
        except Exception as exc:
            classified.update({"online_status": None, "error": str(exc), "status": "not_reachable"})
            findings.append({"severity": "warning", "code": "url_not_reachable", **item, "message": str(exc)})
        result.append(classified)
        time.sleep(0.05)
    return result


def audit(databases: dict[str, Path] | None = None, subject: str | None = None, online: bool = False) -> dict:
    databases = databases or DEFAULT_DATABASES
    findings: list[dict] = []
    inventory = schema_inventory(databases, findings)
    identity_rows = candidate_identity_rows(databases, subject, findings)
    identities = audit_identity_groups(identity_rows, findings)
    relations = validate_local_links(databases, findings)
    raw_urls = collect_urls(databases, findings)
    urls = verify_urls_online(raw_urls, findings, online)
    return {
        "audit_version": "1.0",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "read_only": True,
        "online_enabled": online,
        "subject": subject,
        "databases": inventory,
        "identities": identities,
        "relations": relations,
        "urls": urls,
        "findings": findings,
        "summary": {"findings": len(findings), "severity": severity_counts(findings), "databases": len(inventory), "identity_records": len(identity_rows), "urls": len(urls)},
    }


def render_html(report: dict) -> str:
    summary = report["summary"]
    cards = "".join(f'<div class="card"><b>{html.escape(k)}</b><span>{v}</span></div>' for k, v in summary["severity"].items())
    rows = []
    for finding in report["findings"]:
        rows.append(f'<tr class="{html.escape(finding["severity"])}"><td>{html.escape(finding["severity"])}</td><td>{html.escape(finding.get("code", ""))}</td><td><pre>{html.escape(json.dumps(finding, ensure_ascii=False, indent=2))}</pre></td></tr>')
    urls = []
    for item in report["urls"]:
        link = html.escape(item["url"], quote=True)
        urls.append(f'<tr><td>{html.escape(item["status"])}</td><td>{html.escape(item["database"])}:{html.escape(item["table"])}</td><td><a href="{link}" target="_blank" rel="noopener">{link}</a></td><td>{html.escape(item.get("reason", ""))}</td></tr>')
    return f'''<!doctype html><html lang="it"><head><meta charset="utf-8"><title>Audit cross database</title><style>body{{font:14px system-ui;margin:2rem;color:#202124}}.cards{{display:flex;gap:12px;flex-wrap:wrap}}.card{{padding:12px 18px;border:1px solid #ddd;border-radius:8px;display:grid;gap:4px}}table{{border-collapse:collapse;width:100%;margin-top:1rem}}td,th{{border:1px solid #ddd;padding:8px;vertical-align:top}}.critical{{background:#ffe0e0}}.error{{background:#fff0e0}}.warning{{background:#fffbe0}}pre{{white-space:pre-wrap;margin:0}}a{{word-break:break-all}}</style></head><body><h1>Audit cross-database e fonti online</h1><p>Generato: {html.escape(report["generated_at"])} · Read-only: {report["read_only"]} · Online: {report["online_enabled"]}</p><div class="cards">{cards}</div><h2>URL ({len(report["urls"])})</h2><table><tr><th>Stato</th><th>Record</th><th>URL</th><th>Nota</th></tr>{''.join(urls)}</table><h2>Findings ({len(report["findings"])})</h2><table><tr><th>Severità</th><th>Codice</th><th>Dettaglio</th></tr>{''.join(rows)}</table></body></html>'''


def exit_code(report: dict) -> int:
    severity = report["summary"]["severity"]
    return 2 if severity["critical"] else 1 if severity["error"] else 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Audit read-only cross-database e fonti online")
    parser.add_argument("--db", action="append", metavar="NOME=PERCORSO")
    parser.add_argument("--subject")
    parser.add_argument("--online", action="store_true")
    parser.add_argument("--json", dest="json_path", default="audit_cross_db.json")
    parser.add_argument("--html", dest="html_path", default="audit_cross_db.html")
    args = parser.parse_args(argv)
    databases = dict(DEFAULT_DATABASES)
    for value in args.db or []:
        if "=" not in value:
            parser.error("--db richiede NOME=PERCORSO")
        name, path = value.split("=", 1)
        databases[name] = Path(path)
    report = audit(databases, args.subject, args.online)
    Path(args.json_path).write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    Path(args.html_path).write_text(render_html(report), encoding="utf-8")
    print(json.dumps(report["summary"], ensure_ascii=False, indent=2))
    return exit_code(report)


if __name__ == "__main__":
    sys.exit(main())

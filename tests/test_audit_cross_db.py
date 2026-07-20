import json
import sqlite3
from pathlib import Path

from audit_cross_db import audit, classify_url, normalize_name, render_html


def make_db(path: Path, schema: str, rows: list[tuple] = ()):
    conn = sqlite3.connect(path)
    conn.executescript(schema)
    for sql, values in rows:
        conn.execute(sql, values)
    conn.commit()
    conn.close()


def test_normalize_name_and_url_classification():
    assert normalize_name("  Gaiaschi — Luigi ") == "gaiaschi luigi"
    assert classify_url({"database": "x", "table": "fonti_indice", "row_id": 1, "column": "url_catalogo", "url": "https://open-data.bundesarchiv.de/ddb-bestand/"})["status"] == "catalog_landing"
    assert classify_url({"database": "x", "table": "t", "row_id": 1, "column": "url", "url": "not-a-url"})["status"] == "invalid"


def test_audit_detects_orphan_and_homonym_conflict(tmp_path):
    db = tmp_path / "imi.db"
    make_db(db, """
        CREATE TABLE internati (id INTEGER PRIMARY KEY, cognome TEXT, nome TEXT, luogo_nascita TEXT, data_nascita TEXT);
        CREATE TABLE decorati (id INTEGER PRIMARY KEY, cognome TEXT, nome TEXT, comune_nascita TEXT);
        CREATE TABLE collegamenti (id INTEGER PRIMARY KEY, entita_id INTEGER, tabella_origine TEXT, record_id INTEGER);
        CREATE TABLE fonti_indice (id INTEGER PRIMARY KEY, titolo TEXT, url_catalogo TEXT);
    """, [
        ("INSERT INTO internati VALUES (1, 'Gaiaschi', 'Luigi', 'Nibbiano (Piacenza)', '1920-01-01')", ()),
        ("INSERT INTO decorati VALUES (2, 'Gaiaschi', 'Luigi', 'Bergamo')", ()),
        ("INSERT INTO internati VALUES (3, 'Gaiaschi', 'Luigi', 'Roma', '1920-01-01')", ()),
        ("INSERT INTO collegamenti VALUES (1, 999, 'internati', 404)", ()),
        ("INSERT INTO fonti_indice VALUES (1, 'Fonte', 'https://example.org/record/1')", ()),
    ])
    report = audit({"test": db}, subject="Luigi Gaiaschi")
    codes = {finding["code"] for finding in report["findings"]}
    assert "relation_target_missing" in codes
    assert "identity_attribute_conflict" in codes
    assert report["read_only"] is True
    assert report["summary"]["identity_records"] == 3


def test_audit_json_and_html_are_serializable(tmp_path):
    db = tmp_path / "empty.db"
    make_db(db, "CREATE TABLE fonti_indice (id INTEGER PRIMARY KEY, url_catalogo TEXT);")
    report = audit({"empty": db})
    encoded = json.dumps(report, ensure_ascii=False)
    page = render_html(report)
    assert '"read_only": true' in encoded
    assert "Audit cross-database" in page
    assert "fonti_indice" not in page or "URL" in page

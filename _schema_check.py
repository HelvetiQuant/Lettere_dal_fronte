"""Diagnostic: check table schemas — import-safe, read-only.

All work is inside main(). Importing this module has zero side effects.
"""
import sqlite3
import os

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "imi_internati.db")


def main():
    conn = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    print("=== SCHEMI TABELLE ===")
    for tab in ["caduti_albooro", "decorati_nastroazzurro", "archivio_documenti", "collegamenti", "entita", "fonti_indice"]:
        print(f"\n--- {tab} ---")
        for r in conn.execute(f"PRAGMA table_info({tab})").fetchall():
            print(f"  {r['name']:30s} {r['type']}")
        print(f"  Rows: {conn.execute(f'SELECT COUNT(*) FROM {tab}').fetchone()[0]}")
    conn.close()


if __name__ == "__main__":
    main()

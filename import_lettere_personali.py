"""Migra le lettere OCR da `import_ocr_lettere/ocr_lettere.db` a `imi_internati.db`
come nuova tabella sorgente `lettere_personali`, collegandole allo star schema.
"""

import re
import sqlite3
from datetime import datetime
from pathlib import Path

OCR_DB = Path("import_ocr_lettere/ocr_lettere.db")
MAIN_DB = Path("imi_internati.db")

_LETTERE_DDL = """
CREATE TABLE IF NOT EXISTS lettere_personali (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    filename TEXT,
    file_path TEXT,
    mittente TEXT,
    destinatario TEXT,
    data_lettera TEXT,
    luogo TEXT,
    oggetto TEXT,
    corpo_testo TEXT,
    note TEXT,
    confidenza REAL,
    lingua TEXT,
    raw_response TEXT,
    sha256 TEXT UNIQUE,
    sorgente_db TEXT,
    sorgente_id INTEGER,
    elaborato_il TEXT
);

CREATE INDEX IF NOT EXISTS idx_lettere_mittente ON lettere_personali(mittente);
CREATE INDEX IF NOT EXISTS idx_lettere_destinatario ON lettere_personali(destinatario);
CREATE INDEX IF NOT EXISTS idx_lettere_luogo ON lettere_personali(luogo);
CREATE INDEX IF NOT EXISTS idx_lettere_data ON lettere_personali(data_lettera);
"""


def _sha256_file(path: Path) -> str:
    import hashlib

    if not path.exists():
        return ""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


def _normalizza_nome(valore: str) -> str:
    v = re.sub(r"\s+", " ", valore.lower().strip())
    v = re.sub(r"[^a-zàáâãäåæçèéêëìíîïðñòóôõöøùúûüýþÿ\s'-]", "", v)
    return v


def _estrai_cognome_nome(valore: str):
    """Estrae cognome, nome da stringhe tipo 'Rossi Mario' o 'Mario Rossi'."""
    if not valore:
        return "", ""
    valore = valore.strip()
    # Forma tipica italiana: Cognome Nome
    if "," in valore:
        parti = [p.strip() for p in valore.split(",")]
        return parti[0], " ".join(parti[1:])
    parti = valore.split()
    if len(parti) >= 2:
        return parti[0], " ".join(parti[1:])
    return valore, ""


def _persone_da_testo(testo: str):
    """Euristiche semplici per trovare persone in testo (nomi propri maiuscoli)."""
    if not testo:
        return []
    # Pattern: sequenze di 2-4 parole iniziali maiuscole, escludendo inizio frase
    pattern = re.compile(r"(?<![.!?]\s)(?<![A-Z])([A-Z][a-zàèéìòù]+\s+[A-Z][a-zàèéìòù]+(?:\s+[A-Z][a-zàèéìòù]+)?)")
    cortesia = {"grazie", "caro", "cara", "saluti", "tuo", "tua", "tanti", "affettuosi", "cordiali"}
    trovati = set()
    for m in pattern.finditer(testo):
        nome = m.group(1).strip()
        parole = nome.lower().split()
        if len(nome) > 3 and not any(p in cortesia for p in parole):
            trovati.add(nome)
    return sorted(trovati)


def _upsert_persona(conn, valore: str, now: str, lettera_id: int):
    if not valore:
        return None
    cognome, nome = _estrai_cognome_nome(valore)
    if not cognome and not nome:
        return None
    display = f"{cognome} {nome}".strip()
    norm = _normalizza_nome(display)
    if not norm:
        return None

    row = conn.execute(
        "SELECT id FROM entita WHERE tipo='persona' AND valore_normalizzato=?",
        (norm,),
    ).fetchone()
    if row:
        entita_id = row[0]
    else:
        cur = conn.execute(
            """INSERT INTO entita (tipo, valore, valore_normalizzato, cognome, nome,
                                   fonte_tabella, fonte_id, elaborato_il)
                 VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            ("persona", display, norm, cognome, nome, "lettere_personali", lettera_id, now),
        )
        entita_id = cur.lastrowid

    conn.execute(
        "INSERT OR IGNORE INTO collegamenti (entita_id, tabella_origine, record_id, tipo_collegamento, confidenza, elaborato_il) VALUES (?, ?, ?, ?, ?, ?)",
        (entita_id, "lettere_personali", lettera_id, "menzionato", 0.8, now),
    )
    return entita_id


def migrate():
    if not OCR_DB.exists():
        print(f"Database OCR non trovato: {OCR_DB}")
        return

    main = sqlite3.connect(MAIN_DB)
    main.executescript(_LETTERE_DDL)

    ocr = sqlite3.connect(OCR_DB)
    ocr.row_factory = sqlite3.Row
    rows = ocr.execute("SELECT * FROM lettere").fetchall()
    now = datetime.now().isoformat()

    inserted = 0
    skipped = 0
    for r in rows:
        sha = _sha256_file(Path(r["file_path"])) if r["file_path"] else ""
        # Evita duplicati su sha
        if sha:
            existing = main.execute("SELECT id FROM lettere_personali WHERE sha256=?", (sha,)).fetchone()
            if existing:
                skipped += 1
                continue

        cur = main.execute(
            """INSERT INTO lettere_personali
                 (filename, file_path, mittente, destinatario, data_lettera, luogo, oggetto,
                  corpo_testo, note, confidenza, lingua, raw_response, sha256,
                  sorgente_db, sorgente_id, elaborato_il)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                r["filename"], r["file_path"], r["mittente"], r["destinatario"],
                r["data_lettera"], r["luogo"], r["oggetto"], r["corpo_testo"],
                r["note"], r["confidenza"], r["lingua"], r["raw_response"], sha,
                "ocr_lettere", r["id"], now,
            ),
        )
        lettera_id = cur.lastrowid
        inserted += 1

        # Collegamenti entita
        _upsert_persona(main, r["mittente"] or "", now, lettera_id)
        _upsert_persona(main, r["destinatario"] or "", now, lettera_id)

        # Persone da corpo testo (euristica)
        for persona in _persone_da_testo(r["corpo_testo"] or ""):
            _upsert_persona(main, persona, now, lettera_id)

    main.commit()
    print(f"Migrazione completata: {inserted} lettere inserite, {skipped} saltate.")
    ocr.close()
    main.close()


if __name__ == "__main__":
    migrate()

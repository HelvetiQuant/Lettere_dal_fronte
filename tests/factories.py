"""Factory helper per creare record di esempio nei test.

Perche' esistono: quasi ogni test ha bisogno di uno o due record minimi in
una tabella sorgente (internati, decorati, entita/collegamenti, ...) senza
dover riscrivere ogni volta l'INSERT completo. Quando aggiungi una nuova
tabella sorgente al progetto, aggiungi qui una funzione `make_<tabella>()`
con valori di default sensati: i test futuri (tuoi o di altri) la troveranno
gia' pronta invece di duplicare INSERT sparsi nei singoli file di test.

Convenzione: ogni make_*() accetta **overrides per sovrascrivere i default e
ritorna l'id (lastrowid) del record creato.
"""
from datetime import datetime


def _now():
    return datetime.now().isoformat()


def make_internato(conn, **overrides):
    data = {
        "lettera": "Z", "file_pdf": "test_ZZZ.pdf", "pagina": 1,
        "cognome": "Rossi", "nome": "Mario", "data_nascita": "1920-01-01",
        "luogo_nascita": "Trento", "residenza": "Trento", "grado": "Soldato",
        "luogo_cattura": "", "data_cattura": "", "luogo_internamento": "Stalag VII",
        "matricola": "12345", "arbeitskommando": "", "mansione": "",
        "sorte": "Rimpatriato", "data": "", "documenti": "",
        "raw_text": "", "elaborato_il": _now(),
    }
    data.update(overrides)
    cols = ", ".join(data)
    marks = ", ".join("?" for _ in data)
    cur = conn.execute(f"INSERT INTO internati ({cols}) VALUES ({marks})", tuple(data.values()))
    conn.commit()
    return cur.lastrowid


def make_decorato(conn, **overrides):
    data = {
        "source_id": f"TEST-{datetime.now().timestamp()}", "albo_id": "1",
        "albo_nome": "Test Albo", "cognome": "Bianchi", "nome": "Luigi",
        "comune_nascita": "Bologna", "comune_residenza": "Bologna",
        "data_nascita": "1918-01-01", "data_morte": "1943-01-01",
        "guerra": "WW2", "grado": "Caporale", "corpo_militare": "Fanteria",
        "reparto": "", "decorazione": "Medaglia di bronzo", "motivazione": "",
        "causa_morte": "", "luogo_morte": "", "url_scheda": "", "raw_json": "{}",
    }
    data.update(overrides)
    cols = ", ".join(data)
    marks = ", ".join("?" for _ in data)
    cur = conn.execute(f"INSERT INTO decorati ({cols}) VALUES ({marks})", tuple(data.values()))
    conn.commit()
    return cur.lastrowid


def make_entita(conn, tipo="persona", valore="Rossi Mario", **overrides):
    data = {
        "tipo": tipo, "valore": valore,
        "valore_normalizzato": valore.strip().lower(),
        "cognome": overrides.pop("cognome", valore.split()[0] if valore else ""),
        "nome": overrides.pop("nome", " ".join(valore.split()[1:]) if valore else ""),
        "fonte_tabella": "internati", "fonte_id": 1,
        "elaborato_il": _now(),
    }
    data.update(overrides)
    cols = ", ".join(data)
    marks = ", ".join("?" for _ in data)
    cur = conn.execute(f"INSERT INTO entita ({cols}) VALUES ({marks})", tuple(data.values()))
    conn.commit()
    return cur.lastrowid


def make_collegamento(conn, entita_id, tabella_origine="internati", record_id=1, **overrides):
    data = {
        "entita_id": entita_id, "tabella_origine": tabella_origine,
        "record_id": record_id, "tipo_collegamento": "menzionato",
        "confidenza": 0.8, "elaborato_il": _now(),
    }
    data.update(overrides)
    cols = ", ".join(data)
    marks = ", ".join("?" for _ in data)
    cur = conn.execute(f"INSERT INTO collegamenti ({cols}) VALUES ({marks})", tuple(data.values()))
    conn.commit()
    return cur.lastrowid


def make_fonte_indice(conn, **overrides):
    data = {
        "archivio": "NARA", "fondo": "T315", "segnatura": "T315-1299-0001",
        "titolo": "Documento di test", "tipo_fonte": "documento",
        "persone_possibili": "Rossi Mario", "reparto": "", "luogo": "",
        "url_catalogo": "https://catalog.archives.gov/id/test",
        "access_type": "online", "fetch_status": "mai_scaricato",
        "confidence": 0.5, "created_at": _now(),
    }
    data.update(overrides)
    cols = ", ".join(data)
    marks = ", ".join("?" for _ in data)
    cur = conn.execute(f"INSERT INTO fonti_indice ({cols}) VALUES ({marks})", tuple(data.values()))
    conn.commit()
    return cur.lastrowid


def make_caduto_albooro(conn, **overrides):
    data = {
        "source_id": "TEST-ALBO-1", "volume_id": "1",
        "volume_name": "Abruzzo e Molise", "nominativo": "Rossi Mario",
        "paternita": "di Giuseppe", "classe": "1890", "comune_attuale": "Roma",
        "grado": "Soldato", "reparto": "3° Reggimento", "anno_morte": "1916",
        "luogo_morte": "Carso", "causa_morte": "Caduto in azione",
        "detail_url": "", "img_url": "", "elaborato_il": _now(),
    }
    data.update(overrides)
    cols = ", ".join(data)
    marks = ", ".join("?" for _ in data)
    cur = conn.execute(f"INSERT INTO caduti_albooro ({cols}) VALUES ({marks})", tuple(data.values()))
    conn.commit()
    return cur.lastrowid

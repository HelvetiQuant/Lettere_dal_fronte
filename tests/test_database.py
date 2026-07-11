"""Test per database.py — schema, CRUD di base, ricerca incrociata.

Copre in particolare due bug storici gia' emersi nel progetto (vedi
TODO.md #1 "Fix tecnici"):
  1. search_all() con query multi-parola ("Rossi Mario") doveva restituire
     0 risultati anche quando il dato esisteva (fix: tokenizzazione).
  2. search_all() include SELECT su `fonti_narrative`, tabella che nel DB
     base (solo database.init_db()) non esiste ancora: deve degradare in
     silenzio (try/except), non far esplodere l'intera ricerca.
Se uno di questi due comportamenti regredisce, i test qui sotto falliscono.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _helpers import TempDBTestCase
from factories import make_internato, make_decorato, make_entita, make_collegamento

import database


class TestSchema(TempDBTestCase):
    def test_init_db_crea_tabelle_base(self):
        conn = self.conn()
        tables = {r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()}
        conn.close()
        attese = {"internati", "progress", "fondi_archivistici", "menzioni",
                  "decorati", "entita", "collegamenti", "ai_ricerche"}
        mancanti = attese - tables
        self.assertFalse(mancanti, f"Tabelle attese mancanti dopo init_db(): {mancanti}")

    def test_init_db_e_idempotente(self):
        # Richiamare init_db() due volte non deve sollevare errori
        # (usato ad ogni startup di app.py).
        database.init_db()
        database.init_db()


class TestInternatiCRUD(TempDBTestCase):
    def test_save_e_get_internato(self):
        conn = self.conn()
        rid = make_internato(conn, cognome="Gaiaschi", nome="Luigi")
        conn.close()

        row = database.get_internato_by_id(rid)
        self.assertIsNotNone(row)
        self.assertEqual(row["cognome"], "Gaiaschi")
        self.assertEqual(row["nome"], "Luigi")

    def test_update_internato(self):
        conn = self.conn()
        rid = make_internato(conn)
        conn.close()

        ok = database.update_internato(rid, {"sorte": "Deceduto in prigionia"})
        self.assertTrue(ok)
        row = database.get_internato_by_id(rid)
        self.assertEqual(row["sorte"], "Deceduto in prigionia")

    def test_delete_internato(self):
        conn = self.conn()
        rid = make_internato(conn)
        conn.close()

        self.assertTrue(database.delete_internato(rid))
        self.assertIsNone(database.get_internato_by_id(rid))

    def test_count_internati(self):
        conn = self.conn()
        make_internato(conn, cognome="Uno")
        make_internato(conn, cognome="Due")
        conn.close()
        self.assertEqual(database.count_internati(), 2)


class TestSearchAll(TempDBTestCase):
    """Copre la regressione descritta in TODO_2026-07-10.md Priorita' 4."""

    def test_query_multiparola_trova_il_record(self):
        conn = self.conn()
        make_internato(conn, cognome="Gaiaschi", nome="Giuseppe")
        conn.close()

        risultati = database.search_all("Gaiaschi Giuseppe")
        self.assertGreaterEqual(len(risultati["internati"]), 1,
            "Bug storico: search_all('Cognome Nome') non trova il record. "
            "Verificare _tokenize()/_where_like_clause() in database.py.")

    def test_query_singola_parola_trova_il_record(self):
        conn = self.conn()
        make_internato(conn, cognome="Verdi", nome="Anna")
        conn.close()
        risultati = database.search_all("Verdi")
        self.assertEqual(len(risultati["internati"]), 1)

    def test_query_vuota_non_esplode(self):
        risultati = database.search_all("")
        self.assertEqual(risultati["internati"], [])
        self.assertEqual(risultati["tokens"], [])

    def test_fonti_narrative_assente_non_fa_fallire_la_ricerca(self):
        """`fonti_narrative` non esiste nello schema base (viene creata solo
        da schema_proposal_fonti_narrative.sql, eseguito a parte). search_all()
        deve comunque completare e restituire una lista vuota per quella
        chiave, non sollevare sqlite3.OperationalError."""
        conn = self.conn()
        make_internato(conn, cognome="Rossi", nome="Mario")
        conn.close()

        risultati = database.search_all("Rossi Mario")
        self.assertIn("fonti_narrative", risultati)
        self.assertEqual(risultati["fonti_narrative"], [])

    def test_fonti_narrative_presente_viene_interrogata(self):
        """Quando la tabella esiste (dopo la migrazione), search_all() deve
        includerne i risultati pertinenti."""
        conn = self.conn()
        conn.executescript("""
            CREATE TABLE fonti_narrative (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                nome_file TEXT, formato TEXT, tipo_fonte TEXT, archivio TEXT,
                autore TEXT, soggetti_json TEXT, persone_possibili TEXT,
                titolo TEXT, descrizione TEXT, testo_ocr TEXT, data_documento TEXT,
                path_locale TEXT
            );
        """)
        conn.execute(
            "INSERT INTO fonti_narrative (nome_file, persone_possibili, titolo, path_locale) "
            "VALUES (?, ?, ?, ?)",
            ("lettera_gaiaschi.pdf", "Gaiaschi Luigi", "Lettera dal fronte", "/tmp/x.pdf"),
        )
        conn.commit()
        conn.close()

        risultati = database.search_all("Gaiaschi Luigi")
        self.assertEqual(len(risultati["fonti_narrative"]), 1)


class TestEntitaCollegamenti(TempDBTestCase):
    def test_save_entita_e_collegamenti(self):
        conn = self.conn()
        eid = make_entita(conn, tipo="persona", valore="Rossi Mario")
        make_collegamento(conn, eid, tabella_origine="internati", record_id=1)
        conn.close()

        self.assertEqual(database.count_entita(), 1)
        self.assertEqual(database.count_collegamenti(), 1)

    def test_get_collegamenti_entita(self):
        conn = self.conn()
        rid = make_internato(conn, cognome="Rossi", nome="Mario")
        eid = make_entita(conn)
        make_collegamento(conn, eid, tabella_origine="internati", record_id=rid)
        conn.close()

        dettaglio = database.get_collegamenti_entita(eid)
        self.assertEqual(dettaglio["entita"]["id"], eid)
        self.assertEqual(len(dettaglio["collegamenti"]), 1)
        self.assertEqual(dettaglio["collegamenti"][0]["tabella"], "internati")

    def test_get_collegamenti_entita_ignora_tabelle_non_mappate(self):
        """GAP REALE (trovato scrivendo questo test, non solo ipotetico):
        get_collegamenti_entita() risolve solo 4 tabelle hardcoded
        (internati, decorati, fondi_archivistici, menzioni). Un collegamento
        verso caduti_albooro/caduti_cwgc/caduti_ministero/caduti_sardi/
        caduti_bologna/decorati_nastroazzurro/fonti_narrative/lettere_personali
        viene silenziosamente scartato, anche se il record collegato esiste.
        Dato che questi dataset da soli generano la maggioranza dei
        collegamenti nel grafo reale (vedi CHANGELOG: caduti_albooro
        1.092.843 link, quasi il doppio di internati+decorati insieme),
        la vista dettaglio entita' e' oggi strutturalmente incompleta per
        la maggior parte dei nodi del grafo.
        Questo test documenta il comportamento ATTUALE (collegamento
        scartato). Se in futuro get_collegamenti_entita() viene esteso per
        risolvere anche caduti_albooro, questo test va aggiornato per
        aspettarsi il record risolto, non piu' scartato."""
        conn = self.conn()
        eid = make_entita(conn)
        make_collegamento(conn, eid, tabella_origine="caduti_albooro", record_id=1)
        conn.close()

        dettaglio = database.get_collegamenti_entita(eid)
        self.assertEqual(len(dettaglio["collegamenti"]), 0,
            "Se questo assert fallisce con collegamenti > 0, "
            "get_collegamenti_entita() e' stata estesa: bella notizia, "
            "aggiorna il commento/assert di questo test.")


class TestExport(TempDBTestCase):
    def test_export_excel_produce_file(self):
        conn = self.conn()
        make_internato(conn)
        conn.close()
        path = database.export_excel(output_path=str(Path(self.db_path).parent / "export.xlsx"))
        self.assertTrue(Path(path).exists())

    def test_export_csv_produce_file(self):
        conn = self.conn()
        make_internato(conn)
        conn.close()
        path = database.export_csv(output_path=str(Path(self.db_path).parent / "export.csv"))
        self.assertTrue(Path(path).exists())


if __name__ == "__main__":
    import unittest
    unittest.main()

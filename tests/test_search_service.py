"""Test per search_service.py — ricerca FTS5/BM25 e grafo entita'/collegamenti.

La tabella virtuale `idx_entita_search` non viene creata da database.init_db():
la crea `db_init_fts.py` (migrazione a parte, coi trigger di sincronizzazione).
Qui riusiamo le funzioni vere di db_init_fts.py (create_fts_table,
create_triggers) invece di duplicarne la DDL: se la migrazione cambia,
questi test la seguono senza bisogno di aggiornarli a mano.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _helpers import TempDBTestCase
from factories import make_entita, make_collegamento, make_internato

import search_service
from db_init_fts import create_fts_table, create_triggers


class FTSTestCase(TempDBTestCase):
    """Base per i test che richiedono idx_entita_search + trigger attivi."""

    def setUp(self):
        super().setUp()
        conn = self.conn()
        create_fts_table(conn)
        create_triggers(conn)
        conn.close()


class TestSearchEntities(FTSTestCase):
    def test_trova_entita_per_cognome(self):
        conn = self.conn()
        make_entita(conn, tipo="persona", valore="Gaiaschi Luigi",
                    cognome="Gaiaschi", nome="Luigi")
        conn.close()

        risultati = search_service.search_entities("Gaiaschi")
        self.assertGreaterEqual(len(risultati), 1)
        self.assertEqual(risultati[0]["cognome"], "Gaiaschi")

    def test_query_vuota_ritorna_lista_vuota(self):
        self.assertEqual(search_service.search_entities(""), [])
        self.assertEqual(search_service.search_entities("   "), [])

    def test_filtro_per_tipo(self):
        conn = self.conn()
        make_entita(conn, tipo="persona", valore="Trento Persona Fittizia")
        make_entita(conn, tipo="luogo", valore="Trento")
        conn.close()

        solo_luoghi = search_service.search_entities("Trento", tipo="luogo")
        self.assertTrue(all(r["tipo"] == "luogo" for r in solo_luoghi))

    def test_trigger_sync_su_insert_update_delete(self):
        """L'indice FTS5 deve restare sincronizzato con `entita` tramite i
        trigger AFTER INSERT/UPDATE/DELETE (vedi db_init_fts.create_triggers).
        """
        conn = self.conn()
        eid = make_entita(conn, valore="Prova Sync", cognome="Prova", nome="Sync")
        conn.close()
        self.assertEqual(len(search_service.search_entities("Prova Sync")), 1)

        conn = self.conn()
        conn.execute("UPDATE entita SET valore=?, cognome=?, nome=? WHERE id=?",
                     ("Zelinda Ultimo", "Zelinda", "Ultimo", eid))
        conn.commit()
        conn.close()
        self.assertEqual(len(search_service.search_entities("Prova Sync")), 0,
            "Il vecchio testo non deve piu' essere trovabile dopo l'UPDATE "
            "(il trigger trg_entita_au deve rimuovere la vecchia riga FTS).")
        self.assertEqual(len(search_service.search_entities("Zelinda Ultimo")), 1)

        conn = self.conn()
        conn.execute("DELETE FROM entita WHERE id=?", (eid,))
        conn.commit()
        conn.close()
        self.assertEqual(len(search_service.search_entities("Aggiornata")), 0)


class TestSearchWithoutFTS(TempDBTestCase):
    """Senza idx_entita_search (schema base non lo crea): search_entities()
    deve degradare a lista vuota, non sollevare sqlite3.OperationalError."""

    def test_niente_fts_non_esplode(self):
        risultati = search_service.search_entities("qualunque cosa")
        self.assertEqual(risultati, [])


class TestEntityNetwork(FTSTestCase):
    def test_due_entita_sullo_stesso_record_sono_collegate(self):
        """get_entity_network trova le entita' che condividono lo STESSO
        record sorgente (tabella_origine, record_id) dell'entita' di partenza
        — es. un soldato e il suo reparto menzionati nella stessa riga di
        `internati`. Un singolo collegamento isolato non produce archi."""
        conn = self.conn()
        rid = make_internato(conn, cognome="Rossi", nome="Mario")
        persona = make_entita(conn, tipo="persona", valore="Rossi Mario", cognome="Rossi", nome="Mario")
        reparto = make_entita(conn, tipo="evento", valore="Stalag VII")
        make_collegamento(conn, persona, tabella_origine="internati", record_id=rid)
        make_collegamento(conn, reparto, tabella_origine="internati", record_id=rid)
        conn.close()

        rete = search_service.get_entity_network(persona, max_depth=2)
        self.assertEqual(rete["center"], persona)
        nodi_trovati = {n["id"] for n in rete["nodes"]}
        self.assertIn(reparto, nodi_trovati,
            "L'entita' 'reparto' condivide lo stesso record di 'persona': "
            "deve comparire come nodo collegato.")
        self.assertGreaterEqual(rete["edge_count"], 1)

    def test_entita_isolata_non_ha_archi(self):
        conn = self.conn()
        rid = make_internato(conn)
        eid = make_entita(conn)
        make_collegamento(conn, eid, tabella_origine="internati", record_id=rid)
        conn.close()

        rete = search_service.get_entity_network(eid)
        self.assertEqual(rete["edge_count"], 0)
        self.assertEqual(rete["node_count"], 1)  # solo il nodo centrale

    def test_entita_inesistente_non_esplode(self):
        rete = search_service.get_entity_network(999999)
        self.assertIsInstance(rete, dict)
        self.assertEqual(rete["node_count"], 0)


if __name__ == "__main__":
    import unittest
    unittest.main()

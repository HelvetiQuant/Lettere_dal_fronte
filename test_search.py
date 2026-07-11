"""Test suite per l'IR Layer (FTS5 + Graph CTE).

Usa il DB reale (imi_internati.db) con assert non distruttivi.
I test di trigger sync usano entita' temporanee che vengono pulite.

Esegui con: python -m pytest test_search.py -v
Oppure:      python test_search.py
"""
import sqlite3
import unittest
from database import get_conn, DB_PATH
from search_service import (
    search_entities,
    get_entity_network,
    get_entity_full_context,
    get_fts_stats,
    _normalize_query,
)


class TestFTS5Sync(unittest.TestCase):
    """Test sincronizzazione trigger FTS5 su INSERT/UPDATE/DELETE."""

    @classmethod
    def setUpClass(cls):
        cls.conn = get_conn()
        cls.test_valore = "ZZZ_TEST_ENTITY_FTS5"
        cls.test_cognome = "ZZZTEST"
        cls.test_nome = "Probe"

    @classmethod
    def tearDownClass(cls):
        cls.conn.close()

    def tearDown(self):
        self.conn.execute(
            "DELETE FROM entita WHERE valore = ?", (self.test_valore,)
        )
        self.conn.commit()

    def test_01_insert_sync(self):
        """Trigger AFTER INSERT: nuovo record in entita deve apparire in FTS5."""
        cur = self.conn.execute(
            """INSERT INTO entita (tipo, valore, cognome, nome, luogo, contesto, fonte_tabella, fonte_id, elaborato_il)
               VALUES ('persona', ?, ?, ?, 'TestCity', 'test context', 'internati', 999999, '2026-01-01')""",
            (self.test_valore, self.test_cognome, self.test_nome)
        )
        self.conn.commit()
        new_id = cur.lastrowid

        row = self.conn.execute(
            "SELECT COUNT(*) FROM idx_entita_search WHERE entita_id = ?", (new_id,)
        ).fetchone()
        self.assertEqual(row[0], 1, "Record non sincronizzato in FTS5 dopo INSERT")

    def test_02_update_sync(self):
        """Trigger AFTER UPDATE: modifica in entita deve propagarsi a FTS5."""
        cur = self.conn.execute(
            """INSERT INTO entita (tipo, valore, cognome, nome, luogo, contesto, fonte_tabella, fonte_id, elaborato_il)
               VALUES ('persona', ?, ?, ?, 'OldCity', 'old context', 'internati', 999998, '2026-01-01')""",
            (self.test_valore, self.test_cognome, self.test_nome)
        )
        self.conn.commit()
        new_id = cur.lastrowid

        self.conn.execute(
            "UPDATE entita SET luogo = 'NewCityUpdated' WHERE id = ?", (new_id,)
        )
        self.conn.commit()

        row = self.conn.execute(
            "SELECT COUNT(*) FROM idx_entita_search WHERE entita_id = ? AND idx_entita_search MATCH 'NewCityUpdated'",
            (new_id,)
        ).fetchone()
        self.assertEqual(row[0], 1, "FTS5 non aggiornato dopo UPDATE")

        row_old = self.conn.execute(
            "SELECT COUNT(*) FROM idx_entita_search WHERE entita_id = ? AND idx_entita_search MATCH 'OldCity'",
            (new_id,)
        ).fetchone()
        self.assertEqual(row_old[0], 0, "Vecchio valore ancora presente in FTS5 dopo UPDATE")

    def test_03_delete_sync(self):
        """Trigger AFTER DELETE: record eliminato da entita deve sparire da FTS5."""
        cur = self.conn.execute(
            """INSERT INTO entita (tipo, valore, cognome, nome, luogo, contesto, fonte_tabella, fonte_id, elaborato_il)
               VALUES ('persona', ?, ?, ?, 'DeleteCity', 'delete context', 'internati', 999997, '2026-01-01')""",
            (self.test_valore, self.test_cognome, self.test_nome)
        )
        self.conn.commit()
        new_id = cur.lastrowid

        self.conn.execute("DELETE FROM entita WHERE id = ?", (new_id,))
        self.conn.commit()

        row = self.conn.execute(
            "SELECT COUNT(*) FROM idx_entita_search WHERE entita_id = ?", (new_id,)
        ).fetchone()
        self.assertEqual(row[0], 0, "Record ancora presente in FTS5 dopo DELETE")


class TestBM25Search(unittest.TestCase):
    """Test Full-Text Search con BM25 ranking."""

    def test_01_search_persona(self):
        """Ricerca per cognome deve trovare persone."""
        results = search_entities("ROSSI", limit=5)
        self.assertIsInstance(results, list)
        self.assertGreater(len(results), 0, "Nessun risultato per 'ROSSI'")
        for r in results:
            self.assertIn("entita_id", r)
            self.assertIn("rank", r)
            self.assertIn("valore", r)

    def test_02_search_luogo(self):
        """Ricerca per luogo deve trovare entita' di tipo luogo."""
        results = search_entities("Agrigento", limit=5, tipo="luogo")
        self.assertIsInstance(results, list)
        self.assertGreater(len(results), 0, "Nessun risultato per 'Agrigento' tipo=luogo")
        for r in results:
            self.assertEqual(r["tipo"], "luogo")

    def test_03_search_prefix(self):
        """Prefix matching: 'Ross*' deve trovare Rossi, Rosso, etc."""
        results = search_entities("Ross*", limit=10)
        self.assertIsInstance(results, list)
        self.assertGreater(len(results), 0, "Nessun risultato per prefix 'Ross*'")

    def test_04_search_empty(self):
        """Query vuota deve ritornare lista vuota."""
        results = search_entities("", limit=10)
        self.assertEqual(results, [])

    def test_05_search_spaces_only(self):
        """Query con solo spazi deve ritornare lista vuota."""
        results = search_entities("   ", limit=10)
        self.assertEqual(results, [])

    def test_06_search_multi_word(self):
        """Ricerca multi-parola: nome + cognome."""
        results = search_entities("ALTA Antonio", limit=5)
        self.assertIsInstance(results, list)
        if results:
            self.assertIn("entita_id", results[0])

    def test_07_search_nonexistent(self):
        """Ricerca di stringa inesistente deve ritornare lista vuota."""
        results = search_entities("ZZZNOMECHENONESISTE12345", limit=10)
        self.assertEqual(results, [])

    def test_08_bm25_ranking_order(self):
        """BM25 deve ordinare per rilevanza (rank crescente = piu' rilevante)."""
        results = search_entities("Milano", limit=10)
        if len(results) >= 2:
            for i in range(len(results) - 1):
                self.assertLessEqual(
                    results[i]["rank"], results[i + 1]["rank"] + 0.001,
                    "Risultati non ordinati per rank BM25"
                )

    def test_09_search_evento(self):
        """Ricerca per tipo evento."""
        results = search_entities("deceduto", limit=5, tipo="evento")
        self.assertIsInstance(results, list)
        self.assertGreater(len(results), 0, "Nessun risultato per 'deceduto' tipo=evento")
        for r in results:
            self.assertEqual(r["tipo"], "evento")


class TestGraphTraversal(unittest.TestCase):
    """Test graph traversal via CTE/JOIN."""

    @classmethod
    def setUpClass(cls):
        cls.conn = get_conn()
        row = cls.conn.execute(
            """SELECT c.entita_id, COUNT(DISTINCT c2.entita_id) as n_neighbors
               FROM collegamenti c
               JOIN collegamenti c2
                 ON c.tabella_origine = c2.tabella_origine
                AND c.record_id = c2.record_id
               WHERE c2.entita_id != c.entita_id
               GROUP BY c.entita_id
               ORDER BY n_neighbors DESC
               LIMIT 1"""
        ).fetchone()
        cls.hub_entity_id = row["entita_id"] if row else 1
        cls.hub_neighbors = row["n_neighbors"] if row else 0

    @classmethod
    def tearDownClass(cls):
        cls.conn.close()

    def test_01_network_depth2(self):
        """get_entity_network con depth=2 deve trovare entita' collegate."""
        net = get_entity_network(self.hub_entity_id, max_depth=2)
        self.assertIsInstance(net, dict)
        self.assertIn("nodes", net)
        self.assertIn("edges", net)
        self.assertIn("center", net)
        self.assertEqual(net["center"], self.hub_entity_id)
        self.assertGreater(net["node_count"], 1, "Nessun nodo collegato trovato")
        self.assertGreater(net["edge_count"], 0, "Nessun edge trovato")

    def test_02_network_structure(self):
        """Il grafo deve avere nodi con campi validi."""
        net = get_entity_network(self.hub_entity_id, max_depth=2)
        for node in net["nodes"]:
            self.assertIn("id", node)
            self.assertIn("tipo", node)
            self.assertIn("valore", node)

    def test_03_network_edges_format(self):
        """Gli edge devono avere source, target, via_record."""
        net = get_entity_network(self.hub_entity_id, max_depth=2)
        for edge in net["edges"]:
            self.assertIn("source", edge)
            self.assertIn("target", edge)
            self.assertIn("via_record", edge)

    def test_04_network_no_self_loop(self):
        """Nessun edge deve avere source == target."""
        net = get_entity_network(self.hub_entity_id, max_depth=2)
        for edge in net["edges"]:
            self.assertNotEqual(edge["source"], edge["target"], "Self-loop trovato")

    def test_05_network_recursive_depth3(self):
        """get_entity_network con depth=3 (recursive CTE) deve funzionare."""
        net = get_entity_network(self.hub_entity_id, max_depth=3)
        self.assertIsInstance(net, dict)
        self.assertIn("nodes", net)
        self.assertGreater(net["node_count"], 0)

    def test_06_network_nonexistent_entity(self):
        """Entity ID inesistente deve ritornare grafo vuoto."""
        net = get_entity_network(999999999, max_depth=2)
        self.assertIsInstance(net, dict)
        self.assertEqual(net["node_count"], 0)

    def test_07_network_center_in_nodes(self):
        """L'entita' centro deve essere nei nodi."""
        net = get_entity_network(self.hub_entity_id, max_depth=2)
        node_ids = [n["id"] for n in net["nodes"]]
        self.assertIn(self.hub_entity_id, node_ids, "Centro non nei nodi")


class TestEntityFullContext(unittest.TestCase):
    """Test get_entity_full_context - deep-dive relazionale."""

    @classmethod
    def setUpClass(cls):
        cls.conn = get_conn()
        row = cls.conn.execute(
            "SELECT id FROM entita WHERE fonte_tabella = 'internati' AND fonte_id IS NOT NULL LIMIT 1"
        ).fetchone()
        cls.sample_entity_id = row["id"] if row else 1

    @classmethod
    def tearDownClass(cls):
        cls.conn.close()

    def test_01_full_context_existing(self):
        """get_entity_full_context su entita' esistente deve ritornare dati completi."""
        ctx = get_entity_full_context(self.sample_entity_id)
        self.assertIsInstance(ctx, dict)
        self.assertIsNotNone(ctx["entity"])
        self.assertEqual(ctx["entity"]["id"], self.sample_entity_id)

    def test_02_full_context_source_record(self):
        """Il record sorgente deve essere risolto dinamicamente."""
        ctx = get_entity_full_context(self.sample_entity_id)
        self.assertIsNotNone(ctx["source_record"], "Record sorgente non risolto")
        self.assertIsNotNone(ctx["source_table"], "Tabella sorgente non impostata")
        if ctx["source_record"] and "error" not in ctx["source_record"]:
            self.assertIn("id", ctx["source_record"])

    def test_03_full_context_collegamenti(self):
        """Deve restituire i collegamenti dell'entita'."""
        ctx = get_entity_full_context(self.sample_entity_id)
        self.assertIsInstance(ctx["collegamenti"], list)

    def test_04_full_context_nonexistent(self):
        """Entity ID inesistente deve gestire gracefully."""
        ctx = get_entity_full_context(999999999)
        self.assertIsNone(ctx["entity"])
        self.assertIn("error", ctx)

    def test_05_full_context_all_source_tables(self):
        """Verifica che tutte le tabelle sorgente mappate siano accessibili."""
        from search_service import SOURCE_TABLE_FIELDS
        for table_name in SOURCE_TABLE_FIELDS:
            row = self.conn.execute(
                "SELECT id FROM entita WHERE fonte_tabella = ? LIMIT 1",
                (table_name,)
            ).fetchone()
            if row:
                ctx = get_entity_full_context(row["id"])
                self.assertEqual(ctx["source_table"], table_name,
                                 f"Tabella {table_name} non risolta correttamente")


class TestNormalizeQuery(unittest.TestCase):
    """Test utility di normalizzazione query."""

    def test_01_empty(self):
        self.assertEqual(_normalize_query(""), "")
        self.assertEqual(_normalize_query("   "), "")

    def test_02_single_word_prefix(self):
        result = _normalize_query("Rossi")
        self.assertIn("*", result)

    def test_03_already_has_wildcard(self):
        result = _normalize_query("Ross*")
        self.assertEqual(result, "Ross*")

    def test_04_multi_word(self):
        result = _normalize_query("Rossi Mario")
        self.assertIn("*", result)


class TestFTSStats(unittest.TestCase):
    """Test statistiche indice."""

    def test_01_stats_structure(self):
        stats = get_fts_stats()
        self.assertIsInstance(stats, dict)
        self.assertIn("fts5_indexed", stats)
        self.assertIn("entita_total", stats)
        self.assertIn("collegamenti_total", stats)
        self.assertIn("synced", stats)
        self.assertIn("tipi", stats)
        self.assertIn("fonti", stats)

    def test_02_stats_synced(self):
        stats = get_fts_stats()
        self.assertTrue(stats["synced"], "FTS5 non sincronizzato con entita")
        self.assertGreater(stats["entita_total"], 0)

    def test_03_stats_tipi(self):
        stats = get_fts_stats()
        self.assertIn("persona", stats["tipi"])
        self.assertIn("luogo", stats["tipi"])
        self.assertGreater(stats["tipi"]["persona"], 0)


if __name__ == "__main__":
    unittest.main(verbosity=2)

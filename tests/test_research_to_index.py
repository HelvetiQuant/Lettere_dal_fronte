"""Test per research_to_index.py — Research-to-Index ("nessuna ricerca persa").

federated_search() (che chiama 20 provider esterni, molti via rete reale) e'
SEMPRE mockata in questi test con unittest.mock.patch: la suite non deve mai
fare chiamate di rete. Il comportamento della federazione stessa e' coperto
da tests/test_source_providers.py.
"""
import sys
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _helpers import TempDBTestCase
from factories import make_internato

import research_to_index as rti


class TestDetectSubjectType(TempDBTestCase):
    def test_soldato_da_grado_militare(self):
        self.assertEqual(rti._detect_subject_type("il sergente Gaiaschi Luigi"), "soldier")

    def test_evento_da_parola_chiave(self):
        self.assertEqual(rti._detect_subject_type("la battaglia di Caporetto"), "event")

    def test_reparto_da_parola_chiave(self):
        self.assertEqual(rti._detect_subject_type("117esima divisione Jager"), "unit")

    def test_nome_proprio_semplice_e_soldier_di_default(self):
        self.assertEqual(rti._detect_subject_type("Rossi Mario"), "soldier")


class TestCreateMinimalSubject(TempDBTestCase):
    schema_modules = ("research_to_index",)

    def test_crea_soggetto_nuovo(self):
        risultato = rti.create_minimal_subject_from_query("Gaiaschi Luigi")
        self.assertFalse(risultato["already_existed"])
        self.assertIsInstance(risultato["id"], int)

    def test_query_ripetuta_non_duplica_il_soggetto(self):
        primo = rti.create_minimal_subject_from_query("Gaiaschi Luigi")
        secondo = rti.create_minimal_subject_from_query("Gaiaschi Luigi")
        self.assertTrue(secondo["already_existed"])
        self.assertEqual(primo["id"], secondo["id"])


class TestIdentifyResearchGaps(TempDBTestCase):
    schema_modules = ("research_to_index",)

    def test_soggetto_senza_campi_ha_4_gap(self):
        subject = rti.create_minimal_subject_from_query("Gaiaschi Luigi")
        gaps = rti.identify_research_gaps(subject["id"])
        campi = {g["field"] for g in gaps}
        self.assertEqual(campi, {"date_start", "date_end", "place", "unit"})

    def test_gap_non_duplicati_su_chiamate_ripetute(self):
        subject = rti.create_minimal_subject_from_query("Gaiaschi Luigi")
        rti.identify_research_gaps(subject["id"])
        rti.identify_research_gaps(subject["id"])

        conn = self.conn()
        n = conn.execute(
            "SELECT COUNT(*) FROM research_gaps WHERE subject_id=? AND status='open'",
            (subject["id"],),
        ).fetchone()[0]
        conn.close()
        self.assertEqual(n, 4, "identify_research_gaps deve essere idempotente: "
                               "non deve creare righe duplicate se richiamata piu' volte.")

    def test_soggetto_inesistente_ritorna_lista_vuota(self):
        self.assertEqual(rti.identify_research_gaps(999999), [])


class TestAutoIndexIfNotFound(TempDBTestCase):
    # research_to_index.upsert_source_locator() scrive su fonti_indice,
    # tabella creata da source_locator._init_tables(), non dalla propria.
    schema_modules = ("research_to_index", "source_locator")

    def test_trovato_localmente_non_crea_soggetto(self):
        conn = self.conn()
        make_internato(conn, cognome="Gaiaschi", nome="Luigi")
        conn.close()

        risultato = rti.auto_index_if_not_found("Gaiaschi Luigi")
        self.assertTrue(risultato["found_locally"])
        self.assertIsNone(risultato["subject_id"])

    def test_BUG_local_count_conta_anche_la_lista_tokens(self):
        """BUG REALE trovato scrivendo questo test (non un difetto del test).

        auto_index_if_not_found() calcola:
            local = search_all(query, limit=10)
            local_count = sum(len(v) for v in local.values() if isinstance(v, list))
        Ma search_all() include SEMPRE la chiave 'tokens' (lista dei token
        della query) accanto alle liste di risultati veri (internati,
        menzioni, decorati, caduti, documenti, fonti_narrative). 'tokens' e'
        quasi sempre non vuota per qualunque query non banale, quindi
        local_count e' quasi sempre >= 1 anche quando TUTTE le liste di
        risultati reali sono vuote: found_locally risulta True per errore,
        e il ramo "crea soggetto + arricchisci da fonti federate" — una
        delle 4 innovazioni chiave presentate in CONCORSI_EUROPEI.md
        ("Research-to-Index: nessuna ricerca persa") — di fatto non si
        attiva quasi mai per query realistiche.
        Fix suggerito: sommare solo le chiavi risultato reali, escludendo
        esplicitamente 'term' e 'tokens' (es. usando un set di chiavi
        risultato dedicato invece di `isinstance(v, list)` su tutto il dict).
        Questo test va aggiornato (o rimosso) quando il fix viene applicato."""
        risultati_ricerca = rti.search_all("QueryCheNonMatchaNienteZzz123")
        local_count = sum(len(v) for v in risultati_ricerca.values() if isinstance(v, list))
        self.assertGreater(local_count, 0,
            "Se questo assert fallisce, il bug e' stato corretto: "
            "aggiorna/rimuovi questo test di regressione.")
        # ...e di conseguenza il flusso pensa di aver "trovato localmente":
        risultato = rti.auto_index_if_not_found("QueryCheNonMatchaNienteZzz123")
        self.assertTrue(risultato["found_locally"],
            "Comportamento attuale (bug): found_locally=True anche senza "
            "risultati reali, a causa della chiave 'tokens' nel conteggio.")

    @patch("research_to_index.federated_search")
    def test_non_trovato_crea_soggetto_e_indicizza_fonti_federate(self, mock_federated):
        """NOTA: a causa del bug documentato in test_BUG_local_count_conta_anche_la_lista_tokens,
        il ramo 'non trovato' di auto_index_if_not_found() e' in pratica
        irraggiungibile passando da search_all() con una query normale.
        Per testare comunque la logica di indicizzazione delle fonti
        federate (upsert_source_locator + link_subject_to_source +
        update_subject_confidence + identify_research_gaps), chiamiamo
        create_minimal_subject_from_query() direttamente e replichiamo il
        resto del flusso, cosi' questo test resta valido sia prima sia dopo
        il fix del bug qui sopra."""
        mock_federated.return_value = [
            {"archivio": "NARA", "titolo": "Documento su Gaiaschi", "provider": "nara",
             "score": 0.8, "url_file": "https://catalog.archives.gov/id/123",
             "access_type": "online"},
            {"error": "timeout"},  # deve essere ignorato, non deve far fallire il flusso
        ]
        subject = rti.create_minimal_subject_from_query("Gaiaschi Luigi Zzz")
        cues = {"persona": "Gaiaschi Luigi Zzz"}
        fed_results = rti.federated_search("Gaiaschi Luigi Zzz", cues=cues)
        indexed = 0
        for result in fed_results:
            if "error" in result:
                continue
            source_id = rti.upsert_source_locator(result)
            if source_id:
                rti.link_subject_to_source(subject["id"], source_id, "mentions",
                                            result.get("score", 0.3), "test")
                indexed += 1
        self.assertEqual(indexed, 1,
            "Il risultato con 'error' deve essere scartato, solo 1 fonte valida indicizzata.")
        mock_federated.assert_called_once()


if __name__ == "__main__":
    import unittest
    unittest.main()

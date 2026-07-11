"""Test per source_locator.py — indice leggero fonti esterne, whitelist domini.

Principio architetturale da preservare (vedi ARCHITETTURA_DB.md Livello 5):
il DB locale salva SOLO metadati; il fetch di un file avviene solo da domini
in AUTHORIZED_DOMAINS. I test su _domain_authorized() sono un guardrail
esplicito contro regressioni di sicurezza (es. whitelist svuotata per
errore, o un dominio aggiunto senza intenzione).
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _helpers import TempDBTestCase
from factories import make_fonte_indice

import source_locator as sl


class TestDomainWhitelist(TempDBTestCase):
    schema_modules = ("source_locator",)

    def test_dominio_autorizzato_esatto(self):
        for dominio in sl.AUTHORIZED_DOMAINS:
            with self.subTest(dominio=dominio):
                self.assertTrue(sl._domain_authorized(f"https://{dominio}/qualcosa"))

    def test_sottodominio_di_dominio_autorizzato(self):
        dominio = next(iter(sl.AUTHORIZED_DOMAINS))
        self.assertTrue(sl._domain_authorized(f"https://sub.{dominio}/x"))

    def test_dominio_non_autorizzato_rifiutato(self):
        self.assertFalse(sl._domain_authorized("https://evil-example-not-authorized.test/x"))

    def test_url_malformato_non_esplode(self):
        self.assertFalse(sl._domain_authorized("non-e-un-url"))
        self.assertFalse(sl._domain_authorized(""))


class TestRegisterSourceMetadata(TempDBTestCase):
    schema_modules = ("source_locator",)

    def test_crea_nuova_scheda(self):
        risultato = sl.register_source_metadata(
            archivio="NARA", segnatura="T315-1299-0001", titolo="Test doc",
            persone_possibili="Rossi Mario", access_type="online",
        )
        self.assertTrue(risultato["created"])
        self.assertIsInstance(risultato["id"], int)

    def test_stessa_scheda_viene_aggiornata_non_duplicata(self):
        primo = sl.register_source_metadata(
            archivio="NARA", segnatura="T315-1299-0001", titolo="Test doc",
            confidence=0.5,
        )
        secondo = sl.register_source_metadata(
            archivio="NARA", segnatura="T315-1299-0001", titolo="Test doc",
            confidence=0.9,
        )
        self.assertFalse(secondo["created"])
        self.assertEqual(primo["id"], secondo["id"])

    def test_campi_non_ammessi_vengono_ignorati(self):
        risultato = sl.register_source_metadata(
            archivio="NARA", segnatura="X", titolo="Y",
            campo_inventato_pericoloso="ignorami",
        )
        self.assertTrue(risultato["created"])  # non deve sollevare errore SQL


class TestFindCandidateSources(TempDBTestCase):
    schema_modules = ("source_locator",)

    def test_trova_per_persona(self):
        conn = self.conn()
        make_fonte_indice(conn, persone_possibili="Gaiaschi Luigi", titolo="Foglio matricolare")
        conn.close()

        risultato = sl.find_candidate_sources("Gaiaschi Luigi")
        self.assertGreaterEqual(risultato["total"], 1)
        self.assertIn("availability", risultato["candidates"][0])

    def test_nessun_cue_usa_fallback_tokenizzato(self):
        conn = self.conn()
        make_fonte_indice(conn, titolo="Diario di guerra inedito", persone_possibili="")
        conn.close()
        # "diario" e "guerra" sono token >3 caratteri: attivano il fallback
        # quando extract_cues() non trova persona/reparto/luogo/archivio/data.
        risultato = sl.find_candidate_sources("diario guerra")
        self.assertIsInstance(risultato["candidates"], list)


if __name__ == "__main__":
    import unittest
    unittest.main()

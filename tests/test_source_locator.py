"""Test per source_locator.py — indice leggero fonti esterne, whitelist domini.

Principio architetturale da preservare (vedi ARCHITETTURA_DB.md Livello 5):
il DB locale salva SOLO metadati; il fetch di un file avviene solo da domini
in AUTHORIZED_DOMAINS. I test su _domain_authorized() sono un guardrail
esplicito contro regressioni di sicurezza (es. whitelist svuotata per
errore, o un dominio aggiunto senza intenzione).
"""
import sys
from pathlib import Path
from unittest.mock import patch

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


class TestImportFontiCatalogo(TempDBTestCase):
    schema_modules = ("source_locator",)

    def test_importa_25_fonti_da_excel(self):
        from import_fonti_catalogo import import_catalogo
        excel = Path(__file__).resolve().parent.parent / "fonti_scrapabili_metadata.xlsx"
        stats = import_catalogo(excel)
        self.assertEqual(stats["total"], 25)
        self.assertEqual(stats["created"], 25)
        self.assertEqual(stats["updated"], 0)

    def test_import_e_idempotente(self):
        from import_fonti_catalogo import import_catalogo
        excel = Path(__file__).resolve().parent.parent / "fonti_scrapabili_metadata.xlsx"
        primo = import_catalogo(excel)
        self.assertEqual(primo["created"], 25)
        secondo = import_catalogo(excel)
        self.assertEqual(secondo["created"], 0)
        self.assertEqual(secondo["updated"], 25)


class TestProviderDirectLinks(TempDBTestCase):
    schema_modules = ("source_locator",)

    def test_tna_build_direct_link(self):
        from source_providers.providers import ProviderNationalArchivesUK
        p = ProviderNationalArchivesUK()
        url = p.build_direct_link("C14567")
        self.assertEqual(url, "https://discovery.nationalarchives.gov.uk/details/r/C14567")

    def test_europeana_build_direct_link(self):
        from source_providers.providers import ProviderEuropeana
        p = ProviderEuropeana()
        url = p.build_direct_link("09312/1038913")
        self.assertEqual(url, "https://www.europeana.eu/en/item/09312/1038913")

    def test_antenati_build_direct_link(self):
        from source_providers.antenati import ProviderAntenati
        p = ProviderAntenati()
        url = p.build_direct_link("an_ua19944535/w9DWR8x")
        self.assertEqual(
            url,
            "https://antenati.cultura.gov.it/ark:/12657/an_ua19944535/w9DWR8x",
        )

    def test_memoire_des_hommes_build_direct_link(self):
        from source_providers.memoire_des_hommes import ProviderMemoireDesHommes
        p = ProviderMemoireDesHommes()
        url = p.build_direct_link("m005239dfea7f0db/5242bcfce998")
        self.assertIn("/fr/ark:/40699/m005239dfea7f0db/5242bcfce998", url)

    def test_ddb_build_direct_link(self):
        from source_providers.deutsche_digitale_bibliothek import ProviderDDB
        p = ProviderDDB()
        url = p.build_direct_link("6NBOK4XF3X5G3H4MYVI6FWV72VUJAAQE")
        self.assertEqual(
            url,
            "https://www.deutsche-digitale-bibliothek.de/item/6NBOK4XF3X5G3H4MYVI6FWV72VUJAAQE",
        )

    def test_iwm_lives_build_direct_link(self):
        from source_providers.iwm_lives import ProviderIWMLives
        p = ProviderIWMLives()
        url = p.build_direct_link("697514")
        self.assertEqual(url, "https://livesofthefirstworldwar.iwm.org.uk/lifestory/697514")

    def test_grand_memorial_build_direct_link(self):
        from source_providers.grand_memorial import ProviderGrandMemorial
        p = ProviderGrandMemorial()
        url = p.build_direct_link("qualunque")
        self.assertIn("donnees.culture.gouv.fr", url)


class TestCatalogDomainsWhitelist(TempDBTestCase):
    schema_modules = ("source_locator",)

    def test_domini_catalogo_in_whitelist(self):
        catalog_domains = {
            "memoiredeshommes.sga.defense.gouv.fr",
            "www.deutsche-digitale-bibliothek.de",
            "livesofthefirstworldwar.iwm.org.uk",
            "donnees.culture.gouv.fr",
            "grandeguerre.icrc.org",
        }
        for d in catalog_domains:
            with self.subTest(dominio=d):
                self.assertTrue(sl._domain_authorized(f"https://{d}/record/123"))


class TestEnrichEntities(TempDBTestCase):
    schema_modules = ("source_locator",)

    def _insert_internati(self, rows):
        conn = self.conn()
        conn.executemany(
            "INSERT INTO internati (id, lettera, file_pdf, pagina, cognome, nome, "
            "data_nascita, luogo_nascita, elaborato_il) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [
                (r[0], "test", "test.pdf", 1, r[1], r[2], r[3], r[4], "2026-01-01")
                for r in rows
            ],
        )
        conn.commit()
        conn.close()

    @patch("enrich_entities.federated_search")
    def test_arricchisce_internati_con_fonti_candidate(self, mock_search):
        from enrich_entities import enrich
        self._insert_internati([
            (1, "Rossi", "Mario", "1895-01-01", "Torino"),
            (2, "Bianchi", "Luigi", "1896-02-02", "Milano"),
        ])
        mock_search.return_value = [
            {
                "provider": "europeana",
                "archivio": "Europeana",
                "titolo": "Test document",
                "source_type": "digitized_document",
                "catalog_url": "https://www.europeana.eu/item/123",
                "direct_url": "",
                "access_type": "online",
                "score": 0.75,
            }
        ]

        stats = enrich(limit=2, max_results_per_entity=1)
        self.assertEqual(stats["processed"], 2)
        self.assertEqual(stats["created"], 2)
        self.assertEqual(stats["errors"], 0)

        conn = self.conn()
        count = conn.execute(
            "SELECT COUNT(*) FROM fonti_indice WHERE archivio='Europeana'"
        ).fetchone()[0]
        conn.close()
        self.assertEqual(count, 2)


if __name__ == "__main__":
    import unittest
    unittest.main()

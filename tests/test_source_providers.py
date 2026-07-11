"""Test 'a contratto' per source_providers/ — federazione di 20 archivi esterni.

IMPORTANTE: nessun test qui chiama provider.search() o provider.get_document()
sui provider reali: la maggior parte fa query HTTP live verso archivi esterni
(NARA, Antenati, CWGC, ecc.), quindi non deve mai girare in questa suite
offline. Questi test controllano solo la CONFORMITA' STRUTTURALE all'interfaccia
SourceProvider (vedi source_providers/base.py): ogni nuovo provider aggiunto
alla federazione viene automaticamente incluso qui, senza scrivere altro
codice — e' un test "living", si estende da solo quando federation.py cresce.

Un test end-to-end con chiamate reali (marcato TODO sotto) va scritto a parte,
eseguito manualmente/in CI schedulata, non nella suite standard.
"""
import re
import sys
from pathlib import Path
from urllib.parse import urlparse

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _helpers import TempDBTestCase

from source_providers.base import SourceProvider, score_source
from source_providers.federation import get_registry


class TestProviderRegistryConformance(TempDBTestCase):
    """Itera su TUTTI i provider registrati: aggiungerne uno nuovo a
    federation.py estende automaticamente la copertura di questi test."""

    def test_almeno_un_provider_registrato(self):
        self.assertGreater(len(get_registry()), 0)

    def test_ogni_provider_ha_nome_univoco(self):
        registry = get_registry()
        nomi = [p.name for p in registry.values()]
        self.assertEqual(len(nomi), len(set(nomi)), "Nomi provider duplicati trovati")

    def test_ogni_provider_rispetta_interfaccia_sourceprovider(self):
        for key, provider in get_registry().items():
            with self.subTest(provider=key):
                self.assertIsInstance(provider, SourceProvider)
                self.assertTrue(provider.name, f"{key}: 'name' vuoto")
                self.assertTrue(provider.display_name, f"{key}: 'display_name' vuoto")
                # search() e get_metadata() sono @abc.abstractmethod: se il
                # provider e' istanziabile, sono per forza implementati.
                self.assertTrue(callable(provider.search))
                self.assertTrue(callable(provider.get_metadata))

    def test_domini_autorizzati_sono_hostname_validi_o_vuoti(self):
        """authorized_domains vuoto e' ammesso (provider 'solo catalogo',
        es. archivio_stato oggi) ma se presente deve essere un hostname
        plausibile, non un URL completo o una stringa vuota nascosta."""
        for key, provider in get_registry().items():
            with self.subTest(provider=key):
                for dominio in provider.authorized_domains:
                    self.assertTrue(dominio, f"{key}: dominio vuoto in authorized_domains")
                    self.assertNotIn("://", dominio,
                        f"{key}: '{dominio}' sembra un URL, non un hostname")

    def test_provider_senza_domini_autorizzati_note(self):
        """Non e' un fallimento: solo un promemoria esplicito su quali
        provider oggi non possono mai passare _domain_authorized() (quindi
        fetch_source_on_demand li rifiutera' sempre). Se questo elenco
        cambia, e' un segnale che vale la pena guardare il TODO relativo."""
        senza_domini = [key for key, p in get_registry().items() if not p.authorized_domains]
        # Non un assert di fallimento: serve solo a rendere visibile la lista
        # nel report di test (usare -v per vederla).
        print(f"\n  Provider senza authorized_domains (solo link a catalogo): {senza_domini}")

    def test_build_direct_link_non_esplode(self):
        for key, provider in get_registry().items():
            with self.subTest(provider=key):
                link = provider.build_direct_link("TEST-RECORD-ID")
                self.assertIsInstance(link, str)
                self.assertTrue(link)


class TestScoreSource(TempDBTestCase):
    """score_source() e' logica pura (nessun I/O): testarla direttamente
    e' molto piu' rapido ed affidabile che passare da una ricerca federata."""

    def test_nessun_cue_da_punteggio_basso_ma_non_zero(self):
        score = score_source({"archivio": "Fonte sconosciuta"}, {})
        self.assertGreater(score, 0.0)
        self.assertLess(score, 0.3)

    def test_match_persona_aumenta_il_punteggio(self):
        base = score_source({"archivio": "x"}, {})
        con_match = score_source(
            {"archivio": "x", "persone_possibili": "Gaiaschi Luigi"},
            {"persona": "Gaiaschi Luigi"},
        )
        self.assertGreater(con_match, base)

    def test_archivio_alta_fiducia_aumenta_il_punteggio(self):
        basso = score_source({"archivio": "sito generico"}, {})
        alto = score_source({"archivio": "NARA"}, {})
        self.assertGreater(alto, basso)

    def test_punteggio_sempre_tra_0_e_1(self):
        estremo = score_source(
            {"archivio": "NARA", "persone_possibili": "Rossi Mario",
             "reparto": "117 Divisione", "luogo": "Trento",
             "data_inizio": "1943", "confidence": 1.0},
            {"persona": "Rossi Mario", "reparto": "117 Divisione",
             "luogo": "Trento", "data": "1943"},
        )
        self.assertLessEqual(estremo, 1.0)


if __name__ == "__main__":
    import unittest
    unittest.main()

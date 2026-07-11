"""Test per linker.py — estrazione entita' e cross-linking.

Nota architetturale importante emersa scrivendo questi test (vedi
test_rerun_duplica_collegamenti_per_internati qui sotto): per le tabelle
"grandi" alimentate da scraper (caduti_ministero, caduti_sardi,
caduti_bologna, caduti_albooro, caduti_cwgc, decorati_nastroazzurro,
caduti_francia_ww1, nara_*) il linker salta i record gia' linkati tramite
_already_linked()/resume. Per internati/decorati/menzioni questa logica di
resume NON esiste: ogni ri-esecuzione di build_links() rielabora tutte le
righe. save_entita() deduplica il nodo `entita` (stesso tipo+valore
normalizzato) ma NON deduplica l'arco `collegamenti` (nessun vincolo UNIQUE
su entita_id+tabella_origine+record_id): il risultato e' che ogni ri-run
del linker duplica gli archi per queste tre tabelle. Non e' un bug che
blocchi funzionalmente la ricerca, ma gonfia i conteggi del grafo (rilevante
per le metriche citate in CONCORSI_EUROPEI.md, es. "2,2M collegamenti").
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _helpers import TempDBTestCase
from factories import make_internato

import linker
import database


class TestNorm(TempDBTestCase):
    def test_normalizza_spazi_e_maiuscole(self):
        self.assertEqual(linker._norm("  Rossi   Mario  "), "rossi mario")
        self.assertEqual(linker._norm(""), "")
        self.assertEqual(linker._norm(None), "")


class TestFindCrossReferences(TempDBTestCase):
    def test_trova_record_per_cognome_in_piu_tabelle(self):
        conn = self.conn()
        make_internato(conn, cognome="Gaiaschi", nome="Luigi")
        conn.close()

        risultati = linker.find_cross_references("Gaiaschi")
        dataset_trovati = {r["dataset"] for r in risultati}
        self.assertIn("internati", dataset_trovati)

    def test_nessun_risultato_ritorna_lista_vuota(self):
        risultati = linker.find_cross_references("NomeCheNonEsisteZZZ")
        self.assertEqual(risultati, [])


class TestBuildLinks(TempDBTestCase):
    def test_estrae_persona_e_luoghi_da_internato(self):
        conn = self.conn()
        make_internato(conn, cognome="Gaiaschi", nome="Luigi",
                        luogo_nascita="Bologna", residenza="Bologna",
                        luogo_internamento="Stalag VII", luogo_cattura="Grecia")
        conn.close()

        linker.build_links(resume=True)

        self.assertGreaterEqual(database.count_entita(), 1)
        persone = linker.find_cross_references("Gaiaschi")
        self.assertTrue(persone)

        conn = self.conn()
        n_persona = conn.execute(
            "SELECT COUNT(*) FROM entita WHERE tipo='persona' AND valore_normalizzato=?",
            ("gaiaschi luigi",),
        ).fetchone()[0]
        conn.close()
        self.assertEqual(n_persona, 1, "save_entita deve deduplicare per (tipo, valore_normalizzato)")

    def test_rerun_duplica_collegamenti_per_internati(self):
        """Documenta il comportamento ATTUALE (vedi docstring del modulo):
        internati/decorati/menzioni non hanno logica di resume, quindi un
        secondo giro di build_links() rielabora le stesse righe e duplica
        gli archi in `collegamenti` (l'entita' resta deduplicata, l'arco no).
        Se in futuro viene aggiunta una dedup anche per queste tre tabelle
        (es. tramite _already_linked come per le altre), questo test va
        aggiornato per aspettarsi conteggio invariato, non raddoppiato."""
        conn = self.conn()
        make_internato(conn, cognome="Verdi", nome="Anna", luogo_nascita="Roma")
        conn.close()

        linker.build_links(resume=True)
        collegamenti_dopo_primo_run = database.count_collegamenti()
        entita_dopo_primo_run = database.count_entita()

        linker.build_links(resume=True)
        collegamenti_dopo_secondo_run = database.count_collegamenti()
        entita_dopo_secondo_run = database.count_entita()

        self.assertEqual(entita_dopo_secondo_run, entita_dopo_primo_run,
            "Le entita' devono restare dedupliate tra un run e l'altro.")
        self.assertEqual(collegamenti_dopo_secondo_run, collegamenti_dopo_primo_run * 2,
            "Comportamento attuale noto: i collegamenti per internati/decorati/"
            "menzioni raddoppiano ad ogni ri-esecuzione. Se questo assert "
            "fallisce perche' il conteggio NON e' raddoppiato, il bug e' stato "
            "risolto: aggiorna questo test per riflettere il nuovo comportamento.")


if __name__ == "__main__":
    import unittest
    unittest.main()

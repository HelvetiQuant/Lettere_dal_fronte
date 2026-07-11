"""Test per enrich_events.py — fonti multilaterali per eventi storici curati."""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _helpers import TempDBTestCase

import enrich_events as ev


class TestEnrichEvents(TempDBTestCase):
    schema_modules = ("source_locator",)

    def test_tutte_le_fonti_vengono_registrate(self):
        stats = ev.main()
        total_fonti = sum(len(e["fonti"]) for e in ev.EVENTS)
        self.assertEqual(stats["events"], len(ev.EVENTS))
        self.assertEqual(stats["registered"], total_fonti)
        self.assertEqual(stats["updated"], 0)
        self.assertEqual(stats["errors"], 0)

        # Verifica presenza in fonti_indice
        conn = self.conn()
        count = conn.execute("SELECT COUNT(*) FROM fonti_indice").fetchone()[0]
        conn.close()
        self.assertEqual(count, total_fonti)

    def test_riesecuzione_idempotente(self):
        # Prima esecuzione: tutte nuove
        stats1 = ev.main()
        total = stats1["registered"]
        self.assertGreater(total, 0)

        # Seconda esecuzione: nessuna nuova, tutte aggiornate
        stats2 = ev.main()
        self.assertEqual(stats2["registered"], 0)
        self.assertEqual(stats2["updated"], total)
        self.assertEqual(stats2["errors"], 0)

    def test_almeno_un_url_per_fazione_italia_asse_alleati(self):
        ev.main()
        conn = self.conn()
        conn.row_factory = lambda c, r: {d[0]: r[i] for i, d in enumerate(c.description)}
        rows = conn.execute("SELECT note, url_catalogo FROM fonti_indice").fetchall()
        conn.close()

        fazioni = {"Italia": [], "Germania/Asse": [], "Alleati": []}
        for r in rows:
            note = r["note"]
            try:
                parsed = json.loads(note) if note else {}
            except Exception:
                parsed = {}
            fazione = parsed.get("fazione", "")
            url = r["url_catalogo"] or ""
            if fazione in fazioni:
                fazioni[fazione].append(url)

        for nome, urls in fazioni.items():
            self.assertTrue(all(urls), f"Fazione {nome} ha URL vuoti")
            self.assertTrue(all(url.startswith("http") for url in urls),
                            f"Fazione {nome} ha URL non HTTP")

    def test_luogo_evento_non_e_troncamento_del_nome(self):
        """Verifica che il campo luogo sia un luogo geografico reale."""
        for e in ev.EVENTS:
            with self.subTest(event=e["evento"]):
                luogo = e.get("luogo", "")
                self.assertTrue(luogo, f"Evento {e['evento']} non ha luogo")
                self.assertNotEqual(luogo, e["evento"].split("(")[0].strip(),
                                    "luogo non deve essere il nome evento troncato")

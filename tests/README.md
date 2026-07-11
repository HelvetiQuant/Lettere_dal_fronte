# Suite di test — VOCI DAL FRONTE / IMI Extractor

Suite modulare basata su `unittest` (stdlib, zero dipendenze extra) e
compatibile anche con `pytest` (che scopre le `unittest.TestCase` senza
bisogno di riscriverle). Scelta deliberata rispetto a `test_search.py`
esistente (che gira sul DB reale `imi_internati.db` con record prefissati
`ZZZ_TEST_` puliti a mano): questa suite gira SEMPRE su un SQLite temporaneo
e isolato, cosi' puo' essere eseguita ovunque — laptop di un nuovo
contributore, CI, sandbox — senza il DB di produzione (>1 GB, mai nel repo)
e senza consumare crediti delle API AI.

## Come eseguirla

```bash
# tutta la suite
python -m unittest discover -s tests -v

# un solo modulo
python -m unittest tests.test_database -v

# con pytest, se preferito (identico risultato, output diverso)
pytest tests/ -v
```

Nessuna configurazione richiesta: niente `.env`, niente chiavi API, niente
`imi_internati.db` reale. Alcuni moduli si auto-saltano (`unittest.skipIf`)
se una dipendenza pesante opzionale non e' installata (es. `pymupdf`/`fitz`
per `biography.py` e `import_personal_sources.py`, `fastapi`/`httpx` per
`test_api.py`): sulla macchina reale, con `pip install -r requirements.txt`
gia' fatto, questi test girano per intero.

## Struttura

| File | Copre |
|---|---|
| `_helpers.py` | `TempDBTestCase`: DB temporaneo isolato, registro moduli con schema/percorsi propri |
| `factories.py` | Helper `make_*()` per creare record di esempio nelle tabelle sorgente |
| `test_database.py` | Schema, CRUD internati, `search_all()` (tokenizzazione, degradazione controllata su `fonti_narrative`), entita'/collegamenti, export |
| `test_search_service.py` | FTS5/BM25, sincronizzazione trigger, grafo entita' (`get_entity_network`) |
| `test_memory_router.py` | `extract_cues()`, `_select_route()`, `route_query()` (sempre `use_cloud_fallback=False`) |
| `test_linker.py` | Estrazione entita', cross-linking, comportamento noto sul resume parziale |
| `test_source_locator.py` | Whitelist domini (guardrail di sicurezza), indice fonti esterne |
| `test_research_to_index.py` | Research-to-Index, incluso il bug noto sul conteggio `local_count` (vedi sotto) |
| `test_soldier_dashboard.py` | Dashboard investigativa, federazione mockata |
| `test_biography.py` | Dossier AI con fallback multi-provider, sempre mockato (skip se manca `pymupdf`) |
| `test_archivio_fonti.py` | Ingestione documenti, dedup SHA256 |
| `test_source_providers.py` | Test "a contratto": ogni provider registrato rispetta l'interfaccia `SourceProvider` — si estende da solo quando se ne aggiunge uno |
| `test_personal_sources_import.py` | Le due pipeline di import lettere/fonti personali (skip parziale se manca `pymupdf`) |
| `test_api.py` | Smoke HTTP su alcuni endpoint chiave via `TestClient` (skip se manca `fastapi`) |
| `test_project_health.py` | Test "living": copertura `requirements.txt`, sanity generiche sullo schema |
| `_TEMPLATE_test_new_module.py` | Copia-e-adatta per ogni nuovo modulo |

## Come estendere la suite

**Nuovo modulo Python** → copia `_TEMPLATE_test_new_module.py` in
`test_<modulo>.py` e segui le istruzioni nel suo docstring.

**Nuova tabella nel DB** → aggiungi un `make_<tabella>()` in `factories.py`
(vedi quelli esistenti come esempio) e, se la tabella viene creata da una
funzione `_init_table()`/`_init_tables()` di un modulo, registra quel modulo
in `MODULES_WITH_SCHEMA_INIT` dentro `_helpers.py`.

**Nuovo provider in `source_providers/`** → nessuna azione richiesta:
`test_source_providers.py` itera automaticamente su tutti i provider
registrati in `federation.get_registry()`.

**Nuova dipendenza esterna (import di terze parti)** → aggiungila a
`requirements.txt`. `test_project_health.py` fallisce apposta se te ne
dimentichi (vedi sotto).

## Bug reali documentati da questa suite (non ipotetici: trovati eseguendo i test)

Scrivere questi test ha fatto emergere comportamenti reali del codice,
alcuni probabilmente non voluti. Ogni test che li documenta spiega nel
proprio docstring/commento cosa succede oggi e come va aggiornato quando
viene corretto:

1. **`get_collegamenti_entita()` (`database.py`)** ignora silenziosamente i
   collegamenti verso qualunque tabella diversa da
   `internati`/`decorati`/`fondi_archivistici`/`menzioni`. Dato che
   `caduti_albooro` da sola genera piu' archi di internati+decorati insieme
   (vedi CHANGELOG), la vista dettaglio entita' e' oggi strutturalmente
   incompleta per la maggior parte dei nodi del grafo reale.
   → `test_database.py::test_get_collegamenti_entita_ignora_tabelle_non_mappate`

2. **`linker.build_links()`** non ha logica di resume per
   `internati`/`decorati`/`menzioni` (ce l'ha per le tabelle scraper piu'
   grandi): ogni ri-esecuzione duplica gli archi in `collegamenti` per
   queste tre tabelle (le entita' restano deduplicate).
   → `test_linker.py::test_rerun_duplica_collegamenti_per_internati`

3. **`research_to_index.auto_index_if_not_found()`** calcola quanti
   risultati locali esistono sommando la lunghezza di OGNI lista nel dict
   di `search_all()`, inclusa la chiave `tokens` (sempre non vuota per
   query non banali). Il risultato: `found_locally=True` quasi sempre, anche
   a zero risultati reali — il ramo "crea soggetto + arricchisci da fonti
   federate" (una delle 4 innovazioni chiave del progetto per i bandi EU)
   di fatto non si attiva quasi mai passando da questa funzione.
   → `test_research_to_index.py::test_BUG_local_count_conta_anche_la_lista_tokens`

4. **`import_lettere_personali._persone_da_testo()`** ha un filtro di
   cortesia (`{"Grazie","Caro","Cara",...}`) che confronta l'INTERA stringa
   catturata dal pattern (sempre 2-3 parole) contro parole singole: non
   esclude mai nulla nella pratica. "Caro Amico", "Cara Mamma" ecc. finiscono
   nel grafo entita' come se fossero persone.
   → `test_personal_sources_import.py::test_BUG_filtro_cortesia_confronta_stringa_intera_con_parola_singola`

5. **`requirements.txt`** non elenca `anthropic` ne' `psutil`, entrambi
   importati (con guardia try/except) rispettivamente da
   `ai_research.py`/`biography.py` (fallback "claude") e da `_bench_report2.py`.
   Il fallback Claude nel Dossier verificato fallira' silenziosamente con
   "Anthropic SDK non installato" finche' non viene aggiunto.
   → `test_project_health.py::test_ogni_import_esterno_e_in_requirements`
     (questo test FALLISCE di proposito finche' il gap non viene chiuso)

Nessuno di questi e' un test "rotto da sistemare": sono guardrail che
documentano lo stato attuale e vanno aggiornati (non cancellati) quando il
comportamento viene corretto — ogni docstring spiega esattamente come.

## Cosa NON e' (ancora) coperto

- Provider reali (`source_providers/*.py` con chiamate HTTP vere): richiede
  rete + eventualmente chiavi API, va testato a parte/manualmente.
- `biography.py`/`ai_research.py` con chiavi API reali: idem, vedi
  `TODO.md #2 "Dossier verificato"`.
- Gli scraper (`caduti_*.py`, `nara_*.py`, `decorati*.py`): fanno scraping
  HTTP live su siti terzi, fuori scope per una suite offline. Se si vuole
  coprirli, isolare la logica di parsing (data in → dict out) dalla parte
  di rete e testare solo quella, seguendo lo stesso principio usato qui per
  tutto il resto.

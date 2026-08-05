# TODO — Priorità di lavoro

**Aggiornato:** 2 Agosto 2026

---

## 🔴 ALTA PRIORITÀ — Domani (3 Agosto 2026)

### [V7.2] Fix identità, narrazione e ricostruzione

**Prompt:** `prompt_devin_v7_2_fix_identita_narrazione_ricostruzione.md`  
**Changelog V7.1:** `CHANGELOG_V7_1_AI_ACTIVATION.md`  
**Pipeline doc:** `V7_PIPELINE_METHODOLOGY.md`

**Ordine di esecuzione:**

1. Congela i 6 target canary e acquisisci baseline end-to-end
2. Dimostra il call path attivo (`V7_2_ACTIVE_CALL_PATH.md`)
3. Introduci identity cluster e gate bloccante prima della fusione
4. Implementa FETCH/LOCATE reale e layout-aware OCR
5. Separa person evidence e context evidence
6. Migra snapshot e invalida i derivati contaminati
7. Implementa JSON narrativo e renderer discorsivo
8. Esegui test e canary con AI disponibile e AI_OFF
9. Confronta prima/dopo e blocca il batch esteso finché tutti i gate non sono a zero

**Moduli da modificare (8):**
- `semantic_query_plan.py` — target ancorato a `origin_record_id`
- `v7_provider_adapters.py` — exact full-name query primaria, `SURNAME_ONLY_NON_CANDIDATE`
- `v7_identity_model.py` — cluster, tie handling, 5 nuovi stati identità
- `unified_orchestrator_v7.py` — vero FETCH/LOCATE, blocco pre-FUSE se ambigua
- `v7_fusion_engine.py` — fusione limitata al cluster, source lineage reale
- `evidence_snapshot_v7.py` — nuovi stati, cluster ID obbligatori, context claims
- `v7_narrator.py` — JSON strutturato, renderer discorsivo
- `run_canary_v7.py` — stessi target, endpoint pubblico, oracle semantici

**Gate di accettazione (tutti a zero):**
- `cross_identity_claims = 0`
- `surname_only_candidates_visible = 0`
- `exact_name_multi_record_resolved = 0`
- `unlocated_ocr_person_claims = 0`
- `internal_tokens_visible = 0`
- `unsupported_narrative_sentences = 0`
- `context_misattributed_to_person = 0`
- `row_order_dependent_results = 0`

**6 canary target (congelati):**
1. CAIS Arduino — `ANCHORED_RECORD`, nessun cognome visualizzato
2. BROGNARA Cristino — `ANCHORED_RECORD`, nessun cognome visualizzato
3. TONIOLI Pasquale — `PARTIAL_IDENTITY` o `ANCHORED_RECORD` con `ROW_ALIGNMENT_UNCERTAIN`
4. DEVINCENZI Giovanni — `AMBIGUOUS_IDENTITY`, cluster separati
5. EGINETI Arturo — `ANCHORED_RECORD`, contesto Brigata Sele separato
6. RIGAMONTI Pietro — `AMBIGUOUS_IDENTITY`, cluster separati

**Deliverable (9):**
1. `V7_2_ACTIVE_CALL_PATH.md`
2. Diff moduli attivi
3. Migrazione/schema per `identity_cluster_id`, evidence scope, locator
4. Test unitari + integration test + exit code
5. `CANARY_V7_2_RESULTS.json` + `CANARY_V7_2_REPORT.md`
6. Confronto prima/dopo delle 6 risposte
7. Esempio completo EGINETI + esempio ambiguo RIGAMONTI
8. Inventario snapshot contaminati + piano invalidazione
9. Limiti rimasti

---

## 🟡 MEDIA PRIORITÀ — Post V7.2

### Supabase sync
- Completare sync `event_links` (~18% syncato, 1.5M righe rimanenti)
- Sync tabelle rimanenti: `internati`, `decorati`, `caduti_*`, `graph_nodes`, `graph_edges`
- Abilitare vector extension per RAG embeddings
- Configurare Storage buckets per thumbnails

### Backfill canonico
- Eseguire `backfill_canonical.py` (1M+ righe)
- Estendere `supabase_client.py` per multi-schema
- Integrare `repository_layer.py` nelle pipeline

### LeBI Fase 5+7
- Report, FTS, Memory Router, Source Locator, citations
- Test e documentazione

---

## 🟢 BASSA PRIORITÀ — Backlog

### Graph provenance
- PR review e merge branch `devin/ai-storica-eventi-mappe`
- Master test file per moduli graph/rag/map
- Fine-tuning opzionale (solo se RAG passa quality bar)

### Frontend admin
- Review UI per links, claims, evidence
- Integrazione V7.2 narrator output nel frontend

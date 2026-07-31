# TODO — V4 Post-Audit Action Items

*Generato: 2026-07-31*
*Stato: 13/13 task V4 completati, canary offline passato*

---

## ✅ Completato (V4 Audit)

- [x] A. EvidenceSnapshot V4 — DTO unificato con origin_record, claims, provider_ledger
- [x] B. SOURCE_RECORD_ONLY invariants — richiede URL verificata, compute_typed_counts riconciliato
- [x] C. Relevance gate multi-stage — pipeline 6-stage con 4 bucket
- [x] D. False negative proofs — CONSULTED_NO_MATCH richiede fetch verificata
- [x] E. URL dedup e rendering — AI riceve source_id, no URL in context
- [x] F. missing_claims — claim-per-field completeness
- [x] G. Unified capability routing — source_capability_registry con 25 provider
- [x] H. ArchiveJurisdictionRegistry — 11 comuni verificati, no template
- [x] I. Parser COGNOME NOME DI PADRE — name_parser_v4 con provenance
- [x] J. Post-generation validator — contradiction/hallucination detection + fallback
- [x] K. Conversational report — ReportConversationProvider, Mistral/local, no OpenAI
- [x] L. Tests — 149 test (82 V4 + 67 V3), tutti PASS
- [x] M. Canary V4 offline — 10/10 target, 0 violazioni

---

## 🔲 Pending — Integrazione e Deploy

### Priorità alta

- [ ] **Canary V4 con AI live** — eseguire `run_canary.py` con `use_ai=True` per testare Mistral + Tavily con il snapshot V4
  - Verificare che il prompt V4 (snapshot context, no URL) produca output corretto
  - Verificare che `ai_output_validator` non scarti output validi
  - Verificare che il fallback deterministico si attivi solo su reali violazioni

- [ ] **Wire ReportConversationProvider in app.py** — 3 endpoint API
  - `POST /research/reports/{report_id}/conversations` — crea conversazione bound a snapshot
  - `POST /research/conversations/{conversation_id}/messages` — invia messaggio
  - `GET /research/conversations/{conversation_id}` — recupera conversazione

- [ ] **Fetch integration nel relevance gate** — il pipeline V4 supporta `fetch_status=SUCCESS` + `fetched_content` ma il fetcher non è collegato
  - Implementare fetch HTTP con timeout e content extraction
  - Passare `fetched_content` a `classify_relevance_v4` per stage 6 (evidence acceptance)

- [ ] **Espandere ArchiveJurisdictionRegistry** — attualmente 11 comuni mappati
  - Aggiungere comuni dai canary target: Modica, San Lorenzo, Casaluce, Brienza, Lettere
  - Verificare mapping presso Archivi di Stato competenti
  - Considerare import da dataset ISTAT → distretto militare storico

### Priorità media

- [ ] **Renderer link generation** — implementare il renderer che genera link HTML da `source_id` nello snapshot
  - Il modello emette solo `source_id`, il renderer costruisce `<a href="{canonical_url}">{source_id}</a>`
  - Integrare nel template RISPOSTE_BACKEND.md

- [ ] **Aggiungere provider mancanti al capability registry** — 25/27 provider registrati
  - Verificare `federation.py` per provider non in registry
  - Aggiungere capability declarations mancanti

- [ ] **V4 snapshot in API response** — esporre `evidence_snapshot_v4` nell'endpoint `/api/research-protocol`
  - Sostituire o affiancare il vecchio `evidence_snapshot` V3
  - Aggiornare frontend per consumare V4

- [ ] **Property-based tests con hypothesis** — espandere test con generazione automatica
  - Property: per ogni input, parser preserva raw_value
  - Property: per ogni conflict, routing matrix non ha overlap
  - Property: per ogni snapshot, validate() è idempotente

### Priorità bassa

- [ ] **Documentazione ADR** — Architecture Decision Record per V4
  - Documentare le 12 decisioni architetturali
  - Tracciare il flusso: SearchInput → Dossier → EvidenceSnapshotV4 → AI → Validator → Report

- [ ] **Cleanup vecchi EvidenceSnapshot** — rimuovere o deprecare `evidence_snapshot.py` e `EvidenceSnapshot` in `research_protocol.py`
  - Mantenere backward compatibility con flag `--snapshot-version=v4|v3`
  - Rimuovere dopo conferma completa migrazione

- [ ] **Metriche V4** — dashboard con metriche quality
  - Tasso di fallback deterministico
  - Tasso di violazioni per categoria
  - Distribution dei result_state dal relevance gate
  - Coverage claims per target

- [ ] **Git push** — committare e pushare tutti i cambiamenti V4
  - Branch: `v4/evidence-snapshot-reconstruction`
  - Tag: `v4.0.0-audit`

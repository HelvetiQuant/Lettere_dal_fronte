# TODO — V4 Post-Audit Action Items

*Generato: 2026-07-31*
*Aggiornato: 2026-08-01*
*Stato: 13/13 task V4 + 5/5 post-audit alta priorità completati*

---

## ✅ Completato (V4 Audit — 13 task)

- [x] A. EvidenceSnapshot V4 — DTO unificato con origin_record, claims, provider_ledger
- [x] B. SOURCE_RECORD_ONLY invariants — richiede URL verificata, compute_typed_counts riconciliato
- [x] C. Relevance gate multi-stage — pipeline 6-stage con 4 bucket
- [x] D. False negative proofs — CONSULTED_NO_MATCH richiede fetch verificata
- [x] E. URL dedup e rendering — AI riceve source_id, no URL in context
- [x] F. missing_claims — claim-per-field completeness
- [x] G. Unified capability routing — source_capability_registry con 25 provider
- [x] H. ArchiveJurisdictionRegistry — 16 comuni verificati (11 + 5 post-audit), no template
- [x] I. Parser COGNOME NOME DI PADRE — name_parser_v4 con provenance
- [x] J. Post-generation validator — contradiction/hallucination detection + fallback
- [x] K. Conversational report — ReportConversationProvider, Mistral/local, no OpenAI
- [x] L. Tests — 149 test (82 V4 + 67 V3), tutti PASS
- [x] M. Canary V4 offline — 10/10 target, 0 violazioni

---

## ✅ Completato (Post-Audit — Alta Priorità)

- [x] **Canary V4 con AI live** — `run_canary.py` con `use_ai=True`, 10/10 SUCCESS
  - Tavily attivo su 9/10, AI Mistral su tutti, fix encoding cp1252
  - `CANARY_RESULTS.json` + `CANARY_DOSSIERS.json` + `CANARY_REPORT.md`

- [x] **Wire ReportConversationProvider in app.py** — `report_conversation_api.py`
  - 3 endpoint: POST create, POST message, GET conversation
  - Router registrato in `app.py`

- [x] **Fetch integration nel relevance gate** — `fetch_and_classify()` in `relevance_gate_v4.py`
  - HTTP GET + HTML text extraction + classificazione con fetched_content

- [x] **Espandere ArchiveJurisdictionRegistry** — +5 comuni (Modica, San Lorenzo, Casaluce, Brienza, Lettere)
  - Totale: 16 comuni mappati

- [x] **Git push** — commit `99b2d6e` su `fix/provenance-linking-v2`

---

## 🔲 Pending — Media Priorità

- [ ] **Report conversazionali per target** — `generate_conversational_reports.py` creato, da eseguire
  - Output: `CONVERSATIONAL_REPORTS.json` + `CONVERSATIONAL_REPORTS.md`

- [ ] **Renderer link generation** — renderer che genera link HTML da `source_id` nello snapshot
  - Modello emette source_id, renderer costruisce `<a href="{canonical_url}">{source_id}</a>`

- [ ] **Aggiungere 2 provider mancanti al capability registry** — 25/27 registrati
  - Verificare `federation.py` per provider non in registry

- [ ] **V4 snapshot in API response** — esporre `evidence_snapshot_v4` in `/api/research-protocol`
  - Sostituire/affiancare V3, aggiornare frontend

- [ ] **Property-based tests con hypothesis** — espandere test
  - Property: parser preserva raw_value; routing no overlap; validate() idempotente

- [ ] **Fix discovery_persistence `idempotency_key`** — colonna mancante in `source_registry`
  - Aggiungere colonna SQLite, verificare schema

---

## 🔲 Pending — Bassa Priorità

- [ ] **Documentazione ADR V4** — 12 decisioni architetturali
- [ ] **Cleanup vecchi EvidenceSnapshot V3** — deprecare con flag `--snapshot-version`
- [ ] **Metriche V4** — dashboard quality (fallback rate, violation rate, claim coverage)
- [ ] **Tag release** — `v4.0.0-audit` dopo merge su main

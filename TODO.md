# TODO — Priorità di lavoro

**Aggiornato:** 6 Agosto 2026

---

## ✅ COMPLETATO — V7.3-PERSON-FIX (14/14 task)

Branch: `fix/provenance-linking-v2` — Commit: `fdd2c77`

1. Diagnosi call graph + baseline 20 nomi
2. Modelli tipizzati (PersonCandidate, PersonFact, FactEvidence, SourceProvenance, ConflictSet)
3. PERSON_SOURCE_SCHEMAS: mapping 5 tabelle con validator/normalizer
4. Fix retrieval: 5 tabelle queryate, word boundary, normalizzazione nominativo
5. Fix schema OpenAI + circuit breaker provider AI
6. Separazione fatti/evidenze/provenance con dedup
7. Identity resolver cluster-based, no fusione omonimi, war-period-aware
8. Unit test: 43/43 PASS
9. _gen_record_links.py: quarantena, CLI, pairwise linking
10. _gen_event_links.py: word boundary, barriere temporali, incremental
11. Narratore evidence-locked: _validate_payload, _compute_evidence_hash, _post_gen_hallucination_check
12. Migrazioni DB: data_corrections table, sync_parity_audit, Supabase parity (6/8 OK)
13. Sicurezza script: _clean_bad_links (DELETE→quarantine), _fix_gaiaschi_db (UPDATE→overlay)
14. Regression benchmark: 5/5 PASS, 6/6 backend test, 0 errori

**Changelog:** `CHANGELOG_V73_PERSON_FIX.md`

---

## � ALTA PRIORITÀ — Prossimi task

### Supabase sync completion
- Completare sync `event_links` (~18% syncato, 1.5M righe rimanenti)
- Sync tabelle rimanenti: `graph_nodes`, `graph_edges`
- Risolvere mismatch `eventi_1gm` (15 SQLite vs 49 Supabase — DB separato)
- Abilitare vector extension in Supabase dashboard per RAG embeddings
- Configurare Storage buckets per thumbnails/representations

### Backfill canonico
- Eseguire `backfill_canonical.py` (1M+ righe, dry-run verificato)
- Estendere `supabase_client.py` per multi-schema support
- Integrare `repository_layer.py` nelle pipeline esistenti

---

## 🟡 MEDIA PRIORITÀ

### LeBI Fase 5+7
- Report generazione, FTS (Full Text Search)
- Memory Router, Source Locator, citations
- Test e documentazione integrazione LeBI

### V7.3 follow-up
- Eseguire regression benchmark completo (20 PERSON + 3 EVENT, non solo quick 5)
- Risolvere hallucination check false positive su decorazioni ("Croce", "Valor")
- Allineare `eventi_1gm` tra SQLite e Supabase (49 vs 15 righe)
- Eseguire `--re-evaluate` su production DB per riclassificare link legacy con V3

---

## 🟢 BASSA PRIORITÀ — Backlog

### Graph provenance
- PR review e merge branch `devin/ai-storica-eventi-mappe`
- Master test file per moduli graph/rag/map
- Fine-tuning opzionale (solo se RAG passa quality bar)

### Frontend admin
- Review UI per links, claims, evidence
- Integrazione V7.3 narrator output nel frontend
- Dashboard per data_corrections overlay management

### Qwen / RAG
- Abilitare vector extension in Supabase
- Configurare RAG embeddings pipeline
- Test quality bar prima di fine-tuning

# ADR: Archivio Documentale Canonico Supabase

**Data:** 2026-07-26  
**Stato:** Proposed  
**Branch:** `devin/ai-storica-eventi-mappe`

## Contesto

Il sistema IMI Extractor gestisce attualmente ~9.5M righe in 75 tabelle SQLite, 27 provider federati, 163 endpoint API, pipeline RAG, claims/evidence, e training ML Qwen. I dati sono dispersi su 3 database SQLite senza separazione tra livelli logici (discovery, repository, item, file, page, passage, claim, evidence, RAG, ML dataset).

La migrazione a Supabase/PostgreSQL è iniziata ma interrotta (checkpoint a 65 tabelle). Non esistono:
- Tabelle per passaggi citabili (`passages`)
- Tracciamento provenienza discovery (`discovery_queries/candidates`)
- Revisioni metadati immutabili
- Diritti versionati per-item
- Job queue atomica
- Dataset ML tracciati in DB
- Bucket Storage configurati
- Schemi PostgreSQL separati

## Decisione

Adottare un'architettura a **schemi PostgreSQL separati** con **strato canonico additivo**:

### Schemi

| Schema | Responsabilità | Accesso |
|---|---|---|
| `archive` | Repository, collezioni, item esterni, rappresentazioni, unità documentali, versioni testuali, passaggi, chunk RAG | Public read (con filter), service write |
| `evidence` | Link in quarantena, valutazioni diritti, claims estesi | Service only (eccetto rights: public read) |
| `ops` | Discovery queries/candidates, job queue, fetch cache | Service only |
| `ai` | Dataset ML, versioni, items, sources, evaluation runs | Service only |
| `api_public` | Viste pubbliche per API | Public read |
| `legacy` | Viste di compatibilità per tabelle rinominate | Public read |

### Principi

1. **Additivo e idempotente**: `CREATE IF NOT EXISTS`, `ALTER ADD COLUMN`, nessun `DROP`
2. **Legacy preservato**: Tabelle SQLite originali non toccate, viste di compatibilità
3. **Provenienza end-to-end**: discovery → item → representation → text_version → passage → claim → evidence → dataset
4. **RLS su ogni tabella**: public read con filtri, service_role write
5. **ALTER DEFAULT PRIVILEGES**: nuovi oggetti non accessibili a anon
6. **Stable IDs deterministici**: SHA-256 di `namespace:external_id:provider`
7. **Hash contenuti**: SHA-256 per deduplica e integrità
8. **Diritti versionati**: 8 dimensioni (metadata_access, content_access, download, training, redistribution, commercial, attribution, license)

### Consegne

| Deliverable | File | Stato |
|---|---|---|
| Audit completo | `docs/architecture/canonical-historical-archive.md` | Completato |
| Registry provider | `config/archive_providers.yml` | Completato (27 provider + 2 pending) |
| Schema SQL canonico | `sql/001_supabase_historical_archive_core.sql` | Completato (21 tabelle, 40+ indici, RLS, trigger) |
| Repository layer Python | `repository_layer.py` | Completato (SupabaseBackend, 8 dataclass) |
| Script backfill | `backfill_canonical.py` | Completato (6 tabelle, --dry-run verificato) |
| Training Qwen | `finetune_cpu.py` | Completato (75 chunk, loss 3.9) |

## Conseguenze

### Positive
- Separazione chiara tra livelli logici
- Provenienza verificabile end-to-end
- RLS granulare per sicurezza
- Dataset ML tracciati con anti-leakage
- Job queue atomica per worker distribuiti
- Viste di compatibilità per backward compatibility

### Negative
- Complessità aggiunta (5 schemi, 21 nuove tabelle)
- Necessità di estendere `supabase_client.py` per supportare schemi
- Backfill richiede tempo per 1M+ righe
- Vector extension richiede installazione su Supabase

### Mitigazioni
- Viste `legacy.*` per compatibilità
- Script backfill idempotenti con `--dry-run`
- RLS policy predefinite per nuove tabelle
- Documentazione completa in `docs/architecture/`

## Prossimi passi

1. **Conferma utente** per applicare migrazione SQL a Supabase
2. Esecuzione `001_supabase_historical_archive_core.sql` su Supabase
3. Backfill dati legacy (eventi, items, repositories, claims, links, datasets)
4. Estensione `supabase_client.py` per schemi multipli
5. Integrazione `repository_layer.py` in pipeline esistenti
6. Test di regressione su endpoint API esistenti
7. Configurazione bucket Storage Supabase

-- VOCI DAL FRONTE Schema per Supabase PostgreSQL
-- Tabelle: 114, Indici: 236

-- STEP 1: TABELLE

-- acquisitions (0 righe)
CREATE TABLE IF NOT EXISTS "acquisitions" (
    "id" SERIAL PRIMARY KEY,
    "source_item_id" INTEGER,
    "source_table" TEXT NOT NULL DEFAULT 'fonti_indice',
    "external_record_id" INTEGER,
    "connector_code" TEXT,
    "acquisition_date" TEXT NOT NULL,
    "acquisition_method" TEXT NOT NULL,
    "access_mode" TEXT NOT NULL,
    "policy_version_id" INTEGER,
    "permitted_operations_json" TEXT,
    "operator_user" TEXT,
    "notes" TEXT,
    "created_at" TEXT NOT NULL
);

-- ai_models (7 righe)
CREATE TABLE IF NOT EXISTS "ai_models" (
    "id" SERIAL PRIMARY KEY,
    "provider_id" INTEGER NOT NULL,
    "model_identifier" TEXT NOT NULL,
    "capabilities_json" TEXT,
    "context_window" INTEGER,
    "cost_per_unit" DOUBLE PRECISION,
    "quality_score" DOUBLE PRECISION DEFAULT 0.5,
    "latency_score" DOUBLE PRECISION DEFAULT 0.5,
    "status" TEXT DEFAULT 'enabled',
    "last_benchmarked_at" TEXT,
    "created_at" TEXT NOT NULL,
    "updated_at" TEXT NOT NULL
);

-- ai_providers (6 righe)
CREATE TABLE IF NOT EXISTS "ai_providers" (
    "id" SERIAL PRIMARY KEY,
    "code" TEXT NOT NULL,
    "name" TEXT NOT NULL,
    "status" TEXT DEFAULT 'active',
    "declared_capabilities_json" TEXT,
    "verified_capabilities_json" TEXT,
    "credit_detection_method" TEXT DEFAULT 'unknown',
    "currency" TEXT DEFAULT 'USD',
    "budget_configured" DOUBLE PRECISION DEFAULT 50.0,
    "budget_reserve" DOUBLE PRECISION DEFAULT 5.0,
    "priority" INTEGER DEFAULT 5,
    "last_health_check" TEXT,
    "config_json" TEXT,
    "created_at" TEXT NOT NULL,
    "updated_at" TEXT NOT NULL
);

-- ai_ricerche (217 righe)
CREATE TABLE IF NOT EXISTS "ai_ricerche" (
    "id" SERIAL PRIMARY KEY,
    "query" TEXT NOT NULL,
    "provider" TEXT NOT NULL,
    "model" TEXT NOT NULL,
    "risposta" TEXT,
    "contesto_dati" TEXT,
    "cost_usd" DOUBLE PRECISION DEFAULT 0.0,
    "elaborato_il" TEXT NOT NULL
);

-- ai_routing_policies (21 righe)
CREATE TABLE IF NOT EXISTS "ai_routing_policies" (
    "id" SERIAL PRIMARY KEY,
    "task_type" TEXT NOT NULL,
    "min_requirements_json" TEXT,
    "primary_model_id" INTEGER,
    "fallback_model_ids_json" TEXT,
    "max_cost" DOUBLE PRECISION,
    "min_reserve_credit" DOUBLE PRECISION,
    "timeout_seconds" INTEGER DEFAULT 60,
    "max_retries" INTEGER DEFAULT 2,
    "quality_criterion" TEXT,
    "version" TEXT DEFAULT '1',
    "created_at" TEXT NOT NULL,
    "updated_at" TEXT NOT NULL
);

-- ai_task_runs (74 righe)
CREATE TABLE IF NOT EXISTS "ai_task_runs" (
    "id" SERIAL PRIMARY KEY,
    "research_plan_id" INTEGER,
    "session_id" INTEGER,
    "cycle_id" INTEGER,
    "task_type" TEXT NOT NULL,
    "provider_code" TEXT,
    "model_identifier" TEXT,
    "selection_reason" TEXT,
    "policy_version" TEXT,
    "input_fingerprint" TEXT,
    "input_tokens" INTEGER,
    "output_tokens" INTEGER,
    "cost_estimated" DOUBLE PRECISION,
    "cost_actual" DOUBLE PRECISION,
    "credit_before" TEXT,
    "credit_after" TEXT,
    "latency_ms" INTEGER,
    "outcome" TEXT,
    "validation_result_json" TEXT,
    "fallback_from" TEXT,
    "fallback_to" TEXT,
    "idempotency_key" TEXT,
    "created_at" TEXT NOT NULL,
    "completed_at" TEXT
);

-- ai_usage_ledger (64 righe)
CREATE TABLE IF NOT EXISTS "ai_usage_ledger" (
    "id" SERIAL PRIMARY KEY,
    "provider_code" TEXT NOT NULL,
    "model_identifier" TEXT NOT NULL,
    "period" TEXT NOT NULL,
    "units_consumed" DOUBLE PRECISION,
    "cost" DOUBLE PRECISION,
    "data_source" TEXT NOT NULL DEFAULT 'internal_estimate',
    "task_run_id" INTEGER,
    "updated_at" TEXT NOT NULL
);

-- api_usage (10624 righe)
CREATE TABLE IF NOT EXISTS "api_usage" (
    "id" SERIAL PRIMARY KEY,
    "timestamp" TEXT NOT NULL,
    "provider" TEXT NOT NULL,
    "model" TEXT NOT NULL,
    "input_tokens" INTEGER DEFAULT 0,
    "output_tokens" INTEGER DEFAULT 0,
    "ocr_pages" INTEGER DEFAULT 0,
    "cost_usd" DOUBLE PRECISION DEFAULT 0.0,
    "lettera" TEXT,
    "pagina" INTEGER
);

-- archival_metadata (0 righe)
CREATE TABLE IF NOT EXISTS "archival_metadata" (
    "stable_id" TEXT PRIMARY KEY,
    "source_table" TEXT NOT NULL,
    "source_id" INTEGER NOT NULL,
    "metadata_standard" TEXT NOT NULL,
    "title" TEXT NOT NULL,
    "metadata_json" TEXT NOT NULL,
    "checksum" TEXT,
    "status" TEXT NOT NULL DEFAULT 'generated',
    "algorithm_version" TEXT NOT NULL,
    "generated_at" TEXT NOT NULL,
    "reviewed_by" TEXT,
    "reviewed_at" TEXT
);

-- archive_connectors (27 righe)
CREATE TABLE IF NOT EXISTS "archive_connectors" (
    "id" SERIAL PRIMARY KEY,
    "code" TEXT NOT NULL,
    "name" TEXT NOT NULL,
    "scope" TEXT,
    "historical_periods" TEXT,
    "geographic_areas" TEXT,
    "entity_types" TEXT,
    "document_types" TEXT,
    "integration_type" TEXT NOT NULL DEFAULT 'metadata_only',
    "capabilities_json" TEXT,
    "access_mode" TEXT NOT NULL DEFAULT 'assisted',
    "authority_score" DOUBLE PRECISION DEFAULT 0.5,
    "reliability_criteria" TEXT,
    "provenance_group" TEXT,
    "languages" TEXT,
    "cost_priority" INTEGER DEFAULT 5,
    "config_json" TEXT,
    "status" TEXT DEFAULT 'active',
    "terms_limitations" TEXT,
    "last_verified_at" TEXT,
    "version" TEXT DEFAULT '1.0',
    "created_at" TEXT NOT NULL,
    "updated_at" TEXT NOT NULL
);

-- archivio_documenti (433 righe)
CREATE TABLE IF NOT EXISTS "archivio_documenti" (
    "provider" TEXT,
    "external_id" TEXT,
    "doc_type" TEXT,
    "title" TEXT,
    "description" TEXT,
    "creator" TEXT,
    "date_text" TEXT,
    "year_start" INTEGER,
    "year_end" INTEGER,
    "place" TEXT,
    "war" TEXT DEFAULT 'WWI',
    "language" TEXT,
    "rights" TEXT,
    "source_url" TEXT NOT NULL,
    "thumbnail_url" TEXT,
    "iiif_manifest" TEXT,
    "provider_collection" TEXT,
    "retrieved_at" TEXT,
    "raw_json" TEXT,
    PRIMARY KEY ("provider", "external_id")
);

-- archivio_fonti (1153 righe)
CREATE TABLE IF NOT EXISTS "archivio_fonti" (
    "id" SERIAL PRIMARY KEY,
    "hash_sha256" TEXT NOT NULL,
    "path_originale" TEXT,
    "path_storage" TEXT,
    "formato" TEXT,
    "dimensione_bytes" INTEGER,
    "pagine" INTEGER,
    "ocr_status" TEXT DEFAULT 'pending',
    "readable" INTEGER DEFAULT 0,
    "htr_attempted" INTEGER DEFAULT 0,
    "qualita_immagine" DOUBLE PRECISION,
    "testo_ocr" TEXT,
    "lingua_documento" TEXT,
    "archivio" TEXT,
    "fondo" TEXT,
    "serie" TEXT,
    "busta" TEXT,
    "fascicolo" TEXT,
    "segnatura" TEXT,
    "titolo_documento" TEXT,
    "unita_principale" TEXT,
    "livello_unita" TEXT,
    "unita_superiore" TEXT,
    "teatro_operazioni" TEXT,
    "nazione_forza" TEXT,
    "data_inizio" TEXT,
    "data_fine" TEXT,
    "data_raw" TEXT,
    "tipo_documento" TEXT,
    "conflitto" TEXT,
    "unita_citate" TEXT,
    "luoghi_citati" TEXT,
    "parole_chiave" TEXT,
    "attendibilita_fonte" INTEGER DEFAULT 3,
    "note" TEXT,
    "fonte_acquisizione" TEXT,
    "elaborato_il" TEXT NOT NULL,
    "aggiornato_il" TEXT,
    "iiif_manifest_url" TEXT,
    "url_catalogo" TEXT,
    "licenza" TEXT,
    "digitale_pubblico" INTEGER DEFAULT 0,
    "htr_engine" TEXT,
    "htr_confidence" DOUBLE PRECISION,
    "testo_htr" TEXT,
    "richiede_revisione" INTEGER DEFAULT 0
);

-- budget_reservations (0 righe)
CREATE TABLE IF NOT EXISTS "budget_reservations" (
    "id" SERIAL PRIMARY KEY,
    "plan_id" INTEGER,
    "task_type" TEXT,
    "provider_code" TEXT,
    "reserved_amount" DOUBLE PRECISION,
    "consumed_amount" DOUBLE PRECISION DEFAULT 0.0,
    "currency" TEXT DEFAULT 'USD',
    "status" TEXT DEFAULT 'active',
    "expires_at" TEXT,
    "created_at" TEXT NOT NULL,
    "updated_at" TEXT NOT NULL
);

-- caduti_albooro (342555 righe)
CREATE TABLE IF NOT EXISTS "caduti_albooro" (
    "id" SERIAL PRIMARY KEY,
    "source_id" TEXT,
    "volume_id" TEXT,
    "volume_name" TEXT,
    "nominativo" TEXT,
    "paternita" TEXT,
    "classe" TEXT,
    "comune_attuale" TEXT,
    "grado" TEXT,
    "reparto" TEXT,
    "anno_morte" TEXT,
    "luogo_morte" TEXT,
    "causa_morte" TEXT,
    "detail_url" TEXT,
    "img_url" TEXT,
    "elaborato_il" TEXT NOT NULL
);

-- caduti_bologna (9656 righe)
CREATE TABLE IF NOT EXISTS "caduti_bologna" (
    "id" SERIAL PRIMARY KEY,
    "nome" TEXT,
    "paternita" TEXT,
    "grado" TEXT,
    "reparto" TEXT,
    "luogo_nascita" TEXT,
    "anno_nascita" TEXT,
    "luogo_dimora" TEXT,
    "causa_morte" TEXT,
    "luogo_morte" TEXT,
    "data_morte" TEXT,
    "professione" TEXT,
    "stato_civile" TEXT,
    "decorazioni" TEXT,
    "scheda_completa" TEXT,
    "elaborato_il" TEXT NOT NULL
);

-- caduti_cwgc (506446 righe)
CREATE TABLE IF NOT EXISTS "caduti_cwgc" (
    "id" SERIAL PRIMARY KEY,
    "cwgc_id" TEXT,
    "nome" TEXT,
    "cognome" TEXT,
    "initials" TEXT,
    "rank" TEXT,
    "service_number" TEXT,
    "service" TEXT,
    "regiment" TEXT,
    "nationality" TEXT,
    "data_morte" TEXT,
    "eta" TEXT,
    "cimitero" TEXT,
    "paese_cimitero" TEXT,
    "guerra" TEXT,
    "data_nascita" TEXT,
    "elaborato_il" TEXT NOT NULL,
    "unit_detail" TEXT,
    "memorial" TEXT,
    "grave_ref" TEXT
);

-- caduti_francia_ww1 (24279 righe)
CREATE TABLE IF NOT EXISTS "caduti_francia_ww1" (
    "id" SERIAL PRIMARY KEY,
    "images_href" TEXT,
    "nom" TEXT,
    "naissance" TEXT,
    "grade" TEXT,
    "unite" TEXT,
    "lieu_naissance" TEXT,
    "bureau_recrutement" TEXT,
    "classe" TEXT,
    "matricule" TEXT,
    "date_deces" TEXT,
    "lieu_deces" TEXT,
    "lieu_deces_suite" TEXT,
    "departement_deces" TEXT,
    "pays_deces" TEXT,
    "lieu_transcription" TEXT,
    "departement_transcription" TEXT,
    "pays_transcription" TEXT,
    "source" TEXT,
    "elaborato_il" TEXT NOT NULL
);

-- caduti_ministero (162646 righe)
CREATE TABLE IF NOT EXISTS "caduti_ministero" (
    "id" SERIAL PRIMARY KEY,
    "source_id" INTEGER,
    "cognome" TEXT,
    "nome" TEXT,
    "nominativo_paternita" TEXT,
    "paternita" TEXT,
    "maternita" TEXT,
    "data_nascita" TEXT,
    "data_decesso" TEXT,
    "provincia_nascita" TEXT,
    "comune_nascita" TEXT,
    "nazione_decesso" TEXT,
    "luogo_sepoltura" TEXT,
    "codice_volume" INTEGER,
    "pagina" INTEGER,
    "sub" INTEGER,
    "scheda_url" TEXT,
    "elaborato_il" TEXT NOT NULL
);

-- caduti_sardi (20435 righe)
CREATE TABLE IF NOT EXISTS "caduti_sardi" (
    "id" SERIAL PRIMARY KEY,
    "source_id" TEXT,
    "cognome" TEXT,
    "nome" TEXT,
    "paternita" TEXT,
    "luogo_nascita" TEXT,
    "data_nascita" TEXT,
    "comune_residenza" TEXT,
    "guerra" TEXT,
    "grado" TEXT,
    "reparto" TEXT,
    "data_morte" TEXT,
    "luogo_morte" TEXT,
    "causa_morte" TEXT,
    "decorazioni" TEXT,
    "scheda_url" TEXT,
    "elaborato_il" TEXT NOT NULL
);

-- claim_evidence (550 righe)
CREATE TABLE IF NOT EXISTS "claim_evidence" (
    "id" SERIAL PRIMARY KEY,
    "claim_id" INTEGER NOT NULL,
    "source_id" INTEGER,
    "source_table" TEXT,
    "document_id" INTEGER,
    "document_table" TEXT,
    "extraction_id" INTEGER,
    "page_or_frame" TEXT,
    "coordinates" TEXT,
    "supporting_quote" TEXT,
    "evidence_role" TEXT NOT NULL DEFAULT 'supports',
    "source_independence_group" TEXT,
    "strength" DOUBLE PRECISION DEFAULT 0.5,
    "note" TEXT,
    "created_at" TEXT NOT NULL,
    "content_hash" TEXT,
    "verified_at" TEXT
);

-- claim_relations (102 righe)
CREATE TABLE IF NOT EXISTS "claim_relations" (
    "id" SERIAL PRIMARY KEY,
    "claim_a_id" INTEGER NOT NULL,
    "claim_b_id" INTEGER NOT NULL,
    "relation_type" TEXT NOT NULL,
    "confidence" DOUBLE PRECISION DEFAULT 0.5,
    "motivation" TEXT,
    "method" TEXT,
    "review_status" TEXT DEFAULT 'pending',
    "reviewed_by" TEXT,
    "reviewed_at" TEXT,
    "created_at" TEXT NOT NULL
);

-- claims (43 righe)
CREATE TABLE IF NOT EXISTS "claims" (
    "id" SERIAL PRIMARY KEY,
    "stable_id" TEXT,
    "subject_type" TEXT NOT NULL,
    "subject_id" INTEGER,
    "subject_label" TEXT,
    "predicate" TEXT NOT NULL,
    "object_type" TEXT,
    "object_id" INTEGER,
    "object_label" TEXT,
    "object_value" TEXT,
    "original_value" TEXT,
    "temporal_range_start" TEXT,
    "temporal_range_end" TEXT,
    "temporal_precision" TEXT,
    "temporal_uncertainty" TEXT,
    "place" TEXT,
    "epistemic_status" TEXT DEFAULT 'possible',
    "confidence" DOUBLE PRECISION DEFAULT 0.3,
    "extraction_method" TEXT,
    "extraction_id" INTEGER,
    "review_status" TEXT DEFAULT 'proposed',
    "reviewed_by" TEXT,
    "reviewed_at" TEXT,
    "review_reason" TEXT,
    "created_by" TEXT,
    "version" TEXT DEFAULT '1',
    "created_at" TEXT NOT NULL,
    "updated_at" TEXT NOT NULL,
    "unit" TEXT,
    "qualifiers_json" TEXT,
    "polarity" TEXT DEFAULT 'positive'
);

-- collegamenti (2349417 righe)
CREATE TABLE IF NOT EXISTS "collegamenti" (
    "id" SERIAL PRIMARY KEY,
    "entita_id" INTEGER NOT NULL,
    "tabella_origine" TEXT NOT NULL,
    "record_id" INTEGER NOT NULL,
    "tipo_collegamento" TEXT,
    "confidenza" DOUBLE PRECISION DEFAULT 1.0,
    "elaborato_il" TEXT NOT NULL
);

-- compliance_authorizations (0 righe)
CREATE TABLE IF NOT EXISTS "compliance_authorizations" (
    "id" SERIAL PRIMARY KEY,
    "source_policy_id" INTEGER,
    "record_id" TEXT,
    "scope" TEXT,
    "purpose" TEXT,
    "granted_by" TEXT,
    "granted_to" TEXT,
    "protocol" TEXT,
    "valid_from" TEXT,
    "valid_until" TEXT,
    "limitations" TEXT,
    "revoked" INTEGER DEFAULT 0,
    "revoked_at" TEXT,
    "revoked_by" TEXT,
    "revoke_reason" TEXT,
    "created_at" TEXT
);

-- compliance_decisions (0 righe)
CREATE TABLE IF NOT EXISTS "compliance_decisions" (
    "id" SERIAL PRIMARY KEY,
    "source_record_id" TEXT,
    "digital_object_id" TEXT,
    "requested_action" TEXT NOT NULL,
    "decision" TEXT NOT NULL,
    "policy_id" INTEGER,
    "rule_code" TEXT,
    "reason" TEXT,
    "limitations_json" TEXT,
    "authorization_id" INTEGER,
    "decided_by" TEXT,
    "decision_source" TEXT DEFAULT 'automatic_policy',
    "created_at" TEXT
);

-- compliance_review_queue (0 righe)
CREATE TABLE IF NOT EXISTS "compliance_review_queue" (
    "id" SERIAL PRIMARY KEY,
    "item_type" TEXT NOT NULL,
    "record_id" TEXT,
    "source_policy_id" INTEGER,
    "reason" TEXT,
    "priority" TEXT DEFAULT 'medium',
    "status" TEXT DEFAULT 'pending',
    "reviewed_by" TEXT,
    "reviewed_at" TEXT,
    "decision" TEXT,
    "motivation" TEXT,
    "created_at" TEXT
);

-- consolidated_memory (1 righe)
CREATE TABLE IF NOT EXISTS "consolidated_memory" (
    "id" SERIAL PRIMARY KEY,
    "topic" TEXT NOT NULL,
    "summary" TEXT,
    "entities_json" TEXT,
    "sources_json" TEXT,
    "archivio_fonti_ids" TEXT,
    "query_count" INTEGER DEFAULT 1,
    "confidence" DOUBLE PRECISION DEFAULT 0.0,
    "last_verified_at" TEXT,
    "created_at" TEXT NOT NULL
);

-- content_fingerprints (0 righe)
CREATE TABLE IF NOT EXISTS "content_fingerprints" (
    "id" SERIAL PRIMARY KEY,
    "source_item_id" INTEGER,
    "source_table" TEXT,
    "content_hash" TEXT NOT NULL,
    "hash_algorithm" TEXT DEFAULT 'sha256',
    "content_type" TEXT,
    "content_size" INTEGER,
    "fingerprint_scope" TEXT DEFAULT 'full',
    "created_at" TEXT NOT NULL
);

-- decorati (1286 righe)
CREATE TABLE IF NOT EXISTS "decorati" (
    "id" SERIAL PRIMARY KEY,
    "source_id" TEXT,
    "albo_id" TEXT,
    "albo_nome" TEXT,
    "cognome" TEXT,
    "nome" TEXT,
    "comune_nascita" TEXT,
    "comune_residenza" TEXT,
    "data_nascita" TEXT,
    "data_morte" TEXT,
    "anno_nascita" INTEGER,
    "anno_morte" INTEGER,
    "guerra" TEXT,
    "grado" TEXT,
    "corpo_militare" TEXT,
    "reparto" TEXT,
    "decorazione" TEXT,
    "motivazione" TEXT,
    "causa_morte" TEXT,
    "luogo_morte" TEXT,
    "luogo_cattura" TEXT,
    "luogo_internamento" TEXT,
    "matricola" TEXT,
    "professione" TEXT,
    "note" TEXT,
    "url_scheda" TEXT,
    "foto_urls" TEXT,
    "raw_json" TEXT,
    "elaborato_il" TEXT NOT NULL
);

-- decorati_nastroazzurro (279832 righe)
CREATE TABLE IF NOT EXISTS "decorati_nastroazzurro" (
    "id" SERIAL PRIMARY KEY,
    "source_id" TEXT,
    "id_arma" INTEGER,
    "arma" TEXT,
    "cognome" TEXT,
    "nome" TEXT,
    "anno_decorazione" TEXT,
    "tipo_decorazione" TEXT,
    "elaborato_il" TEXT NOT NULL
);

-- document_extractions (0 righe)
CREATE TABLE IF NOT EXISTS "document_extractions" (
    "id" SERIAL PRIMARY KEY,
    "document_id" INTEGER,
    "document_table" TEXT,
    "version" TEXT DEFAULT '1',
    "method" TEXT NOT NULL,
    "original_text" TEXT,
    "ocr_text" TEXT,
    "language" TEXT,
    "coordinates" TEXT,
    "raw_structured_output_json" TEXT,
    "model_version" TEXT,
    "review_status" TEXT DEFAULT 'pending',
    "reviewed_by" TEXT,
    "reviewed_at" TEXT,
    "created_at" TEXT NOT NULL,
    "updated_at" TEXT NOT NULL
);

-- documenti_nara_catalog (272 righe)
CREATE TABLE IF NOT EXISTS "documenti_nara_catalog" (
    "id" SERIAL PRIMARY KEY,
    "na_id" TEXT NOT NULL,
    "title" TEXT,
    "description" TEXT,
    "record_group" TEXT,
    "series" TEXT,
    "inclusive_dates" TEXT,
    "unit" TEXT,
    "location" TEXT,
    "document_type" TEXT,
    "has_digital_objects" INTEGER DEFAULT 0,
    "file_urls" TEXT,
    "search_query" TEXT,
    "source_url" TEXT,
    "elaborato_il" TEXT NOT NULL,
    "pdf_url" TEXT,
    "pdf_scaricato" INTEGER DEFAULT 0,
    "archivio_fonti_id" INTEGER
);

-- documenti_nara_t315 (1153 righe)
CREATE TABLE IF NOT EXISTS "documenti_nara_t315" (
    "id" SERIAL PRIMARY KEY,
    "roll" TEXT NOT NULL,
    "frame" INTEGER NOT NULL,
    "file_immagine" TEXT,
    "tipo_documento" TEXT,
    "data_documento" TEXT,
    "data_raw" TEXT,
    "numero_documento" TEXT,
    "mittente" TEXT,
    "destinatario" TEXT,
    "unita_citate" TEXT,
    "luoghi_citati" TEXT,
    "perdite" TEXT,
    "testo_ocr" TEXT,
    "lingua" TEXT DEFAULT 'de',
    "divisione" TEXT,
    "confidenza" DOUBLE PRECISION,
    "note" TEXT,
    "elaborato_il" TEXT NOT NULL,
    "archivio_fonti_id" INTEGER
);

-- edge_evidence (0 righe)
CREATE TABLE IF NOT EXISTS "edge_evidence" (
    "id" SERIAL PRIMARY KEY,
    "edge_id" INTEGER NOT NULL,
    "evidence_type" TEXT NOT NULL,
    "source_item_id" INTEGER,
    "source_table" TEXT,
    "claim_id" INTEGER,
    "supporting_quote" TEXT,
    "evidence_role" TEXT DEFAULT 'supports',
    "strength" DOUBLE PRECISION DEFAULT 0.5,
    "created_at" TEXT NOT NULL
);

-- edge_versions (0 righe)
CREATE TABLE IF NOT EXISTS "edge_versions" (
    "id" SERIAL PRIMARY KEY,
    "edge_id" INTEGER NOT NULL,
    "version" INTEGER NOT NULL,
    "score" DOUBLE PRECISION,
    "algorithm_version" TEXT,
    "feature_contributions_json" TEXT,
    "contrary_signals_json" TEXT,
    "status" TEXT,
    "changed_by" TEXT,
    "change_reason" TEXT,
    "created_at" TEXT NOT NULL
);

-- entita (688739 righe)
CREATE TABLE IF NOT EXISTS "entita" (
    "id" SERIAL PRIMARY KEY,
    "tipo" TEXT NOT NULL,
    "valore" TEXT NOT NULL,
    "valore_normalizzato" TEXT,
    "cognome" TEXT,
    "nome" TEXT,
    "data" TEXT,
    "luogo" TEXT,
    "contesto" TEXT,
    "fonte_tabella" TEXT,
    "fonte_id" INTEGER,
    "elaborato_il" TEXT NOT NULL
);

-- entity_match_candidates (0 righe)
CREATE TABLE IF NOT EXISTS "entity_match_candidates" (
    "id" SERIAL PRIMARY KEY,
    "local_entity_type" TEXT NOT NULL,
    "local_entity_id" INTEGER NOT NULL,
    "local_table" TEXT,
    "local_record_id" INTEGER,
    "candidate_source" TEXT,
    "candidate_record_id" INTEGER,
    "candidate_external_id" TEXT,
    "score" DOUBLE PRECISION DEFAULT 0.0,
    "score_breakdown_json" TEXT,
    "contrary_signals_json" TEXT,
    "missing_data_json" TEXT,
    "threshold_applied" DOUBLE PRECISION,
    "algorithm_version" TEXT,
    "status" TEXT DEFAULT 'candidate',
    "review_decision" TEXT,
    "reviewer" TEXT,
    "review_reason" TEXT,
    "reviewed_at" TEXT,
    "created_at" TEXT NOT NULL,
    "updated_at" TEXT NOT NULL
);

-- entity_variants (299 righe)
CREATE TABLE IF NOT EXISTS "entity_variants" (
    "id" SERIAL PRIMARY KEY,
    "entity_type" TEXT NOT NULL,
    "entity_id" INTEGER NOT NULL,
    "field_name" TEXT NOT NULL,
    "original_value" TEXT NOT NULL,
    "variant_value" TEXT NOT NULL,
    "variant_type" TEXT NOT NULL,
    "origin" TEXT,
    "confidence" DOUBLE PRECISION DEFAULT 0.5,
    "verified" INTEGER DEFAULT 0,
    "created_at" TEXT NOT NULL
);

-- event_aliases (90 righe)
CREATE TABLE IF NOT EXISTS "event_aliases" (
    "id" SERIAL PRIMARY KEY,
    "event_id" INTEGER NOT NULL,
    "alias" TEXT NOT NULL,
    "alias_type" TEXT DEFAULT 'alias',
    "created_at" TEXT NOT NULL
);

-- event_links (0 righe)
CREATE TABLE IF NOT EXISTS "event_links" (
    "id" SERIAL PRIMARY KEY,
    "evento_id" INTEGER NOT NULL,
    "target_table" TEXT NOT NULL,
    "target_id" INTEGER NOT NULL,
    "link_type" TEXT NOT NULL,
    "match_field" TEXT,
    "match_value" TEXT,
    "confidence" DOUBLE PRECISION DEFAULT 0.5,
    "created_at" TEXT
);

-- event_links (891874 righe)
CREATE TABLE IF NOT EXISTS "event_links" (
    "id" SERIAL PRIMARY KEY,
    "evento_id" INTEGER NOT NULL,
    "target_table" TEXT NOT NULL,
    "target_id" INTEGER NOT NULL,
    "link_type" TEXT NOT NULL,
    "match_field" TEXT,
    "match_value" TEXT,
    "confidence" DOUBLE PRECISION DEFAULT 0.5,
    "created_at" TEXT
);

-- eventi_1gm (15 righe)
CREATE TABLE IF NOT EXISTS "eventi_1gm" (
    "id" SERIAL PRIMARY KEY,
    "nome" TEXT NOT NULL,
    "data_inizio" TEXT,
    "data_fine" TEXT,
    "luogo" TEXT,
    "aliases" TEXT,
    "keywords" TEXT,
    "descrizione" TEXT,
    "created_at" TEXT
);

-- eventi_1gm (22 righe)
CREATE TABLE IF NOT EXISTS "eventi_1gm" (
    "id" SERIAL PRIMARY KEY,
    "nome" TEXT NOT NULL,
    "data_inizio" TEXT,
    "data_fine" TEXT,
    "luogo" TEXT,
    "aliases" TEXT,
    "keywords" TEXT,
    "descrizione" TEXT,
    "created_at" TEXT,
    "stable_id" TEXT,
    "conflict" TEXT DEFAULT 'WWI',
    "event_type" TEXT DEFAULT 'battaglia',
    "parent_event_id" TEXT,
    "temporal_precision" TEXT DEFAULT 'day',
    "general_location" TEXT,
    "localities_json" TEXT DEFAULT '[]',
    "subjects_json" TEXT DEFAULT '[]',
    "units_json" TEXT DEFAULT '[]',
    "review_status" TEXT DEFAULT 'candidate',
    "narrative_version" TEXT,
    "narrative_updated_at" TEXT
);

-- external_access_requests (0 righe)
CREATE TABLE IF NOT EXISTS "external_access_requests" (
    "id" SERIAL PRIMARY KEY,
    "external_source_record_id" INTEGER NOT NULL,
    "candidate_id" INTEGER,
    "research_subject_id" INTEGER,
    "request_status" TEXT DEFAULT 'da_valutare',
    "recipient" TEXT,
    "request_reason" TEXT,
    "requested_documents" TEXT,
    "requested_at" TEXT,
    "response_received_at" TEXT,
    "authorization_reference" TEXT,
    "authorization_date" TEXT,
    "usage_scope" TEXT,
    "publication_allowed" INTEGER DEFAULT 0,
    "notes" TEXT,
    "created_by" TEXT,
    "created_at" TEXT NOT NULL,
    "updated_at" TEXT NOT NULL
);

-- external_digital_objects (0 righe)
CREATE TABLE IF NOT EXISTS "external_digital_objects" (
    "id" SERIAL PRIMARY KEY,
    "external_source_record_id" INTEGER NOT NULL,
    "external_object_id" TEXT,
    "object_type" TEXT,
    "media_type" TEXT,
    "label" TEXT,
    "viewer_url" TEXT,
    "page_url" TEXT,
    "download_url" TEXT,
    "iiif_manifest_url" TEXT,
    "thumbnail_url" TEXT,
    "digital_object_available" INTEGER DEFAULT 0,
    "publicly_viewable" INTEGER DEFAULT 0,
    "public_download_allowed" INTEGER DEFAULT 0,
    "authorization_required" INTEGER DEFAULT 0,
    "local_file_path" TEXT,
    "sha256" TEXT,
    "file_size" INTEGER,
    "ocr_status" TEXT DEFAULT 'pending',
    "rights_statement" TEXT,
    "credit_line" TEXT,
    "retrieved_at" TEXT,
    "created_at" TEXT NOT NULL,
    "updated_at" TEXT NOT NULL
);

-- external_import_jobs (2 righe)
CREATE TABLE IF NOT EXISTS "external_import_jobs" (
    "id" SERIAL PRIMARY KEY,
    "provider" TEXT NOT NULL,
    "job_type" TEXT NOT NULL,
    "status" TEXT DEFAULT 'pending',
    "total_records" INTEGER DEFAULT 0,
    "processed_records" INTEGER DEFAULT 0,
    "error_count" INTEGER DEFAULT 0,
    "last_error" TEXT,
    "checkpoint_data" TEXT,
    "started_at" TEXT,
    "finished_at" TEXT,
    "created_at" TEXT NOT NULL,
    "updated_at" TEXT NOT NULL
);

-- external_person_mentions (0 righe)
CREATE TABLE IF NOT EXISTS "external_person_mentions" (
    "id" SERIAL PRIMARY KEY,
    "external_source_record_id" INTEGER NOT NULL,
    "surname_raw" TEXT,
    "name_raw" TEXT,
    "full_name_raw" TEXT,
    "normalized_surname" TEXT,
    "normalized_name" TEXT,
    "father_name_raw" TEXT,
    "mother_name_raw" TEXT,
    "birth_date_text" TEXT,
    "birth_date" TEXT,
    "birth_place_raw" TEXT,
    "residence_raw" TEXT,
    "rank_raw" TEXT,
    "military_unit_raw" TEXT,
    "service_number" TEXT,
    "prisoner_number" TEXT,
    "camp_raw" TEXT,
    "status_raw" TEXT,
    "event_date_text" TEXT,
    "event_place_raw" TEXT,
    "role_in_metadata" TEXT,
    "source_text" TEXT,
    "extraction_method" TEXT,
    "extraction_confidence" DOUBLE PRECISION DEFAULT 1.0,
    "human_verified" INTEGER DEFAULT 0,
    "created_at" TEXT NOT NULL,
    "updated_at" TEXT NOT NULL
);

-- external_record_links (0 righe)
CREATE TABLE IF NOT EXISTS "external_record_links" (
    "id" SERIAL PRIMARY KEY,
    "external_source_record_id" INTEGER NOT NULL,
    "external_person_mention_id" INTEGER,
    "target_table" TEXT NOT NULL,
    "target_record_id" INTEGER NOT NULL,
    "target_entity_id" INTEGER,
    "link_type" TEXT NOT NULL,
    "match_status" TEXT DEFAULT 'candidate',
    "match_score" DOUBLE PRECISION DEFAULT 0.0,
    "match_method" TEXT,
    "matched_fields_json" TEXT,
    "conflicting_fields_json" TEXT,
    "evidence_json" TEXT,
    "explanation" TEXT,
    "review_status" TEXT DEFAULT 'pending',
    "reviewed_by" TEXT,
    "reviewed_at" TEXT,
    "created_at" TEXT NOT NULL,
    "updated_at" TEXT NOT NULL
);

-- external_source_facts (0 righe)
CREATE TABLE IF NOT EXISTS "external_source_facts" (
    "id" SERIAL PRIMARY KEY,
    "external_source_record_id" INTEGER NOT NULL,
    "external_person_mention_id" INTEGER,
    "fact_type" TEXT NOT NULL,
    "fact_value" TEXT,
    "date_text" TEXT,
    "date_value" TEXT,
    "place_raw" TEXT,
    "description" TEXT,
    "source_text" TEXT,
    "extraction_method" TEXT,
    "confidence" DOUBLE PRECISION DEFAULT 1.0,
    "human_verified" INTEGER DEFAULT 0,
    "created_at" TEXT NOT NULL
);

-- external_source_records (1 righe)
CREATE TABLE IF NOT EXISTS "external_source_records" (
    "id" SERIAL PRIMARY KEY,
    "provider" TEXT NOT NULL,
    "archive_name" TEXT,
    "archive_branch" TEXT,
    "external_id" TEXT NOT NULL,
    "record_level" TEXT NOT NULL,
    "record_type" TEXT,
    "title" TEXT,
    "description" TEXT,
    "date_text" TEXT,
    "date_from" TEXT,
    "date_to" TEXT,
    "fonds_external_id" TEXT,
    "fonds_title" TEXT,
    "series_external_id" TEXT,
    "series_title" TEXT,
    "subseries_external_id" TEXT,
    "subseries_title" TEXT,
    "parent_external_id" TEXT,
    "reference_code" TEXT,
    "box_number" TEXT,
    "file_number" TEXT,
    "register_number" TEXT,
    "protocol_number" TEXT,
    "extent" TEXT,
    "language" TEXT,
    "people_metadata_json" TEXT,
    "places_metadata_json" TEXT,
    "military_units_metadata_json" TEXT,
    "camps_metadata_json" TEXT,
    "subjects_metadata_json" TEXT,
    "canonical_record_url" TEXT NOT NULL,
    "parent_record_url" TEXT,
    "digital_object_available" INTEGER DEFAULT 0,
    "digital_object_url" TEXT,
    "access_status" TEXT DEFAULT 'active',
    "source_notes" TEXT,
    "metadata_hash" TEXT,
    "http_status" INTEGER,
    "first_seen_at" TEXT NOT NULL,
    "last_verified_at" TEXT,
    "created_at" TEXT NOT NULL,
    "updated_at" TEXT NOT NULL
);

-- fondi_archivistici (4808 righe)
CREATE TABLE IF NOT EXISTS "fondi_archivistici" (
    "id" SERIAL PRIMARY KEY,
    "codice_fondo" TEXT,
    "titolo" TEXT,
    "file_pdf" TEXT NOT NULL,
    "url" TEXT,
    "pagina" INTEGER NOT NULL,
    "descrizione" TEXT,
    "periodo" TEXT,
    "busta" TEXT,
    "fascicolo" TEXT,
    "luoghi" TEXT,
    "raw_text" TEXT,
    "elaborato_il" TEXT NOT NULL
);

-- fonti_indice (35664 righe)
CREATE TABLE IF NOT EXISTS "fonti_indice" (
    "id" SERIAL PRIMARY KEY,
    "archivio" TEXT,
    "fondo" TEXT,
    "serie" TEXT,
    "segnatura" TEXT,
    "titolo" TEXT,
    "tipo_fonte" TEXT,
    "soggetti_collegati" TEXT,
    "persone_possibili" TEXT,
    "reparto" TEXT,
    "luogo" TEXT,
    "data_inizio" TEXT,
    "data_fine" TEXT,
    "url_catalogo" TEXT,
    "url_file" TEXT,
    "iiif_manifest" TEXT,
    "page_start" INTEGER,
    "page_end" INTEGER,
    "hash_se_disponibile" TEXT,
    "access_type" TEXT DEFAULT 'online',
    "fetch_status" TEXT DEFAULT 'mai_scaricato',
    "last_checked_at" TEXT,
    "confidence" DOUBLE PRECISION DEFAULT 0.5,
    "note" TEXT,
    "created_at" TEXT NOT NULL,
    "url_kind" TEXT DEFAULT 'source',
    "quarantined_at" TEXT
);

-- fonti_narrative (40 righe)
CREATE TABLE IF NOT EXISTS "fonti_narrative" (
    "id" SERIAL PRIMARY KEY,
    "sha256" TEXT NOT NULL,
    "nome_file" TEXT NOT NULL,
    "path_locale" TEXT NOT NULL,
    "formato" TEXT NOT NULL,
    "tipo_fonte" TEXT NOT NULL,
    "archivio" TEXT,
    "fondo" TEXT,
    "unita_principale" TEXT,
    "teatro" TEXT,
    "data_documento" TEXT,
    "data_inizio" TEXT,
    "data_fine" TEXT,
    "autore" TEXT,
    "soggetti_json" TEXT,
    "persone_possibili" TEXT,
    "titolo" TEXT,
    "descrizione" TEXT,
    "testo_ocr" TEXT,
    "ocr_status" TEXT DEFAULT 'pending',
    "access_type" TEXT DEFAULT 'locale',
    "fetch_status" TEXT DEFAULT 'scaricato',
    "created_at" TEXT DEFAULT NOW(),
    "updated_at" TEXT DEFAULT NOW()
);

-- fonti_risorse (0 righe)
CREATE TABLE IF NOT EXISTS "fonti_risorse" (
    "id" SERIAL PRIMARY KEY,
    "fonte_id" INTEGER,
    "url_pagina" TEXT NOT NULL,
    "url_documento" TEXT,
    "tipo_risorsa" TEXT,
    "titolo" TEXT,
    "descrizione" TEXT,
    "autore" TEXT,
    "ente_titolare" TEXT,
    "data_pubblicazione" TEXT,
    "lingua" TEXT,
    "licenza" TEXT,
    "note_copyright" TEXT,
    "hash_contenuto" TEXT,
    "first_seen_at" TEXT,
    "last_checked_at" TEXT,
    "stato" TEXT DEFAULT 'non_verificato'
);

-- generated_narratives (0 righe)
CREATE TABLE IF NOT EXISTS "generated_narratives" (
    "id" SERIAL PRIMARY KEY,
    "entity_type" TEXT NOT NULL,
    "entity_id" INTEGER NOT NULL,
    "narrative_type" TEXT NOT NULL,
    "audience" TEXT DEFAULT 'public',
    "structured_text" TEXT,
    "claim_ids_json" TEXT,
    "gaps_json" TEXT,
    "deductions_json" TEXT,
    "confidence_level" DOUBLE PRECISION DEFAULT 0.3,
    "model_version" TEXT,
    "prompt_version" TEXT,
    "review_status" TEXT DEFAULT 'draft',
    "reviewed_by" TEXT,
    "reviewed_at" TEXT,
    "version" TEXT DEFAULT '1',
    "created_at" TEXT NOT NULL,
    "updated_at" TEXT NOT NULL
);

-- graph_edge_reviews (0 righe)
CREATE TABLE IF NOT EXISTS "graph_edge_reviews" (
    "edge_id" TEXT PRIMARY KEY,
    "decision" TEXT NOT NULL,
    "status" TEXT NOT NULL,
    "note" TEXT,
    "reviewed_by" TEXT NOT NULL,
    "reviewed_at" TEXT NOT NULL
);

-- graph_edges (0 righe)
CREATE TABLE IF NOT EXISTS "graph_edges" (
    "id" TEXT PRIMARY KEY,
    "source_node_id" TEXT NOT NULL,
    "target_node_id" TEXT NOT NULL,
    "relation_type" TEXT NOT NULL,
    "relation_label" TEXT NOT NULL,
    "direction" TEXT NOT NULL DEFAULT 'directed',
    "status" TEXT NOT NULL DEFAULT 'candidate',
    "confidence" DOUBLE PRECISION,
    "explanation" TEXT NOT NULL,
    "evidence_json" TEXT NOT NULL DEFAULT '[]',
    "contrary_signals_json" TEXT NOT NULL DEFAULT '[]',
    "algorithm" TEXT NOT NULL,
    "algorithm_version" TEXT NOT NULL,
    "source_system" TEXT NOT NULL,
    "source_edge_id" TEXT,
    "first_seen_at" TEXT NOT NULL,
    "last_seen_at" TEXT NOT NULL,
    "active" INTEGER NOT NULL DEFAULT 1
);

-- graph_integrity_issues (0 righe)
CREATE TABLE IF NOT EXISTS "graph_integrity_issues" (
    "id" SERIAL PRIMARY KEY,
    "run_id" INTEGER,
    "issue_key" TEXT NOT NULL,
    "code" TEXT NOT NULL,
    "severity" TEXT NOT NULL,
    "source_system" TEXT,
    "source_edge_id" TEXT,
    "message" TEXT NOT NULL,
    "details_json" TEXT,
    "status" TEXT NOT NULL DEFAULT 'open',
    "created_at" TEXT NOT NULL,
    "resolved_at" TEXT
);

-- graph_nodes (0 righe)
CREATE TABLE IF NOT EXISTS "graph_nodes" (
    "id" TEXT PRIMARY KEY,
    "namespace" TEXT NOT NULL,
    "node_type" TEXT NOT NULL,
    "label" TEXT NOT NULL,
    "source_table" TEXT NOT NULL,
    "source_id" INTEGER NOT NULL,
    "external_id" TEXT,
    "attributes_json" TEXT NOT NULL DEFAULT '{}',
    "status" TEXT NOT NULL DEFAULT 'active',
    "algorithm_version" TEXT NOT NULL,
    "first_seen_at" TEXT NOT NULL,
    "updated_at" TEXT NOT NULL
);

-- graph_pipeline_runs (0 righe)
CREATE TABLE IF NOT EXISTS "graph_pipeline_runs" (
    "id" SERIAL PRIMARY KEY,
    "pipeline" TEXT NOT NULL,
    "algorithm_version" TEXT NOT NULL,
    "mode" TEXT NOT NULL,
    "status" TEXT NOT NULL,
    "scanned" INTEGER NOT NULL DEFAULT 0,
    "nodes_written" INTEGER NOT NULL DEFAULT 0,
    "edges_written" INTEGER NOT NULL DEFAULT 0,
    "issues_found" INTEGER NOT NULL DEFAULT 0,
    "checkpoint_json" TEXT,
    "started_at" TEXT NOT NULL,
    "finished_at" TEXT,
    "error" TEXT
);

-- internati (20465 righe)
CREATE TABLE IF NOT EXISTS "internati" (
    "id" SERIAL PRIMARY KEY,
    "lettera" TEXT NOT NULL,
    "file_pdf" TEXT NOT NULL,
    "pagina" INTEGER NOT NULL,
    "cognome" TEXT,
    "nome" TEXT,
    "data_nascita" TEXT,
    "luogo_nascita" TEXT,
    "residenza" TEXT,
    "grado" TEXT,
    "luogo_cattura" TEXT,
    "data_cattura" TEXT,
    "luogo_internamento" TEXT,
    "matricola" TEXT,
    "arbeitskommando" TEXT,
    "mansione" TEXT,
    "sorte" TEXT,
    "data" TEXT,
    "documenti" TEXT,
    "raw_text" TEXT,
    "elaborato_il" TEXT NOT NULL,
    "needs_review" INTEGER DEFAULT 0,
    "review_reason" TEXT,
    "luogo_validato" INTEGER DEFAULT 0
);

-- lettere_personali (1 righe)
CREATE TABLE IF NOT EXISTS "lettere_personali" (
    "id" SERIAL PRIMARY KEY,
    "filename" TEXT,
    "file_path" TEXT,
    "mittente" TEXT,
    "destinatario" TEXT,
    "data_lettera" TEXT,
    "luogo" TEXT,
    "oggetto" TEXT,
    "corpo_testo" TEXT,
    "note" TEXT,
    "confidenza" DOUBLE PRECISION,
    "lingua" TEXT,
    "raw_response" TEXT,
    "sha256" TEXT,
    "sorgente_db" TEXT,
    "sorgente_id" INTEGER,
    "elaborato_il" TEXT
);

-- map_features (0 righe)
CREATE TABLE IF NOT EXISTS "map_features" (
    "id" TEXT PRIMARY KEY,
    "event_id" TEXT NOT NULL,
    "phase" TEXT NOT NULL DEFAULT '',
    "feature_type" TEXT NOT NULL,
    "geojson" TEXT NOT NULL,
    "date_start" TEXT,
    "date_end" TEXT,
    "label" TEXT NOT NULL,
    "description" TEXT,
    "certainty" TEXT NOT NULL DEFAULT 'verified',
    "source_table" TEXT,
    "source_id" INTEGER,
    "source_url" TEXT,
    "review_status" TEXT NOT NULL DEFAULT 'proposed',
    "reviewed_by" TEXT,
    "reviewed_at" TEXT,
    "created_at" TEXT NOT NULL,
    "updated_at" TEXT NOT NULL
);

-- memory_trace (55 righe)
CREATE TABLE IF NOT EXISTS "memory_trace" (
    "id" SERIAL PRIMARY KEY,
    "query" TEXT NOT NULL,
    "cue_persona" TEXT,
    "cue_luogo" TEXT,
    "cue_reparto" TEXT,
    "cue_data" TEXT,
    "cue_guerra" TEXT,
    "cue_archivio" TEXT,
    "route_selected" TEXT,
    "sources_found" INTEGER DEFAULT 0,
    "image_only_found" INTEGER DEFAULT 0,
    "confidence" DOUBLE PRECISION DEFAULT 0.0,
    "used_fts" INTEGER DEFAULT 0,
    "used_graph" INTEGER DEFAULT 0,
    "used_cloud_ai" INTEGER DEFAULT 0,
    "tokens_saved_estimate" INTEGER DEFAULT 0,
    "response_ms" INTEGER DEFAULT 0,
    "created_at" TEXT NOT NULL
);

-- menzioni (10976 righe)
CREATE TABLE IF NOT EXISTS "menzioni" (
    "id" SERIAL PRIMARY KEY,
    "fondo_id" INTEGER,
    "file_pdf" TEXT NOT NULL,
    "pagina" INTEGER,
    "tipo" TEXT NOT NULL,
    "cognome" TEXT,
    "nome" TEXT,
    "testo_originale" TEXT,
    "grado" TEXT,
    "reparto" TEXT,
    "luogo" TEXT,
    "data" TEXT,
    "contesto" TEXT,
    "elaborato_il" TEXT NOT NULL
);

-- nara_catalog_files (0 righe)
CREATE TABLE IF NOT EXISTS "nara_catalog_files" (
    "id" SERIAL PRIMARY KEY,
    "nara_catalog_id" INTEGER NOT NULL,
    "na_id" TEXT,
    "url_originale" TEXT,
    "hash_sha256" TEXT,
    "archivio_fonti_id" INTEGER,
    "scaricato" INTEGER DEFAULT 0,
    "scaricato_il" TEXT
);

-- ocr_lettere (1 righe)
CREATE TABLE IF NOT EXISTS "ocr_lettere" (
    "id" SERIAL PRIMARY KEY,
    "filename" TEXT NOT NULL,
    "file_path" TEXT NOT NULL,
    "mittente" TEXT,
    "destinatario" TEXT,
    "data_lettera" TEXT,
    "luogo" TEXT,
    "oggetto" TEXT,
    "corpo_testo" TEXT,
    "note" TEXT,
    "confidenza" DOUBLE PRECISION,
    "lingua" TEXT,
    "raw_response" TEXT,
    "elaborato_il" TEXT NOT NULL
);

-- permitted_operations (68 righe)
CREATE TABLE IF NOT EXISTS "permitted_operations" (
    "id" SERIAL PRIMARY KEY,
    "policy_id" INTEGER NOT NULL,
    "operation" TEXT NOT NULL,
    "decision" TEXT NOT NULL,
    "conditions_json" TEXT,
    "minimization_rules_json" TEXT,
    "destination_allowed" TEXT,
    "retention_days" INTEGER,
    "ai_providers_allowed_json" TEXT,
    "attribution_required" INTEGER DEFAULT 0,
    "attribution_text" TEXT,
    "expires_at" TEXT,
    "created_at" TEXT NOT NULL,
    "updated_at" TEXT NOT NULL
);

-- populate_progress (8516 righe)
CREATE TABLE IF NOT EXISTS "populate_progress" (
    "internato_id" SERIAL PRIMARY KEY,
    "status" TEXT,
    "found_count" INTEGER,
    "processed_at" TEXT
);

-- progress (63 righe)
CREATE TABLE IF NOT EXISTS "progress" (
    "lettera" TEXT PRIMARY KEY,
    "total_pages" INTEGER,
    "processed_pages" INTEGER DEFAULT 0,
    "status" TEXT DEFAULT 'pending',
    "started_at" TEXT,
    "finished_at" TEXT
);

-- prompt_versions (1 righe)
CREATE TABLE IF NOT EXISTS "prompt_versions" (
    "id" SERIAL PRIMARY KEY,
    "prompt_name" TEXT NOT NULL,
    "version" TEXT NOT NULL,
    "system_prompt" TEXT,
    "user_prompt_template" TEXT,
    "variables_json" TEXT,
    "constraints_json" TEXT,
    "active" INTEGER DEFAULT 0,
    "created_at" TEXT NOT NULL,
    "updated_at" TEXT NOT NULL
);

-- publication_versions (0 righe)
CREATE TABLE IF NOT EXISTS "publication_versions" (
    "id" SERIAL PRIMARY KEY,
    "narrative_id" INTEGER,
    "version" INTEGER NOT NULL,
    "published_text" TEXT,
    "audience" TEXT DEFAULT 'public',
    "review_status" TEXT DEFAULT 'pending',
    "reviewed_by" TEXT,
    "reviewed_at" TEXT,
    "published_by" TEXT,
    "published_at" TEXT,
    "redactions_json" TEXT,
    "claim_ids_json" TEXT,
    "created_at" TEXT NOT NULL
);

-- rc_administrative_cases (0 righe)
CREATE TABLE IF NOT EXISTS "rc_administrative_cases" (
    "id" SERIAL PRIMARY KEY,
    "candidate_id" INTEGER NOT NULL,
    "recognition_type_id" INTEGER,
    "ente_destinatario" TEXT,
    "ufficio" TEXT,
    "protocollo" TEXT,
    "data_invio" TEXT,
    "modalita_trasmissione" TEXT,
    "responsabile" TEXT,
    "scadenze" TEXT,
    "stato" TEXT DEFAULT 'in_preparazione',
    "richieste_integrazione" TEXT,
    "esito" TEXT,
    "decreto_provvedimento" TEXT,
    "created_at" TEXT NOT NULL,
    "updated_at" TEXT NOT NULL
);

-- rc_ai_analyses (28 righe)
CREATE TABLE IF NOT EXISTS "rc_ai_analyses" (
    "id" SERIAL PRIMARY KEY,
    "candidate_id" INTEGER NOT NULL,
    "tipo_analisi" TEXT NOT NULL,
    "riepilogo_esecutivo" TEXT,
    "processo_logico_dettagliato" TEXT,
    "fonti_consultate_json" TEXT,
    "onorificenze_ipotizzabili_json" TEXT,
    "percentuali_stimate_json" TEXT,
    "precedenti_attribuzioni_json" TEXT,
    "fattori_favorevoli" TEXT,
    "fattori_sfavorevoli" TEXT,
    "raccomandazioni" TEXT,
    "livello_confidenza" TEXT DEFAULT 'basso',
    "modello_ai" TEXT,
    "versione_modello" TEXT,
    "created_at" TEXT NOT NULL,
    "updated_at" TEXT NOT NULL
);

-- rc_audit_log (164 righe)
CREATE TABLE IF NOT EXISTS "rc_audit_log" (
    "id" SERIAL PRIMARY KEY,
    "user_id" INTEGER,
    "username" TEXT,
    "azione" TEXT NOT NULL,
    "entita" TEXT NOT NULL,
    "entita_id" INTEGER,
    "valore_precedente" TEXT,
    "valore_successivo" TEXT,
    "ip_address" TEXT,
    "motivazione" TEXT,
    "created_at" TEXT NOT NULL
);

-- rc_candidates (83 righe)
CREATE TABLE IF NOT EXISTS "rc_candidates" (
    "id" SERIAL PRIMARY KEY,
    "nome" TEXT NOT NULL,
    "cognome" TEXT NOT NULL,
    "varianti_nominativi" TEXT,
    "paternita" TEXT,
    "maternita" TEXT,
    "data_nascita" TEXT,
    "luogo_nascita" TEXT,
    "data_morte" TEXT,
    "luogo_morte" TEXT,
    "comune_residenza" TEXT,
    "grado" TEXT,
    "reparto" TEXT,
    "forza_armata" TEXT,
    "matricola" TEXT,
    "conflitto" TEXT,
    "stato" TEXT NOT NULL DEFAULT 'BOZZA',
    "livello_certezza" TEXT DEFAULT 'da_verificare',
    "note_interne" TEXT,
    "priorita_json" TEXT,
    "created_at" TEXT NOT NULL,
    "updated_at" TEXT NOT NULL,
    "created_by" INTEGER,
    "life_status" TEXT DEFAULT 'deceased'
);

-- rc_communications (0 righe)
CREATE TABLE IF NOT EXISTS "rc_communications" (
    "id" SERIAL PRIMARY KEY,
    "candidate_id" INTEGER,
    "descendant_contact_id" INTEGER,
    "practice_id" INTEGER,
    "institutional_contact_id" INTEGER,
    "document_id" INTEGER,
    "thread_id" TEXT,
    "parent_communication_id" INTEGER,
    "tipo" TEXT NOT NULL,
    "direzione" TEXT NOT NULL,
    "mittente" TEXT,
    "destinatari" TEXT,
    "copia_conoscenza" TEXT,
    "oggetto" TEXT,
    "contenuto" TEXT,
    "allegati" TEXT,
    "data_ora_effettiva" TEXT,
    "data_ora_registrazione" TEXT NOT NULL,
    "operatore" TEXT,
    "stato" TEXT DEFAULT 'bozza',
    "ricevuta_consegna" TEXT,
    "protocollo" TEXT,
    "risposta_attesa" INTEGER DEFAULT 0,
    "data_entro_rispondere" TEXT,
    "esito" TEXT,
    "note" TEXT,
    "created_at" TEXT NOT NULL,
    "updated_at" TEXT NOT NULL,
    "created_by" INTEGER
);

-- rc_contact_attempts (0 righe)
CREATE TABLE IF NOT EXISTS "rc_contact_attempts" (
    "id" SERIAL PRIMARY KEY,
    "candidate_id" INTEGER NOT NULL,
    "destinatario_id" INTEGER,
    "canale" TEXT,
    "intermediario" TEXT,
    "testo_approvato" TEXT,
    "data_invio" TEXT,
    "esito" TEXT DEFAULT 'in_attesa',
    "operatore" TEXT,
    "divieto_ulteriori" INTEGER DEFAULT 0,
    "prova_inoltro" TEXT,
    "approvato" INTEGER DEFAULT 0,
    "approvato_da" TEXT,
    "created_at" TEXT NOT NULL,
    "updated_at" TEXT NOT NULL
);

-- rc_descendant_cases (0 righe)
CREATE TABLE IF NOT EXISTS "rc_descendant_cases" (
    "id" SERIAL PRIMARY KEY,
    "candidate_id" INTEGER NOT NULL,
    "discendente_referente_id" INTEGER,
    "parentela_dichiarata" TEXT,
    "parentela_verificata" TEXT DEFAULT 'non_verificata',
    "documenti_prova" TEXT,
    "consenso" INTEGER DEFAULT 0,
    "delega" TEXT,
    "data_adesione" TEXT,
    "altri_rami_familiari" TEXT,
    "created_at" TEXT NOT NULL,
    "updated_at" TEXT NOT NULL
);

-- rc_descendant_contacts (0 righe)
CREATE TABLE IF NOT EXISTS "rc_descendant_contacts" (
    "id" SERIAL PRIMARY KEY,
    "candidate_id" INTEGER NOT NULL,
    "nome" TEXT NOT NULL,
    "cognome" TEXT NOT NULL,
    "nome_precedente" TEXT,
    "rapporto_parentela_presunto" TEXT,
    "rapporto_parentela_verificato" TEXT,
    "ramo_familiare" TEXT,
    "comune_residenza" TEXT,
    "indirizzo_postale" TEXT,
    "email" TEXT,
    "pec" TEXT,
    "telefono" TEXT,
    "altro_canale" TEXT,
    "profilo_pubblico_url" TEXT,
    "preferenza_contatto" TEXT,
    "lingua" TEXT DEFAULT 'it',
    "note" TEXT,
    "stato_verifica" TEXT DEFAULT 'NON_VERIFICATO',
    "fonte_contatto" TEXT,
    "url_fonte" TEXT,
    "titolo_pagina_fonte" TEXT,
    "data_consultazione_fonte" TEXT,
    "operatore_inserimento" TEXT,
    "data_reperimento" TEXT,
    "data_ultima_verifica" TEXT,
    "livello_attendibilita" TEXT DEFAULT 'da_verificare',
    "consenso_acquisito" INTEGER DEFAULT 0,
    "data_consenso" TEXT,
    "modalita_consenso" TEXT,
    "opposizione_contatto" INTEGER DEFAULT 0,
    "richiesta_non_contattare" INTEGER DEFAULT 0,
    "cancellazione_limitazione" TEXT,
    "visibilita_limitata" INTEGER DEFAULT 1,
    "created_at" TEXT NOT NULL,
    "updated_at" TEXT NOT NULL,
    "created_by" INTEGER
);

-- rc_descendant_packages (0 righe)
CREATE TABLE IF NOT EXISTS "rc_descendant_packages" (
    "id" SERIAL PRIMARY KEY,
    "candidate_id" INTEGER NOT NULL,
    "descendant_contact_id" INTEGER,
    "practice_id" INTEGER,
    "versione" INTEGER DEFAULT 1,
    "file_path" TEXT NOT NULL,
    "checksum" TEXT,
    "dimensione" INTEGER,
    "documenti_inclusi" TEXT,
    "documenti_esclusi" TEXT,
    "dati_personali_presenti" TEXT,
    "livello_riservatezza" TEXT,
    "approvatore" TEXT,
    "data_generazione" TEXT NOT NULL,
    "token_condivisione" TEXT,
    "token_scadenza" TEXT,
    "created_at" TEXT NOT NULL,
    "created_by" INTEGER
);

-- rc_document_checklists (0 righe)
CREATE TABLE IF NOT EXISTS "rc_document_checklists" (
    "id" SERIAL PRIMARY KEY,
    "recognition_type_id" INTEGER,
    "practice_id" INTEGER,
    "nome_documento" TEXT NOT NULL,
    "descrizione" TEXT,
    "obbligatorietà" TEXT DEFAULT 'obbligatorio',
    "soggetto_produttore" TEXT,
    "ente_reperizione" TEXT,
    "modello_disponibile" TEXT,
    "stato_documento" TEXT DEFAULT 'mancante',
    "motivazione_invalidita" TEXT,
    "data_richiesta" TEXT,
    "scadenza" TEXT,
    "operatore_responsabile" TEXT,
    "documento_collegato_id" INTEGER,
    "created_at" TEXT NOT NULL,
    "updated_at" TEXT NOT NULL
);

-- rc_document_versions (1 righe)
CREATE TABLE IF NOT EXISTS "rc_document_versions" (
    "id" SERIAL PRIMARY KEY,
    "document_id" INTEGER NOT NULL,
    "versione" INTEGER NOT NULL,
    "file_path" TEXT NOT NULL,
    "checksum" TEXT,
    "dimensione" INTEGER,
    "motivazione_sostituzione" TEXT,
    "sostituito_da" TEXT,
    "created_at" TEXT NOT NULL,
    "created_by" INTEGER
);

-- rc_documents (0 righe)
CREATE TABLE IF NOT EXISTS "rc_documents" (
    "id" SERIAL PRIMARY KEY,
    "candidate_id" INTEGER,
    "descendant_case_id" INTEGER,
    "filename" TEXT NOT NULL,
    "file_path" TEXT NOT NULL,
    "file_checksum" TEXT,
    "file_size" INTEGER,
    "mime_type" TEXT,
    "uploaded_by" TEXT,
    "visibilita" TEXT DEFAULT 'operatore',
    "created_at" TEXT NOT NULL
);

-- rc_family_persons (0 righe)
CREATE TABLE IF NOT EXISTS "rc_family_persons" (
    "id" SERIAL PRIMARY KEY,
    "candidate_id" INTEGER NOT NULL,
    "nome" TEXT,
    "cognome" TEXT,
    "data_nascita" TEXT,
    "luogo_nascita" TEXT,
    "data_morte" TEXT,
    "rapporto_candidato" TEXT,
    "stato_vita" TEXT DEFAULT 'non_accertato',
    "fonte_genealogica" TEXT,
    "livello_certezza" TEXT DEFAULT 'basso',
    "visibilita_limitata" INTEGER DEFAULT 1,
    "stato_contatto" TEXT DEFAULT 'nessuno',
    "created_at" TEXT NOT NULL,
    "updated_at" TEXT NOT NULL
);

-- rc_historical_events (45 righe)
CREATE TABLE IF NOT EXISTS "rc_historical_events" (
    "id" SERIAL PRIMARY KEY,
    "candidate_id" INTEGER NOT NULL,
    "tipo_evento" TEXT,
    "data_inizio" TEXT,
    "data_fine" TEXT,
    "luogo" TEXT,
    "descrizione_verificata" TEXT,
    "testo_originale_fonte" TEXT,
    "condotta_individuale" TEXT,
    "rischio_affrontato" TEXT,
    "conseguenze" TEXT,
    "testimoni" TEXT,
    "grado_attendibilita" TEXT DEFAULT 'da_verificare',
    "created_at" TEXT NOT NULL,
    "updated_at" TEXT NOT NULL
);

-- rc_institutional_contacts (0 righe)
CREATE TABLE IF NOT EXISTS "rc_institutional_contacts" (
    "id" SERIAL PRIMARY KEY,
    "ente" TEXT NOT NULL,
    "ministero_amministrazione" TEXT,
    "dipartimento" TEXT,
    "direzione_generale" TEXT,
    "ufficio" TEXT,
    "archivio" TEXT,
    "sede" TEXT,
    "indirizzo" TEXT,
    "email" TEXT,
    "pec" TEXT,
    "telefono" TEXT,
    "sito_ufficiale" TEXT,
    "pagina_procedura" TEXT,
    "referente_nome" TEXT,
    "referente_cognome" TEXT,
    "referente_qualifica" TEXT,
    "referente_telefono_interno" TEXT,
    "orari" TEXT,
    "ambito_competenza" TEXT,
    "territori_competenza" TEXT,
    "tipi_riconoscimento_gestiti" TEXT,
    "modalita_preferita_contatto" TEXT,
    "fonte_recapito" TEXT,
    "url_fonte_ufficiale" TEXT,
    "data_ultima_verifica" TEXT,
    "stato" TEXT DEFAULT 'non_verificato',
    "note" TEXT,
    "created_at" TEXT NOT NULL,
    "updated_at" TEXT NOT NULL,
    "created_by" INTEGER
);

-- rc_invitations (0 righe)
CREATE TABLE IF NOT EXISTS "rc_invitations" (
    "id" SERIAL PRIMARY KEY,
    "token" TEXT NOT NULL,
    "descendant_case_id" INTEGER NOT NULL,
    "email" TEXT,
    "created_at" TEXT NOT NULL,
    "expires_at" TEXT NOT NULL,
    "accettato" INTEGER DEFAULT 0,
    "data_accettazione" TEXT,
    "revocato" INTEGER DEFAULT 0
);

-- rc_kinship_links (0 righe)
CREATE TABLE IF NOT EXISTS "rc_kinship_links" (
    "id" SERIAL PRIMARY KEY,
    "persona_origine_id" INTEGER NOT NULL,
    "persona_destinazione_id" INTEGER NOT NULL,
    "tipo_rapporto" TEXT,
    "fonte" TEXT,
    "grado_certezza" TEXT DEFAULT 'basso',
    "verificato_da" TEXT,
    "created_at" TEXT NOT NULL
);

-- rc_practice_deadlines (0 righe)
CREATE TABLE IF NOT EXISTS "rc_practice_deadlines" (
    "id" SERIAL PRIMARY KEY,
    "practice_id" INTEGER,
    "candidate_id" INTEGER,
    "tipo_scadenza" TEXT NOT NULL,
    "data_scadenza" TEXT NOT NULL,
    "descrizione" TEXT,
    "promemoria_inviato" INTEGER DEFAULT 0,
    "risolta" INTEGER DEFAULT 0,
    "data_risoluzione" TEXT,
    "note" TEXT,
    "created_at" TEXT NOT NULL,
    "created_by" INTEGER
);

-- rc_practice_documents (1 righe)
CREATE TABLE IF NOT EXISTS "rc_practice_documents" (
    "id" SERIAL PRIMARY KEY,
    "practice_id" INTEGER,
    "candidate_id" INTEGER,
    "descendant_contact_id" INTEGER,
    "titolo" TEXT NOT NULL,
    "descrizione" TEXT,
    "categoria_documentale" TEXT,
    "filename_originale" TEXT NOT NULL,
    "file_path" TEXT NOT NULL,
    "formato_mime" TEXT,
    "dimensione" INTEGER,
    "numero_pagine" INTEGER,
    "checksum" TEXT,
    "autore_caricamento" TEXT,
    "data_caricamento" TEXT NOT NULL,
    "data_documento" TEXT,
    "mittente" TEXT,
    "destinatario" TEXT,
    "ente_produttore" TEXT,
    "fonte" TEXT,
    "segnatura" TEXT,
    "protocollo" TEXT,
    "livello_riservatezza" TEXT DEFAULT 'operatore',
    "stato_verifica" TEXT DEFAULT 'non_verificata',
    "versione" INTEGER DEFAULT 1,
    "documento_sostituito_id" INTEGER,
    "scadenza" TEXT,
    "firma_digitale_rilevata" INTEGER DEFAULT 0,
    "esito_scansione_antivirus" TEXT,
    "note" TEXT,
    "archiviato" INTEGER DEFAULT 0,
    "created_at" TEXT NOT NULL,
    "updated_at" TEXT NOT NULL,
    "created_by" INTEGER,
    "ocr_text" TEXT,
    "ocr_status" TEXT DEFAULT 'pending',
    "ocr_pages" INTEGER
);

-- rc_practices (0 righe)
CREATE TABLE IF NOT EXISTS "rc_practices" (
    "id" SERIAL PRIMARY KEY,
    "candidate_id" INTEGER NOT NULL,
    "recognition_type_id" INTEGER,
    "descendant_contact_id" INTEGER,
    "institutional_contact_id" INTEGER,
    "protocollo" TEXT,
    "data_invio" TEXT,
    "modalita_trasmissione" TEXT,
    "ufficio_assegnatario" TEXT,
    "responsabile_procedimento" TEXT,
    "data_apertura" TEXT,
    "termine_previsto" TEXT,
    "stato" TEXT DEFAULT 'in_preparazione',
    "richieste_integrazione" TEXT,
    "esito" TEXT,
    "decreto_provvedimento" TEXT,
    "data_esito" TEXT,
    "data_consegna_attestato" TEXT,
    "note_cerimonia" TEXT,
    "pronto_invio" INTEGER DEFAULT 0,
    "validato_da_revisore" INTEGER DEFAULT 0,
    "motivazione_eccezione" TEXT,
    "created_at" TEXT NOT NULL,
    "updated_at" TEXT NOT NULL,
    "created_by" INTEGER
);

-- rc_recognition_assessments (50 righe)
CREATE TABLE IF NOT EXISTS "rc_recognition_assessments" (
    "id" SERIAL PRIMARY KEY,
    "candidate_id" INTEGER NOT NULL,
    "recognition_type_id" INTEGER NOT NULL,
    "riconoscimento_ipotizzato" TEXT,
    "requisiti_presenti" TEXT,
    "requisiti_mancanti" TEXT,
    "elementi_contrari" TEXT,
    "procedura" TEXT DEFAULT 'da_verificare',
    "motivazione" TEXT,
    "valutatore" TEXT,
    "data_valutazione" TEXT,
    "validazione_storica" INTEGER DEFAULT 0,
    "validazione_amministrativa" INTEGER DEFAULT 0,
    "created_at" TEXT NOT NULL,
    "updated_at" TEXT NOT NULL,
    "processo_logico" TEXT,
    "fonti_consultate" TEXT,
    "percentuale_stimata_concessione" DOUBLE PRECISION,
    "precedenti_storici" TEXT,
    "fattori_favorevoli" TEXT,
    "fattori_sfavorevoli" TEXT,
    "onorificenze_alternative" TEXT,
    "livello_confidenza" TEXT DEFAULT 'basso'
);

-- rc_recognition_types (12 righe)
CREATE TABLE IF NOT EXISTS "rc_recognition_types" (
    "id" SERIAL PRIMARY KEY,
    "denominazione" TEXT NOT NULL,
    "categoria" TEXT,
    "autorita_concedente" TEXT,
    "ente_istruttore" TEXT,
    "base_normativa" TEXT,
    "requisiti" TEXT,
    "concessione_memoria" INTEGER DEFAULT 0,
    "soggetti_legittimati" TEXT,
    "modalita_avvio" TEXT,
    "termini" TEXT,
    "documenti_richiesti" TEXT,
    "procedura_attiva" TEXT DEFAULT 'da_verificare',
    "data_ultimo_aggiornamento" TEXT,
    "fonti_istituzionali" TEXT,
    "created_at" TEXT NOT NULL,
    "updated_at" TEXT NOT NULL
);

-- rc_sessions (44 righe)
CREATE TABLE IF NOT EXISTS "rc_sessions" (
    "token" TEXT PRIMARY KEY,
    "user_id" INTEGER NOT NULL,
    "created_at" TEXT NOT NULL,
    "expires_at" TEXT NOT NULL,
    "ip_address" TEXT,
    "user_agent" TEXT
);

-- rc_sources (80 righe)
CREATE TABLE IF NOT EXISTS "rc_sources" (
    "id" SERIAL PRIMARY KEY,
    "titolo" TEXT NOT NULL,
    "tipologia" TEXT,
    "ente_conservatore" TEXT,
    "fondo" TEXT,
    "serie" TEXT,
    "busta" TEXT,
    "fascicolo" TEXT,
    "pagina_immagine" TEXT,
    "segnatura_completa" TEXT,
    "url_istituzionale" TEXT,
    "data_documento" TEXT,
    "file_path" TEXT,
    "file_checksum" TEXT,
    "trascrizione" TEXT,
    "estrazione_automatica" TEXT,
    "livello_attendibilita" TEXT DEFAULT 'da_verificare',
    "stato_verifica" TEXT DEFAULT 'non_verificata',
    "verificatore" TEXT,
    "created_at" TEXT NOT NULL,
    "updated_at" TEXT NOT NULL,
    "candidate_id" INTEGER
);

-- rc_state_transitions (0 righe)
CREATE TABLE IF NOT EXISTS "rc_state_transitions" (
    "id" SERIAL PRIMARY KEY,
    "candidate_id" INTEGER NOT NULL,
    "stato_precedente" TEXT NOT NULL,
    "stato_successivo" TEXT NOT NULL,
    "autore" TEXT,
    "data_ora" TEXT NOT NULL,
    "motivazione" TEXT,
    "allegati" TEXT,
    "approvazione_richiesta" INTEGER DEFAULT 0
);

-- rc_users (2 righe)
CREATE TABLE IF NOT EXISTS "rc_users" (
    "id" SERIAL PRIMARY KEY,
    "username" TEXT NOT NULL,
    "password_hash" TEXT NOT NULL,
    "role" TEXT NOT NULL DEFAULT 'ricercatore',
    "email" TEXT,
    "full_name" TEXT,
    "is_active" INTEGER DEFAULT 1,
    "created_at" TEXT NOT NULL,
    "updated_at" TEXT NOT NULL
);

-- record_link_validations (200 righe)
CREATE TABLE IF NOT EXISTS "record_link_validations" (
    "id" SERIAL PRIMARY KEY,
    "link_id" INTEGER NOT NULL,
    "cycle" INTEGER NOT NULL,
    "ai_provider" TEXT NOT NULL,
    "verdict" TEXT NOT NULL,
    "score" DOUBLE PRECISION,
    "reason" TEXT,
    "validated_at" TEXT
);

-- record_links (169184 righe)
CREATE TABLE IF NOT EXISTS "record_links" (
    "id" SERIAL PRIMARY KEY,
    "from_table" TEXT NOT NULL,
    "from_id" INTEGER NOT NULL,
    "to_table" TEXT NOT NULL,
    "to_id" INTEGER NOT NULL,
    "link_type" TEXT NOT NULL,
    "confidence" DOUBLE PRECISION DEFAULT 0.5,
    "elaborato_il" TEXT,
    "match_status" TEXT DEFAULT 'candidate',
    "match_method" TEXT,
    "matched_fields_json" TEXT,
    "conflicting_fields_json" TEXT,
    "evidence_json" TEXT,
    "explanation" TEXT,
    "review_status" TEXT DEFAULT 'pending',
    "reviewed_by" TEXT,
    "reviewed_at" TEXT,
    "algorithm_version" TEXT DEFAULT 'legacy',
    "score_breakdown_json" TEXT,
    "contrary_signals_json" TEXT,
    "legacy_unverified" INTEGER DEFAULT 0,
    "nature" TEXT DEFAULT 'heuristic',
    "direction" TEXT DEFAULT 'undirected'
);

-- research_cycles (50 righe)
CREATE TABLE IF NOT EXISTS "research_cycles" (
    "id" SERIAL PRIMARY KEY,
    "plan_id" INTEGER NOT NULL,
    "session_id" INTEGER,
    "cycle_number" INTEGER NOT NULL,
    "initial_knowledge_json" TEXT,
    "gaps_selected_json" TEXT,
    "sources_selected_json" TEXT,
    "sources_motivation" TEXT,
    "queries_executed_json" TEXT,
    "new_fragments_json" TEXT,
    "utility_metrics_json" TEXT,
    "decision" TEXT DEFAULT 'continue',
    "stop_reason" TEXT,
    "created_at" TEXT NOT NULL,
    "completed_at" TEXT
);

-- research_gaps (472 righe)
CREATE TABLE IF NOT EXISTS "research_gaps" (
    "id" SERIAL PRIMARY KEY,
    "subject_id" INTEGER NOT NULL,
    "missing_field" TEXT,
    "suggested_provider" TEXT,
    "priority" TEXT DEFAULT 'medium',
    "status" TEXT DEFAULT 'open',
    "created_at" TEXT NOT NULL
);

-- research_hits (0 righe)
CREATE TABLE IF NOT EXISTS "research_hits" (
    "id" SERIAL PRIMARY KEY,
    "query_id" INTEGER,
    "connector_code" TEXT NOT NULL,
    "external_id" TEXT,
    "title" TEXT,
    "description" TEXT,
    "url" TEXT,
    "url_kind" TEXT DEFAULT 'unknown',
    "metadata_json" TEXT,
    "score" DOUBLE PRECISION DEFAULT 0.0,
    "status" TEXT DEFAULT 'candidate',
    "resolved_to_source_item_id" INTEGER,
    "resolved_at" TEXT,
    "locator_status" TEXT DEFAULT 'pending',
    "coverage_note" TEXT,
    "warnings_json" TEXT,
    "executed_at" TEXT NOT NULL,
    "created_at" TEXT NOT NULL
);

-- research_plans (46 righe)
CREATE TABLE IF NOT EXISTS "research_plans" (
    "id" SERIAL PRIMARY KEY,
    "original_input" TEXT NOT NULL,
    "entity_type" TEXT,
    "entity_id" INTEGER,
    "objective" TEXT,
    "initial_context" TEXT,
    "gaps_to_fill" TEXT,
    "budget_cycles" INTEGER DEFAULT 10,
    "budget_time_seconds" INTEGER DEFAULT 300,
    "budget_cost_usd" DOUBLE PRECISION DEFAULT 5.0,
    "status" TEXT DEFAULT 'draft',
    "generated_by" TEXT,
    "created_at" TEXT NOT NULL,
    "updated_at" TEXT NOT NULL
);

-- research_queries (0 righe)
CREATE TABLE IF NOT EXISTS "research_queries" (
    "id" SERIAL PRIMARY KEY,
    "session_id" INTEGER NOT NULL,
    "query_text" TEXT NOT NULL,
    "query_language" TEXT DEFAULT 'it',
    "filters_json" TEXT,
    "variant_used" TEXT,
    "generated_from_claim_id" INTEGER,
    "generated_from_fragment" TEXT,
    "priority" INTEGER DEFAULT 5,
    "motivation" TEXT,
    "search_tool" TEXT,
    "assisted_search_url" TEXT,
    "executed_at" TEXT,
    "outcome" TEXT,
    "created_at" TEXT NOT NULL
);

-- research_results (0 righe)
CREATE TABLE IF NOT EXISTS "research_results" (
    "id" SERIAL PRIMARY KEY,
    "session_id" INTEGER NOT NULL,
    "query_id" INTEGER,
    "external_id" TEXT,
    "result_type" TEXT NOT NULL DEFAULT 'search_hit',
    "record_url" TEXT,
    "document_url" TEXT,
    "canonical_url" TEXT,
    "title" TEXT,
    "author_or_entity" TEXT,
    "publication_date" TEXT,
    "retrieved_at" TEXT,
    "raw_metadata_json" TEXT,
    "fingerprint" TEXT,
    "source_quality" DOUBLE PRECISION DEFAULT 0.5,
    "authority_score" DOUBLE PRECISION DEFAULT 0.5,
    "independence_group" TEXT,
    "status" TEXT DEFAULT 'new',
    "status_reason" TEXT,
    "linked_source_id" INTEGER,
    "linked_document_id" INTEGER,
    "first_seen_at" TEXT NOT NULL,
    "last_seen_at" TEXT
);

-- research_sessions (46 righe)
CREATE TABLE IF NOT EXISTS "research_sessions" (
    "id" SERIAL PRIMARY KEY,
    "plan_id" INTEGER NOT NULL,
    "connector_id" INTEGER,
    "mode" TEXT NOT NULL DEFAULT 'auto',
    "started_at" TEXT,
    "completed_at" TEXT,
    "status" TEXT DEFAULT 'pending',
    "cycle_number" INTEGER DEFAULT 0,
    "result_count" INTEGER DEFAULT 0,
    "linked_count" INTEGER DEFAULT 0,
    "excluded_count" INTEGER DEFAULT 0,
    "snapshot_version" TEXT,
    "stop_reason" TEXT,
    "note" TEXT,
    "created_at" TEXT NOT NULL,
    "updated_at" TEXT
);

-- research_subject_sources (1431 righe)
CREATE TABLE IF NOT EXISTS "research_subject_sources" (
    "id" SERIAL PRIMARY KEY,
    "subject_id" INTEGER NOT NULL,
    "source_locator_id" INTEGER,
    "relation_type" TEXT,
    "confidence" DOUBLE PRECISION DEFAULT 0.3,
    "evidence_note" TEXT,
    "created_at" TEXT NOT NULL
);

-- research_subjects (118 righe)
CREATE TABLE IF NOT EXISTS "research_subjects" (
    "id" SERIAL PRIMARY KEY,
    "subject_type" TEXT NOT NULL,
    "name" TEXT,
    "normalized_name" TEXT,
    "date_start" TEXT,
    "date_end" TEXT,
    "place" TEXT,
    "unit" TEXT,
    "status" TEXT DEFAULT 'not_verified',
    "confidence" DOUBLE PRECISION DEFAULT 0.1,
    "created_from_query" TEXT,
    "linked_soldier_id" INTEGER,
    "created_at" TEXT NOT NULL,
    "updated_at" TEXT NOT NULL
);

-- source_access_audit (0 righe)
CREATE TABLE IF NOT EXISTS "source_access_audit" (
    "id" SERIAL PRIMARY KEY,
    "connector_code" TEXT NOT NULL,
    "operation" TEXT NOT NULL,
    "target_url" TEXT,
    "target_domain" TEXT,
    "policy_version_id" INTEGER,
    "decision" TEXT,
    "response_status" INTEGER,
    "response_time_ms" INTEGER,
    "error_message" TEXT,
    "operator_user" TEXT,
    "ip_address" TEXT,
    "created_at" TEXT NOT NULL
);

-- source_fetch_cache (14 righe)
CREATE TABLE IF NOT EXISTS "source_fetch_cache" (
    "id" SERIAL PRIMARY KEY,
    "source_id" INTEGER NOT NULL,
    "url_fetched" TEXT,
    "path_file" TEXT,
    "sha256" TEXT,
    "size_bytes" INTEGER,
    "content_type" TEXT,
    "permanent" INTEGER DEFAULT 0,
    "fetched_at" TEXT NOT NULL,
    "expires_at" TEXT
);

-- source_policies (4 righe)
CREATE TABLE IF NOT EXISTS "source_policies" (
    "id" SERIAL PRIMARY KEY,
    "provider" TEXT NOT NULL,
    "domain" TEXT NOT NULL,
    "source_name" TEXT NOT NULL,
    "terms_url" TEXT,
    "privacy_url" TEXT,
    "robots_url" TEXT,
    "archive_regulation_url" TEXT,
    "metadata_license" TEXT,
    "digital_object_license" TEXT,
    "commercial_use_allowed" INTEGER DEFAULT 0,
    "automated_access_allowed" INTEGER DEFAULT 0,
    "metadata_indexing_allowed" INTEGER DEFAULT 1,
    "document_download_allowed" INTEGER DEFAULT 0,
    "republication_allowed" INTEGER DEFAULT 0,
    "attribution_required" INTEGER DEFAULT 1,
    "required_credit_line" TEXT,
    "request_contact" TEXT,
    "policy_status" TEXT DEFAULT 'unknown',
    "verified_by" TEXT,
    "verified_at" TEXT,
    "valid_from" TEXT,
    "review_due_at" TEXT,
    "notes" TEXT,
    "created_at" TEXT,
    "updated_at" TEXT
);

-- source_rights (0 righe)
CREATE TABLE IF NOT EXISTS "source_rights" (
    "id" SERIAL PRIMARY KEY,
    "source_item_id" INTEGER,
    "source_table" TEXT,
    "domain" TEXT NOT NULL,
    "rights_type" TEXT NOT NULL,
    "rights_holder" TEXT,
    "license_url" TEXT,
    "license_name" TEXT,
    "valid_from" TEXT,
    "valid_until" TEXT,
    "notes" TEXT,
    "created_at" TEXT NOT NULL,
    "updated_at" TEXT NOT NULL
);

-- stable_locators (0 righe)
CREATE TABLE IF NOT EXISTS "stable_locators" (
    "id" SERIAL PRIMARY KEY,
    "source_item_id" INTEGER NOT NULL,
    "source_table" TEXT NOT NULL DEFAULT 'fonti_indice',
    "locator_kind" TEXT NOT NULL,
    "locator_value" TEXT NOT NULL,
    "canonical_url" TEXT,
    "permalink" TEXT,
    "persistent_id" TEXT,
    "persistent_id_type" TEXT,
    "iiif_manifest" TEXT,
    "direct_document_url" TEXT,
    "reference_code" TEXT,
    "retrieval_instruction" TEXT,
    "domain" TEXT,
    "verified_at" TEXT,
    "verified_by" TEXT,
    "redirect_target" TEXT,
    "is_stable" INTEGER DEFAULT 0,
    "created_at" TEXT NOT NULL,
    "updated_at" TEXT NOT NULL
);


-- STEP 2: INDICI
CREATE INDEX IF NOT EXISTS idx_ac_code ON archive_connectors(code);
CREATE INDEX IF NOT EXISTS idx_ac_status ON archive_connectors(status);
CREATE INDEX IF NOT EXISTS idx_acquisitions_source ON acquisitions(source_item_id, source_table);
CREATE INDEX IF NOT EXISTS idx_af_archivio ON archivio_fonti(archivio);
CREATE INDEX IF NOT EXISTS idx_af_conflitto ON archivio_fonti(conflitto);
CREATE INDEX IF NOT EXISTS idx_af_data ON archivio_fonti(data_inizio);
CREATE INDEX IF NOT EXISTS idx_af_data_range ON archivio_fonti(data_inizio, data_fine);
CREATE INDEX IF NOT EXISTS idx_af_fondo ON archivio_fonti(fondo);
CREATE INDEX IF NOT EXISTS idx_af_hash ON archivio_fonti(hash_sha256);
CREATE INDEX IF NOT EXISTS idx_af_ocr ON archivio_fonti(ocr_status);
CREATE INDEX IF NOT EXISTS idx_af_segnatura ON archivio_fonti(segnatura);
CREATE INDEX IF NOT EXISTS idx_af_teatro ON archivio_fonti(teatro_operazioni);
CREATE INDEX IF NOT EXISTS idx_af_tipo ON archivio_fonti(tipo_documento);
CREATE INDEX IF NOT EXISTS idx_af_unita ON archivio_fonti(unita_principale);
CREATE INDEX IF NOT EXISTS idx_albo_nominativo ON caduti_albooro(nominativo);
CREATE INDEX IF NOT EXISTS idx_albooro_nominativo ON caduti_albooro(nominativo);
CREATE INDEX IF NOT EXISTS idx_albooro_volume ON caduti_albooro(volume_id);
CREATE INDEX IF NOT EXISTS idx_am_provider ON ai_models(provider_id);
CREATE INDEX IF NOT EXISTS idx_am_status ON ai_models(status);
CREATE INDEX IF NOT EXISTS idx_ap_code ON ai_providers(code);
CREATE INDEX IF NOT EXISTS idx_ap_status ON ai_providers(status);
CREATE INDEX IF NOT EXISTS idx_archival_metadata_source
    ON archival_metadata(source_table, source_id);
CREATE INDEX IF NOT EXISTS idx_arp_task ON ai_routing_policies(task_type);
CREATE INDEX IF NOT EXISTS idx_atr_idem ON ai_task_runs(idempotency_key);
CREATE INDEX IF NOT EXISTS idx_atr_plan ON ai_task_runs(research_plan_id);
CREATE INDEX IF NOT EXISTS idx_atr_task ON ai_task_runs(task_type);
CREATE INDEX IF NOT EXISTS idx_aul_period ON ai_usage_ledger(provider_code, period);
CREATE INDEX IF NOT EXISTS idx_bologna_nome ON caduti_bologna(nome);
CREATE INDEX IF NOT EXISTS idx_budget_reservations_plan ON budget_reservations(plan_id);
CREATE INDEX IF NOT EXISTS idx_ce_claim ON claim_evidence(claim_id);
CREATE INDEX IF NOT EXISTS idx_ce_role ON claim_evidence(evidence_role);
CREATE INDEX IF NOT EXISTS idx_claim_evidence_claim ON claim_evidence(claim_id);
CREATE INDEX IF NOT EXISTS idx_claims_epistemic ON claims(epistemic_status);
CREATE INDEX IF NOT EXISTS idx_claims_predicate ON claims(predicate);
CREATE INDEX IF NOT EXISTS idx_claims_review ON claims(review_status);
CREATE INDEX IF NOT EXISTS idx_claims_stable ON claims(stable_id);
CREATE INDEX IF NOT EXISTS idx_claims_stable_id ON claims(stable_id);
CREATE INDEX IF NOT EXISTS idx_claims_subject ON claims(subject_type, subject_id);
CREATE INDEX IF NOT EXISTS idx_cm_qcount ON consolidated_memory(query_count DESC);
CREATE INDEX IF NOT EXISTS idx_cm_topic ON consolidated_memory(topic);
CREATE INDEX IF NOT EXISTS idx_collegamenti_entita ON collegamenti(entita_id);
CREATE INDEX IF NOT EXISTS idx_collegamenti_record ON collegamenti(tabella_origine, record_id);
CREATE INDEX IF NOT EXISTS idx_collegamenti_tab_rec ON collegamenti(tabella_origine, record_id);
CREATE INDEX IF NOT EXISTS idx_content_fp_hash ON content_fingerprints(content_hash);
CREATE INDEX IF NOT EXISTS idx_cr_a ON claim_relations(claim_a_id);
CREATE INDEX IF NOT EXISTS idx_cr_b ON claim_relations(claim_b_id);
CREATE INDEX IF NOT EXISTS idx_cr_type ON claim_relations(relation_type);
CREATE INDEX IF NOT EXISTS idx_cwgc_cognome ON caduti_cwgc(cognome);
CREATE INDEX IF NOT EXISTS idx_cwgc_cognome_nocase ON caduti_cwgc(cognome);
CREATE INDEX IF NOT EXISTS idx_cwgc_data ON caduti_cwgc(data_morte);
CREATE INDEX IF NOT EXISTS idx_cwgc_guerra ON caduti_cwgc(guerra);
CREATE INDEX IF NOT EXISTS idx_cwgc_nationality ON caduti_cwgc(nationality);
CREATE INDEX IF NOT EXISTS idx_cwgc_nome ON caduti_cwgc(nome);
CREATE INDEX IF NOT EXISTS idx_de_document ON document_extractions(document_table, document_id);
CREATE INDEX IF NOT EXISTS idx_decorati_cognome ON decorati(cognome);
CREATE INDEX IF NOT EXISTS idx_doc_provider ON archivio_documenti(provider);
CREATE INDEX IF NOT EXISTS idx_doc_type ON archivio_documenti(doc_type);
CREATE INDEX IF NOT EXISTS idx_doc_year ON archivio_documenti(year_start);
CREATE INDEX IF NOT EXISTS idx_ear_record ON external_access_requests(external_source_record_id);
CREATE INDEX IF NOT EXISTS idx_ear_status ON external_access_requests(request_status);
CREATE INDEX IF NOT EXISTS idx_edge_evidence_edge ON edge_evidence(edge_id);
CREATE INDEX IF NOT EXISTS idx_edge_versions_edge ON edge_versions(edge_id);
CREATE INDEX IF NOT EXISTS idx_edo_record ON external_digital_objects(external_source_record_id);
CREATE INDEX IF NOT EXISTS idx_eij_provider ON external_import_jobs(provider);
CREATE INDEX IF NOT EXISTS idx_eij_status ON external_import_jobs(status);
CREATE INDEX IF NOT EXISTS idx_emc_local ON entity_match_candidates(local_entity_type, local_entity_id);
CREATE INDEX IF NOT EXISTS idx_emc_status ON entity_match_candidates(status);
CREATE INDEX IF NOT EXISTS idx_entita_norm_tipo ON entita(valore_normalizzato, tipo);
CREATE INDEX IF NOT EXISTS idx_entita_tipo ON entita(tipo);
CREATE INDEX IF NOT EXISTS idx_entita_valore ON entita(valore_normalizzato);
CREATE INDEX IF NOT EXISTS idx_entity_match_candidates_status ON entity_match_candidates(status);
CREATE INDEX IF NOT EXISTS idx_epm_name ON external_person_mentions(normalized_name);
CREATE INDEX IF NOT EXISTS idx_epm_prisoner ON external_person_mentions(prisoner_number);
CREATE INDEX IF NOT EXISTS idx_epm_record ON external_person_mentions(external_source_record_id);
CREATE INDEX IF NOT EXISTS idx_epm_service ON external_person_mentions(service_number);
CREATE INDEX IF NOT EXISTS idx_epm_surname ON external_person_mentions(normalized_surname);
CREATE INDEX IF NOT EXISTS idx_erl_mention ON external_record_links(external_person_mention_id);
CREATE INDEX IF NOT EXISTS idx_erl_record ON external_record_links(external_source_record_id);
CREATE INDEX IF NOT EXISTS idx_erl_review ON external_record_links(review_status);
CREATE INDEX IF NOT EXISTS idx_erl_status ON external_record_links(match_status);
CREATE INDEX IF NOT EXISTS idx_erl_target ON external_record_links(target_table, target_record_id);
CREATE INDEX IF NOT EXISTS idx_esf_mention ON external_source_facts(external_person_mention_id);
CREATE INDEX IF NOT EXISTS idx_esf_record ON external_source_facts(external_source_record_id);
CREATE INDEX IF NOT EXISTS idx_esf_type ON external_source_facts(fact_type);
CREATE INDEX IF NOT EXISTS idx_esr_access ON external_source_records(access_status);
CREATE INDEX IF NOT EXISTS idx_esr_fonds ON external_source_records(fonds_external_id);
CREATE INDEX IF NOT EXISTS idx_esr_hash ON external_source_records(metadata_hash);
CREATE INDEX IF NOT EXISTS idx_esr_level ON external_source_records(record_level);
CREATE INDEX IF NOT EXISTS idx_esr_parent ON external_source_records(parent_external_id);
CREATE INDEX IF NOT EXISTS idx_esr_provider ON external_source_records(provider);
CREATE INDEX IF NOT EXISTS idx_esr_url ON external_source_records(canonical_record_url);
CREATE INDEX IF NOT EXISTS idx_ev_entity ON entity_variants(entity_type, entity_id);
CREATE INDEX IF NOT EXISTS idx_event_aliases_event ON event_aliases(event_id);
CREATE INDEX IF NOT EXISTS idx_event_aliases_text ON event_aliases(alias);
CREATE INDEX IF NOT EXISTS idx_event_links_evento ON event_links(evento_id);
CREATE INDEX IF NOT EXISTS idx_event_links_target ON event_links(target_table, target_id);
CREATE INDEX IF NOT EXISTS idx_fi_archivio ON fonti_indice(archivio);
CREATE INDEX IF NOT EXISTS idx_fi_fetch_status ON fonti_indice(fetch_status);
CREATE INDEX IF NOT EXISTS idx_fi_luogo ON fonti_indice(luogo);
CREATE INDEX IF NOT EXISTS idx_fi_reparto ON fonti_indice(reparto);
CREATE INDEX IF NOT EXISTS idx_fi_soggetti ON fonti_indice(soggetti_collegati);
CREATE INDEX IF NOT EXISTS idx_fn_archivio ON fonti_narrative(archivio);
CREATE INDEX IF NOT EXISTS idx_fn_data_documento ON fonti_narrative(data_documento);
CREATE INDEX IF NOT EXISTS idx_fn_ocr_status ON fonti_narrative(ocr_status);
CREATE INDEX IF NOT EXISTS idx_fn_persone ON fonti_narrative(persone_possibili);
CREATE INDEX IF NOT EXISTS idx_fn_tipo_fonte ON fonti_narrative(tipo_fonte);
CREATE INDEX IF NOT EXISTS idx_fonti_risorse_fonte_id ON fonti_risorse(fonte_id);
CREATE INDEX IF NOT EXISTS idx_fonti_risorse_stato ON fonti_risorse(stato);
CREATE INDEX IF NOT EXISTS idx_fonti_risorse_url ON fonti_risorse(url_pagina);
CREATE INDEX IF NOT EXISTS idx_fr_deces ON caduti_francia_ww1(date_deces);
CREATE INDEX IF NOT EXISTS idx_fr_lieu ON caduti_francia_ww1(lieu_deces);
CREATE INDEX IF NOT EXISTS idx_fr_nom ON caduti_francia_ww1(nom);
CREATE INDEX IF NOT EXISTS idx_fr_unite ON caduti_francia_ww1(unite);
CREATE INDEX IF NOT EXISTS idx_gn_entity ON generated_narratives(entity_type, entity_id);
CREATE INDEX IF NOT EXISTS idx_gn_status ON generated_narratives(review_status);
CREATE INDEX IF NOT EXISTS idx_graph_edges_origin
    ON graph_edges(source_system, source_edge_id);
CREATE INDEX IF NOT EXISTS idx_graph_edges_source
    ON graph_edges(source_node_id, active);
CREATE INDEX IF NOT EXISTS idx_graph_edges_status
    ON graph_edges(status, active);
CREATE INDEX IF NOT EXISTS idx_graph_edges_target
    ON graph_edges(target_node_id, active);
CREATE INDEX IF NOT EXISTS idx_graph_issues_status
    ON graph_integrity_issues(status, severity);
CREATE INDEX IF NOT EXISTS idx_graph_nodes_label ON graph_nodes(label);
CREATE INDEX IF NOT EXISTS idx_graph_nodes_source
    ON graph_nodes(namespace, source_table, source_id);
CREATE INDEX IF NOT EXISTS idx_graph_nodes_type ON graph_nodes(node_type);
CREATE INDEX IF NOT EXISTS idx_internati_cognome ON internati(cognome);
CREATE INDEX IF NOT EXISTS idx_internati_luogo_cattura ON internati(luogo_cattura);
CREATE INDEX IF NOT EXISTS idx_internati_luogo_internamento ON internati(luogo_internamento);
CREATE INDEX IF NOT EXISTS idx_internati_luogo_nascita ON internati(luogo_nascita);
CREATE INDEX IF NOT EXISTS idx_internati_nome ON internati(nome);
CREATE INDEX IF NOT EXISTS idx_internati_sorte ON internati(sorte);
CREATE INDEX IF NOT EXISTS idx_lettere_data ON lettere_personali(data_lettera);
CREATE INDEX IF NOT EXISTS idx_lettere_destinatario ON lettere_personali(destinatario);
CREATE INDEX IF NOT EXISTS idx_lettere_luogo ON lettere_personali(luogo);
CREATE INDEX IF NOT EXISTS idx_lettere_mittente ON lettere_personali(mittente);
CREATE INDEX IF NOT EXISTS idx_map_features_certainty ON map_features(certainty);
CREATE INDEX IF NOT EXISTS idx_map_features_event ON map_features(event_id);
CREATE INDEX IF NOT EXISTS idx_map_features_type ON map_features(feature_type);
CREATE INDEX IF NOT EXISTS idx_menzioni_cognome ON menzioni(cognome);
CREATE INDEX IF NOT EXISTS idx_menzioni_luogo ON menzioni(luogo);
CREATE INDEX IF NOT EXISTS idx_ministero_cognome ON caduti_ministero(cognome);
CREATE INDEX IF NOT EXISTS idx_ministero_nominativo ON caduti_ministero(nominativo_paternita);
CREATE INDEX IF NOT EXISTS idx_mt_created ON memory_trace(created_at);
CREATE INDEX IF NOT EXISTS idx_mt_cue_persona ON memory_trace(cue_persona);
CREATE INDEX IF NOT EXISTS idx_mt_cue_reparto ON memory_trace(cue_reparto);
CREATE INDEX IF NOT EXISTS idx_na_arma ON decorati_nastroazzurro(id_arma);
CREATE INDEX IF NOT EXISTS idx_na_cognome ON decorati_nastroazzurro(cognome);
CREATE INDEX IF NOT EXISTS idx_na_decorazione ON decorati_nastroazzurro(tipo_decorazione);
CREATE INDEX IF NOT EXISTS idx_nara_cat_date ON documenti_nara_catalog(inclusive_dates);
CREATE INDEX IF NOT EXISTS idx_nara_cat_dates ON documenti_nara_catalog(inclusive_dates);
CREATE INDEX IF NOT EXISTS idx_nara_cat_naid ON documenti_nara_catalog(na_id);
CREATE INDEX IF NOT EXISTS idx_nara_cat_rg ON documenti_nara_catalog(record_group);
CREATE INDEX IF NOT EXISTS idx_nara_cat_type ON documenti_nara_catalog(document_type);
CREATE INDEX IF NOT EXISTS idx_nara_cat_unit ON documenti_nara_catalog(unit);
CREATE INDEX IF NOT EXISTS idx_nara_t315_data ON documenti_nara_t315(data_documento);
CREATE INDEX IF NOT EXISTS idx_nara_t315_frame ON documenti_nara_t315(frame);
CREATE INDEX IF NOT EXISTS idx_nara_t315_mittente ON documenti_nara_t315(mittente);
CREATE INDEX IF NOT EXISTS idx_nara_t315_tipo ON documenti_nara_t315(tipo_documento);
CREATE INDEX IF NOT EXISTS idx_nastro_arma ON decorati_nastroazzurro(arma);
CREATE INDEX IF NOT EXISTS idx_nastro_cognome ON decorati_nastroazzurro(cognome);
CREATE INDEX IF NOT EXISTS idx_nastro_tipo_dec ON decorati_nastroazzurro(tipo_decorazione);
CREATE INDEX IF NOT EXISTS idx_ncf_hash ON nara_catalog_files(hash_sha256);
CREATE INDEX IF NOT EXISTS idx_ncf_nara ON nara_catalog_files(nara_catalog_id);
CREATE INDEX IF NOT EXISTS idx_permitted_ops_policy ON permitted_operations(policy_id);
CREATE INDEX IF NOT EXISTS idx_prompt_versions_name ON prompt_versions(prompt_name, active);
CREATE INDEX IF NOT EXISTS idx_publication_versions_narr ON publication_versions(narrative_id);
CREATE INDEX IF NOT EXISTS idx_rc_ac_cand ON rc_administrative_cases(candidate_id);
CREATE INDEX IF NOT EXISTS idx_rc_ai_cand ON rc_ai_analyses(candidate_id);
CREATE INDEX IF NOT EXISTS idx_rc_ass_cand ON rc_recognition_assessments(candidate_id);
CREATE INDEX IF NOT EXISTS idx_rc_audit_data ON rc_audit_log(created_at);
CREATE INDEX IF NOT EXISTS idx_rc_audit_entita ON rc_audit_log(entita, entita_id);
CREATE INDEX IF NOT EXISTS idx_rc_audit_user ON rc_audit_log(user_id);
CREATE INDEX IF NOT EXISTS idx_rc_ca_cand ON rc_contact_attempts(candidate_id);
CREATE INDEX IF NOT EXISTS idx_rc_cand_cognome ON rc_candidates(cognome);
CREATE INDEX IF NOT EXISTS idx_rc_cand_conflitto ON rc_candidates(conflitto);
CREATE INDEX IF NOT EXISTS idx_rc_cand_stato ON rc_candidates(stato);
CREATE INDEX IF NOT EXISTS idx_rc_chk_prac ON rc_document_checklists(practice_id);
CREATE INDEX IF NOT EXISTS idx_rc_chk_rt ON rc_document_checklists(recognition_type_id);
CREATE INDEX IF NOT EXISTS idx_rc_comm_cand ON rc_communications(candidate_id);
CREATE INDEX IF NOT EXISTS idx_rc_comm_prac ON rc_communications(practice_id);
CREATE INDEX IF NOT EXISTS idx_rc_comm_stato ON rc_communications(stato);
CREATE INDEX IF NOT EXISTS idx_rc_comm_thread ON rc_communications(thread_id);
CREATE INDEX IF NOT EXISTS idx_rc_dc_cand ON rc_descendant_cases(candidate_id);
CREATE INDEX IF NOT EXISTS idx_rc_dcon_cand ON rc_descendant_contacts(candidate_id);
CREATE INDEX IF NOT EXISTS idx_rc_dcon_email ON rc_descendant_contacts(email);
CREATE INDEX IF NOT EXISTS idx_rc_dcon_stato ON rc_descendant_contacts(stato_verifica);
CREATE INDEX IF NOT EXISTS idx_rc_dl_data ON rc_practice_deadlines(data_scadenza);
CREATE INDEX IF NOT EXISTS idx_rc_dl_prac ON rc_practice_deadlines(practice_id);
CREATE INDEX IF NOT EXISTS idx_rc_doc_cand ON rc_documents(candidate_id);
CREATE INDEX IF NOT EXISTS idx_rc_dv_doc ON rc_document_versions(document_id);
CREATE INDEX IF NOT EXISTS idx_rc_fp_cand ON rc_family_persons(candidate_id);
CREATE INDEX IF NOT EXISTS idx_rc_hev_cand ON rc_historical_events(candidate_id);
CREATE INDEX IF NOT EXISTS idx_rc_inst_ente ON rc_institutional_contacts(ente);
CREATE INDEX IF NOT EXISTS idx_rc_inst_stato ON rc_institutional_contacts(stato);
CREATE INDEX IF NOT EXISTS idx_rc_inv_token ON rc_invitations(token);
CREATE INDEX IF NOT EXISTS idx_rc_pdoc_cand ON rc_practice_documents(candidate_id);
CREATE INDEX IF NOT EXISTS idx_rc_pdoc_cat ON rc_practice_documents(categoria_documentale);
CREATE INDEX IF NOT EXISTS idx_rc_pdoc_prac ON rc_practice_documents(practice_id);
CREATE INDEX IF NOT EXISTS idx_rc_pkg_cand ON rc_descendant_packages(candidate_id);
CREATE INDEX IF NOT EXISTS idx_rc_pkg_token ON rc_descendant_packages(token_condivisione);
CREATE INDEX IF NOT EXISTS idx_rc_plan ON research_cycles(plan_id);
CREATE INDEX IF NOT EXISTS idx_rc_prac_cand ON rc_practices(candidate_id);
CREATE INDEX IF NOT EXISTS idx_rc_prac_proto ON rc_practices(protocollo);
CREATE INDEX IF NOT EXISTS idx_rc_prac_stato ON rc_practices(stato);
CREATE INDEX IF NOT EXISTS idx_rc_session ON research_cycles(session_id);
CREATE INDEX IF NOT EXISTS idx_rc_sessions_expires ON rc_sessions(expires_at);
CREATE INDEX IF NOT EXISTS idx_rc_sessions_user ON rc_sessions(user_id);
CREATE INDEX IF NOT EXISTS idx_rc_src_cand ON rc_sources(candidate_id);
CREATE INDEX IF NOT EXISTS idx_rc_src_tipo ON rc_sources(tipologia);
CREATE INDEX IF NOT EXISTS idx_rc_st_cand ON rc_state_transitions(candidate_id);
CREATE INDEX IF NOT EXISTS idx_rc_users_role ON rc_users(role);
CREATE INDEX IF NOT EXISTS idx_record_links_legacy ON record_links(legacy_unverified) WHERE legacy_unverified=1;
CREATE INDEX IF NOT EXISTS idx_research_hits_query ON research_hits(query_id);
CREATE INDEX IF NOT EXISTS idx_research_hits_status ON research_hits(status);
CREATE INDEX IF NOT EXISTS idx_rg_status ON research_gaps(status);
CREATE INDEX IF NOT EXISTS idx_rg_subject ON research_gaps(subject_id);
CREATE INDEX IF NOT EXISTS idx_rp_entity ON research_plans(entity_type, entity_id);
CREATE INDEX IF NOT EXISTS idx_rp_status ON research_plans(status);
CREATE INDEX IF NOT EXISTS idx_rq_executed ON research_queries(executed_at);
CREATE INDEX IF NOT EXISTS idx_rq_session ON research_queries(session_id);
CREATE INDEX IF NOT EXISTS idx_rr_canonical ON research_results(canonical_url);
CREATE INDEX IF NOT EXISTS idx_rr_fingerprint ON research_results(fingerprint);
CREATE INDEX IF NOT EXISTS idx_rr_session ON research_results(session_id);
CREATE INDEX IF NOT EXISTS idx_rr_status ON research_results(status);
CREATE INDEX IF NOT EXISTS idx_rs_plan ON research_sessions(plan_id);
CREATE INDEX IF NOT EXISTS idx_rs_soldier ON research_subjects(linked_soldier_id);
CREATE INDEX IF NOT EXISTS idx_rs_status ON research_subjects(status);
CREATE INDEX IF NOT EXISTS idx_rs_type ON research_subjects(subject_type);
CREATE INDEX IF NOT EXISTS idx_rss_source ON research_subject_sources(source_locator_id);
CREATE INDEX IF NOT EXISTS idx_rss_subject ON research_subject_sources(subject_id);
CREATE INDEX IF NOT EXISTS idx_sardi_cognome ON caduti_sardi(cognome);
CREATE INDEX IF NOT EXISTS idx_sardi_comune ON caduti_sardi(comune_residenza);
CREATE INDEX IF NOT EXISTS idx_sfc_source ON source_fetch_cache(source_id);
CREATE INDEX IF NOT EXISTS idx_source_access_audit_conn ON source_access_audit(connector_code, created_at);
CREATE INDEX IF NOT EXISTS idx_source_rights_domain ON source_rights(domain);
CREATE INDEX IF NOT EXISTS idx_stable_locators_source ON stable_locators(source_item_id, source_table);

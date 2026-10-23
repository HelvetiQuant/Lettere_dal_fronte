"""Research Engine — Schema migrazioni per il motore agentico di ricerca.

Tutte le migrazioni sono idempotenti (CREATE TABLE IF NOT EXISTS, ALTER TABLE
con try/except). Non tocca tabelle esistenti. Estende record_links e
research_subjects con campi probatori dove necessario.

Tabelle nuove:
- archive_connectors: registry unificato delle fonti
- research_plans: piano di ricerca con budget
- research_sessions: sessione per connector
- research_queries: query individuali
- research_results: risultati con fingerprint
- research_cycles: tracking cicli di ricerca
- entity_variants: varianti d'identita'
- entity_match_candidates: match scoring
- document_extractions: estrazioni strutturate
- claims: affermazioni atomiche
- claim_evidence: evidenze per claim
- claim_relations: relazioni tra claim
- generated_narratives: narrazioni versionate
- ai_providers: provider IA
- ai_models: modelli IA
- ai_routing_policies: policy di routing
- ai_task_runs: esecuzioni task IA
- ai_usage_ledger: ledger consumi
"""
from database import get_conn


def init_research_engine_schema():
    """Crea tutte le tabelle del research engine se non esistono gia'."""
    conn = get_conn()
    conn.executescript("""
        -- ═══ ARCHIVE CONNECTORS ═══════════════════════════════════════════
        CREATE TABLE IF NOT EXISTS archive_connectors (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            code TEXT NOT NULL UNIQUE,
            name TEXT NOT NULL,
            scope TEXT,
            historical_periods TEXT,
            geographic_areas TEXT,
            entity_types TEXT,
            document_types TEXT,
            integration_type TEXT NOT NULL DEFAULT 'metadata_only',
            capabilities_json TEXT,
            access_mode TEXT NOT NULL DEFAULT 'assisted',
            authority_score REAL DEFAULT 0.5,
            reliability_criteria TEXT,
            provenance_group TEXT,
            languages TEXT,
            cost_priority INTEGER DEFAULT 5,
            config_json TEXT,
            status TEXT DEFAULT 'active',
            terms_limitations TEXT,
            last_verified_at TEXT,
            version TEXT DEFAULT '1.0',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );

        -- ═══ RESEARCH PLANS ═══════════════════════════════════════════════
        CREATE TABLE IF NOT EXISTS research_plans (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            original_input TEXT NOT NULL,
            entity_type TEXT,
            entity_id INTEGER,
            objective TEXT,
            initial_context TEXT,
            gaps_to_fill TEXT,
            budget_cycles INTEGER DEFAULT 10,
            budget_time_seconds INTEGER DEFAULT 300,
            budget_cost_usd REAL DEFAULT 5.0,
            status TEXT DEFAULT 'draft',
            generated_by TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );

        -- ═══ RESEARCH SESSIONS ════════════════════════════════════════════
        CREATE TABLE IF NOT EXISTS research_sessions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            plan_id INTEGER NOT NULL,
            connector_id INTEGER,
            mode TEXT NOT NULL DEFAULT 'auto',
            started_at TEXT,
            completed_at TEXT,
            status TEXT DEFAULT 'pending',
            cycle_number INTEGER DEFAULT 0,
            result_count INTEGER DEFAULT 0,
            linked_count INTEGER DEFAULT 0,
            excluded_count INTEGER DEFAULT 0,
            snapshot_version TEXT,
            stop_reason TEXT,
            note TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT,
            FOREIGN KEY (plan_id) REFERENCES research_plans(id) ON DELETE CASCADE
        );

        -- ═══ RESEARCH QUERIES ═════════════════════════════════════════════
        CREATE TABLE IF NOT EXISTS research_queries (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id INTEGER NOT NULL,
            query_text TEXT NOT NULL,
            query_language TEXT DEFAULT 'it',
            filters_json TEXT,
            variant_used TEXT,
            generated_from_claim_id INTEGER,
            generated_from_fragment TEXT,
            priority INTEGER DEFAULT 5,
            motivation TEXT,
            search_tool TEXT,
            assisted_search_url TEXT,
            executed_at TEXT,
            outcome TEXT,
            created_at TEXT NOT NULL,
            FOREIGN KEY (session_id) REFERENCES research_sessions(id) ON DELETE CASCADE
        );

        -- ═══ RESEARCH RESULTS ═════════════════════════════════════════════
        CREATE TABLE IF NOT EXISTS research_results (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id INTEGER NOT NULL,
            query_id INTEGER,
            external_id TEXT,
            result_type TEXT NOT NULL DEFAULT 'search_hit',
            record_url TEXT,
            document_url TEXT,
            canonical_url TEXT,
            title TEXT,
            author_or_entity TEXT,
            publication_date TEXT,
            retrieved_at TEXT,
            raw_metadata_json TEXT,
            fingerprint TEXT,
            source_quality REAL DEFAULT 0.5,
            authority_score REAL DEFAULT 0.5,
            independence_group TEXT,
            status TEXT DEFAULT 'new',
            status_reason TEXT,
            linked_source_id INTEGER,
            linked_document_id INTEGER,
            first_seen_at TEXT NOT NULL,
            last_seen_at TEXT,
            FOREIGN KEY (session_id) REFERENCES research_sessions(id) ON DELETE CASCADE
        );

        -- ═══ RESEARCH CYCLES ══════════════════════════════════════════════
        CREATE TABLE IF NOT EXISTS research_cycles (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            plan_id INTEGER NOT NULL,
            session_id INTEGER,
            cycle_number INTEGER NOT NULL,
            initial_knowledge_json TEXT,
            gaps_selected_json TEXT,
            sources_selected_json TEXT,
            sources_motivation TEXT,
            queries_executed_json TEXT,
            new_fragments_json TEXT,
            utility_metrics_json TEXT,
            decision TEXT DEFAULT 'continue',
            stop_reason TEXT,
            created_at TEXT NOT NULL,
            completed_at TEXT,
            FOREIGN KEY (plan_id) REFERENCES research_plans(id) ON DELETE CASCADE
        );

        -- ═══ ENTITY VARIANTS ═══════════════════════════════════════════════
        CREATE TABLE IF NOT EXISTS entity_variants (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            entity_type TEXT NOT NULL,
            entity_id INTEGER NOT NULL,
            field_name TEXT NOT NULL,
            original_value TEXT NOT NULL,
            variant_value TEXT NOT NULL,
            variant_type TEXT NOT NULL,
            origin TEXT,
            confidence REAL DEFAULT 0.5,
            verified INTEGER DEFAULT 0,
            created_at TEXT NOT NULL
        );

        -- ═══ ENTITY MATCH CANDIDATES ══════════════════════════════════════
        CREATE TABLE IF NOT EXISTS entity_match_candidates (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            local_entity_type TEXT NOT NULL,
            local_entity_id INTEGER NOT NULL,
            local_table TEXT,
            local_record_id INTEGER,
            candidate_source TEXT,
            candidate_record_id INTEGER,
            candidate_external_id TEXT,
            score REAL DEFAULT 0.0,
            score_breakdown_json TEXT,
            contrary_signals_json TEXT,
            missing_data_json TEXT,
            threshold_applied REAL,
            algorithm_version TEXT,
            status TEXT DEFAULT 'candidate',
            review_decision TEXT,
            reviewer TEXT,
            review_reason TEXT,
            reviewed_at TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );

        -- ═══ DOCUMENT EXTRACTIONS ═════════════════════════════════════════
        CREATE TABLE IF NOT EXISTS document_extractions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            document_id INTEGER,
            document_table TEXT,
            version TEXT DEFAULT '1',
            method TEXT NOT NULL,
            original_text TEXT,
            ocr_text TEXT,
            language TEXT,
            coordinates TEXT,
            raw_structured_output_json TEXT,
            model_version TEXT,
            review_status TEXT DEFAULT 'pending',
            reviewed_by TEXT,
            reviewed_at TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );

        -- ═══ CLAIMS ════════════════════════════════════════════════════════
        CREATE TABLE IF NOT EXISTS claims (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            stable_id TEXT UNIQUE,
            subject_type TEXT NOT NULL,
            subject_id INTEGER,
            subject_label TEXT,
            predicate TEXT NOT NULL,
            object_type TEXT,
            object_id INTEGER,
            object_label TEXT,
            object_value TEXT,
            original_value TEXT,
            temporal_range_start TEXT,
            temporal_range_end TEXT,
            temporal_precision TEXT,
            temporal_uncertainty TEXT,
            place TEXT,
            epistemic_status TEXT DEFAULT 'possible',
            confidence REAL DEFAULT 0.3,
            extraction_method TEXT,
            extraction_id INTEGER,
            review_status TEXT DEFAULT 'proposed',
            reviewed_by TEXT,
            reviewed_at TEXT,
            review_reason TEXT,
            created_by TEXT,
            version TEXT DEFAULT '1',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );

        -- ═══ CLAIM EVIDENCE ════════════════════════════════════════════════
        CREATE TABLE IF NOT EXISTS claim_evidence (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            claim_id INTEGER NOT NULL,
            source_id INTEGER,
            source_table TEXT,
            document_id INTEGER,
            document_table TEXT,
            extraction_id INTEGER,
            page_or_frame TEXT,
            coordinates TEXT,
            supporting_quote TEXT,
            evidence_role TEXT NOT NULL DEFAULT 'supports',
            source_independence_group TEXT,
            strength REAL DEFAULT 0.5,
            note TEXT,
            created_at TEXT NOT NULL,
            FOREIGN KEY (claim_id) REFERENCES claims(id) ON DELETE CASCADE
        );

        -- ═══ CLAIM RELATIONS ═══════════════════════════════════════════════
        CREATE TABLE IF NOT EXISTS claim_relations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            claim_a_id INTEGER NOT NULL,
            claim_b_id INTEGER NOT NULL,
            relation_type TEXT NOT NULL,
            confidence REAL DEFAULT 0.5,
            motivation TEXT,
            method TEXT,
            review_status TEXT DEFAULT 'pending',
            reviewed_by TEXT,
            reviewed_at TEXT,
            created_at TEXT NOT NULL,
            FOREIGN KEY (claim_a_id) REFERENCES claims(id) ON DELETE CASCADE,
            FOREIGN KEY (claim_b_id) REFERENCES claims(id) ON DELETE CASCADE
        );

        -- ═══ GENERATED NARRATIVES ═════════════════════════════════════════
        CREATE TABLE IF NOT EXISTS generated_narratives (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            entity_type TEXT NOT NULL,
            entity_id INTEGER NOT NULL,
            narrative_type TEXT NOT NULL,
            audience TEXT DEFAULT 'public',
            structured_text TEXT,
            claim_ids_json TEXT,
            gaps_json TEXT,
            deductions_json TEXT,
            confidence_level REAL DEFAULT 0.3,
            model_version TEXT,
            prompt_version TEXT,
            review_status TEXT DEFAULT 'draft',
            reviewed_by TEXT,
            reviewed_at TEXT,
            version TEXT DEFAULT '1',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );

        -- ═══ AI PROVIDERS ══════════════════════════════════════════════════
        CREATE TABLE IF NOT EXISTS ai_providers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            code TEXT NOT NULL UNIQUE,
            name TEXT NOT NULL,
            status TEXT DEFAULT 'active',
            declared_capabilities_json TEXT,
            verified_capabilities_json TEXT,
            credit_detection_method TEXT DEFAULT 'unknown',
            currency TEXT DEFAULT 'USD',
            budget_configured REAL DEFAULT 50.0,
            budget_reserve REAL DEFAULT 5.0,
            priority INTEGER DEFAULT 5,
            last_health_check TEXT,
            config_json TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );

        -- ═══ AI MODELS ═════════════════════════════════════════════════════
        CREATE TABLE IF NOT EXISTS ai_models (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            provider_id INTEGER NOT NULL,
            model_identifier TEXT NOT NULL,
            capabilities_json TEXT,
            context_window INTEGER,
            cost_per_unit REAL,
            quality_score REAL DEFAULT 0.5,
            latency_score REAL DEFAULT 0.5,
            status TEXT DEFAULT 'enabled',
            last_benchmarked_at TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            FOREIGN KEY (provider_id) REFERENCES ai_providers(id) ON DELETE CASCADE
        );

        -- ═══ AI ROUTING POLICIES ═══════════════════════════════════════════
        CREATE TABLE IF NOT EXISTS ai_routing_policies (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            task_type TEXT NOT NULL,
            min_requirements_json TEXT,
            primary_model_id INTEGER,
            fallback_model_ids_json TEXT,
            max_cost REAL,
            min_reserve_credit REAL,
            timeout_seconds INTEGER DEFAULT 60,
            max_retries INTEGER DEFAULT 2,
            quality_criterion TEXT,
            version TEXT DEFAULT '1',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );

        -- ═══ AI TASK RUNS ══════════════════════════════════════════════════
        CREATE TABLE IF NOT EXISTS ai_task_runs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            research_plan_id INTEGER,
            session_id INTEGER,
            cycle_id INTEGER,
            task_type TEXT NOT NULL,
            provider_code TEXT,
            model_identifier TEXT,
            selection_reason TEXT,
            policy_version TEXT,
            input_fingerprint TEXT,
            input_tokens INTEGER,
            output_tokens INTEGER,
            cost_estimated REAL,
            cost_actual REAL,
            credit_before TEXT,
            credit_after TEXT,
            latency_ms INTEGER,
            outcome TEXT,
            validation_result_json TEXT,
            fallback_from TEXT,
            fallback_to TEXT,
            idempotency_key TEXT,
            created_at TEXT NOT NULL,
            completed_at TEXT
        );

        -- ═══ AI USAGE LEDGER ═══════════════════════════════════════════════
        CREATE TABLE IF NOT EXISTS ai_usage_ledger (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            provider_code TEXT NOT NULL,
            model_identifier TEXT NOT NULL,
            period TEXT NOT NULL,
            units_consumed REAL,
            cost REAL,
            data_source TEXT NOT NULL DEFAULT 'internal_estimate',
            task_run_id INTEGER,
            updated_at TEXT NOT NULL
        );
    """)

    # ─── Indici ────────────────────────────────────────────────────────────
    conn.executescript("""
        CREATE INDEX IF NOT EXISTS idx_ac_code ON archive_connectors(code);
        CREATE INDEX IF NOT EXISTS idx_ac_status ON archive_connectors(status);

        CREATE INDEX IF NOT EXISTS idx_rp_entity ON research_plans(entity_type, entity_id);
        CREATE INDEX IF NOT EXISTS idx_rp_status ON research_plans(status);

        CREATE INDEX IF NOT EXISTS idx_rs_plan ON research_sessions(plan_id);
        CREATE INDEX IF NOT EXISTS idx_rs_status ON research_sessions(status);

        CREATE INDEX IF NOT EXISTS idx_rq_session ON research_queries(session_id);
        CREATE INDEX IF NOT EXISTS idx_rq_executed ON research_queries(executed_at);

        CREATE INDEX IF NOT EXISTS idx_rr_session ON research_results(session_id);
        CREATE INDEX IF NOT EXISTS idx_rr_fingerprint ON research_results(fingerprint);
        CREATE INDEX IF NOT EXISTS idx_rr_status ON research_results(status);
        CREATE INDEX IF NOT EXISTS idx_rr_canonical ON research_results(canonical_url);

        CREATE INDEX IF NOT EXISTS idx_rc_plan ON research_cycles(plan_id);
        CREATE INDEX IF NOT EXISTS idx_rc_session ON research_cycles(session_id);

        CREATE INDEX IF NOT EXISTS idx_ev_entity ON entity_variants(entity_type, entity_id);

        CREATE INDEX IF NOT EXISTS idx_emc_local ON entity_match_candidates(local_entity_type, local_entity_id);
        CREATE INDEX IF NOT EXISTS idx_emc_status ON entity_match_candidates(status);

        CREATE INDEX IF NOT EXISTS idx_de_document ON document_extractions(document_table, document_id);

        CREATE INDEX IF NOT EXISTS idx_claims_subject ON claims(subject_type, subject_id);
        CREATE INDEX IF NOT EXISTS idx_claims_predicate ON claims(predicate);
        CREATE INDEX IF NOT EXISTS idx_claims_epistemic ON claims(epistemic_status);
        CREATE INDEX IF NOT EXISTS idx_claims_review ON claims(review_status);
        CREATE INDEX IF NOT EXISTS idx_claims_stable ON claims(stable_id);

        CREATE INDEX IF NOT EXISTS idx_ce_claim ON claim_evidence(claim_id);
        CREATE INDEX IF NOT EXISTS idx_ce_role ON claim_evidence(evidence_role);

        CREATE INDEX IF NOT EXISTS idx_cr_a ON claim_relations(claim_a_id);
        CREATE INDEX IF NOT EXISTS idx_cr_b ON claim_relations(claim_b_id);
        CREATE INDEX IF NOT EXISTS idx_cr_type ON claim_relations(relation_type);

        CREATE INDEX IF NOT EXISTS idx_gn_entity ON generated_narratives(entity_type, entity_id);
        CREATE INDEX IF NOT EXISTS idx_gn_status ON generated_narratives(review_status);

        CREATE INDEX IF NOT EXISTS idx_ap_code ON ai_providers(code);
        CREATE INDEX IF NOT EXISTS idx_ap_status ON ai_providers(status);

        CREATE INDEX IF NOT EXISTS idx_am_provider ON ai_models(provider_id);
        CREATE INDEX IF NOT EXISTS idx_am_status ON ai_models(status);

        CREATE INDEX IF NOT EXISTS idx_arp_task ON ai_routing_policies(task_type);

        CREATE INDEX IF NOT EXISTS idx_atr_plan ON ai_task_runs(research_plan_id);
        CREATE INDEX IF NOT EXISTS idx_atr_task ON ai_task_runs(task_type);
        CREATE INDEX IF NOT EXISTS idx_atr_idem ON ai_task_runs(idempotency_key);

        CREATE INDEX IF NOT EXISTS idx_aul_period ON ai_usage_ledger(provider_code, period);
    """)

    # ─── Estensione record_links con campi per collegamenti euristici ──────
    for col, coltype in [
        ("algorithm_version", "TEXT DEFAULT 'legacy'"),
        ("score_breakdown_json", "TEXT"),
        ("contrary_signals_json", "TEXT"),
        ("explanation", "TEXT"),
    ]:
        try:
            conn.execute(f"ALTER TABLE record_links ADD COLUMN {col} {coltype}")
        except Exception:
            pass

    # ─── Seed AI providers di base (idempotente) ───────────────────────────
    _seed_ai_providers(conn)

    # ─── Migrazione research_sessions.updated_at ───────────────────────────
    try:
        conn.execute("ALTER TABLE research_sessions ADD COLUMN updated_at TEXT")
    except Exception:
        pass

    conn.commit()
    conn.close()


def _seed_ai_providers(conn):
    """Inserisce i provider IA di base se non gia' presenti."""
    now = __import__('datetime').datetime.now().isoformat(timespec="seconds")
    providers = [
        ("openai", "OpenAI", '["text","vision","pdf","structured_output","embeddings"]',
         "api_header", 50.0, 5.0, 1),
        ("anthropic", "Anthropic", '["text","vision","pdf","structured_output"]',
         "unknown", 50.0, 5.0, 2),
        ("mistral", "Mistral AI", '["text","vision","ocr","structured_output"]',
         "unknown", 30.0, 3.0, 3),
        ("perplexity", "Perplexity", '["text","web_search","structured_output"]',
         "unknown", 20.0, 2.0, 4),
        ("gemini", "Google Gemini", '["text","vision","pdf","structured_output","embeddings"]',
         "unknown", 30.0, 3.0, 5),
        ("ollama", "Ollama (local)", '["text","vision","structured_output"]',
         "none", 0.0, 0.0, 6),
        ("lmstudio", "LM Studio (local)", '["text","structured_output"]',
         "none", 0.0, 0.0, 10),
    ]
    for code, name, caps, credit_method, budget, reserve, priority in providers:
        existing = conn.execute(
            "SELECT id FROM ai_providers WHERE code=?", (code,)
        ).fetchone()
        if not existing:
            conn.execute(
                "INSERT INTO ai_providers (code, name, status, declared_capabilities_json, "
                "credit_detection_method, budget_configured, budget_reserve, priority, "
                "config_json, created_at, updated_at) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                (code, name, "active", caps, credit_method, budget, reserve,
                 priority, "{}", now, now)
            )


if __name__ == "__main__":
    init_research_engine_schema()
    print("Research Engine schema inizializzato.")

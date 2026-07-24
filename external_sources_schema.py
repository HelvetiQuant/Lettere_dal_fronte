"""Schema per modulo Fonti Esterne Federate (CRI e altri archivi).

Tabelle:
- external_source_records: metadati archivistici esterni (fondi, serie, unità)
- external_person_mentions: nominativi estratti dai metadati
- external_source_facts: fatti descritti nei metadati
- external_digital_objects: oggetti digitali rilevati
- external_record_links: collegamenti candidati/confermati con record interni
- external_access_requests: richieste di accesso per documenti non scaricabili
- external_import_jobs: tracking job import incrementali

Migrazioni idempotenti. Estende record_links con campi probatori.
"""
from database import get_conn


def init_external_sources_schema():
    """Crea tutte le tabelle del modulo se non esistono già."""
    conn = get_conn()
    conn.executescript("""
        -- ─── Record archivistici esterni ────────────────────────────────────
        CREATE TABLE IF NOT EXISTS external_source_records (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            provider TEXT NOT NULL,
            archive_name TEXT,
            archive_branch TEXT,
            external_id TEXT NOT NULL,
            record_level TEXT NOT NULL,
            record_type TEXT,
            title TEXT,
            description TEXT,
            date_text TEXT,
            date_from TEXT,
            date_to TEXT,
            fonds_external_id TEXT,
            fonds_title TEXT,
            series_external_id TEXT,
            series_title TEXT,
            subseries_external_id TEXT,
            subseries_title TEXT,
            parent_external_id TEXT,
            reference_code TEXT,
            box_number TEXT,
            file_number TEXT,
            register_number TEXT,
            protocol_number TEXT,
            extent TEXT,
            language TEXT,
            people_metadata_json TEXT,
            places_metadata_json TEXT,
            military_units_metadata_json TEXT,
            camps_metadata_json TEXT,
            subjects_metadata_json TEXT,
            canonical_record_url TEXT NOT NULL,
            parent_record_url TEXT,
            digital_object_available INTEGER DEFAULT 0,
            digital_object_url TEXT,
            access_status TEXT DEFAULT 'active',
            source_notes TEXT,
            metadata_hash TEXT,
            http_status INTEGER,
            first_seen_at TEXT NOT NULL,
            last_verified_at TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            UNIQUE(provider, external_id)
        );

        -- ─── Menzioni nominative esterne ───────────────────────────────────
        CREATE TABLE IF NOT EXISTS external_person_mentions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            external_source_record_id INTEGER NOT NULL,
            surname_raw TEXT,
            name_raw TEXT,
            full_name_raw TEXT,
            normalized_surname TEXT,
            normalized_name TEXT,
            father_name_raw TEXT,
            mother_name_raw TEXT,
            birth_date_text TEXT,
            birth_date TEXT,
            birth_place_raw TEXT,
            residence_raw TEXT,
            rank_raw TEXT,
            military_unit_raw TEXT,
            service_number TEXT,
            prisoner_number TEXT,
            camp_raw TEXT,
            status_raw TEXT,
            event_date_text TEXT,
            event_place_raw TEXT,
            role_in_metadata TEXT,
            source_text TEXT,
            extraction_method TEXT,
            extraction_confidence REAL DEFAULT 1.0,
            human_verified INTEGER DEFAULT 0,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            FOREIGN KEY (external_source_record_id) REFERENCES external_source_records(id) ON DELETE CASCADE
        );

        -- ─── Fatti descritti nei metadati ──────────────────────────────────
        CREATE TABLE IF NOT EXISTS external_source_facts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            external_source_record_id INTEGER NOT NULL,
            external_person_mention_id INTEGER,
            fact_type TEXT NOT NULL,
            fact_value TEXT,
            date_text TEXT,
            date_value TEXT,
            place_raw TEXT,
            description TEXT,
            source_text TEXT,
            extraction_method TEXT,
            confidence REAL DEFAULT 1.0,
            human_verified INTEGER DEFAULT 0,
            created_at TEXT NOT NULL,
            FOREIGN KEY (external_source_record_id) REFERENCES external_source_records(id) ON DELETE CASCADE,
            FOREIGN KEY (external_person_mention_id) REFERENCES external_person_mentions(id) ON DELETE SET NULL
        );

        -- ─── Oggetti digitali esterni ──────────────────────────────────────
        CREATE TABLE IF NOT EXISTS external_digital_objects (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            external_source_record_id INTEGER NOT NULL,
            external_object_id TEXT,
            object_type TEXT,
            media_type TEXT,
            label TEXT,
            viewer_url TEXT,
            page_url TEXT,
            download_url TEXT,
            iiif_manifest_url TEXT,
            thumbnail_url TEXT,
            digital_object_available INTEGER DEFAULT 0,
            publicly_viewable INTEGER DEFAULT 0,
            public_download_allowed INTEGER DEFAULT 0,
            authorization_required INTEGER DEFAULT 0,
            local_file_path TEXT,
            sha256 TEXT,
            file_size INTEGER,
            ocr_status TEXT DEFAULT 'pending',
            rights_statement TEXT,
            credit_line TEXT,
            retrieved_at TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            FOREIGN KEY (external_source_record_id) REFERENCES external_source_records(id) ON DELETE CASCADE
        );

        -- ─── Collegamenti esterni ↔ record interni ─────────────────────────
        CREATE TABLE IF NOT EXISTS external_record_links (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            external_source_record_id INTEGER NOT NULL,
            external_person_mention_id INTEGER,
            target_table TEXT NOT NULL,
            target_record_id INTEGER NOT NULL,
            target_entity_id INTEGER,
            link_type TEXT NOT NULL,
            match_status TEXT DEFAULT 'candidate',
            match_score REAL DEFAULT 0.0,
            match_method TEXT,
            matched_fields_json TEXT,
            conflicting_fields_json TEXT,
            evidence_json TEXT,
            explanation TEXT,
            review_status TEXT DEFAULT 'pending',
            reviewed_by TEXT,
            reviewed_at TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            FOREIGN KEY (external_source_record_id) REFERENCES external_source_records(id) ON DELETE CASCADE,
            FOREIGN KEY (external_person_mention_id) REFERENCES external_person_mentions(id) ON DELETE SET NULL
        );

        -- ─── Richieste di accesso ──────────────────────────────────────────
        CREATE TABLE IF NOT EXISTS external_access_requests (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            external_source_record_id INTEGER NOT NULL,
            candidate_id INTEGER,
            research_subject_id INTEGER,
            request_status TEXT DEFAULT 'da_valutare',
            recipient TEXT,
            request_reason TEXT,
            requested_documents TEXT,
            requested_at TEXT,
            response_received_at TEXT,
            authorization_reference TEXT,
            authorization_date TEXT,
            usage_scope TEXT,
            publication_allowed INTEGER DEFAULT 0,
            notes TEXT,
            created_by TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            FOREIGN KEY (external_source_record_id) REFERENCES external_source_records(id) ON DELETE CASCADE
        );

        -- ─── Job di import incrementali ────────────────────────────────────
        CREATE TABLE IF NOT EXISTS external_import_jobs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            provider TEXT NOT NULL,
            job_type TEXT NOT NULL,
            status TEXT DEFAULT 'pending',
            total_records INTEGER DEFAULT 0,
            processed_records INTEGER DEFAULT 0,
            error_count INTEGER DEFAULT 0,
            last_error TEXT,
            checkpoint_data TEXT,
            started_at TEXT,
            finished_at TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
    """)

    # ─── Indici ────────────────────────────────────────────────────────────
    conn.executescript("""
        CREATE INDEX IF NOT EXISTS idx_esr_provider ON external_source_records(provider);
        CREATE INDEX IF NOT EXISTS idx_esr_level ON external_source_records(record_level);
        CREATE INDEX IF NOT EXISTS idx_esr_parent ON external_source_records(parent_external_id);
        CREATE INDEX IF NOT EXISTS idx_esr_fonds ON external_source_records(fonds_external_id);
        CREATE INDEX IF NOT EXISTS idx_esr_url ON external_source_records(canonical_record_url);
        CREATE INDEX IF NOT EXISTS idx_esr_hash ON external_source_records(metadata_hash);
        CREATE INDEX IF NOT EXISTS idx_esr_access ON external_source_records(access_status);

        CREATE INDEX IF NOT EXISTS idx_epm_record ON external_person_mentions(external_source_record_id);
        CREATE INDEX IF NOT EXISTS idx_epm_surname ON external_person_mentions(normalized_surname);
        CREATE INDEX IF NOT EXISTS idx_epm_name ON external_person_mentions(normalized_name);
        CREATE INDEX IF NOT EXISTS idx_epm_service ON external_person_mentions(service_number);
        CREATE INDEX IF NOT EXISTS idx_epm_prisoner ON external_person_mentions(prisoner_number);

        CREATE INDEX IF NOT EXISTS idx_esf_record ON external_source_facts(external_source_record_id);
        CREATE INDEX IF NOT EXISTS idx_esf_mention ON external_source_facts(external_person_mention_id);
        CREATE INDEX IF NOT EXISTS idx_esf_type ON external_source_facts(fact_type);

        CREATE INDEX IF NOT EXISTS idx_edo_record ON external_digital_objects(external_source_record_id);

        CREATE INDEX IF NOT EXISTS idx_erl_record ON external_record_links(external_source_record_id);
        CREATE INDEX IF NOT EXISTS idx_erl_mention ON external_record_links(external_person_mention_id);
        CREATE INDEX IF NOT EXISTS idx_erl_target ON external_record_links(target_table, target_record_id);
        CREATE INDEX IF NOT EXISTS idx_erl_status ON external_record_links(match_status);
        CREATE INDEX IF NOT EXISTS idx_erl_review ON external_record_links(review_status);

        CREATE INDEX IF NOT EXISTS idx_ear_record ON external_access_requests(external_source_record_id);
        CREATE INDEX IF NOT EXISTS idx_ear_status ON external_access_requests(request_status);

        CREATE INDEX IF NOT EXISTS idx_eij_provider ON external_import_jobs(provider);
        CREATE INDEX IF NOT EXISTS idx_eij_status ON external_import_jobs(status);
    """)

    # ─── Estensione record_links con campi probatori ───────────────────────
    # Idempotente: try/except per colonne già esistenti
    for col, coltype in [
        ("match_status", "TEXT DEFAULT 'candidate'"),
        ("match_method", "TEXT"),
        ("matched_fields_json", "TEXT"),
        ("conflicting_fields_json", "TEXT"),
        ("evidence_json", "TEXT"),
        ("explanation", "TEXT"),
        ("review_status", "TEXT DEFAULT 'pending'"),
        ("reviewed_by", "TEXT"),
        ("reviewed_at", "TEXT"),
    ]:
        try:
            conn.execute(f"ALTER TABLE record_links ADD COLUMN {col} {coltype}")
        except Exception:
            pass

    conn.commit()
    conn.close()


if __name__ == "__main__":
    init_external_sources_schema()
    print("Schema external_sources inizializzato.")

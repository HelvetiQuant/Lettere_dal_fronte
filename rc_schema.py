"""Schema del database per il modulo Percorso Riconoscimenti.

Tutte le tabelle usano il prefisso `rc_` per isolamento nel DB esistente.
La funzione `init_rc_schema()` è idempotente (CREATE TABLE IF NOT EXISTS).
"""
from database import get_conn


def init_rc_schema():
    """Crea tutte le tabelle del modulo se non esistono già."""
    conn = get_conn()
    conn.executescript("""
        -- ─── Candidati ─────────────────────────────────────────────────────
        CREATE TABLE IF NOT EXISTS rc_candidates (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nome TEXT NOT NULL,
            cognome TEXT NOT NULL,
            varianti_nominativi TEXT,
            paternita TEXT,
            maternita TEXT,
            data_nascita TEXT,
            luogo_nascita TEXT,
            data_morte TEXT,
            luogo_morte TEXT,
            comune_residenza TEXT,
            grado TEXT,
            reparto TEXT,
            forza_armata TEXT,
            matricola TEXT,
            conflitto TEXT,
            stato TEXT NOT NULL DEFAULT 'BOZZA',
            livello_certezza TEXT DEFAULT 'da_verificare',
            note_interne TEXT,
            priorita_json TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            created_by INTEGER
        );
        CREATE INDEX IF NOT EXISTS idx_rc_cand_stato ON rc_candidates(stato);
        CREATE INDEX IF NOT EXISTS idx_rc_cand_cognome ON rc_candidates(cognome);
        CREATE INDEX IF NOT EXISTS idx_rc_cand_conflitto ON rc_candidates(conflitto);

        -- ─── Eventi storici ────────────────────────────────────────────────
        CREATE TABLE IF NOT EXISTS rc_historical_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            candidate_id INTEGER NOT NULL,
            tipo_evento TEXT,
            data_inizio TEXT,
            data_fine TEXT,
            luogo TEXT,
            descrizione_verificata TEXT,
            testo_originale_fonte TEXT,
            condotta_individuale TEXT,
            rischio_affrontato TEXT,
            conseguenze TEXT,
            testimoni TEXT,
            grado_attendibilita TEXT DEFAULT 'da_verificare',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            FOREIGN KEY (candidate_id) REFERENCES rc_candidates(id)
        );
        CREATE INDEX IF NOT EXISTS idx_rc_hev_cand ON rc_historical_events(candidate_id);

        -- ─── Fonti ─────────────────────────────────────────────────────────
        CREATE TABLE IF NOT EXISTS rc_sources (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            titolo TEXT NOT NULL,
            tipologia TEXT,
            ente_conservatore TEXT,
            fondo TEXT,
            serie TEXT,
            busta TEXT,
            fascicolo TEXT,
            pagina_immagine TEXT,
            segnatura_completa TEXT,
            url_istituzionale TEXT,
            data_documento TEXT,
            file_path TEXT,
            file_checksum TEXT,
            trascrizione TEXT,
            estrazione_automatica TEXT,
            livello_attendibilita TEXT DEFAULT 'da_verificare',
            stato_verifica TEXT DEFAULT 'non_verificata',
            verificatore TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            candidate_id INTEGER,
            FOREIGN KEY (candidate_id) REFERENCES rc_candidates(id)
        );
        CREATE INDEX IF NOT EXISTS idx_rc_src_cand ON rc_sources(candidate_id);
        CREATE INDEX IF NOT EXISTS idx_rc_src_tipo ON rc_sources(tipologia);

        -- ─── Catalogo riconoscimenti ───────────────────────────────────────
        CREATE TABLE IF NOT EXISTS rc_recognition_types (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            denominazione TEXT NOT NULL,
            categoria TEXT,
            autorita_concedente TEXT,
            ente_istruttore TEXT,
            base_normativa TEXT,
            requisiti TEXT,
            concessione_memoria INTEGER DEFAULT 0,
            soggetti_legittimati TEXT,
            modalita_avvio TEXT,
            termini TEXT,
            documenti_richiesti TEXT,
            procedura_attiva TEXT DEFAULT 'da_verificare',
            data_ultimo_aggiornamento TEXT,
            fonti_istituzionali TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );

        -- ─── Valutazioni riconoscimento ────────────────────────────────────
        CREATE TABLE IF NOT EXISTS rc_recognition_assessments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            candidate_id INTEGER NOT NULL,
            recognition_type_id INTEGER NOT NULL,
            riconoscimento_ipotizzato TEXT,
            requisiti_presenti TEXT,
            requisiti_mancanti TEXT,
            elementi_contrari TEXT,
            procedura TEXT DEFAULT 'da_verificare',
            motivazione TEXT,
            valutatore TEXT,
            data_valutazione TEXT,
            validazione_storica INTEGER DEFAULT 0,
            validazione_amministrativa INTEGER DEFAULT 0,
            -- Campi analisi AI
            processo_logico TEXT,
            fonti_consultate TEXT,
            percentuale_stimata_concessione REAL,
            precedenti_storici TEXT,
            fattori_favorevoli TEXT,
            fattori_sfavorevoli TEXT,
            onorificenze_alternative TEXT,
            livello_confidenza TEXT DEFAULT 'basso',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            FOREIGN KEY (candidate_id) REFERENCES rc_candidates(id),
            FOREIGN KEY (recognition_type_id) REFERENCES rc_recognition_types(id)
        );
        CREATE INDEX IF NOT EXISTS idx_rc_ass_cand ON rc_recognition_assessments(candidate_id);

        -- ─── Analisi AI dettagliate per candidato ───────────────────────────
        CREATE TABLE IF NOT EXISTS rc_ai_analyses (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            candidate_id INTEGER NOT NULL,
            tipo_analisi TEXT NOT NULL,
            riepilogo_esecutivo TEXT,
            processo_logico_dettagliato TEXT,
            fonti_consultate_json TEXT,
            onorificenze_ipotizzabili_json TEXT,
            percentuali_stimate_json TEXT,
            precedenti_attribuzioni_json TEXT,
            fattori_favorevoli TEXT,
            fattori_sfavorevoli TEXT,
            raccomandazioni TEXT,
            livello_confidenza TEXT DEFAULT 'basso',
            modello_ai TEXT,
            versione_modello TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            FOREIGN KEY (candidate_id) REFERENCES rc_candidates(id)
        );
        CREATE INDEX IF NOT EXISTS idx_rc_ai_cand ON rc_ai_analyses(candidate_id);

        -- ─── Persone famiglia ──────────────────────────────────────────────
        CREATE TABLE IF NOT EXISTS rc_family_persons (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            candidate_id INTEGER NOT NULL,
            nome TEXT,
            cognome TEXT,
            data_nascita TEXT,
            luogo_nascita TEXT,
            data_morte TEXT,
            rapporto_candidato TEXT,
            stato_vita TEXT DEFAULT 'non_accertato',
            fonte_genealogica TEXT,
            livello_certezza TEXT DEFAULT 'basso',
            visibilita_limitata INTEGER DEFAULT 1,
            stato_contatto TEXT DEFAULT 'nessuno',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            FOREIGN KEY (candidate_id) REFERENCES rc_candidates(id)
        );
        CREATE INDEX IF NOT EXISTS idx_rc_fp_cand ON rc_family_persons(candidate_id);

        -- ─── Legami parentela ──────────────────────────────────────────────
        CREATE TABLE IF NOT EXISTS rc_kinship_links (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            persona_origine_id INTEGER NOT NULL,
            persona_destinazione_id INTEGER NOT NULL,
            tipo_rapporto TEXT,
            fonte TEXT,
            grado_certezza TEXT DEFAULT 'basso',
            verificato_da TEXT,
            created_at TEXT NOT NULL,
            FOREIGN KEY (persona_origine_id) REFERENCES rc_family_persons(id),
            FOREIGN KEY (persona_destinazione_id) REFERENCES rc_family_persons(id)
        );

        -- ─── Tentativi di contatto ─────────────────────────────────────────
        CREATE TABLE IF NOT EXISTS rc_contact_attempts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            candidate_id INTEGER NOT NULL,
            destinatario_id INTEGER,
            canale TEXT,
            intermediario TEXT,
            testo_approvato TEXT,
            data_invio TEXT,
            esito TEXT DEFAULT 'in_attesa',
            operatore TEXT,
            divieto_ulteriori INTEGER DEFAULT 0,
            prova_inoltro TEXT,
            approvato INTEGER DEFAULT 0,
            approvato_da TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            FOREIGN KEY (candidate_id) REFERENCES rc_candidates(id),
            FOREIGN KEY (destinatario_id) REFERENCES rc_family_persons(id)
        );
        CREATE INDEX IF NOT EXISTS idx_rc_ca_cand ON rc_contact_attempts(candidate_id);

        -- ─── Casi discendenti ──────────────────────────────────────────────
        CREATE TABLE IF NOT EXISTS rc_descendant_cases (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            candidate_id INTEGER NOT NULL,
            discendente_referente_id INTEGER,
            parentela_dichiarata TEXT,
            parentela_verificata TEXT DEFAULT 'non_verificata',
            documenti_prova TEXT,
            consenso INTEGER DEFAULT 0,
            delega TEXT,
            data_adesione TEXT,
            altri_rami_familiari TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            FOREIGN KEY (candidate_id) REFERENCES rc_candidates(id),
            FOREIGN KEY (discendente_referente_id) REFERENCES rc_family_persons(id)
        );
        CREATE INDEX IF NOT EXISTS idx_rc_dc_cand ON rc_descendant_cases(candidate_id);

        -- ─── Pratiche amministrative ───────────────────────────────────────
        CREATE TABLE IF NOT EXISTS rc_administrative_cases (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            candidate_id INTEGER NOT NULL,
            recognition_type_id INTEGER,
            ente_destinatario TEXT,
            ufficio TEXT,
            protocollo TEXT,
            data_invio TEXT,
            modalita_trasmissione TEXT,
            responsabile TEXT,
            scadenze TEXT,
            stato TEXT DEFAULT 'in_preparazione',
            richieste_integrazione TEXT,
            esito TEXT,
            decreto_provvedimento TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            FOREIGN KEY (candidate_id) REFERENCES rc_candidates(id),
            FOREIGN KEY (recognition_type_id) REFERENCES rc_recognition_types(id)
        );
        CREATE INDEX IF NOT EXISTS idx_rc_ac_cand ON rc_administrative_cases(candidate_id);

        -- ─── Audit log ─────────────────────────────────────────────────────
        CREATE TABLE IF NOT EXISTS rc_audit_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            username TEXT,
            azione TEXT NOT NULL,
            entita TEXT NOT NULL,
            entita_id INTEGER,
            valore_precedente TEXT,
            valore_successivo TEXT,
            ip_address TEXT,
            motivazione TEXT,
            created_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_rc_audit_entita ON rc_audit_log(entita, entita_id);
        CREATE INDEX IF NOT EXISTS idx_rc_audit_user ON rc_audit_log(user_id);
        CREATE INDEX IF NOT EXISTS idx_rc_audit_data ON rc_audit_log(created_at);

        -- ─── Transizioni di stato ──────────────────────────────────────────
        CREATE TABLE IF NOT EXISTS rc_state_transitions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            candidate_id INTEGER NOT NULL,
            stato_precedente TEXT NOT NULL,
            stato_successivo TEXT NOT NULL,
            autore TEXT,
            data_ora TEXT NOT NULL,
            motivazione TEXT,
            allegati TEXT,
            approvazione_richiesta INTEGER DEFAULT 0,
            FOREIGN KEY (candidate_id) REFERENCES rc_candidates(id)
        );
        CREATE INDEX IF NOT EXISTS idx_rc_st_cand ON rc_state_transitions(candidate_id);

        -- ─── Inviti discendenti ────────────────────────────────────────────
        CREATE TABLE IF NOT EXISTS rc_invitations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            token TEXT UNIQUE NOT NULL,
            descendant_case_id INTEGER NOT NULL,
            email TEXT,
            created_at TEXT NOT NULL,
            expires_at TEXT NOT NULL,
            accettato INTEGER DEFAULT 0,
            data_accettazione TEXT,
            revocato INTEGER DEFAULT 0,
            FOREIGN KEY (descendant_case_id) REFERENCES rc_descendant_cases(id)
        );
        CREATE INDEX IF NOT EXISTS idx_rc_inv_token ON rc_invitations(token);

        -- ─── Documenti ─────────────────────────────────────────────────────
        CREATE TABLE IF NOT EXISTS rc_documents (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            candidate_id INTEGER,
            descendant_case_id INTEGER,
            filename TEXT NOT NULL,
            file_path TEXT NOT NULL,
            file_checksum TEXT,
            file_size INTEGER,
            mime_type TEXT,
            uploaded_by TEXT,
            visibilita TEXT DEFAULT 'operatore',
            created_at TEXT NOT NULL,
            FOREIGN KEY (candidate_id) REFERENCES rc_candidates(id),
            FOREIGN KEY (descendant_case_id) REFERENCES rc_descendant_cases(id)
        );
        CREATE INDEX IF NOT EXISTS idx_rc_doc_cand ON rc_documents(candidate_id);

        -- ─── Contatti discendenti estesi ───────────────────────────────────
        CREATE TABLE IF NOT EXISTS rc_descendant_contacts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            candidate_id INTEGER NOT NULL,
            nome TEXT NOT NULL,
            cognome TEXT NOT NULL,
            nome_precedente TEXT,
            rapporto_parentela_presunto TEXT,
            rapporto_parentela_verificato TEXT,
            ramo_familiare TEXT,
            comune_residenza TEXT,
            indirizzo_postale TEXT,
            email TEXT,
            pec TEXT,
            telefono TEXT,
            altro_canale TEXT,
            profilo_pubblico_url TEXT,
            preferenza_contatto TEXT,
            lingua TEXT DEFAULT 'it',
            note TEXT,
            stato_verifica TEXT DEFAULT 'NON_VERIFICATO',
            fonte_contatto TEXT,
            url_fonte TEXT,
            titolo_pagina_fonte TEXT,
            data_consultazione_fonte TEXT,
            operatore_inserimento TEXT,
            data_reperimento TEXT,
            data_ultima_verifica TEXT,
            livello_attendibilita TEXT DEFAULT 'da_verificare',
            consenso_acquisito INTEGER DEFAULT 0,
            data_consenso TEXT,
            modalita_consenso TEXT,
            opposizione_contatto INTEGER DEFAULT 0,
            richiesta_non_contattare INTEGER DEFAULT 0,
            cancellazione_limitazione TEXT,
            visibilita_limitata INTEGER DEFAULT 1,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            created_by INTEGER,
            FOREIGN KEY (candidate_id) REFERENCES rc_candidates(id)
        );
        CREATE INDEX IF NOT EXISTS idx_rc_dcon_cand ON rc_descendant_contacts(candidate_id);
        CREATE INDEX IF NOT EXISTS idx_rc_dcon_stato ON rc_descendant_contacts(stato_verifica);
        CREATE INDEX IF NOT EXISTS idx_rc_dcon_email ON rc_descendant_contacts(email);

        -- ─── Contatti istituzionali ────────────────────────────────────────
        CREATE TABLE IF NOT EXISTS rc_institutional_contacts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ente TEXT NOT NULL,
            ministero_amministrazione TEXT,
            dipartimento TEXT,
            direzione_generale TEXT,
            ufficio TEXT,
            archivio TEXT,
            sede TEXT,
            indirizzo TEXT,
            email TEXT,
            pec TEXT,
            telefono TEXT,
            sito_ufficiale TEXT,
            pagina_procedura TEXT,
            referente_nome TEXT,
            referente_cognome TEXT,
            referente_qualifica TEXT,
            referente_telefono_interno TEXT,
            orari TEXT,
            ambito_competenza TEXT,
            territori_competenza TEXT,
            tipi_riconoscimento_gestiti TEXT,
            modalita_preferita_contatto TEXT,
            fonte_recapito TEXT,
            url_fonte_ufficiale TEXT,
            data_ultima_verifica TEXT,
            stato TEXT DEFAULT 'non_verificato',
            note TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            created_by INTEGER
        );
        CREATE INDEX IF NOT EXISTS idx_rc_inst_ente ON rc_institutional_contacts(ente);
        CREATE INDEX IF NOT EXISTS idx_rc_inst_stato ON rc_institutional_contacts(stato);

        -- ─── Pratiche amministrative estese ────────────────────────────────
        CREATE TABLE IF NOT EXISTS rc_practices (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            candidate_id INTEGER NOT NULL,
            recognition_type_id INTEGER,
            descendant_contact_id INTEGER,
            institutional_contact_id INTEGER,
            protocollo TEXT,
            data_invio TEXT,
            modalita_trasmissione TEXT,
            ufficio_assegnatario TEXT,
            responsabile_procedimento TEXT,
            data_apertura TEXT,
            termine_previsto TEXT,
            stato TEXT DEFAULT 'in_preparazione',
            richieste_integrazione TEXT,
            esito TEXT,
            decreto_provvedimento TEXT,
            data_esito TEXT,
            data_consegna_attestato TEXT,
            note_cerimonia TEXT,
            pronto_invio INTEGER DEFAULT 0,
            validato_da_revisore INTEGER DEFAULT 0,
            motivazione_eccezione TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            created_by INTEGER,
            FOREIGN KEY (candidate_id) REFERENCES rc_candidates(id),
            FOREIGN KEY (recognition_type_id) REFERENCES rc_recognition_types(id),
            FOREIGN KEY (descendant_contact_id) REFERENCES rc_descendant_contacts(id),
            FOREIGN KEY (institutional_contact_id) REFERENCES rc_institutional_contacts(id)
        );
        CREATE INDEX IF NOT EXISTS idx_rc_prac_cand ON rc_practices(candidate_id);
        CREATE INDEX IF NOT EXISTS idx_rc_prac_stato ON rc_practices(stato);
        CREATE INDEX IF NOT EXISTS idx_rc_prac_proto ON rc_practices(protocollo);

        -- ─── Documenti di pratica (esteso) ─────────────────────────────────
        CREATE TABLE IF NOT EXISTS rc_practice_documents (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            practice_id INTEGER,
            candidate_id INTEGER,
            descendant_contact_id INTEGER,
            titolo TEXT NOT NULL,
            descrizione TEXT,
            categoria_documentale TEXT,
            filename_originale TEXT NOT NULL,
            file_path TEXT NOT NULL,
            formato_mime TEXT,
            dimensione INTEGER,
            numero_pagine INTEGER,
            checksum TEXT,
            autore_caricamento TEXT,
            data_caricamento TEXT NOT NULL,
            data_documento TEXT,
            mittente TEXT,
            destinatario TEXT,
            ente_produttore TEXT,
            fonte TEXT,
            segnatura TEXT,
            protocollo TEXT,
            livello_riservatezza TEXT DEFAULT 'operatore',
            stato_verifica TEXT DEFAULT 'non_verificata',
            versione INTEGER DEFAULT 1,
            documento_sostituito_id INTEGER,
            scadenza TEXT,
            firma_digitale_rilevata INTEGER DEFAULT 0,
            esito_scansione_antivirus TEXT,
            note TEXT,
            archiviato INTEGER DEFAULT 0,
            ocr_text TEXT,
            ocr_status TEXT DEFAULT 'pending',
            ocr_pages INTEGER,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            created_by INTEGER,
            FOREIGN KEY (practice_id) REFERENCES rc_practices(id),
            FOREIGN KEY (candidate_id) REFERENCES rc_candidates(id),
            FOREIGN KEY (descendant_contact_id) REFERENCES rc_descendant_contacts(id)
        );
        CREATE INDEX IF NOT EXISTS idx_rc_pdoc_prac ON rc_practice_documents(practice_id);
        CREATE INDEX IF NOT EXISTS idx_rc_pdoc_cand ON rc_practice_documents(candidate_id);
        CREATE INDEX IF NOT EXISTS idx_rc_pdoc_cat ON rc_practice_documents(categoria_documentale);

        -- ─── Versioni documenti ─────────────────────────────────────────────
        CREATE TABLE IF NOT EXISTS rc_document_versions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            document_id INTEGER NOT NULL,
            versione INTEGER NOT NULL,
            file_path TEXT NOT NULL,
            checksum TEXT,
            dimensione INTEGER,
            motivazione_sostituzione TEXT,
            sostituito_da TEXT,
            created_at TEXT NOT NULL,
            created_by INTEGER,
            FOREIGN KEY (document_id) REFERENCES rc_practice_documents(id)
        );
        CREATE INDEX IF NOT EXISTS idx_rc_dv_doc ON rc_document_versions(document_id);

        -- ─── Checklist documenti per riconoscimento ─────────────────────────
        CREATE TABLE IF NOT EXISTS rc_document_checklists (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            recognition_type_id INTEGER,
            practice_id INTEGER,
            nome_documento TEXT NOT NULL,
            descrizione TEXT,
            obbligatorietà TEXT DEFAULT 'obbligatorio',
            soggetto_produttore TEXT,
            ente_reperizione TEXT,
            modello_disponibile TEXT,
            stato_documento TEXT DEFAULT 'mancante',
            motivazione_invalidita TEXT,
            data_richiesta TEXT,
            scadenza TEXT,
            operatore_responsabile TEXT,
            documento_collegato_id INTEGER,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            FOREIGN KEY (recognition_type_id) REFERENCES rc_recognition_types(id),
            FOREIGN KEY (practice_id) REFERENCES rc_practices(id),
            FOREIGN KEY (documento_collegato_id) REFERENCES rc_practice_documents(id)
        );
        CREATE INDEX IF NOT EXISTS idx_rc_chk_prac ON rc_document_checklists(practice_id);
        CREATE INDEX IF NOT EXISTS idx_rc_chk_rt ON rc_document_checklists(recognition_type_id);

        -- ─── Comunicazioni ──────────────────────────────────────────────────
        CREATE TABLE IF NOT EXISTS rc_communications (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            candidate_id INTEGER,
            descendant_contact_id INTEGER,
            practice_id INTEGER,
            institutional_contact_id INTEGER,
            document_id INTEGER,
            thread_id TEXT,
            parent_communication_id INTEGER,
            tipo TEXT NOT NULL,
            direzione TEXT NOT NULL,
            mittente TEXT,
            destinatari TEXT,
            copia_conoscenza TEXT,
            oggetto TEXT,
            contenuto TEXT,
            allegati TEXT,
            data_ora_effettiva TEXT,
            data_ora_registrazione TEXT NOT NULL,
            operatore TEXT,
            stato TEXT DEFAULT 'bozza',
            ricevuta_consegna TEXT,
            protocollo TEXT,
            risposta_attesa INTEGER DEFAULT 0,
            data_entro_rispondere TEXT,
            esito TEXT,
            note TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            created_by INTEGER,
            FOREIGN KEY (candidate_id) REFERENCES rc_candidates(id),
            FOREIGN KEY (descendant_contact_id) REFERENCES rc_descendant_contacts(id),
            FOREIGN KEY (practice_id) REFERENCES rc_practices(id),
            FOREIGN KEY (institutional_contact_id) REFERENCES rc_institutional_contacts(id),
            FOREIGN KEY (document_id) REFERENCES rc_practice_documents(id),
            FOREIGN KEY (parent_communication_id) REFERENCES rc_communications(id)
        );
        CREATE INDEX IF NOT EXISTS idx_rc_comm_cand ON rc_communications(candidate_id);
        CREATE INDEX IF NOT EXISTS idx_rc_comm_prac ON rc_communications(practice_id);
        CREATE INDEX IF NOT EXISTS idx_rc_comm_thread ON rc_communications(thread_id);
        CREATE INDEX IF NOT EXISTS idx_rc_comm_stato ON rc_communications(stato);

        -- ─── Scadenze pratiche ──────────────────────────────────────────────
        CREATE TABLE IF NOT EXISTS rc_practice_deadlines (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            practice_id INTEGER,
            candidate_id INTEGER,
            tipo_scadenza TEXT NOT NULL,
            data_scadenza TEXT NOT NULL,
            descrizione TEXT,
            promemoria_inviato INTEGER DEFAULT 0,
            risolta INTEGER DEFAULT 0,
            data_risoluzione TEXT,
            note TEXT,
            created_at TEXT NOT NULL,
            created_by INTEGER,
            FOREIGN KEY (practice_id) REFERENCES rc_practices(id),
            FOREIGN KEY (candidate_id) REFERENCES rc_candidates(id)
        );
        CREATE INDEX IF NOT EXISTS idx_rc_dl_prac ON rc_practice_deadlines(practice_id);
        CREATE INDEX IF NOT EXISTS idx_rc_dl_data ON rc_practice_deadlines(data_scadenza);

        -- ─── Pacchetti per discendenti ──────────────────────────────────────
        CREATE TABLE IF NOT EXISTS rc_descendant_packages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            candidate_id INTEGER NOT NULL,
            descendant_contact_id INTEGER,
            practice_id INTEGER,
            versione INTEGER DEFAULT 1,
            file_path TEXT NOT NULL,
            checksum TEXT,
            dimensione INTEGER,
            documenti_inclusi TEXT,
            documenti_esclusi TEXT,
            dati_personali_presenti TEXT,
            livello_riservatezza TEXT,
            approvatore TEXT,
            data_generazione TEXT NOT NULL,
            token_condivisione TEXT UNIQUE,
            token_scadenza TEXT,
            created_at TEXT NOT NULL,
            created_by INTEGER,
            FOREIGN KEY (candidate_id) REFERENCES rc_candidates(id),
            FOREIGN KEY (descendant_contact_id) REFERENCES rc_descendant_contacts(id),
            FOREIGN KEY (practice_id) REFERENCES rc_practices(id)
        );
        CREATE INDEX IF NOT EXISTS idx_rc_pkg_cand ON rc_descendant_packages(candidate_id);
        CREATE INDEX IF NOT EXISTS idx_rc_pkg_token ON rc_descendant_packages(token_condivisione);
    """)

    # Migrazione per DB esistenti: aggiungi nuove colonne se mancanti
    _migrate_assessment_columns(conn)

    # ── Compliance tables ──────────────────────────────────────────────
    conn.executescript("""
    CREATE TABLE IF NOT EXISTS source_policies (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        provider TEXT NOT NULL,
        domain TEXT NOT NULL,
        source_name TEXT NOT NULL,
        terms_url TEXT,
        privacy_url TEXT,
        robots_url TEXT,
        archive_regulation_url TEXT,
        metadata_license TEXT,
        digital_object_license TEXT,
        commercial_use_allowed INTEGER DEFAULT 0,
        automated_access_allowed INTEGER DEFAULT 0,
        metadata_indexing_allowed INTEGER DEFAULT 1,
        document_download_allowed INTEGER DEFAULT 0,
        republication_allowed INTEGER DEFAULT 0,
        attribution_required INTEGER DEFAULT 1,
        required_credit_line TEXT,
        request_contact TEXT,
        policy_status TEXT DEFAULT 'unknown',
        verified_by TEXT,
        verified_at TEXT,
        valid_from TEXT,
        review_due_at TEXT,
        notes TEXT,
        created_at TEXT,
        updated_at TEXT
    );

    CREATE TABLE IF NOT EXISTS compliance_decisions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        source_record_id TEXT,
        digital_object_id TEXT,
        requested_action TEXT NOT NULL,
        decision TEXT NOT NULL,
        policy_id INTEGER,
        rule_code TEXT,
        reason TEXT,
        limitations_json TEXT,
        authorization_id INTEGER,
        decided_by TEXT,
        decision_source TEXT DEFAULT 'automatic_policy',
        created_at TEXT
    );

    CREATE TABLE IF NOT EXISTS compliance_authorizations (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        source_policy_id INTEGER,
        record_id TEXT,
        scope TEXT,
        purpose TEXT,
        granted_by TEXT,
        granted_to TEXT,
        protocol TEXT,
        valid_from TEXT,
        valid_until TEXT,
        limitations TEXT,
        revoked INTEGER DEFAULT 0,
        revoked_at TEXT,
        revoked_by TEXT,
        revoke_reason TEXT,
        created_at TEXT
    );

    CREATE TABLE IF NOT EXISTS compliance_review_queue (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        item_type TEXT NOT NULL,
        record_id TEXT,
        source_policy_id INTEGER,
        reason TEXT,
        priority TEXT DEFAULT 'medium',
        status TEXT DEFAULT 'pending',
        reviewed_by TEXT,
        reviewed_at TEXT,
        decision TEXT,
        motivation TEXT,
        created_at TEXT
    );
    """)
    conn.commit()

    # Migration: add life_status to rc_candidates
    try:
        conn.execute("ALTER TABLE rc_candidates ADD COLUMN life_status TEXT DEFAULT 'deceased'")
    except Exception:
        pass
    conn.commit()
    conn.close()


def _migrate_assessment_columns(conn):
    """Aggiunge le colonne AI a rc_recognition_assessments se non esistono."""
    cols = {r["name"] for r in conn.execute("PRAGMA table_info(rc_recognition_assessments)").fetchall()}
    new_cols = [
        ("processo_logico", "TEXT"),
        ("fonti_consultate", "TEXT"),
        ("percentuale_stimata_concessione", "REAL"),
        ("precedenti_storici", "TEXT"),
        ("fattori_favorevoli", "TEXT"),
        ("fattori_sfavorevoli", "TEXT"),
        ("onorificenze_alternative", "TEXT"),
        ("livello_confidenza", "TEXT DEFAULT 'basso'"),
    ]
    for col_name, col_type in new_cols:
        if col_name not in cols:
            conn.execute(f"ALTER TABLE rc_recognition_assessments ADD COLUMN {col_name} {col_type}")


def seed_recognition_types():
    """Inserisce il catalogo iniziale dei riconoscimenti se vuoto.
    Tutte le voci con procedura_attiva='da_verificare' finché non confermate
    da fonte istituzionale."""
    conn = get_conn()
    count = conn.execute("SELECT COUNT(*) as c FROM rc_recognition_types").fetchone()["c"]
    if count > 0:
        conn.close()
        return
    from datetime import datetime
    now = datetime.now().isoformat()
    types = [
        ("Medaglia d'Oro al Valor Militare", "valor militare",
         "Presidente della Repubblica", "Ministero della Difesa",
         "R.D. 4 novembre 1932 n. 1423 (T.U. delle decorazioni militari)",
         "da_verificare", "da_verificare"),
        ("Medaglia d'Argento al Valor Militare", "valor militare",
         "Presidente della Repubblica", "Ministero della Difesa",
         "R.D. 4 novembre 1932 n. 1423", "da_verificare", "da_verificare"),
        ("Medaglia di Bronzo al Valor Militare", "valor militare",
         "Presidente della Repubblica", "Ministero della Difesa",
         "R.D. 4 novembre 1932 n. 1423", "da_verificare", "da_verificare"),
        ("Croce di Guerra al Valor Militare", "valor militare",
         "Presidente della Repubblica", "Ministero della Difesa",
         "R.D. 4 novembre 1932 n. 1423", "da_verificare", "da_verificare"),
        ("Medaglia d'Oro al Valor Civile", "valor civile",
         "Presidente della Repubblica", "Presidenza del Consiglio",
         "D.P.R. 24 maggio 1949 n. 356", "da_verificare", "da_verificare"),
        ("Medaglia d'Argento al Valor Civile", "valor civile",
         "Presidente della Repubblica", "Presidenza del Consiglio",
         "D.P.R. 24 maggio 1949 n. 356", "da_verificare", "da_verificare"),
        ("Medaglia di Bronzo al Valor Civile", "valor civile",
         "Presidente della Repubblica", "Presidenza del Consiglio",
         "D.P.R. 24 maggio 1949 n. 356", "da_verificare", "da_verificare"),
        ("Croce al Merito di Guerra", "merito di guerra",
         "Presidente della Repubblica", "Ministero della Difesa",
         "R.D. 19 gennaio 1918 n. 205", "da_verificare", "da_verificare"),
        ("Medaglia d'Onore per i cittadini italiani deportati e internati nei lager nazisti e destinati al lavoro coatto",
         "onorificenza speciale", "Presidente della Repubblica",
         "Presidenza del Consiglio - Ministero dell'Interno",
         "L. 22 giugno 2007 n. 96", "da_verificare", "da_verificare"),
        ("Ordine al Merito della Repubblica Italiana (OMRI) - Cavaliere",
         "onorificenza OMRI", "Presidente della Repubblica",
         "Presidenza del Consiglio", "L. 3 marzo 1951 n. 178",
         "da_verificare", "da_verificare"),
        ("Distintivo di Campagna", "distintivo di campagna",
         "Ministero della Difesa", "Ministero della Difesa",
         "da_verificare", "da_verificare", "da_verificare"),
        ("Ricompensa al Valore di Forza Armata", "valore di forza armata",
         "Ministero della Difesa", "Ministero della Difesa",
         "da_verificare", "da_verificare", "da_verificare"),
    ]
    for t in types:
        conn.execute(
            """INSERT INTO rc_recognition_types
               (denominazione, categoria, autorita_concedente, ente_istruttore,
                base_normativa, requisiti, procedura_attiva,
                data_ultimo_aggiornamento, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (t[0], t[1], t[2], t[3], t[4], t[5], t[6], now, now, now),
        )
    conn.commit()
    # Migrations for existing DBs
    try:
        conn.execute("ALTER TABLE rc_practice_documents ADD COLUMN ocr_text TEXT")
    except Exception:
        pass
    try:
        conn.execute("ALTER TABLE rc_practice_documents ADD COLUMN ocr_status TEXT DEFAULT 'pending'")
    except Exception:
        pass
    try:
        conn.execute("ALTER TABLE rc_practice_documents ADD COLUMN ocr_pages INTEGER")
    except Exception:
        pass
    conn.commit()
    conn.close()

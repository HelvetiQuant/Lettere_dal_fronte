-- ============================================================
-- RLS (Row Level Security) Policies per Voci dal Fronte
-- ============================================================

-- Tabelle storiche: lettura pubblica, scrittura solo service_role
-- (dati di ricerca storica, consultazione aperta)

ALTER TABLE IF EXISTS "caduti_albooro" ENABLE ROW LEVEL SECURITY;
CREATE POLICY "public_read_caduti_albooro" ON "caduti_albooro" FOR SELECT USING (true);
CREATE POLICY "service_write_caduti_albooro" ON "caduti_albooro" FOR INSERT WITH CHECK (current_setting('request.jwt.claim.role', true) = 'service_role');
CREATE POLICY "service_update_caduti_albooro" ON "caduti_albooro" FOR UPDATE USING (current_setting('request.jwt.claim.role', true) = 'service_role');
CREATE POLICY "service_delete_caduti_albooro" ON "caduti_albooro" FOR DELETE USING (current_setting('request.jwt.claim.role', true) = 'service_role');

ALTER TABLE IF EXISTS "caduti_bologna" ENABLE ROW LEVEL SECURITY;
CREATE POLICY "public_read_caduti_bologna" ON "caduti_bologna" FOR SELECT USING (true);
CREATE POLICY "service_write_caduti_bologna" ON "caduti_bologna" FOR INSERT WITH CHECK (current_setting('request.jwt.claim.role', true) = 'service_role');
CREATE POLICY "service_update_caduti_bologna" ON "caduti_bologna" FOR UPDATE USING (current_setting('request.jwt.claim.role', true) = 'service_role');
CREATE POLICY "service_delete_caduti_bologna" ON "caduti_bologna" FOR DELETE USING (current_setting('request.jwt.claim.role', true) = 'service_role');

ALTER TABLE IF EXISTS "caduti_cwgc" ENABLE ROW LEVEL SECURITY;
CREATE POLICY "public_read_caduti_cwgc" ON "caduti_cwgc" FOR SELECT USING (true);
CREATE POLICY "service_write_caduti_cwgc" ON "caduti_cwgc" FOR INSERT WITH CHECK (current_setting('request.jwt.claim.role', true) = 'service_role');
CREATE POLICY "service_update_caduti_cwgc" ON "caduti_cwgc" FOR UPDATE USING (current_setting('request.jwt.claim.role', true) = 'service_role');
CREATE POLICY "service_delete_caduti_cwgc" ON "caduti_cwgc" FOR DELETE USING (current_setting('request.jwt.claim.role', true) = 'service_role');

ALTER TABLE IF EXISTS "caduti_francia_ww1" ENABLE ROW LEVEL SECURITY;
CREATE POLICY "public_read_caduti_francia_ww1" ON "caduti_francia_ww1" FOR SELECT USING (true);
CREATE POLICY "service_write_caduti_francia_ww1" ON "caduti_francia_ww1" FOR INSERT WITH CHECK (current_setting('request.jwt.claim.role', true) = 'service_role');
CREATE POLICY "service_update_caduti_francia_ww1" ON "caduti_francia_ww1" FOR UPDATE USING (current_setting('request.jwt.claim.role', true) = 'service_role');
CREATE POLICY "service_delete_caduti_francia_ww1" ON "caduti_francia_ww1" FOR DELETE USING (current_setting('request.jwt.claim.role', true) = 'service_role');

ALTER TABLE IF EXISTS "caduti_ministero" ENABLE ROW LEVEL SECURITY;
CREATE POLICY "public_read_caduti_ministero" ON "caduti_ministero" FOR SELECT USING (true);
CREATE POLICY "service_write_caduti_ministero" ON "caduti_ministero" FOR INSERT WITH CHECK (current_setting('request.jwt.claim.role', true) = 'service_role');
CREATE POLICY "service_update_caduti_ministero" ON "caduti_ministero" FOR UPDATE USING (current_setting('request.jwt.claim.role', true) = 'service_role');
CREATE POLICY "service_delete_caduti_ministero" ON "caduti_ministero" FOR DELETE USING (current_setting('request.jwt.claim.role', true) = 'service_role');

ALTER TABLE IF EXISTS "caduti_sardi" ENABLE ROW LEVEL SECURITY;
CREATE POLICY "public_read_caduti_sardi" ON "caduti_sardi" FOR SELECT USING (true);
CREATE POLICY "service_write_caduti_sardi" ON "caduti_sardi" FOR INSERT WITH CHECK (current_setting('request.jwt.claim.role', true) = 'service_role');
CREATE POLICY "service_update_caduti_sardi" ON "caduti_sardi" FOR UPDATE USING (current_setting('request.jwt.claim.role', true) = 'service_role');
CREATE POLICY "service_delete_caduti_sardi" ON "caduti_sardi" FOR DELETE USING (current_setting('request.jwt.claim.role', true) = 'service_role');

ALTER TABLE IF EXISTS "decorati" ENABLE ROW LEVEL SECURITY;
CREATE POLICY "public_read_decorati" ON "decorati" FOR SELECT USING (true);
CREATE POLICY "service_write_decorati" ON "decorati" FOR INSERT WITH CHECK (current_setting('request.jwt.claim.role', true) = 'service_role');
CREATE POLICY "service_update_decorati" ON "decorati" FOR UPDATE USING (current_setting('request.jwt.claim.role', true) = 'service_role');
CREATE POLICY "service_delete_decorati" ON "decorati" FOR DELETE USING (current_setting('request.jwt.claim.role', true) = 'service_role');

ALTER TABLE IF EXISTS "decorati_nastroazzurro" ENABLE ROW LEVEL SECURITY;
CREATE POLICY "public_read_decorati_nastroazzurro" ON "decorati_nastroazzurro" FOR SELECT USING (true);
CREATE POLICY "service_write_decorati_nastroazzurro" ON "decorati_nastroazzurro" FOR INSERT WITH CHECK (current_setting('request.jwt.claim.role', true) = 'service_role');
CREATE POLICY "service_update_decorati_nastroazzurro" ON "decorati_nastroazzurro" FOR UPDATE USING (current_setting('request.jwt.claim.role', true) = 'service_role');
CREATE POLICY "service_delete_decorati_nastroazzurro" ON "decorati_nastroazzurro" FOR DELETE USING (current_setting('request.jwt.claim.role', true) = 'service_role');

ALTER TABLE IF EXISTS "fondi_archivistici" ENABLE ROW LEVEL SECURITY;
CREATE POLICY "public_read_fondi_archivistici" ON "fondi_archivistici" FOR SELECT USING (true);
CREATE POLICY "service_write_fondi_archivistici" ON "fondi_archivistici" FOR INSERT WITH CHECK (current_setting('request.jwt.claim.role', true) = 'service_role');
CREATE POLICY "service_update_fondi_archivistici" ON "fondi_archivistici" FOR UPDATE USING (current_setting('request.jwt.claim.role', true) = 'service_role');
CREATE POLICY "service_delete_fondi_archivistici" ON "fondi_archivistici" FOR DELETE USING (current_setting('request.jwt.claim.role', true) = 'service_role');

ALTER TABLE IF EXISTS "menzioni" ENABLE ROW LEVEL SECURITY;
CREATE POLICY "public_read_menzioni" ON "menzioni" FOR SELECT USING (true);
CREATE POLICY "service_write_menzioni" ON "menzioni" FOR INSERT WITH CHECK (current_setting('request.jwt.claim.role', true) = 'service_role');
CREATE POLICY "service_update_menzioni" ON "menzioni" FOR UPDATE USING (current_setting('request.jwt.claim.role', true) = 'service_role');
CREATE POLICY "service_delete_menzioni" ON "menzioni" FOR DELETE USING (current_setting('request.jwt.claim.role', true) = 'service_role');

ALTER TABLE IF EXISTS "entita" ENABLE ROW LEVEL SECURITY;
CREATE POLICY "public_read_entita" ON "entita" FOR SELECT USING (true);
CREATE POLICY "service_write_entita" ON "entita" FOR INSERT WITH CHECK (current_setting('request.jwt.claim.role', true) = 'service_role');
CREATE POLICY "service_update_entita" ON "entita" FOR UPDATE USING (current_setting('request.jwt.claim.role', true) = 'service_role');
CREATE POLICY "service_delete_entita" ON "entita" FOR DELETE USING (current_setting('request.jwt.claim.role', true) = 'service_role');

ALTER TABLE IF EXISTS "internati" ENABLE ROW LEVEL SECURITY;
CREATE POLICY "public_read_internati" ON "internati" FOR SELECT USING (true);
CREATE POLICY "service_write_internati" ON "internati" FOR INSERT WITH CHECK (current_setting('request.jwt.claim.role', true) = 'service_role');
CREATE POLICY "service_update_internati" ON "internati" FOR UPDATE USING (current_setting('request.jwt.claim.role', true) = 'service_role');
CREATE POLICY "service_delete_internati" ON "internati" FOR DELETE USING (current_setting('request.jwt.claim.role', true) = 'service_role');

ALTER TABLE IF EXISTS "fonti_indice" ENABLE ROW LEVEL SECURITY;
CREATE POLICY "public_read_fonti_indice" ON "fonti_indice" FOR SELECT USING (true);
CREATE POLICY "service_write_fonti_indice" ON "fonti_indice" FOR INSERT WITH CHECK (current_setting('request.jwt.claim.role', true) = 'service_role');
CREATE POLICY "service_update_fonti_indice" ON "fonti_indice" FOR UPDATE USING (current_setting('request.jwt.claim.role', true) = 'service_role');
CREATE POLICY "service_delete_fonti_indice" ON "fonti_indice" FOR DELETE USING (current_setting('request.jwt.claim.role', true) = 'service_role');

ALTER TABLE IF EXISTS "fonti_narrative" ENABLE ROW LEVEL SECURITY;
CREATE POLICY "public_read_fonti_narrative" ON "fonti_narrative" FOR SELECT USING (true);
CREATE POLICY "service_write_fonti_narrative" ON "fonti_narrative" FOR INSERT WITH CHECK (current_setting('request.jwt.claim.role', true) = 'service_role');
CREATE POLICY "service_update_fonti_narrative" ON "fonti_narrative" FOR UPDATE USING (current_setting('request.jwt.claim.role', true) = 'service_role');
CREATE POLICY "service_delete_fonti_narrative" ON "fonti_narrative" FOR DELETE USING (current_setting('request.jwt.claim.role', true) = 'service_role');

ALTER TABLE IF EXISTS "eventi_1gm" ENABLE ROW LEVEL SECURITY;
CREATE POLICY "public_read_eventi_1gm" ON "eventi_1gm" FOR SELECT USING (true);
CREATE POLICY "service_write_eventi_1gm" ON "eventi_1gm" FOR INSERT WITH CHECK (current_setting('request.jwt.claim.role', true) = 'service_role');
CREATE POLICY "service_update_eventi_1gm" ON "eventi_1gm" FOR UPDATE USING (current_setting('request.jwt.claim.role', true) = 'service_role');
CREATE POLICY "service_delete_eventi_1gm" ON "eventi_1gm" FOR DELETE USING (current_setting('request.jwt.claim.role', true) = 'service_role');

ALTER TABLE IF EXISTS "event_aliases" ENABLE ROW LEVEL SECURITY;
CREATE POLICY "public_read_event_aliases" ON "event_aliases" FOR SELECT USING (true);
CREATE POLICY "service_write_event_aliases" ON "event_aliases" FOR INSERT WITH CHECK (current_setting('request.jwt.claim.role', true) = 'service_role');
CREATE POLICY "service_update_event_aliases" ON "event_aliases" FOR UPDATE USING (current_setting('request.jwt.claim.role', true) = 'service_role');
CREATE POLICY "service_delete_event_aliases" ON "event_aliases" FOR DELETE USING (current_setting('request.jwt.claim.role', true) = 'service_role');

ALTER TABLE IF EXISTS "event_links" ENABLE ROW LEVEL SECURITY;
CREATE POLICY "public_read_event_links" ON "event_links" FOR SELECT USING (true);
CREATE POLICY "service_write_event_links" ON "event_links" FOR INSERT WITH CHECK (current_setting('request.jwt.claim.role', true) = 'service_role');
CREATE POLICY "service_update_event_links" ON "event_links" FOR UPDATE USING (current_setting('request.jwt.claim.role', true) = 'service_role');
CREATE POLICY "service_delete_event_links" ON "event_links" FOR DELETE USING (current_setting('request.jwt.claim.role', true) = 'service_role');

ALTER TABLE IF EXISTS "collegamenti" ENABLE ROW LEVEL SECURITY;
CREATE POLICY "public_read_collegamenti" ON "collegamenti" FOR SELECT USING (true);
CREATE POLICY "service_write_collegamenti" ON "collegamenti" FOR INSERT WITH CHECK (current_setting('request.jwt.claim.role', true) = 'service_role');
CREATE POLICY "service_update_collegamenti" ON "collegamenti" FOR UPDATE USING (current_setting('request.jwt.claim.role', true) = 'service_role');
CREATE POLICY "service_delete_collegamenti" ON "collegamenti" FOR DELETE USING (current_setting('request.jwt.claim.role', true) = 'service_role');

ALTER TABLE IF EXISTS "record_links" ENABLE ROW LEVEL SECURITY;
CREATE POLICY "public_read_record_links" ON "record_links" FOR SELECT USING (true);
CREATE POLICY "service_write_record_links" ON "record_links" FOR INSERT WITH CHECK (current_setting('request.jwt.claim.role', true) = 'service_role');
CREATE POLICY "service_update_record_links" ON "record_links" FOR UPDATE USING (current_setting('request.jwt.claim.role', true) = 'service_role');
CREATE POLICY "service_delete_record_links" ON "record_links" FOR DELETE USING (current_setting('request.jwt.claim.role', true) = 'service_role');

ALTER TABLE IF EXISTS "archivio_documenti" ENABLE ROW LEVEL SECURITY;
CREATE POLICY "public_read_archivio_documenti" ON "archivio_documenti" FOR SELECT USING (true);
CREATE POLICY "service_write_archivio_documenti" ON "archivio_documenti" FOR INSERT WITH CHECK (current_setting('request.jwt.claim.role', true) = 'service_role');

ALTER TABLE IF EXISTS "archivio_fonti" ENABLE ROW LEVEL SECURITY;
CREATE POLICY "public_read_archivio_fonti" ON "archivio_fonti" FOR SELECT USING (true);
CREATE POLICY "service_write_archivio_fonti" ON "archivio_fonti" FOR INSERT WITH CHECK (current_setting('request.jwt.claim.role', true) = 'service_role');

-- Tabelle operative / admin: solo service_role
ALTER TABLE IF EXISTS "api_usage" ENABLE ROW LEVEL SECURITY;
CREATE POLICY "service_only_api_usage" ON "api_usage" FOR ALL USING (current_setting('request.jwt.claim.role', true) = 'service_role');

ALTER TABLE IF EXISTS "ai_providers" ENABLE ROW LEVEL SECURITY;
CREATE POLICY "service_only_ai_providers" ON "ai_providers" FOR ALL USING (current_setting('request.jwt.claim.role', true) = 'service_role');

ALTER TABLE IF EXISTS "ai_models" ENABLE ROW LEVEL SECURITY;
CREATE POLICY "service_only_ai_models" ON "ai_models" FOR ALL USING (current_setting('request.jwt.claim.role', true) = 'service_role');

ALTER TABLE IF EXISTS "ai_routing_policies" ENABLE ROW LEVEL SECURITY;
CREATE POLICY "service_only_ai_routing_policies" ON "ai_routing_policies" FOR ALL USING (current_setting('request.jwt.claim.role', true) = 'service_role');

ALTER TABLE IF EXISTS "ai_task_runs" ENABLE ROW LEVEL SECURITY;
CREATE POLICY "service_only_ai_task_runs" ON "ai_task_runs" FOR ALL USING (current_setting('request.jwt.claim.role', true) = 'service_role');

ALTER TABLE IF EXISTS "ai_usage_ledger" ENABLE ROW LEVEL SECURITY;
CREATE POLICY "service_only_ai_usage_ledger" ON "ai_usage_ledger" FOR ALL USING (current_setting('request.jwt.claim.role', true) = 'service_role');

ALTER TABLE IF EXISTS "ai_ricerche" ENABLE ROW LEVEL SECURITY;
CREATE POLICY "service_only_ai_ricerche" ON "ai_ricerche" FOR ALL USING (current_setting('request.jwt.claim.role', true) = 'service_role');

ALTER TABLE IF EXISTS "source_policies" ENABLE ROW LEVEL SECURITY;
CREATE POLICY "service_only_source_policies" ON "source_policies" FOR ALL USING (current_setting('request.jwt.claim.role', true) = 'service_role');

ALTER TABLE IF EXISTS "compliance_authorizations" ENABLE ROW LEVEL SECURITY;
CREATE POLICY "service_only_compliance_authorizations" ON "compliance_authorizations" FOR ALL USING (current_setting('request.jwt.claim.role', true) = 'service_role');

ALTER TABLE IF EXISTS "compliance_decisions" ENABLE ROW LEVEL SECURITY;
CREATE POLICY "service_only_compliance_decisions" ON "compliance_decisions" FOR ALL USING (current_setting('request.jwt.claim.role', true) = 'service_role');

ALTER TABLE IF EXISTS "compliance_review_queue" ENABLE ROW LEVEL SECURITY;
CREATE POLICY "service_only_compliance_review_queue" ON "compliance_review_queue" FOR ALL USING (current_setting('request.jwt.claim.role', true) = 'service_role');

ALTER TABLE IF EXISTS "graph_nodes" ENABLE ROW LEVEL SECURITY;
CREATE POLICY "service_only_graph_nodes" ON "graph_nodes" FOR ALL USING (current_setting('request.jwt.claim.role', true) = 'service_role');

ALTER TABLE IF EXISTS "graph_edges" ENABLE ROW LEVEL SECURITY;
CREATE POLICY "service_only_graph_edges" ON "graph_edges" FOR ALL USING (current_setting('request.jwt.claim.role', true) = 'service_role');

ALTER TABLE IF EXISTS "graph_edge_reviews" ENABLE ROW LEVEL SECURITY;
CREATE POLICY "service_only_graph_edge_reviews" ON "graph_edge_reviews" FOR ALL USING (current_setting('request.jwt.claim.role', true) = 'service_role');

ALTER TABLE IF EXISTS "graph_pipeline_runs" ENABLE ROW LEVEL SECURITY;
CREATE POLICY "service_only_graph_pipeline_runs" ON "graph_pipeline_runs" FOR ALL USING (current_setting('request.jwt.claim.role', true) = 'service_role');

ALTER TABLE IF EXISTS "graph_integrity_issues" ENABLE ROW LEVEL SECURITY;
CREATE POLICY "service_only_graph_integrity_issues" ON "graph_integrity_issues" FOR ALL USING (current_setting('request.jwt.claim.role', true) = 'service_role');

-- Tabelle OCR/lettere: autenticati possono leggere, service scrive
ALTER TABLE IF EXISTS "ocr_lettere" ENABLE ROW LEVEL SECURITY;
CREATE POLICY "public_read_ocr_lettere" ON "ocr_lettere" FOR SELECT USING (true);
CREATE POLICY "service_write_ocr_lettere" ON "ocr_lettere" FOR INSERT WITH CHECK (current_setting('request.jwt.claim.role', true) = 'service_role');
CREATE POLICY "service_update_ocr_lettere" ON "ocr_lettere" FOR UPDATE USING (current_setting('request.jwt.claim.role', true) = 'service_role');

ALTER TABLE IF EXISTS "lettere_personali" ENABLE ROW LEVEL SECURITY;
CREATE POLICY "public_read_lettere_personali" ON "lettere_personali" FOR SELECT USING (true);
CREATE POLICY "service_write_lettere_personali" ON "lettere_personali" FOR INSERT WITH CHECK (current_setting('request.jwt.claim.role', true) = 'service_role');
CREATE POLICY "service_update_lettere_personali" ON "lettere_personali" FOR UPDATE USING (current_setting('request.jwt.claim.role', true) = 'service_role');

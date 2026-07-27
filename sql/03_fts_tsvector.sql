-- FTS (Full-Text Search) via tsvector per tabella entita
ALTER TABLE "entita" ADD COLUMN IF NOT EXISTS search_vector tsvector;

CREATE INDEX IF NOT EXISTS idx_entita_search_vector
ON "entita" USING GIN(search_vector);

-- Trigger per auto-update del tsvector
CREATE OR REPLACE FUNCTION entita_search_vector_update() RETURNS trigger AS $$
BEGIN
    NEW.search_vector := to_tsvector('simple',
        coalesce(NEW.valore, '') || ' ' ||
        coalesce(NEW.cognome, '') || ' ' ||
        coalesce(NEW.nome, '') || ' ' ||
        coalesce(NEW.luogo, '') || ' ' ||
        coalesce(NEW.contesto, ''));
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_entita_search_vector ON "entita";
CREATE TRIGGER trg_entita_search_vector
BEFORE INSERT OR UPDATE ON "entita"
FOR EACH ROW EXECUTE FUNCTION entita_search_vector_update();

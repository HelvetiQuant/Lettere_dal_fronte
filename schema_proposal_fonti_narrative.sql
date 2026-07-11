-- PROPOSTA — Integrazione fonti storiche personali/narrative dal Desktop
-- Non altera schema o dati esistenti. Da eseguire solo dopo approvazione.
-- Fonti coinvolte:
--   - Desktop\ARCHIVIO STORIE\STORIE IMI\  (biografie .odt)
--   - Desktop\ARO\                          (corrispondenza .odt/.docx/.pdf)
--   - Desktop\1945 gaiaschi è libero!\      (foto .jpg)
--   - Desktop\rebancadatiinternatimilitariitaliani\  (riferimento .odt/.pdf)
--   - Desktop\racconti, storie, libro\      (memoriale .pdf)
-- ESCLUSE (come da istruzione): Desktop\DOMANDE RENZI\, Desktop\vaticano\

CREATE TABLE IF NOT EXISTS fonti_narrative (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    sha256 TEXT UNIQUE NOT NULL,
    nome_file TEXT NOT NULL,
    path_locale TEXT NOT NULL,
    formato TEXT NOT NULL CHECK(formato IN ('odt','docx','pdf','jpg','jpeg','tiff','png')),
    tipo_fonte TEXT NOT NULL CHECK(tipo_fonte IN ('biografia','corrispondenza','fotografia','memoriale','riferimento_archivio','altro')),
    archivio TEXT,        -- es. 'Desktop — ARCHIVIO STORIE', 'Desktop — ARO'
    fondo TEXT,           -- sottocartella
    unita_principale TEXT,
    teatro TEXT,
    data_documento TEXT,
    data_inizio TEXT,
    data_fine TEXT,
    autore TEXT,
    soggetti_json TEXT,   -- JSON array [{cognome, nome, note}]
    persone_possibili TEXT,
    titolo TEXT,
    descrizione TEXT,
    testo_ocr TEXT,
    ocr_status TEXT DEFAULT 'pending' CHECK(ocr_status IN ('pending','done','partial','skip_quality','error')),
    access_type TEXT DEFAULT 'locale',
    fetch_status TEXT DEFAULT 'scaricato',
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_fn_tipo_fonte ON fonti_narrative(tipo_fonte);
CREATE INDEX IF NOT EXISTS idx_fn_persone ON fonti_narrative(persone_possibili);
CREATE INDEX IF NOT EXISTS idx_fn_archivio ON fonti_narrative(archivio);
CREATE INDEX IF NOT EXISTS idx_fn_data_documento ON fonti_narrative(data_documento);
CREATE INDEX IF NOT EXISTS idx_fn_ocr_status ON fonti_narrative(ocr_status);

-- Collegamento allo star schema entita/collegamenti (gia esistente).
-- Per ogni persona menzionata verranno creati/aggiornati record in `entita`
-- e un arco in `collegamenti` con tabella_origine='fonti_narrative'.
-- Non servono ulteriori tabelle di linking.

-- Modifiche minime al codice Python previste (solo a seguito approvazione):
-- 1. database.py: estendere search_all() e get_all_records_for_ai() con SELECT su fonti_narrative.
-- 2. database.py: helper import_personal_source(file_path) per hashing, estrazione testo/OCR, insert.
-- 3. templates/index.html: aggiungere 'fonti_narrative' a renderCrossDBLinks/renderSourcesTab.

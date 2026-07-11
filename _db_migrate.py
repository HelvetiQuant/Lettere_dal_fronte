"""
Migrazione DB non distruttiva:
- ALTER TABLE ADD COLUMN (ignora se colonna già esiste)
- CREATE INDEX IF NOT EXISTS (ignora se già esiste)
- PRAGMA cache_size e page_size
Nessun dato viene modificato o cancellato.
"""
from database import get_conn
import time

conn = get_conn()

def add_column(table, col, col_type, default=None):
    try:
        if default is not None:
            conn.execute(f"ALTER TABLE {table} ADD COLUMN {col} {col_type} DEFAULT {default}")
        else:
            conn.execute(f"ALTER TABLE {table} ADD COLUMN {col} {col_type}")
        print(f"  + {table}.{col} ({col_type})")
    except Exception as e:
        if "duplicate column" in str(e).lower():
            print(f"  ~ {table}.{col} già presente, skip")
        else:
            print(f"  ! {table}.{col} ERRORE: {e}")

def add_index(name, table, cols, unique=False):
    u = "UNIQUE " if unique else ""
    try:
        conn.execute(f"CREATE {u}INDEX IF NOT EXISTS {name} ON {table}({cols})")
        print(f"  + INDEX {name} ON {table}({cols})")
    except Exception as e:
        print(f"  ! INDEX {name} ERRORE: {e}")


print("=" * 60)
print("MIGRAZIONE DB — nessun dato verrà cancellato")
print("=" * 60)

# ─── 1. PRAGMA performance ──────────────────────────────────────
print("\n[1] PRAGMA performance")
conn.execute("PRAGMA cache_size = -65536")   # 64 MB cache
conn.execute("PRAGMA temp_store = MEMORY")
conn.execute("PRAGMA mmap_size = 268435456") # 256 MB memory-mapped I/O
print("  cache_size: 64 MB")
print("  temp_store: MEMORY")
print("  mmap_size:  256 MB")

# ─── 2. Indici mancanti ────────────────────────────────────────
print("\n[2] Indici aggiuntivi")

# caduti_cwgc — LIKE non funziona con l'indice standard, serve indice esplicito
add_index("idx_cwgc_cognome_nocase", "caduti_cwgc", "cognome COLLATE NOCASE")
add_index("idx_cwgc_guerra", "caduti_cwgc", "guerra")
add_index("idx_cwgc_data", "caduti_cwgc", "data_morte")
add_index("idx_cwgc_nationality", "caduti_cwgc", "nationality")

# entita — ricerche per valore normalizzato (dedup e lookup)
add_index("idx_entita_norm_tipo", "entita", "valore_normalizzato, tipo")

# collegamenti — GROUP BY + join frequenti
add_index("idx_collegamenti_tab_rec", "collegamenti", "tabella_origine, record_id")

# archivio_fonti — ricerche frequenti per data e segnatura
add_index("idx_af_segnatura", "archivio_fonti", "segnatura")
add_index("idx_af_data_range", "archivio_fonti", "data_inizio, data_fine")

# documenti_nara_catalog
add_index("idx_nara_cat_unit", "documenti_nara_catalog", "unit")
add_index("idx_nara_cat_dates", "documenti_nara_catalog", "dates")

# decorati_nastroazzurro
add_index("idx_nastro_cognome", "decorati_nastroazzurro", "cognome")
add_index("idx_nastro_comune", "decorati_nastroazzurro", "comune_nascita")

# caduti_albooro
add_index("idx_albo_nominativo", "caduti_albooro", "nominativo")

# ─── 3. Nuove colonne — archivio_fonti ────────────────────────
print("\n[3] Nuove colonne archivio_fonti")
add_column("archivio_fonti", "iiif_manifest_url", "TEXT")
add_column("archivio_fonti", "url_catalogo", "TEXT")
add_column("archivio_fonti", "licenza", "TEXT")
add_column("archivio_fonti", "digitale_pubblico", "INTEGER", default=0)
add_column("archivio_fonti", "htr_engine", "TEXT")          # es. Transkribus, eScriptorium
add_column("archivio_fonti", "htr_confidence", "REAL")
add_column("archivio_fonti", "testo_htr", "TEXT")           # testo prodotto da HTR (corsivo)
add_column("archivio_fonti", "richiede_revisione", "INTEGER", default=0)

# ─── 4. Nuove colonne — documenti_nara_t315 ───────────────────
print("\n[4] Nuove colonne documenti_nara_t315")
add_column("documenti_nara_t315", "archivio_fonti_id", "INTEGER")  # FK → archivio_fonti

# ─── 5. Nuove colonne — caduti_cwgc ───────────────────────────
print("\n[5] Nuove colonne caduti_cwgc")
add_column("caduti_cwgc", "unit_detail", "TEXT")    # dettaglio unità (es. company)
add_column("caduti_cwgc", "memorial", "TEXT")       # monumento commemorativo
add_column("caduti_cwgc", "grave_ref", "TEXT")      # riferimento tomba

# ─── 6. Nuove colonne — documenti_nara_catalog ────────────────
print("\n[6] Nuove colonne documenti_nara_catalog")
add_column("documenti_nara_catalog", "pdf_url", "TEXT")
add_column("documenti_nara_catalog", "pdf_scaricato", "INTEGER", default=0)
add_column("documenti_nara_catalog", "archivio_fonti_id", "INTEGER")  # FK → archivio_fonti

# ─── 7. Tabella link NARA → archivio_fonti ────────────────────
print("\n[7] Tabella nara_catalog_files (link metadati→file originali)")
conn.execute("""
    CREATE TABLE IF NOT EXISTS nara_catalog_files (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        nara_catalog_id INTEGER NOT NULL,
        na_id TEXT,
        url_originale TEXT,
        hash_sha256 TEXT,
        archivio_fonti_id INTEGER,
        scaricato INTEGER DEFAULT 0,
        scaricato_il TEXT,
        UNIQUE(nara_catalog_id, url_originale)
    )
""")
conn.execute("CREATE INDEX IF NOT EXISTS idx_ncf_nara ON nara_catalog_files(nara_catalog_id)")
conn.execute("CREATE INDEX IF NOT EXISTS idx_ncf_hash ON nara_catalog_files(hash_sha256)")
print("  + TABLE nara_catalog_files")

conn.commit()

# ─── Verifica finale ──────────────────────────────────────────
print("\n[8] Verifica finale")
total = conn.execute("SELECT COUNT(*) FROM archivio_fonti").fetchone()[0]
print(f"  archivio_fonti: {total:,} record intatti")
total_cwgc = conn.execute("SELECT COUNT(*) FROM caduti_cwgc").fetchone()[0]
print(f"  caduti_cwgc:    {total_cwgc:,} record intatti")
total_ent = conn.execute("SELECT COUNT(*) FROM entita").fetchone()[0]
print(f"  entita:         {total_ent:,} record intatti")
total_col = conn.execute("SELECT COUNT(*) FROM collegamenti").fetchone()[0]
print(f"  collegamenti:   {total_col:,} record intatti")

n_idx = conn.execute("SELECT COUNT(*) FROM sqlite_master WHERE type='index'").fetchone()[0]
print(f"  Totale indici nel DB: {n_idx}")

conn.close()
print("\nMigrazione completata. Nessun dato eliminato.")

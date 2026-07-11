from database import get_conn
conn = get_conn()
conn.execute("CREATE INDEX IF NOT EXISTS idx_nara_cat_dates ON documenti_nara_catalog(inclusive_dates)")
conn.execute("CREATE INDEX IF NOT EXISTS idx_nastro_arma ON decorati_nastroazzurro(arma)")
conn.execute("CREATE INDEX IF NOT EXISTS idx_nastro_tipo_dec ON decorati_nastroazzurro(tipo_decorazione)")
conn.commit()
n = conn.execute("SELECT COUNT(*) FROM sqlite_master WHERE type='index'").fetchone()[0]
print(f"Indici totali: {n}")
conn.close()

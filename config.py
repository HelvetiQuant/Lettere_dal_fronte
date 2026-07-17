IMI_PDFS = {
    "A": "https://archiviodistatobolzano.cultura.gov.it/fileadmin/risorse/PDF/IMI-CAR/IMI_OCR/Elenchi_OCR/ASBZ_CG_174_Elenco_A.pdf",
    "B": "https://archiviodistatobolzano.cultura.gov.it/fileadmin/risorse/PDF/IMI-CAR/IMI_OCR/Elenchi_OCR/ASBZ_CG_203_Elenco_B.pdf",
    "C": "https://archiviodistatobolzano.cultura.gov.it/fileadmin/risorse/PDF/IMI-CAR/IMI_OCR/Elenchi_OCR/ASBZ_CG_204_Elenco_C.pdf",
    "D": "https://archiviodistatobolzano.cultura.gov.it/fileadmin/risorse/PDF/IMI-CAR/IMI_OCR/Elenchi_OCR/ASBZ_CG_234_Elenco_D.pdf",
    "E": "https://archiviodistatobolzano.cultura.gov.it/fileadmin/risorse/PDF/IMI-CAR/IMI_OCR/Elenchi_OCR/ASBZ_CG_204_Elenco_E.pdf",
    "F": "https://archiviodistatobolzano.cultura.gov.it/fileadmin/risorse/PDF/IMI-CAR/IMI_OCR/Elenchi_OCR/ASBZ_CG_210_Elenco_F.pdf",
    "G": "https://archiviodistatobolzano.cultura.gov.it/fileadmin/risorse/PDF/IMI-CAR/IMI_OCR/Elenchi_OCR/ASBZ_CG_210_Elenco_G.pdf",
    "I": "https://archiviodistatobolzano.cultura.gov.it/fileadmin/risorse/PDF/IMI-CAR/IMI_OCR/Elenchi_OCR/ASBZ_CG_217_Elenco_I.pdf",
    "L": "https://archiviodistatobolzano.cultura.gov.it/fileadmin/risorse/PDF/IMI-CAR/IMI_OCR/Elenchi_OCR/ASBZ_CG_217_Elenco_L.pdf",
    "M": "https://archiviodistatobolzano.cultura.gov.it/fileadmin/risorse/PDF/IMI-CAR/IMI_OCR/Elenchi_OCR/ASBZ_CG_216_Elenco_M.pdf",
    "N": "https://archiviodistatobolzano.cultura.gov.it/fileadmin/risorse/PDF/IMI-CAR/IMI_OCR/Elenchi_OCR/ASBZ_CG_204_Elenco_N.pdf",
    "O": "https://archiviodistatobolzano.cultura.gov.it/fileadmin/risorse/PDF/IMI-CAR/IMI_OCR/Elenchi_OCR/ASBZ_CG_204_Elenco_O.pdf",
    "P": "https://archiviodistatobolzano.cultura.gov.it/fileadmin/risorse/PDF/IMI-CAR/IMI_OCR/Elenchi_OCR/ASBZ_CG_204_Elenco_P.pdf",
    "Q": "https://archiviodistatobolzano.cultura.gov.it/fileadmin/risorse/PDF/IMI-CAR/IMI_OCR/Elenchi_OCR/ASBZ_CG_022_Elenco_Q.pdf",
    "R": "https://archiviodistatobolzano.cultura.gov.it/fileadmin/risorse/PDF/IMI-CAR/IMI_OCR/Elenchi_OCR/ASBZ_CG_022_Elenco_R.pdf",
    "S": "https://archiviodistatobolzano.cultura.gov.it/fileadmin/risorse/PDF/IMI-CAR/IMI_OCR/Elenchi_OCR/ASBZ_CG_022_Elenco_S.pdf",
    "T": "https://archiviodistatobolzano.cultura.gov.it/fileadmin/risorse/PDF/IMI-CAR/IMI_OCR/Elenchi_OCR/ASBZ_CG_022_Elenco_T.pdf",
    "U": "https://archiviodistatobolzano.cultura.gov.it/fileadmin/risorse/PDF/IMI-CAR/IMI_OCR/Elenchi_OCR/ASBZ_CG_022_Elenco_U.pdf",
    "V": "https://archiviodistatobolzano.cultura.gov.it/fileadmin/risorse/PDF/IMI-CAR/IMI_OCR/Elenchi_OCR/ASBZ_CG_022_Elenco_V.pdf",
    "Z": "https://archiviodistatobolzano.cultura.gov.it/fileadmin/risorse/PDF/IMI-CAR/IMI_OCR/Elenchi_OCR/ASBZ_CG_022_Elenco_Z.pdf",
}

COLUMNS = [
    "cognome",
    "nome",
    "data_nascita",
    "luogo_nascita",
    "residenza",
    "grado",
    "luogo_cattura",
    "data_cattura",
    "luogo_internamento",
    "matricola",
    "arbeitskommando",
    "mansione",
    "sorte",
    "data",
    "documenti",
]

# ─── Scraping configuration ──────────────────────────────────────────────────
# These settings govern the external-source scraper (scraper_service.py).
# fonti_risorse is a METADATA-ONLY catalog: it stores URLs and descriptive
# metadata, never copyrighted content (no full text, no PDFs, no full-res images).

SCRAPER_USER_AGENT = "imi_extractor/1.0 (historical-research; +https://github.com/imi-extractor)"

# Max HTTP requests per minute per domain (rate limiting)
SCRAPER_MAX_REQUESTS_PER_MINUTE = 10

# HTTP timeout in seconds for fetch operations
SCRAPER_TIMEOUT_SECONDS = 20

# TTL for scraping: re-scrape a source if last_checked_at is older than this (days)
SCRAPER_TTL_DAYS = 7

# Max bytes to read from an HTML page (safety limit, prevents memory exhaustion)
SCRAPER_MAX_HTML_BYTES = 2 * 1024 * 1024  # 2 MB

# Domains explicitly allowed for scraping (others require manual approval)
SCRAPER_ALLOWED_DOMAINS = [
    "cadutigrandeguerra.it",
    "www.difesa.it",
    "www.cwgc.org",
    "memoiredeshommes.sga.defense.gouv.fr",
    "www.archiviodistatobolzano.cultura.gov.it",
    "www.istoreco.it",
    "www.nastroazzurro.org",
    "www.anpi.it",
    "www.ussme.gov.it",
    "www.bundesarchiv.de",
    "discovery.nationalarchives.gov.uk",
    "catalog.archives.gov",
]

"""Master test per il modulo fonti_risorse — scraping live fonti esterne.

Covers:
  - config.py scraper settings
  - database.py CRUD + constraints + indici
  - scraper_service.py: HTML parsing, metadati, pipeline, robots.txt, rate limiting, allowlist
  - search_service.py: integrazione entita' ↔ fonti_risorse
  - app.py: API FastAPI endpoint
  - security: copyright, no binary, robots.txt, allowlist
  - integration: end-to-end pipeline
"""
import sqlite3
import pytest
from datetime import datetime, timedelta
from unittest.mock import patch, MagicMock

# ─── Config ──────────────────────────────────────────────────────────────────
from config import (
    SCRAPER_USER_AGENT,
    SCRAPER_MAX_REQUESTS_PER_MINUTE,
    SCRAPER_TIMEOUT_SECONDS,
    SCRAPER_TTL_DAYS,
    SCRAPER_MAX_HTML_BYTES,
    SCRAPER_ALLOWED_DOMAINS,
)

# ─── Scraper ─────────────────────────────────────────────────────────────────
from scraper_service import (
    fetch_html, estrai_risorse, estrai_metadati, scrape_fonte,
    scrape_if_stale, needs_refresh,
    _check_rate_limit, _is_domain_allowed, _check_robots_txt, _parse_robots_txt,
)

# ─── Database CRUD ───────────────────────────────────────────────────────────
from database import (
    insert_fonti_risorsa, get_fonti_risorsa_by_url, update_fonti_risorsa,
    get_fonti_risorse_by_fonte_id, count_fonti_risorse, get_fonti_risorse_stale,
)

# ─── Search service ──────────────────────────────────────────────────────────
from search_service import get_fonti_risorse_for_entity

# ─── Mock utils ──────────────────────────────────────────────────────────────
from tests.utils.mock_db import create_test_db, get_test_conn, cleanup_test_db, insert_test_entity
from tests.utils.mock_http_client import patch_requests_get, MOCK_RESPONSES, MockResponse
from tests.utils.fake_html_sources import (
    ALBO_ORO_HTML, CWGC_HTML, NO_META_HTML, NO_TITLE_HTML,
    CC_LICENSE_HTML, FOOTER_COPYRIGHT_HTML, RELATIVE_URLS_HTML, INVALID_LINKS_HTML,
)
from tests.utils.fake_robots_txt import (
    ROBOTS_ALLOW_ALL, ROBOTS_DISALLOW_ALL, ROBOTS_DISALLOW_PDF, ROBOTS_MALFORMED,
)


# ═══════════════════════════════════════════════════════════════════════════════
# 1. CONFIG
# ═══════════════════════════════════════════════════════════════════════════════

class TestConfig:
    def test_user_agent(self):
        assert SCRAPER_USER_AGENT and "imi_extractor" in SCRAPER_USER_AGENT

    def test_rate_limit(self):
        assert SCRAPER_MAX_REQUESTS_PER_MINUTE == 10

    def test_timeout(self):
        assert SCRAPER_TIMEOUT_SECONDS == 20

    def test_ttl(self):
        assert SCRAPER_TTL_DAYS == 7

    def test_max_html_bytes(self):
        assert SCRAPER_MAX_HTML_BYTES == 2 * 1024 * 1024

    def test_allowed_domains_count(self):
        assert len(SCRAPER_ALLOWED_DOMAINS) == 14

    def test_allowed_domains_known(self):
        for d in ["cadutigrandeguerra.it", "www.cwgc.org", "www.ussme.gov.it"]:
            assert d in SCRAPER_ALLOWED_DOMAINS


# ═══════════════════════════════════════════════════════════════════════════════
# 2. DATABASE CRUD + CONSTRAINTS
# ═══════════════════════════════════════════════════════════════════════════════

class TestDatabaseCRUD:
    @pytest.fixture(autouse=True)
    def setup(self, monkeypatch):
        create_test_db()
        monkeypatch.setattr("database.get_conn", get_test_conn)

    def teardown_method(self):
        cleanup_test_db()

    def test_insert_returns_id(self):
        rid = insert_fonti_risorsa({"url_pagina": "https://t.com/a", "titolo": "A"})
        assert rid > 0

    def test_get_by_url(self):
        insert_fonti_risorsa({"url_pagina": "https://t.com/b", "titolo": "B", "licenza": "CC-BY"})
        r = get_fonti_risorsa_by_url("https://t.com/b")
        assert r["titolo"] == "B" and r["licenza"] == "CC-BY"

    def test_get_by_url_not_found(self):
        assert get_fonti_risorsa_by_url("https://no.com") is None

    def test_update_merge_non_destructive(self):
        rid = insert_fonti_risorsa({"url_pagina": "https://t.com/c", "titolo": "Orig", "lingua": "it"})
        update_fonti_risorsa(rid, {"titolo": "New"})
        r = get_fonti_risorsa_by_url("https://t.com/c")
        assert r["titolo"] == "New" and r["lingua"] == "it"

    def test_update_nonexistent(self):
        assert update_fonti_risorsa(99999, {"titolo": "X"}) is False

    def test_update_refreshes_last_checked(self):
        rid = insert_fonti_risorsa({"url_pagina": "https://t.com/d"})
        old = get_fonti_risorsa_by_url("https://t.com/d")["last_checked_at"]
        update_fonti_risorsa(rid, {"titolo": "N"})
        assert get_fonti_risorsa_by_url("https://t.com/d")["last_checked_at"] >= old

    def test_get_by_fonte_id(self):
        insert_fonti_risorsa({"fonte_id": 5, "url_pagina": "https://t.com/e"})
        insert_fonti_risorsa({"fonte_id": 5, "url_pagina": "https://t.com/f"})
        insert_fonti_risorsa({"fonte_id": 6, "url_pagina": "https://t.com/g"})
        assert len(get_fonti_risorse_by_fonte_id(5)) == 2

    def test_count(self):
        assert count_fonti_risorse() == 0
        insert_fonti_risorsa({"url_pagina": "https://t.com/h"})
        assert count_fonti_risorse() == 1

    def test_stale(self):
        old = (datetime.now() - timedelta(days=30)).isoformat()
        conn = get_test_conn()
        conn.execute(
            "INSERT INTO fonti_risorse (url_pagina, first_seen_at, last_checked_at, stato) VALUES (?,?,?, 'valido')",
            ("https://t.com/stale", old, old)
        )
        conn.commit()
        conn.close()
        insert_fonti_risorsa({"url_pagina": "https://t.com/fresh"})
        stale = get_fonti_risorse_stale(7)
        assert len(stale) == 1 and stale[0]["url_pagina"] == "https://t.com/stale"


class TestDatabaseConstraints:
    @pytest.fixture(autouse=True)
    def setup(self, monkeypatch):
        create_test_db()
        monkeypatch.setattr("database.get_conn", get_test_conn)

    def teardown_method(self):
        cleanup_test_db()

    def test_url_unique(self):
        insert_fonti_risorsa({"url_pagina": "https://t.com/dup"})
        with pytest.raises(sqlite3.IntegrityError):
            insert_fonti_risorsa({"url_pagina": "https://t.com/dup"})

    def test_no_blob_columns(self):
        conn = get_test_conn()
        types = [d[2] for d in conn.execute("PRAGMA table_info(fonti_risorse)").fetchall()]
        conn.close()
        assert "BLOB" not in types and "blob" not in [t.lower() for t in types]

    def test_indexes(self):
        conn = get_test_conn()
        idx = [d[1] for d in conn.execute("PRAGMA index_list(fonti_risorse)").fetchall()]
        conn.close()
        assert "idx_fonti_risorse_fonte_id" in idx
        assert "idx_fonti_risorse_url" in idx
        assert "idx_fonti_risorse_stato" in idx

    def test_default_stato(self):
        insert_fonti_risorsa({"url_pagina": "https://t.com/def"})
        assert get_fonti_risorsa_by_url("https://t.com/def")["stato"] == "non_verificato"

    def test_default_licenza(self):
        insert_fonti_risorsa({"url_pagina": "https://t.com/nolic"})
        assert get_fonti_risorsa_by_url("https://t.com/nolic")["licenza"] == "tutti i diritti riservati"


# ═══════════════════════════════════════════════════════════════════════════════
# 3. SCRAPER — HTML PARSING
# ═══════════════════════════════════════════════════════════════════════════════

class TestScraperHTML:
    def test_page_itself_is_resource(self):
        r = estrai_risorse(ALBO_ORO_HTML, "https://cadutigrandeguerra.it/test")
        assert r[0]["tipo"] == "pagina"

    def test_extracts_pdf(self):
        r = estrai_risorse(ALBO_ORO_HTML, "https://cadutigrandeguerra.it/test")
        assert any(x["tipo"] == "pdf" for x in r)

    def test_extracts_images(self):
        r = estrai_risorse(ALBO_ORO_HTML, "https://cadutigrandeguerra.it/test")
        imgs = [x for x in r if x["tipo"] == "immagine"]
        assert len(imgs) >= 2

    def test_dedup(self):
        html = '<html><body><a href="/d.pdf">A</a><a href="/d.pdf">B</a><img src="/i.png"><img src="/i.png"></body></html>'
        urls = [x["url_pagina"] for x in estrai_risorse(html, "https://t.com")]
        assert len(urls) == len(set(urls))

    def test_relative_urls(self):
        r = estrai_risorse(RELATIVE_URLS_HTML, "https://cadutigrandeguerra.it/dir/page")
        pdfs = [x for x in r if x["tipo"] == "pdf"]
        assert len(pdfs) == 1 and pdfs[0]["url_documento"].startswith("https://cadutigrandeguerra.it/")

    def test_ignores_non_http(self):
        r = estrai_risorse(INVALID_LINKS_HTML, "https://t.com")
        urls = [x["url_pagina"] for x in r]
        assert not any("javascript:" in u or "mailto:" in u for u in urls)

    def test_empty_html(self):
        r = estrai_risorse("", "https://t.com")
        assert len(r) == 1 and r[0]["tipo"] == "pagina"


# ═══════════════════════════════════════════════════════════════════════════════
# 4. SCRAPER — METADATA
# ═══════════════════════════════════════════════════════════════════════════════

class TestScraperMetadata:
    def test_title_from_title_tag(self):
        m = estrai_metadati("https://cadutigrandeguerra.it/test", html_full=ALBO_ORO_HTML)
        assert m["titolo"] == "Albo d'Oro dei Caduti della Grande Guerra"

    def test_title_from_og(self):
        m = estrai_metadati("https://t.com", html_full='<html><meta property="og:title" content="OG"></html>')
        assert m["titolo"] == "OG"

    def test_title_from_h1(self):
        m = estrai_metadati("https://t.com", html_full="<html><body><h1>H1T</h1></body></html>")
        assert m["titolo"] == "H1T"

    def test_title_none(self):
        m = estrai_metadati("https://t.com", html_full=NO_TITLE_HTML)
        assert m["titolo"] is None

    def test_author(self):
        m = estrai_metadati("https://cadutigrandeguerra.it/test", html_full=ALBO_ORO_HTML)
        assert m["autore"] == "Ministero della Difesa"

    def test_ente_from_domain(self):
        m = estrai_metadati("https://www.cwgc.org/test", html_full=CWGC_HTML)
        assert "Commonwealth War Graves" in m["ente_titolare"]

    def test_ente_unknown_domain(self):
        m = estrai_metadati("https://unknown.com", html_full="<html></html>")
        assert "unknown.com" in m["ente_titolare"]

    def test_data_pubblicazione(self):
        m = estrai_metadati("https://www.cwgc.org/test", html_full=CWGC_HTML)
        assert m["data_pubblicazione"] == "2024-01-15"

    def test_lingua(self):
        m = estrai_metadati("https://cadutigrandeguerra.it/test", html_full=ALBO_ORO_HTML)
        assert m["lingua"] == "it"

    def test_licenza_from_meta(self):
        m = estrai_metadati("https://cadutigrandeguerra.it/test", html_full=ALBO_ORO_HTML)
        assert m["licenza"] == "dominio pubblico"

    def test_licenza_default(self):
        m = estrai_metadati("https://t.com", html_full=NO_META_HTML)
        assert m["licenza"] == "tutti i diritti riservati"

    def test_licenza_cc(self):
        m = estrai_metadati("https://t.com", html_full=CC_LICENSE_HTML)
        assert "CC-BY" in m["licenza"]

    def test_descrizione(self):
        m = estrai_metadati("https://cadutigrandeguerra.it/test", html_full=ALBO_ORO_HTML)
        assert "caduti" in m["descrizione"].lower()

    def test_note_copyright_footer(self):
        m = estrai_metadati("https://t.com", html_full=FOOTER_COPYRIGHT_HTML)
        assert m["note_copyright"] and "©" in m["note_copyright"]

    def test_note_copyright_none(self):
        m = estrai_metadati("https://t.com", html_full=NO_META_HTML)
        assert m["note_copyright"] is None

    def test_empty_html(self):
        m = estrai_metadati("https://t.com", html_full="")
        assert m["titolo"] is None and m["licenza"] == "tutti i diritti riservati"


# ═══════════════════════════════════════════════════════════════════════════════
# 5. SCRAPER — PIPELINE (fetch, scrape_fonte, TTL)
# ═══════════════════════════════════════════════════════════════════════════════

class TestScraperPipeline:
    @pytest.fixture(autouse=True)
    def setup(self, monkeypatch):
        create_test_db()
        monkeypatch.setattr("database.get_conn", get_test_conn)
        import scraper_service as ss
        ss._domain_timestamps.clear()
        ss._robots_cache.clear()

    def teardown_method(self):
        cleanup_test_db()

    def test_fetch_allowed(self):
        with patch_requests_get():
            assert "Albo d'Oro" in fetch_html("https://cadutigrandeguerra.it/test")

    def test_fetch_disallowed_domain(self):
        with pytest.raises(ValueError, match="Dominio non autorizzato"):
            fetch_html("https://www.evil.com/p")

    def test_fetch_robots_blocked(self):
        with patch("scraper_service.requests.get") as mg:
            def se(url, **kw):
                if url.endswith("/robots.txt"):
                    return MockResponse(ROBOTS_DISALLOW_ALL, status_code=200)
                return MockResponse("<html></html>", status_code=200)
            mg.side_effect = se
            with pytest.raises(ValueError, match="robots.txt"):
                fetch_html("https://cadutigrandeguerra.it/blocked")

    def test_rate_limit(self):
        with patch_requests_get():
            for _ in range(10):
                fetch_html("https://cadutigrandeguerra.it/test")
            with pytest.raises(ValueError, match="Rate limit"):
                fetch_html("https://cadutigrandeguerra.it/test")

    def test_scrape_inserts(self):
        with patch_requests_get():
            s = scrape_fonte({"id": 1, "url_base": "https://cadutigrandeguerra.it/test"})
        assert s["inserted"] > 0 and s["errors"] == 0

    def test_scrape_updates(self):
        with patch_requests_get():
            scrape_fonte({"id": 1, "url_base": "https://cadutigrandeguerra.it/test"})
            s = scrape_fonte({"id": 1, "url_base": "https://cadutigrandeguerra.it/test"})
        assert s["updated"] > 0

    def test_scrape_no_url(self):
        s = scrape_fonte({"id": 1})
        assert s["errors"] == 1 and "Nessun URL" in s["error"]

    def test_needs_refresh_empty(self):
        assert needs_refresh(999) is True

    def test_needs_refresh_stale(self):
        old = (datetime.now() - timedelta(days=30)).isoformat()
        conn = get_test_conn()
        conn.execute(
            "INSERT INTO fonti_risorse (fonte_id, url_pagina, first_seen_at, last_checked_at, stato) VALUES (?,?,?,?, 'valido')",
            (1, "https://t.com/old", old, old)
        )
        conn.commit()
        conn.close()
        assert needs_refresh(1) is True

    def test_needs_refresh_fresh(self):
        insert_fonti_risorsa({"fonte_id": 1, "url_pagina": "https://t.com/fresh"})
        assert needs_refresh(1) is False

    def test_scrape_if_stale_skips(self):
        insert_fonti_risorsa({"fonte_id": 1, "url_pagina": "https://t.com/fresh"})
        assert scrape_if_stale({"id": 1, "url_base": "https://cadutigrandeguerra.it/test"}) is None

    def test_scrape_if_stale_runs(self):
        with patch_requests_get():
            r = scrape_if_stale({"id": 999, "url_base": "https://cadutigrandeguerra.it/test"})
        assert r is not None and r["scraped"] > 0


# ═══════════════════════════════════════════════════════════════════════════════
# 6. SCRAPER — ROBOTS.TXT PARSER
# ═══════════════════════════════════════════════════════════════════════════════

class TestRobotsParser:
    def test_allow_all(self):
        assert len(_parse_robots_txt(ROBOTS_ALLOW_ALL)["disallowed"]) == 0

    def test_disallow_all(self):
        assert "/" in _parse_robots_txt(ROBOTS_DISALLOW_ALL)["disallowed"]

    def test_disallow_pdf(self):
        assert "/documenti/" in _parse_robots_txt(ROBOTS_DISALLOW_PDF)["disallowed"]

    def test_malformed(self):
        assert "/blocked" in _parse_robots_txt(ROBOTS_MALFORMED)["disallowed"]


# ═══════════════════════════════════════════════════════════════════════════════
# 7. SCRAPER — DOMAIN ALLOWLIST
# ═══════════════════════════════════════════════════════════════════════════════

class TestDomainAllowlist:
    def test_allowed(self):
        assert _is_domain_allowed("https://cadutigrandeguerra.it/page")

    def test_subdomain(self):
        assert _is_domain_allowed("https://sub.cadutigrandeguerra.it/page")

    def test_disallowed(self):
        assert not _is_domain_allowed("https://www.evil.com/page")

    def test_facebook_blocked(self):
        assert not _is_domain_allowed("https://www.facebook.com/post")


# ═══════════════════════════════════════════════════════════════════════════════
# 8. SEARCH SERVICE INTEGRATION
# ═══════════════════════════════════════════════════════════════════════════════

class TestSearchServiceIntegration:
    @pytest.fixture(autouse=True)
    def setup(self, monkeypatch):
        create_test_db()
        self.conn = get_test_conn()
        monkeypatch.setattr("database.get_conn", get_test_conn)

    def teardown_method(self):
        cleanup_test_db()

    def test_empty_when_no_collegamenti(self):
        eid = insert_test_entity(self.conn, tipo="persona", valore="Test")
        ent = {"id": eid, "tipo": "persona", "valore": "Test"}
        assert get_fonti_risorse_for_entity(eid, ent, [], self.conn) == []

    def test_returns_risorse_when_linked(self):
        now = datetime.now().isoformat()
        self.conn.execute(
            "INSERT INTO caduti_albooro (id, nominativo, scheda_url, elaborato_il) VALUES (?,?,?,?)",
            (1, "Rossi Mario", "https://cadutigrandeguerra.it/test", now)
        )
        self.conn.execute(
            """INSERT INTO fonti_risorse (fonte_id, url_pagina, titolo, ente_titolare, licenza, stato, first_seen_at, last_checked_at)
               VALUES (?,?,?,?,?, 'valido', ?, ?)""",
            (1, "https://cadutigrandeguerra.it/test", "Test Title", "Ente", "CC-BY", now, now)
        )
        self.conn.commit()
        eid = insert_test_entity(self.conn, tipo="persona", valore="Rossi Mario")
        ent = {"id": eid, "tipo": "persona", "valore": "Rossi Mario"}
        coll = [{"tabella_origine": "caduti_albooro", "record_id": 1}]
        r = get_fonti_risorse_for_entity(eid, ent, coll, self.conn)
        assert len(r) >= 1 and r[0]["titolo"] == "Test Title"

    def test_filter_for_luogo(self):
        now = datetime.now().isoformat()
        self.conn.execute(
            "INSERT INTO caduti_albooro (id, nominativo, scheda_url, elaborato_il) VALUES (?,?,?,?)",
            (1, "Cefalonia", "https://t.com", now)
        )
        for i, t in enumerate(["Cefalonia 1943", "Altra pagina"]):
            self.conn.execute(
                "INSERT INTO fonti_risorse (fonte_id, url_pagina, titolo, stato, first_seen_at, last_checked_at) VALUES (?,?,?, 'valido', ?, ?)",
                (1, f"https://t.com/{i}", t, now, now)
            )
        self.conn.commit()
        eid = insert_test_entity(self.conn, tipo="luogo", valore="Cefalonia")
        ent = {"id": eid, "tipo": "luogo", "valore": "Cefalonia"}
        coll = [{"tabella_origine": "caduti_albooro", "record_id": 1}]
        r = get_fonti_risorse_for_entity(eid, ent, coll, self.conn)
        assert len(r) == 1 and "Cefalonia" in r[0]["titolo"]

    def test_no_protected_content(self):
        now = datetime.now().isoformat()
        self.conn.execute(
            "INSERT INTO caduti_albooro (id, nominativo, scheda_url, elaborato_il) VALUES (?,?,?,?)",
            (1, "Test", "https://t.com", now)
        )
        self.conn.execute(
            "INSERT INTO fonti_risorse (fonte_id, url_pagina, titolo, stato, first_seen_at, last_checked_at) VALUES (?,?,?, 'valido', ?, ?)",
            (1, "https://t.com", "Test", now, now)
        )
        self.conn.commit()
        eid = insert_test_entity(self.conn)
        ent = {"id": eid, "tipo": "persona", "valore": "Test"}
        coll = [{"tabella_origine": "caduti_albooro", "record_id": 1}]
        r = get_fonti_risorse_for_entity(eid, ent, coll, self.conn)
        for item in r:
            assert "testo" not in item and "contenuto" not in item
            assert "pdf_data" not in item and "image_data" not in item


# ═══════════════════════════════════════════════════════════════════════════════
# 9. API FASTAPI
# ═══════════════════════════════════════════════════════════════════════════════

class TestAPI:
    @pytest.fixture(autouse=True)
    def setup(self, monkeypatch):
        create_test_db()
        monkeypatch.setattr("database.get_conn", get_test_conn)
        from fastapi.testclient import TestClient
        from app import app
        self.client = TestClient(app)

    def teardown_method(self):
        cleanup_test_db()

    def test_list_fonti_risorse(self):
        r = self.client.get("/api/fonti-risorse")
        assert r.status_code == 200
        data = r.json()
        assert "risorse" in data and "count" in data

    def test_stats(self):
        r = self.client.get("/api/fonti-risorse/stats")
        assert r.status_code == 200
        data = r.json()
        assert "total" in data and "by_stato" in data

    def test_detail_404(self):
        r = self.client.get("/api/fonti-risorse/99999")
        assert r.status_code == 404

    def test_scrape_no_params_400(self):
        r = self.client.post("/api/fonti-risorse/scrape")
        assert r.status_code == 400

    def test_stats_not_captured_by_id_route(self):
        """Regression: /stats must not be captured by /{risorsa_id}."""
        r = self.client.get("/api/fonti-risorse/stats")
        assert r.status_code == 200
        assert "total" in r.json()

    def test_list_with_fonte_id(self):
        insert_fonti_risorsa({"fonte_id": 42, "url_pagina": "https://t.com/x"})
        r = self.client.get("/api/fonti-risorse?fonte_id=42")
        assert r.status_code == 200 and r.json()["count"] == 1


# ═══════════════════════════════════════════════════════════════════════════════
# 10. SECURITY
# ═══════════════════════════════════════════════════════════════════════════════

class TestSecurity:
    @pytest.fixture(autouse=True)
    def setup(self, monkeypatch):
        create_test_db()
        self.conn = get_test_conn()
        monkeypatch.setattr("database.get_conn", get_test_conn)
        import scraper_service as ss
        ss._robots_cache.clear()

    def teardown_method(self):
        cleanup_test_db()

    def test_no_pdf_binary_stored(self):
        """Verify insert never stores PDF binary data."""
        rid = insert_fonti_risorsa({
            "url_pagina": "https://t.com/doc",
            "url_documento": "https://t.com/doc.pdf",
            "tipo_risorsa": "pdf",
        })
        r = get_fonti_risorsa_by_url("https://t.com/doc")
        # Only URL is stored, not the PDF content
        assert r["url_documento"] == "https://t.com/doc.pdf"
        cols = [d[1] for d in self.conn.execute("PRAGMA table_info(fonti_risorse)").fetchall()]
        assert "contenuto_pdf" not in cols
        assert "file_binario" not in cols
        assert "pdf_data" not in cols

    def test_no_image_binary_stored(self):
        insert_fonti_risorsa({
            "url_pagina": "https://t.com/img",
            "url_documento": "https://t.com/img.jpg",
            "tipo_risorsa": "immagine",
        })
        r = get_fonti_risorsa_by_url("https://t.com/img")
        assert r["url_documento"] == "https://t.com/img.jpg"
        cols = [d[1] for d in self.conn.execute("PRAGMA table_info(fonti_risorse)").fetchall()]
        assert "image_data" not in cols
        assert "immagine_binaria" not in cols

    def test_no_full_text_stored(self):
        cols = [d[1] for d in self.conn.execute("PRAGMA table_info(fonti_risorse)").fetchall()]
        assert "testo" not in cols
        assert "testo_integrale" not in cols
        assert "contenuto" not in cols
        assert "ocr_text" not in cols

    def test_robots_txt_blocks(self):
        with patch("scraper_service.requests.get") as mg:
            def se(url, **kw):
                if url.endswith("/robots.txt"):
                    return MockResponse(ROBOTS_DISALLOW_ALL, status_code=200)
                return MockResponse("<html></html>", status_code=200)
            mg.side_effect = se
            with pytest.raises(ValueError, match="robots.txt"):
                fetch_html("https://cadutigrandeguerra.it/blocked")

    def test_allowlist_blocks_unknown(self):
        with pytest.raises(ValueError, match="Dominio non autorizzato"):
            fetch_html("https://www.evil.com/page")

    def test_allowlist_blocks_social(self):
        with pytest.raises(ValueError, match="Dominio non autorizzato"):
            fetch_html("https://www.facebook.com/post/123")

    def test_default_licenza_restrictive(self):
        """When no license is specified, default is 'tutti i diritti riservati'."""
        insert_fonti_risorsa({"url_pagina": "https://t.com/nolic"})
        r = get_fonti_risorsa_by_url("https://t.com/nolic")
        assert r["licenza"] == "tutti i diritti riservati"


# ═══════════════════════════════════════════════════════════════════════════════
# 11. INTEGRATION END-TO-END
# ═══════════════════════════════════════════════════════════════════════════════

class TestIntegrationE2E:
    @pytest.fixture(autouse=True)
    def setup(self, monkeypatch):
        create_test_db()
        self.conn = get_test_conn()
        monkeypatch.setattr("database.get_conn", get_test_conn)
        import scraper_service as ss
        ss._domain_timestamps.clear()

    def teardown_method(self):
        cleanup_test_db()

    def test_full_pipeline(self):
        """1. scrape_fonte → 2. DB insert → 3. search_service → 4. API."""
        # 1. Scrape
        with patch_requests_get():
            summary = scrape_fonte({"id": 1, "url_base": "https://cadutigrandeguerra.it/test"})
        assert summary["inserted"] > 0

        # 2. Verify DB
        assert count_fonti_risorse() > 0

        # 3. Search service: create entity + collegamento, query
        now = datetime.now().isoformat()
        self.conn.execute(
            "INSERT INTO caduti_albooro (id, nominativo, scheda_url, elaborato_il) VALUES (?,?,?,?)",
            (1, "Albo d'Oro", "https://cadutigrandeguerra.it/test", now)
        )
        self.conn.commit()
        eid = insert_test_entity(self.conn, tipo="persona", valore="Albo d'Oro")
        ent = {"id": eid, "tipo": "persona", "valore": "Albo d'Oro"}
        coll = [{"tabella_origine": "caduti_albooro", "record_id": 1}]
        risorse = get_fonti_risorse_for_entity(eid, ent, coll, self.conn)
        assert len(risorse) >= 1

        # 4. API
        from fastapi.testclient import TestClient
        from app import app
        client = TestClient(app)
        r = client.get("/api/fonti-risorse")
        assert r.status_code == 200
        data = r.json()
        assert data["count"] > 0
        for item in data["risorse"]:
            assert "url_pagina" in item
            assert "titolo" in item
            assert "testo" not in item
            assert "contenuto" not in item

    def test_metadata_correct_after_scrape(self):
        with patch_requests_get():
            scrape_fonte({"id": 1, "url_base": "https://cadutigrandeguerra.it/test"})
        risorse = get_fonti_risorse_by_fonte_id(1)
        assert len(risorse) > 0
        # At least one should have titolo
        assert any(r.get("titolo") for r in risorse)
        # All should have licenza
        assert all(r.get("licenza") for r in risorse)
        # All should have ente_titolare
        assert all(r.get("ente_titolare") for r in risorse)

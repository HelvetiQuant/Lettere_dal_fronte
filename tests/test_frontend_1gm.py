"""Test frontend PRIMA_Guerra (1GM) — server reale, nessun mock.

Test eseguiti contro http://127.0.0.1:8003 (server uvicorn reale).
Verifica: HTML, JS, API, dati reali, isolamento 1GM, externalSources.

PREREQUISITO: server uvicorn attivo su porta 8003.
"""
import requests
import pytest
import re
import json

BASE = "http://127.0.0.1:8003"
FRONTEND_1GM = f"{BASE}/1gm"
JS_1GM = f"{BASE}/voci-data-1gm.js"
API_STATS = f"{BASE}/api/stats/ww1"
API_SEARCH = f"{BASE}/api/search/ww1"
API_FONTI = f"{BASE}/api/fonti-risorse"
API_FONTI_STATS = f"{BASE}/api/fonti-risorse/stats"
API_STATUS = f"{BASE}/api/status"


def get_page(url):
    """Fetch page and return (status_code, text)."""
    r = requests.get(url, timeout=10)
    return r.status_code, r.text


class TestFrontend1GMHTML:
    """Verifica HTML del frontend 1GM servito dal server reale."""

    def test_page_200(self):
        r = requests.get(FRONTEND_1GM, timeout=10)
        assert r.status_code == 200

    def test_has_doctype(self):
        _, html = get_page(FRONTEND_1GM)
        assert "<!DOCTYPE html>" in html

    def test_has_banner_image(self):
        _, html = get_page(FRONTEND_1GM)
        assert "header_banner.png" in html

    def test_has_dossier_section(self):
        _, html = get_page(FRONTEND_1GM)
        assert "isDossier" in html
        assert "hasDossier" in html

    def test_has_sources_tab(self):
        _, html = get_page(FRONTEND_1GM)
        assert "tabSourcesActive" in html
        assert "dossierSourcesTitle" in html

    def test_has_external_sources_section(self):
        """Verifica che la sezione fonti esterne sia presente nel template."""
        _, html = get_page(FRONTEND_1GM)
        assert "hasExternalSources" in html
        assert "externalSources" in html
        assert "Fonti esterne collegate" in html

    def test_external_sources_has_url_pagina_link(self):
        _, html = get_page(FRONTEND_1GM)
        assert "es.url_pagina" in html

    def test_external_sources_has_url_documento_link(self):
        _, html = get_page(FRONTEND_1GM)
        assert "es.url_documento" in html
        assert "es.hasDocument" in html

    def test_external_sources_has_note_copyright(self):
        _, html = get_page(FRONTEND_1GM)
        assert "es.note_copyright" in html

    def test_has_gaps_tab(self):
        _, html = get_page(FRONTEND_1GM)
        assert "tabGapsActive" in html
        assert "dossierGapsTitle" in html

    def test_has_perspectives_tab(self):
        _, html = get_page(FRONTEND_1GM)
        assert "tabPerspectivesActive" in html

    def test_has_search_section(self):
        _, html = get_page(FRONTEND_1GM)
        assert "isSearch" in html
        assert "searchPlaceholder" in html

    def test_has_explore_section(self):
        _, html = get_page(FRONTEND_1GM)
        assert "isExplore" in html

    def test_has_lang_switcher(self):
        _, html = get_page(FRONTEND_1GM)
        assert "langs" in html
        # Verifica 4 lingue: it, en, de, fr
        assert "'it'" in html or '"it"' in html
        assert "'en'" in html or '"en"' in html

    def test_has_events_section(self):
        _, html = get_page(FRONTEND_1GM)
        assert "featuredEvents" in html
        assert "eventsSectionTitle" in html

    def test_has_db_stats(self):
        _, html = get_page(FRONTEND_1GM)
        assert "dbStats" in html

    def test_has_admin_link(self):
        _, html = get_page(FRONTEND_1GM)
        assert "footerAdminLink" in html


class TestFrontend1GMJS:
    """Verifica JS del frontend 1GM (voci-data-1gm.js + funzioni inline nel template HTML)."""

    def test_js_200(self):
        r = requests.get(JS_1GM, timeout=10)
        assert r.status_code == 200

    def test_js_has_load_external_sources(self):
        # loadExternalSources è definita inline nel template HTML, non nel JS module
        _, html = get_page(FRONTEND_1GM)
        assert "loadExternalSources" in html

    def test_js_load_external_sources_fetches_api(self):
        _, html = get_page(FRONTEND_1GM)
        assert "/api/fonti-risorse" in html

    def test_js_open_dossier_calls_load_external(self):
        _, html = get_page(FRONTEND_1GM)
        assert "openDossier" in html
        # Capture the full openDossier function (greedy until next method definition)
        match = re.search(r'openDossier\s*\(kind.*?\)\s*\{.*?loadExternalSources', html, re.DOTALL)
        assert match is not None, "openDossier does not call loadExternalSources"

    def test_js_external_sources_mapping(self):
        _, html = get_page(FRONTEND_1GM)
        assert "titolo" in html
        assert "ente_titolare" in html
        assert "licenza" in html
        assert "tipo_risorsa" in html
        assert "url_pagina" in html
        assert "url_documento" in html
        assert "hasDocument" in html
        assert "note_copyright" in html

    def test_js_has_external_sources_binding(self):
        _, html = get_page(FRONTEND_1GM)
        assert "externalSources" in html
        assert "hasExternalSources" in html
        assert "_externalSources" in html

    def test_js_has_explore_tables(self):
        _, js = get_page(JS_1GM)
        assert "EXPLORE_TABLES" in js or "exploreTables" in js

    def test_js_has_events_data(self):
        _, js = get_page(JS_1GM)
        assert "EVENTS" in js

    def test_js_has_subjects_data(self):
        _, js = get_page(JS_1GM)
        assert "SUBJECTS" in js

    def test_js_has_db_stats(self):
        _, js = get_page(JS_1GM)
        assert "DB_STATS" in js

    def test_js_has_build_source_view(self):
        # buildSourceView è definita inline nel template HTML
        _, html = get_page(FRONTEND_1GM)
        assert "buildSourceView" in html

    def test_js_has_set_dossier_tab(self):
        # setDossierTab è definita inline nel template HTML
        _, html = get_page(FRONTEND_1GM)
        assert "setDossierTab" in html


class TestFrontend1GMIsolation:
    """Verifica isolamento: il frontend 1GM NON deve contenere riferimenti IMI/internati."""

    def test_no_imi_in_html(self):
        _, html = get_page(FRONTEND_1GM)
        # IMI = Internati Militari Italiani (non pertinente per 1GM)
        assert "internati" not in html.lower()
        assert "IMI" not in html

    def test_no_nara_in_js(self):
        _, js = get_page(JS_1GM)
        # NARA = National Archives (riferito a IMI/WW2)
        assert "NARA" not in js
        assert "national archives" not in js.lower()

    def test_no_ww2_references_in_html(self):
        _, html = get_page(FRONTEND_1GM)
        # Il frontend 1GM non deve avere riferimenti espliciti a WW2
        assert "seconda guerra" not in html.lower()
        assert "WW2" not in html
        assert "World War II" not in html

    def test_no_prigionia_in_js(self):
        _, js = get_page(JS_1GM)
        assert "prigionia" not in js.lower()
        assert "prisoners of war" not in js.lower()


class TestFrontend1GMAPIIntegration:
    """Verifica che le API reali rispondano ai dati attesi dal frontend 1GM."""

    def test_api_stats_ww1(self):
        r = requests.get(API_STATS, timeout=10)
        assert r.status_code == 200
        data = r.json()
        assert "caduti" in data
        assert data["caduti"] > 1000000  # Albo d'Oro: ~1M+ caduti

    def test_api_search_ww1(self):
        r = requests.get(f"{API_SEARCH}?q=Rossi&limit=5", timeout=10)
        assert r.status_code == 200
        data = r.json()
        assert "caduti" in data
        assert "decorati" in data
        assert "menzioni" in data

    def test_api_fonti_risorse_list(self):
        r = requests.get(API_FONTI, timeout=10)
        assert r.status_code == 200
        data = r.json()
        assert "risorse" in data
        assert "count" in data
        assert isinstance(data["risorse"], list)

    def test_api_fonti_risorse_stats(self):
        r = requests.get(API_FONTI_STATS, timeout=10)
        assert r.status_code == 200
        data = r.json()
        assert "total" in data
        assert "by_stato" in data
        assert "by_tipo" in data

    def test_api_status(self):
        r = requests.get(API_STATUS, timeout=10)
        assert r.status_code == 200

    def test_api_fonti_risorse_detail_404(self):
        r = requests.get(f"{BASE}/api/fonti-risorse/99999", timeout=10)
        assert r.status_code == 404

    def test_api_fonti_risorse_scrape_no_params_400(self):
        r = requests.post(f"{BASE}/api/fonti-risorse/scrape", timeout=10)
        assert r.status_code == 400

    def test_api_fonti_risorse_stats_not_shadowed(self):
        """Regression: /stats must not be captured by /{risorsa_id}."""
        r = requests.get(API_FONTI_STATS, timeout=10)
        assert r.status_code == 200
        data = r.json()
        assert "total" in data  # Would be 404 if captured by {risorsa_id}


class TestFrontend1GMDataConsistency:
    """Verifica coerenza tra dati API e struttura attesa dal frontend JS."""

    def test_search_returns_expected_keys(self):
        r = requests.get(f"{API_SEARCH}?q=Baracca&limit=3", timeout=10)
        data = r.json()
        expected_keys = {"caduti", "decorati", "menzioni", "documenti", "fonti_narrative"}
        assert expected_keys.issubset(set(data.keys()))

    def test_stats_has_caduti_count(self):
        r = requests.get(API_STATS, timeout=10)
        data = r.json()
        assert "caduti" in data
        assert isinstance(data["caduti"], int)
        assert data["caduti"] > 0

    def test_fonti_risorse_fields_match_js_mapping(self):
        """Verify API response fields match what JS expects in loadExternalSources."""
        r = requests.get(API_FONTI, timeout=10)
        data = r.json()
        if data["risorse"]:
            r0 = data["risorse"][0]
            # Fields used in JS mapping
            expected = {"url_pagina", "url_documento", "titolo", "ente_titolare",
                       "licenza", "tipo_risorsa", "note_copyright"}
            assert expected.issubset(set(r0.keys()))

    def test_fonti_risorse_stats_fields(self):
        r = requests.get(API_FONTI_STATS, timeout=10)
        data = r.json()
        assert "total" in data
        assert "by_stato" in data
        assert "by_tipo" in data
        assert "by_ente" in data
        assert isinstance(data["total"], int)


class TestFrontend1GMAssets:
    """Verifica asset statici referenziati dal frontend 1GM."""

    def test_support_js_loaded(self):
        _, html = get_page(FRONTEND_1GM)
        assert "support.js" in html

    def test_ds_bundle_loaded(self):
        _, html = get_page(FRONTEND_1GM)
        assert "_ds_bundle.js" in html

    def test_styles_css_loaded(self):
        _, html = get_page(FRONTEND_1GM)
        assert "styles.css" in html

    def test_support_js_200(self):
        r = requests.get(f"{BASE}/support.js", timeout=10)
        assert r.status_code == 200

    def test_header_banner_exists(self):
        r = requests.get(f"{BASE}/static/header_banner.png", timeout=10, stream=True)
        assert r.status_code == 200
        r.close()

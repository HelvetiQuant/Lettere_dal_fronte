"""Mock HTTP client for scraper testing without real network calls."""

from unittest.mock import MagicMock, patch
from tests.utils.fake_html_sources import (
    ALBO_ORO_HTML, CWGC_HTML, NO_META_HTML, NO_TITLE_HTML,
    LARGE_HTML, ROBOTS_DISALLOW_HTML, CC_LICENSE_HTML,
    FOOTER_COPYRIGHT_HTML, RELATIVE_URLS_HTML, INVALID_LINKS_HTML,
)
from tests.utils.fake_robots_txt import (
    ROBOTS_ALLOW_ALL, ROBOTS_DISALLOW_ALL, ROBOTS_DISALLOW_PDF,
    ROBOTS_EMPTY, ROBOTS_MALFORMED,
)


# URL -> HTML mapping for mock responses
MOCK_RESPONSES = {
    "https://cadutigrandeguerra.it/test": ALBO_ORO_HTML,
    "https://www.cwgc.org/test": CWGC_HTML,
    "https://www.ussme.gov.it/test": ALBO_ORO_HTML,
    "https://onorcaduti.difesa.it/test": ALBO_ORO_HTML,
    "https://cadutigrandeguerra.it/no-meta": NO_META_HTML,
    "https://cadutigrandeguerra.it/no-title": NO_TITLE_HTML,
    "https://cadutigrandeguerra.it/cc-license": CC_LICENSE_HTML,
    "https://cadutigrandeguerra.it/copyright-footer": FOOTER_COPYRIGHT_HTML,
    "https://cadutigrandeguerra.it/relative": RELATIVE_URLS_HTML,
    "https://cadutigrandeguerra.it/invalid-links": INVALID_LINKS_HTML,
}

# Domain -> robots.txt mapping
MOCK_ROBOTS = {
    "https://cadutigrandeguerra.it": ROBOTS_ALLOW_ALL,
    "https://www.cwgc.org": ROBOTS_ALLOW_ALL,
    "https://www.ussme.gov.it": ROBOTS_DISALLOW_PDF,
    "https://onorcaduti.difesa.it": ROBOTS_ALLOW_ALL,
    "https://blocked-site.com": ROBOTS_DISALLOW_ALL,
}


class MockResponse:
    """Mock HTTP response object compatible with requests.Response."""

    def __init__(self, text, status_code=200, encoding="utf-8", content=None):
        self.text = text
        self.status_code = status_code
        self.encoding = encoding
        self._content = content or text.encode("utf-8")

    def raise_for_status(self):
        if self.status_code >= 400:
            from requests import HTTPError
            raise HTTPError(f"HTTP {self.status_code}")

    def iter_content(self, chunk_size=8192):
        data = self._content
        for i in range(0, len(data), chunk_size):
            yield data[i:i + chunk_size]

def make_mock_get(url_to_html=None, url_to_robots=None):
    """Create a mock function that replaces requests.get.

    Args:
        url_to_html: dict mapping URL -> HTML string
        url_to_robots: dict mapping domain -> robots.txt string
    """
    html_map = url_to_html or MOCK_RESPONSES
    robots_map = url_to_robots or MOCK_ROBOTS

    def mock_get(url, headers=None, timeout=None, stream=None):
        # Check if it's a robots.txt request
        if url.endswith("/robots.txt"):
            for domain, robots_text in robots_map.items():
                if url.startswith(domain):
                    return MockResponse(robots_text)
            return MockResponse(ROBOTS_EMPTY, status_code=404)

        # Regular HTML request
        for mapped_url, html in html_map.items():
            if url == mapped_url or url.startswith(mapped_url):
                return MockResponse(html)

        # Default: return empty page
        return MockResponse("<html><body>Not found</body></html>", status_code=404)

    return mock_get


def patch_requests_get(url_to_html=None, url_to_robots=None):
    """Context manager that patches requests.get with mock."""
    mock_get = make_mock_get(url_to_html, url_to_robots)
    return patch("scraper_service.requests.get", side_effect=mock_get)

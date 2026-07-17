"""Fake domain allowlist for testing."""

from config import SCRAPER_ALLOWED_DOMAINS

ALLOWED_DOMAINS = SCRAPER_ALLOWED_DOMAINS.copy()

# Domains NOT in allowlist (should be blocked)
DISALLOWED_DOMAINS = [
    "www.example.com",
    "evil-site.ru",
    "random-blog.blogspot.com",
    "www.facebook.com",
    "twitter.com",
]

# Test URLs
ALLOWED_URLS = [
    "https://cadutigrandeguerra.it/scheda/123",
    "https://onorcaduti.difesa.it/caduto/456",
    "https://www.cwgc.org/find-records/casualty-details/789",
    "https://www.ussme.gov.it/fondi/archivio",
]

DISALLOWED_URLS = [
    "https://www.example.com/page",
    "https://evil-site.ru/data",
    "https://www.facebook.com/post/123",
]

"""Provider Deutsche Digitale Bibliothek (DDB).

Punto di accesso al patrimonio culturale digitale tedesco, inclusi documenti
del Bundesarchiv relativi alla Prima Guerra Mondiale.

Pattern verificato: /item/{id}
Esempio: https://www.deutsche-digitale-bibliothek.de/item/6NBOK4XF3X5G3H4MYVI6FWV72VUJAAQE
"""
from typing import List

from .base import SourceProvider


class ProviderDDB(SourceProvider):
    name = "ddb"
    display_name = "Deutsche Digitale Bibliothek"
    country = "Germania"
    archive_name = "Deutsche Digitale Bibliothek"
    base_url = "https://www.deutsche-digitale-bibliothek.de"
    authorized_domains = {
        "www.deutsche-digitale-bibliothek.de",
        "deutsche-digitale-bibliothek.de",
    }
    cache_ttl_days = 90

    def search(self, query: str, filters: dict = None) -> List[dict]:
        return []

    def get_metadata(self, record_id: str) -> dict:
        return {"provider": self.name, "catalog_url": self.build_direct_link(record_id)}

    def build_direct_link(self, record_id: str, page: int = None) -> str:
        record_id = record_id.lstrip("/")
        return f"{self.base_url}/item/{record_id}"

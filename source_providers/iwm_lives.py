"""Provider IWM Lives of the First World War.

Pattern verificato: /lifestory/{id}
Esempio: https://livesofthefirstworldwar.iwm.org.uk/lifestory/697514
"""
from typing import List

from .base import SourceProvider


class ProviderIWMLives(SourceProvider):
    name = "iwm_lives"
    display_name = "IWM Lives of the First World War"
    country = "UK"
    archive_name = "IWM Lives"
    base_url = "https://livesofthefirstworldwar.iwm.org.uk"
    authorized_domains = {
        "livesofthefirstworldwar.iwm.org.uk",
        "www.iwm.org.uk",
    }
    cache_ttl_days = 90

    def search(self, query: str, filters: dict = None) -> List[dict]:
        return []

    def get_metadata(self, record_id: str) -> dict:
        return {"provider": self.name, "catalog_url": self.build_direct_link(record_id)}

    def build_direct_link(self, record_id: str, page: int = None) -> str:
        record_id = record_id.lstrip("/")
        return f"{self.base_url}/lifestory/{record_id}"

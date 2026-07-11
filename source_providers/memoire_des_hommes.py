"""Provider Mémoire des Hommes — morti per la Francia WW1/WW2.

Pattern verificato: /fr/ark:/40699/{id}/{token}
Esempio: https://www.memoiredeshommes.sga.defense.gouv.fr/fr/ark:/40699/m005239dfea7f0db/5242bcfce998

search() e get_metadata() restano stub; l'obiettivo immediato e' costruire
link diretti quando gia' in possesso di un ARK MdH.
"""
from typing import List

from .base import SourceProvider


class ProviderMemoireDesHommes(SourceProvider):
    name = "memoiredeshommes"
    display_name = "Mémoire des Hommes"
    country = "Francia"
    archive_name = "Mémoire des Hommes"
    base_url = "https://www.memoiredeshommes.sga.defense.gouv.fr"
    authorized_domains = {
        "www.memoiredeshommes.sga.defense.gouv.fr",
        "memoiredeshommes.sga.defense.gouv.fr",
    }
    cache_ttl_days = 90

    def search(self, query: str, filters: dict = None) -> List[dict]:
        return []

    def get_metadata(self, record_id: str) -> dict:
        return {"provider": self.name, "catalog_url": self.build_direct_link(record_id)}

    def build_direct_link(self, record_id: str, page: int = None) -> str:
        record_id = record_id.lstrip("/")
        return f"{self.base_url}/fr/ark:/40699/{record_id}"

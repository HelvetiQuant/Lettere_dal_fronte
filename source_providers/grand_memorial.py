"""Provider Grand Mémorial — dataset open data francese.

Non e' una fonte di record singoli, ma un dataset aggregato pubblicato su
donnees.culture.gouv.fr. Il link diretto punta alla pagina del dataset.
"""
from typing import List

from .base import SourceProvider


class ProviderGrandMemorial(SourceProvider):
    name = "grand_memorial"
    display_name = "Grand Mémorial"
    country = "Francia"
    archive_name = "Grand Mémorial"
    base_url = "https://donnees.culture.gouv.fr"
    authorized_domains = {
        "donnees.culture.gouv.fr",
    }
    cache_ttl_days = 120

    DATASET_URL = "https://donnees.culture.gouv.fr/explore/dataset/grand-memorial/"

    def search(self, query: str, filters: dict = None) -> List[dict]:
        return []

    def get_metadata(self, record_id: str) -> dict:
        return {"provider": self.name, "catalog_url": self.DATASET_URL}

    def build_direct_link(self, record_id: str, page: int = None) -> str:
        # Grand Mémorial non supporta link a record singoli tramite questo provider.
        # Si fornisce il link al dataset aggregato.
        return self.DATASET_URL

"""Provider CWGC — Commonwealth War Graves Commission.

Caduti del Commonwealth WW1 + WW2. Dati già nel DB locale (caduti_cwgc).
URL diretti a schede commemorative. Nessun IIIF.
"""

from typing import Dict, List, Optional

from database import get_conn
from .base import SourceProvider, _dict_factory


class ProviderCWGC(SourceProvider):
    name = "cwgc"
    display_name = "CWGC — Commonwealth War Graves Commission"
    country = "UK/Commonwealth"
    archive_name = "CWGC"
    base_url = "https://www.cwgc.org"
    authorized_domains = {"www.cwgc.org", "cwgc.org"}
    cache_ttl_days = 120

    def search(self, query: str, filters: dict = None) -> List[dict]:
        conn = get_conn()
        conn.row_factory = _dict_factory
        cur = conn.cursor()

        # cerca per cognome/nome
        q = f"%{query}%"
        cur.execute("""
            SELECT * FROM caduti_cwgc
            WHERE LOWER(cognome) LIKE ? OR LOWER(nome) LIKE ?
               OR LOWER(CONCAT(nome, ' ', cognome)) LIKE ?
            LIMIT 20
        """, (q, q, q))
        rows = cur.fetchall()
        conn.close()

        results = []
        for r in rows:
            results.append({
                "provider": self.name,
                "provider_record_id": r.get("cwgc_id"),
                "archivio": "CWGC",
                "titolo": f"{r.get('nome', '')} {r.get('cognome', '')} — {r.get('regiment', '')}",
                "description": f"Caduto Commonwealth {r.get('guerra', '')}. "
                               f"Rank: {r.get('rank', '')}. Cimitero: {r.get('cimitero', '')}",
                "source_type": "casualty_record",
                "document_type": "war_grave",
                "conflict": r.get("guerra", ""),
                "date_start": r.get("data_morte", ""),
                "person": f"{r.get('nome', '')} {r.get('cognome', '')}",
                "place": r.get("paese_cimitero", ""),
                "catalog_url": f"{self.base_url}/find-records/find-war-dead/?casualty={r.get('cwgc_id')}",
                "direct_url": f"{self.base_url}/find-records/find-war-dead/?casualty={r.get('cwgc_id')}",
                "access_type": "online",
                "downloadable": False,
                "confidence": 0.85,
            })
        return results

    def get_metadata(self, record_id: str) -> dict:
        conn = get_conn()
        conn.row_factory = _dict_factory
        cur = conn.cursor()
        cur.execute("SELECT * FROM caduti_cwgc WHERE cwgc_id=?", (record_id,))
        r = cur.fetchone()
        conn.close()
        if not r:
            return {}
        return {
            "provider": self.name,
            "provider_record_id": record_id,
            "archivio": "CWGC",
            "titolo": f"{r.get('nome', '')} {r.get('cognome', '')}",
            "catalog_url": f"{self.base_url}/find-records/find-war-dead/?casualty={record_id}",
            "access_type": "online",
        }

    def build_direct_link(self, record_id: str, page: int = None) -> str:
        return f"{self.base_url}/find-records/find-war-dead/?casualty={record_id}"

"""Provider NARA — National Archives (USA).

Recupera metadati dal NARA Catalog API e dal DB locale (documenti_nara_catalog).
IIIF non supportato da NARA, ma ha URL diretti a PDF/immagini digitali.
"""

import json
import re
from typing import Dict, List, Optional

import requests

from database import get_conn
from .base import SourceProvider, _dict_factory, score_source

class ProviderNARA(SourceProvider):
    name = "nara"
    display_name = "NARA — National Archives (USA)"
    country = "USA"
    archive_name = "NARA"
    base_url = "https://catalog.archives.gov"
    authorized_domains = {"catalog.archives.gov", "s3.amazonaws.com",
                          "nara-media-001.s3.amazonaws.com", "archive.org"}
    cache_ttl_days = 60

    def search(self, query: str, filters: dict = None) -> List[dict]:
        results = []

        # 1) Cerca nel DB locale (documenti_nara_catalog)
        conn = get_conn()
        conn.row_factory = _dict_factory
        cur = conn.cursor()
        q = f"%{query}%"
        cur.execute("""
            SELECT * FROM documenti_nara_catalog
            WHERE LOWER(title) LIKE ? OR LOWER(description) LIKE ?
               OR LOWER(series) LIKE ? OR LOWER(search_query) LIKE ?
            ORDER BY has_digital_objects DESC LIMIT 20
        """, (q, q, q, q))
        rows = cur.fetchall()
        conn.close()

        for r in rows:
            results.append({
                "provider": self.name,
                "provider_record_id": r.get("na_id"),
                "archivio": "NARA",
                "fondo": f"RG {r.get('record_group', '')}",
                "serie": r.get("series", ""),
                "titolo": r.get("title", ""),
                "description": r.get("description", ""),
                "source_type": "military_document",
                "document_type": r.get("document_type", ""),
                "date_start": r.get("inclusive_dates", ""),
                "catalog_url": r.get("source_url") or f"{self.base_url}/id/{r.get('na_id')}",
                "direct_url": r.get("file_urls") or "",
                "pdf_url": r.get("pdf_url") or "",
                "access_type": "online" if r.get("has_digital_objects") else "catalog_only",
                "downloadable": bool(r.get("has_digital_objects")),
                "confidence": 0.8,
            })

        # 2) Se pochi risultati, prova NARA Catalog API
        if len(results) < 5:
            api_results = self._search_api(query, filters or {})
            results.extend(api_results)

        return results[:30]

    def _search_api(self, query: str, filters: dict) -> List[dict]:
        """Cerca via NARA Catalog API (opzionale, rate-limited)."""
        try:
            url = "https://catalog.archives.gov/api/v1"
            params = {
                "q": query,
                "resultTypes": "item",
                "rows": 10,
                "includeDigitalObjects": "true",
            }
            resp = requests.get(url, params=params, timeout=20,
                                headers={"User-Agent": "ricerca-storica-IMI/1.0"},
                                verify=False)
            if resp.status_code != 200:
                return []
            data = resp.json()
            ops = data.get("body", {}).get("results", [])
            results = []
            for op in ops:
                results.append({
                    "provider": self.name,
                    "provider_record_id": op.get("naId"),
                    "archivio": "NARA",
                    "titolo": op.get("title", ""),
                    "description": op.get("scopeAndContentNote", ""),
                    "catalog_url": f"{self.base_url}/id/{op.get('naId')}",
                    "source_type": "military_document",
                    "access_type": "online" if op.get("digitalObjects") else "catalog_only",
                    "confidence": 0.7,
                })
            return results
        except Exception:
            return []

    def get_metadata(self, record_id: str) -> dict:
        conn = get_conn()
        conn.row_factory = _dict_factory
        cur = conn.cursor()
        cur.execute("SELECT * FROM documenti_nara_catalog WHERE na_id=?", (record_id,))
        r = cur.fetchone()
        conn.close()
        if not r:
            return {}
        return {
            "provider": self.name,
            "provider_record_id": record_id,
            "archivio": "NARA",
            "fondo": f"RG {r.get('record_group', '')}",
            "serie": r.get("series", ""),
            "titolo": r.get("title", ""),
            "description": r.get("description", ""),
            "catalog_url": r.get("source_url"),
            "direct_url": r.get("file_urls"),
            "pdf_url": r.get("pdf_url"),
            "access_type": "online" if r.get("has_digital_objects") else "catalog_only",
        }

    def get_document(self, record_id: str) -> dict:
        meta = self.get_metadata(record_id)
        url = meta.get("pdf_url") or meta.get("direct_url")
        if not url:
            return {"ok": False, "error": "nessun URL digitale disponibile"}
        return self.fetch_with_cache(url)

    def build_direct_link(self, record_id: str, page: int = None) -> str:
        link = f"{self.base_url}/id/{record_id}"
        return link

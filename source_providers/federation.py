"""Source Federation Layer — registry e orchestrazione provider.

Mantiene il registry di tutti i provider, orchestra la ricerca
multi-provider, e gestisce fetch on-demand con cache.
"""

import json
from datetime import datetime
from typing import Dict, List, Optional

from database import get_conn
from .base import SourceProvider, score_source, _dict_factory
from .nara import ProviderNARA
from .antenati import ProviderAntenati
from .cwgc import ProviderCWGC
from .wikitree import ProviderWikiTree
from .memoire_des_hommes import ProviderMemoireDesHommes
from .deutsche_digitale_bibliothek import ProviderDDB
from .iwm_lives import ProviderIWMLives
from .grand_memorial import ProviderGrandMemorial
from .providers import (
    ProviderArolsen, ProviderBundesarchiv, ProviderSHD,
    ProviderNationalArchivesUK, ProviderEuropeana, ProviderGallica,
    ProviderInternetArchive, ProviderGoogleBooks, ProviderABMC,
    ProviderLibraryCanada, ProviderAustralianWarMemorial,
    ProviderArchivportalD, ProviderInternetCulturale,
    ProviderHathiTrust, ProviderUSSME, ProviderArchivioDiStato,
)

# ─── Registry ──────────────────────────────────────────────────────────────────

_REGISTRY: Dict[str, SourceProvider] = {}


def _register(provider: SourceProvider):
    _REGISTRY[provider.name] = provider


def get_registry() -> Dict[str, SourceProvider]:
    if not _REGISTRY:
        _register(ProviderNARA())
        _register(ProviderAntenati())
        _register(ProviderCWGC())
        _register(ProviderWikiTree())
        _register(ProviderArolsen())
        _register(ProviderBundesarchiv())
        _register(ProviderSHD())
        _register(ProviderNationalArchivesUK())
        _register(ProviderEuropeana())
        _register(ProviderGallica())
        _register(ProviderInternetArchive())
        _register(ProviderGoogleBooks())
        _register(ProviderABMC())
        _register(ProviderLibraryCanada())
        _register(ProviderAustralianWarMemorial())
        _register(ProviderArchivportalD())
        _register(ProviderInternetCulturale())
        _register(ProviderHathiTrust())
        _register(ProviderUSSME())
        _register(ProviderArchivioDiStato())
        _register(ProviderMemoireDesHommes())
        _register(ProviderDDB())
        _register(ProviderIWMLives())
        _register(ProviderGrandMemorial())
    return _REGISTRY


def get_provider(name: str) -> Optional[SourceProvider]:
    return get_registry().get(name)


def list_providers() -> List[dict]:
    reg = get_registry()
    return [
        {
            "name": p.name,
            "display_name": p.display_name,
            "country": p.country,
            "archive_name": p.archive_name,
            "base_url": p.base_url,
            "authorized_domains": list(p.authorized_domains),
            "cache_ttl_days": p.cache_ttl_days,
        }
        for p in reg.values()
    ]


# ─── Federation search ─────────────────────────────────────────────────────────

def federated_search(query: str, cues: dict = None,
                     providers: List[str] = None,
                     filters: dict = None) -> List[dict]:
    """Cerca across provider. Non scarica documenti.
    Ritorna metadati con score.

    Args:
        query: testo query
        cues: cue estratti (persona, reparto, luogo, data)
        providers: lista nomi provider da interrogare (None = tutti)
        filters: filtri aggiuntivi (comune, anno, tipologia, etc.)
    """
    reg = get_registry()
    if providers:
        targets = {k: v for k, v in reg.items() if k in providers}
    else:
        targets = reg

    all_results = []
    for pname, provider in targets.items():
        try:
            results = provider.search(query, filters or {})
            for r in results:
                r["provider"] = pname
                r["score"] = score_source(r, cues or {})
                all_results.append(r)
        except Exception as e:
            all_results.append({
                "provider": pname,
                "error": str(e),
                "score": 0.0,
            })

    # ordina per score
    all_results.sort(key=lambda x: x.get("score", 0), reverse=True)
    return all_results


# ─── Fetch on demand ───────────────────────────────────────────────────────────

def fetch_source(source_id: int) -> dict:
    """Scarica un documento on-demand. Solo backend, solo domini autorizzati."""
    conn = get_conn()
    conn.row_factory = _dict_factory
    cur = conn.cursor()
    cur.execute("SELECT * FROM fonti_indice WHERE id=?", (source_id,))
    meta = cur.fetchone()
    conn.close()
    if not meta:
        return {"ok": False, "error": f"source_id {source_id} non trovato"}

    url = meta.get("url_file") or meta.get("iiif_manifest") or meta.get("url_catalogo")
    if not url:
        return {"ok": False, "error": "nessun URL disponibile per questa fonte"}

    # determina provider dall'archivio
    archivio = (meta.get("archivio") or "").lower()
    provider = _match_provider(archivio)
    if provider:
        return provider.fetch_with_cache(url, source_id=source_id)
    else:
        # fallback: prova fetch diretta se dominio autorizzato di qualche provider
        for p in get_registry().values():
            if p.is_authorized(url):
                return p.fetch_with_cache(url, source_id=source_id)
        return {"ok": False, "error": f"dominio non autorizzato per fetch: {url}"}


def _match_provider(archivio: str) -> Optional[SourceProvider]:
    """Match archivio string → provider."""
    mapping = {
        "nara": "nara",
        "antenati": "antenati",
        "archivio di stato": "antenati",
        "cwgc": "cwgc",
        "commonwealth": "cwgc",
        "arolsen": "arolsen",
        "bundesarchiv": "bundesarchiv",
        "shd": "shd",
        "service historique": "shd",
        "memoire des hommes": "shd",
        "tna": "tna",
        "national archives": "tna",
        "europeana": "europeana",
        "gallica": "gallica",
        "bnf": "gallica",
        "internet archive": "internetarchive",
        "google books": "googlebooks",
        "abmc": "abmc",
        "library and archives canada": "lac",
        "australian war memorial": "awm",
        "archivportal": "archivportal_d",
        "internet culturale": "internetculturale",
        "hathitrust": "hathitrust",
        "ussme": "ussme",
        "ufficio storico": "ussme",
    }
    for key, pname in mapping.items():
        if key in archivio:
            return get_provider(pname)
    return None


# ─── Stats ─────────────────────────────────────────────────────────────────────

def get_federation_stats() -> dict:
    conn = get_conn()
    conn.row_factory = _dict_factory
    cur = conn.cursor()

    cur.execute("SELECT COUNT(*) as n FROM fonti_indice")
    total = cur.fetchone()["n"]

    cur.execute("SELECT archivio, COUNT(*) as n FROM fonti_indice GROUP BY archivio ORDER BY n DESC")
    by_archive = [dict(r) for r in cur.fetchall()]

    cur.execute("SELECT fetch_status, COUNT(*) as n FROM fonti_indice GROUP BY fetch_status")
    by_status = {r["fetch_status"]: r["n"] for r in cur.fetchall()}

    cur.execute("SELECT COUNT(*) as n, SUM(size_bytes) as total_size FROM source_fetch_cache")
    cache = cur.fetchone()

    conn.close()

    return {
        "total_sources": total,
        "by_archive": by_archive,
        "by_fetch_status": by_status,
        "cache_count": cache["n"],
        "cache_total_bytes": cache["total_size"] or 0,
        "providers": len(get_registry()),
        "provider_names": list(get_registry().keys()),
    }

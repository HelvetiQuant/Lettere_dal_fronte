"""Person Finder — orchestratore automatico per ricerca persone non in DB.

Flusso:
1. Parse query → estrae cognome, nome, anno_nascita, luogo_nascita
2. Ricerca esaustiva su tutti i DB locali (SQLite + Supabase)
3. Se non trovato → ricerca federata su 27 provider esterni
4. Ricerca web (search_web) per fonti non coperte da provider
5. Normalizza e consolida risultati cross-source
6. Persiste risultati in Supabase (archive.external_items) per future ricerche
7. Ritorna dashboard strutturato

Usage:
    from person_finder import find_person
    result = find_person("Siracusa Francesco", birth_year=1886, birth_place="Messina")
"""
from __future__ import annotations

import json
import logging
import re
import sqlite3
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

import httpx
from dotenv import load_dotenv

load_dotenv()

log = logging.getLogger(__name__)

# ─── Data structures ──────────────────────────────────────────────────────────

@dataclass
class PersonQuery:
    """Query normalizzata per ricerca persona."""
    raw: str
    cognome: str = ""
    nome: str = ""
    birth_year: Optional[int] = None
    birth_place: str = ""
    conflict: str = ""  # ww1, ww2, unknown

    @property
    def full_name(self) -> str:
        return f"{self.cognome} {self.nome}".strip()

    @property
    def search_query(self) -> str:
        parts = [self.full_name]
        if self.birth_year:
            parts.append(str(self.birth_year))
        if self.birth_place:
            parts.append(self.birth_place)
        return " ".join(parts)


@dataclass
class PersonMatch:
    """Singolo match da una fonte."""
    source: str  # local_sqlite, supabase, federated, web
    source_detail: str  # table name, provider name, url
    name: str
    birth_year: Optional[int] = None
    birth_place: str = ""
    death_year: Optional[int] = None
    death_place: str = ""
    military_unit: str = ""
    rank: str = ""
    fate: str = ""  # deceduto, prigioniero, disperso, sopravvissuto
    url: str = ""
    raw_data: dict = field(default_factory=dict)
    confidence: float = 0.0


@dataclass
class FindResult:
    """Risultato completo della ricerca."""
    query: PersonQuery
    found_locally: bool
    local_matches: List[PersonMatch] = field(default_factory=list)
    federated_matches: List[PersonMatch] = field(default_factory=list)
    web_matches: List[PersonMatch] = field(default_factory=list)
    supabase_matches: List[PersonMatch] = field(default_factory=list)
    persisted: bool = False
    subject_id: Optional[int] = None
    errors: List[str] = field(default_factory=list)

    @property
    def total_matches(self) -> int:
        return len(self.local_matches) + len(self.federated_matches) + len(self.web_matches) + len(self.supabase_matches)

    def to_dict(self) -> dict:
        return {
            "query": {
                "raw": self.query.raw,
                "cognome": self.query.cognome,
                "nome": self.query.nome,
                "birth_year": self.query.birth_year,
                "birth_place": self.query.birth_place,
                "conflict": self.query.conflict,
            },
            "found_locally": self.found_locally,
            "total_matches": self.total_matches,
            "local_matches": [m.__dict__ for m in self.local_matches],
            "federated_matches": [m.__dict__ for m in self.federated_matches],
            "web_matches": [m.__dict__ for m in self.web_matches],
            "supabase_matches": [m.__dict__ for m in self.supabase_matches],
            "persisted": self.persisted,
            "subject_id": self.subject_id,
            "errors": self.errors,
        }


# ─── Query parsing ────────────────────────────────────────────────────────────

def parse_query(raw: str, birth_year: Optional[int] = None, birth_place: str = "", conflict: str = "") -> PersonQuery:
    """Parse a free-text query into structured PersonQuery.

    Handles formats like:
    - "Siracusa Francesco"
    - "Siracusa Francesco classe 1886"
    - "Siracusa Francesco nato a Messina"
    - "Antonio Smiraldi prima guerra mondiale"
    """
    raw_stripped = raw.strip()
    pq = PersonQuery(raw=raw_stripped, birth_year=birth_year, birth_place=birth_place, conflict=conflict)

    # Extract birth year from "classe YYYY" or "nato YYYY" or standalone 4-digit year
    if not pq.birth_year:
        m = re.search(r"(?:classe|nato(?:\s+il)?(?:\s+\d{1,2}[/-])?\s*)?(\d{4})", raw_stripped, re.IGNORECASE)
        if m:
            year = int(m.group(1))
            if 1850 <= year <= 2000:
                pq.birth_year = year

    # Extract birth place from "nato a XXX" or "nato a XXX (YY)"
    if not pq.birth_place:
        m = re.search(r"nato\s+(?:a|il\s+\d{1,2}[/-]\d{1,2}[/-]\d{2,4}\s+a?)\s+([A-Za-zÀ-ÿ'\-\s]+?)(?:\s+(?:classe|prima|seconda|guerra|militare|regio|esercito|$))", raw_stripped, re.IGNORECASE)
        if m:
            pq.birth_place = m.group(1).strip()

    # Extract conflict
    if not pq.conflict:
        if re.search(r"prima\s+guerra\s+mondiale|1915.?1918|grande\s+guerra", raw_stripped, re.IGNORECASE):
            pq.conflict = "ww1"
        elif re.search(r"seconda\s+guerra\s+mondiale|1939.?1945|1940.?1945", raw_stripped, re.IGNORECASE):
            pq.conflict = "ww2"

    # Extract name: remove year, place markers, conflict keywords
    cleaned = re.sub(r"\b(?:classe|nato|a|il|prima|seconda|guerra|mondiale|militare|regio|esercito|caduto|deceduto|disperso|prigioniero)\b", "", raw_stripped, flags=re.IGNORECASE)
    cleaned = re.sub(r"\d{4}", "", cleaned)
    cleaned = re.sub(r"[^\w\s'\-À-ÿ]", " ", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()

    parts = cleaned.split()
    if len(parts) >= 2:
        # Heuristic: first part is cognome (usually shorter, uppercase in original)
        # Check if original had uppercase first word
        original_parts = raw_stripped.split()
        if original_parts and original_parts[0].isupper():
            pq.cognome = parts[0]
            pq.nome = " ".join(parts[1:])
        else:
            # Try: first word = cognome, rest = nome
            pq.cognome = parts[0]
            pq.nome = " ".join(parts[1:])
    elif len(parts) == 1:
        pq.cognome = parts[0]

    return pq


# ─── Local DB search ──────────────────────────────────────────────────────────

def _search_local_sqlite(pq: PersonQuery) -> List[PersonMatch]:
    """Search all SQLite tables exhaustively."""
    matches = []
    db_path = Path(__file__).parent / "imi_internati.db"
    if not db_path.exists():
        return matches

    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row

    search_term = pq.cognome
    if not search_term:
        return matches

    # Define all searchable tables with their text columns
    # surname_cols: columns where the surname appears as a word (name fields)
    # other_cols: additional text columns for nome filtering only
    table_configs = [
        ("internati", ["cognome", "nome"], ["luogo_nascita", "residenza", "luogo_internamento", "raw_text"]),
        ("caduti_albooro", ["nominativo"], ["paternita", "comune_attuale", "grado", "reparto"]),
        ("caduti_ministero", ["cognome", "nome"], ["nominativo_paternita", "comune_nascita"]),
        ("caduti_bologna", ["nome"], ["paternita", "luogo_nascita", "luogo_dimora"]),
        ("caduti_cwgc", ["nome", "cognome"], ["regiment", "cimitero"]),
        ("caduti_sardi", ["cognome", "nome"], ["paternita", "luogo_nascita"]),
        ("caduti_francia_ww1", ["nom"], ["lieu_naissance", "unite"]),
        ("decorati", ["cognome", "nome"], ["comune_nascita", "comune_residenza"]),
        ("decorati_nastroazzurro", ["cognome", "nome"], ["arma", "tipo_decorazione"]),
        ("menzioni", ["cognome", "nome"], ["grado", "reparto", "luogo", "contesto"]),
        ("fonti_indice", [], ["titolo", "descrizione"]),
        ("lettere_personali", [], ["mittente", "destinatario", "testo"]),
        ("entita", ["nome"], ["tipo", "descrizione"]),
        ("eventi_1gm", ["nome"], ["descrizione", "aliases", "keywords"]),
        ("archivio_documenti", [], ["titolo", "descrizione", "soggetto"]),
        ("external_person_mentions", ["person_name"], ["context"]),
    ]

    # Columns that contain person names (for nome filtering)
    name_columns = {"nominativo", "cognome", "nome", "name", "person_name", "nom"}

    for table, surname_cols, other_cols in table_configs:
        try:
            tbl_cols = [d[1] for d in conn.execute(f"PRAGMA table_info({table})").fetchall()]
            s_cols = [c for c in surname_cols if c in tbl_cols]
            o_cols = [c for c in other_cols if c in tbl_cols]
            if not s_cols:
                # No surname columns — skip surname search, only use for nome filtering
                # (e.g. fonti_indice, archivio_documenti)
                if not pq.nome or pq.nome == pq.cognome:
                    continue
                s_cols = o_cols  # fallback: search nome on all columns
            else:
                search_cols = s_cols

            # Word-boundary matching for surname: match at start of field or after space
            # This prevents 'LARI' matching 'ALARIO', 'CLARICE', or place name 'Lari'
            surname = search_term.replace("'", "''")
            conditions = " OR ".join(
                f"(CAST({c} AS TEXT) LIKE '{surname} %' OR CAST({c} AS TEXT) LIKE '{surname}' OR CAST({c} AS TEXT) LIKE '{surname}\\_%' ESCAPE '\\')"
                for c in s_cols
            )

            # Filter by nome on name columns + other text columns
            if pq.nome and pq.nome != pq.cognome:
                nome = pq.nome.replace("'", "''")
                all_cols = s_cols + o_cols
                nome_conditions = " OR ".join(
                    f"(CAST({c} AS TEXT) LIKE '%{nome}%')"
                    for c in all_cols
                )
                conditions = f"({conditions}) AND ({nome_conditions})"

            rows = conn.execute(f"SELECT * FROM {table} WHERE {conditions} LIMIT 30").fetchall()
            for r in rows:
                d = dict(r)
                # Extract name fields
                name = d.get("nominativo") or f"{d.get('cognome', '')} {d.get('nome', '')}".strip() or d.get("nome", "") or d.get("nom", "")
                if not name:
                    continue

                # Extract birth year
                by = None
                for k in ("classe", "anno_nascita", "data_nascita"):
                    v = d.get(k)
                    if v:
                        m = re.search(r"(\d{4})", str(v))
                        if m:
                            by = int(m.group(1))
                            break

                # Extract birth place
                bp = d.get("luogo_nascita") or d.get("comune_nascita") or d.get("comune_attuale") or d.get("lieu_naissance") or ""

                # Extract death info
                dy = None
                for k in ("anno_morte", "data_morte", "anno_decorazione"):
                    v = d.get(k)
                    if v:
                        m = re.search(r"(\d{4})", str(v))
                        if m:
                            dy = int(m.group(1))
                            break
                dp = d.get("luogo_morte") or d.get("lieu_deces") or ""

                # Confidence scoring
                conf = 0.5
                if pq.nome and pq.nome.lower() in name.lower():
                    conf += 0.2
                if pq.birth_year and by == pq.birth_year:
                    conf += 0.2
                if pq.birth_place and pq.birth_place.lower() in bp.lower():
                    conf += 0.1

                matches.append(PersonMatch(
                    source="local_sqlite",
                    source_detail=table,
                    name=name,
                    birth_year=by,
                    birth_place=bp,
                    death_year=dy,
                    death_place=dp,
                    military_unit=d.get("reparto") or d.get("regiment") or d.get("unite") or "",
                    rank=d.get("grado") or d.get("rank") or d.get("grade") or "",
                    fate=d.get("sorte") or d.get("causa_morte") or "",
                    url=d.get("detail_url") or d.get("scheda_url") or d.get("url") or "",
                    raw_data=d,
                    confidence=conf,
                ))
        except Exception as e:
            log.debug("SQLite search error on %s: %s", table, e)

    conn.close()
    return matches


def _search_supabase(pq: PersonQuery) -> List[PersonMatch]:
    """Search Supabase tables for person."""
    import os
    matches = []
    url = os.environ.get("SUPABASE_URL", "")
    key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")
    if not url or not key:
        return matches

    rpc_url = f"{url}/rest/v1/rpc/exec_sql_returning"
    headers = {
        "apikey": key,
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
    }

    search_term = pq.cognome.replace("'", "''")
    queries = [
        # core.entities
        ("supabase_entities", f"SELECT json_agg(row_to_json(x)) FROM (SELECT id, stable_id, canonical_name, entity_type, verification_status, source_system, source_table, source_id FROM core.entities WHERE canonical_name ILIKE '%{search_term}%' LIMIT 20) x"),
        # archive.external_items
        ("supabase_external_items", f"SELECT json_agg(row_to_json(x)) FROM (SELECT id, stable_id, provider_code, external_id, item_type, title, description, canonical_url FROM archive.external_items WHERE title ILIKE '%{search_term}%' OR description ILIKE '%{search_term}%' LIMIT 20) x"),
        # evidence.claims with entity join
        ("supabase_claims", f"SELECT json_agg(row_to_json(x)) FROM (SELECT c.id, c.predicate, c.claim_status, c.object_value, e_s.canonical_name AS subject_name, e_o.canonical_name AS object_name FROM evidence.claims c LEFT JOIN core.entities e_s ON e_s.id = c.subject_entity_id LEFT JOIN core.entities e_o ON e_o.id = c.object_entity_id WHERE e_s.canonical_name ILIKE '%{search_term}%' OR e_o.canonical_name ILIKE '%{search_term}%' OR c.object_value ILIKE '%{search_term}%' LIMIT 20) x"),
    ]

    for label, sql in queries:
        try:
            r = httpx.post(rpc_url, headers=headers, json={"query": sql}, timeout=30)
            if r.status_code in (200, 201):
                data = r.json()
                if isinstance(data, str):
                    data = json.loads(data)
                if isinstance(data, list):
                    for row in data:
                        if not row or not isinstance(row, dict):
                            continue
                        name = row.get("canonical_name") or row.get("title") or row.get("subject_name") or ""
                        if not name:
                            continue
                        matches.append(PersonMatch(
                            source="supabase",
                            source_detail=label,
                            name=name,
                            url=row.get("canonical_url", ""),
                            raw_data=row,
                            confidence=0.6,
                        ))
        except Exception as e:
            log.debug("Supabase search error (%s): %s", label, e)

    return matches


# ─── Federated search ─────────────────────────────────────────────────────────

def _search_federated(pq: PersonQuery) -> List[PersonMatch]:
    """Search all 27 federated providers."""
    matches = []
    try:
        from source_providers.federation import federated_search, get_provider
        from source_providers.base import build_federated_search_context

        context = build_federated_search_context(
            subject_type="person",
            canonical_name=pq.full_name,
        )
        if pq.conflict:
            context = context._replace(conflict=pq.conflict) if hasattr(context, "_replace") else context

        cues = {"persona": pq.full_name}
        if pq.birth_place:
            cues["luogo"] = pq.birth_place
        if pq.birth_year:
            cues["anno"] = str(pq.birth_year)

        # General federated search
        results = federated_search(pq.search_query, cues=cues, context=context)
        for r in results:
            if "error" in r:
                continue
            matches.append(PersonMatch(
                source="federated",
                source_detail=r.get("provider", "unknown"),
                name=r.get("title") or r.get("titolo") or pq.full_name,
                url=r.get("url") or r.get("catalog_url") or "",
                raw_data=r,
                confidence=r.get("score", 0.3),
            ))

        # Per-name ICRC search (WW1 specific)
        if pq.conflict == "ww1" or not pq.conflict:
            try:
                icrc = get_provider("icrc_ww1")
                if icrc:
                    full_name = pq.full_name
                    hits = icrc.search(full_name, {"nationality": "italy", "status": "military"})
                    for h in hits:
                        matches.append(PersonMatch(
                            source="federated",
                            source_detail="icrc_ww1_per_name",
                            name=h.get("title", full_name),
                            url=h.get("url", ""),
                            raw_data=h,
                            confidence=h.get("score", 0.5),
                        ))
            except Exception as e:
                log.debug("ICRC per-name error: %s", e)

        # Per-name LeBI search
        try:
            lebi = get_provider("lebi")
            if lebi:
                hits = lebi.search(pq.cognome, nome=pq.nome)
                for h in hits:
                    matches.append(PersonMatch(
                        source="federated",
                        source_detail="lebi_per_name",
                        name=h.get("title", pq.full_name),
                        url=h.get("url", ""),
                        raw_data=h,
                        confidence=h.get("score", 0.5),
                    ))
        except Exception as e:
            log.debug("LeBI per-name error: %s", e)

    except Exception as e:
        log.error("Federated search error: %s", e)
    return matches


# ─── Web search ───────────────────────────────────────────────────────────────

def _search_web(pq: PersonQuery) -> List[PersonMatch]:
    """Search the web for the person. Uses search_web tool if available,
    otherwise constructs targeted URLs for known archives."""
    matches = []

    # Build targeted search URLs for archives not covered by providers
    query_parts = [pq.full_name]
    if pq.birth_year:
        query_parts.append(str(pq.birth_year))
    if pq.birth_place:
        query_parts.append(pq.birth_place)
    query_parts.append("militare")
    search_string = " ".join(query_parts)

    # Known archive URLs that can be checked directly
    archive_urls = [
        # Albo d'Oro Ministero Difesa
        {
            "name": "Albo d'Oro (Ministero Difesa)",
            "url": f"https://www.difesa.it/OnorificenzeEDecorazioni/Pagine/AlbodOro.aspx",
            "search_hint": f"Cercare '{pq.cognome}' nel volume della provincia di nascita",
        },
        # ICRC WW1
        {
            "name": "ICRC WW1 Prisoners",
            "url": f"https://grandeguerre.icrc.org/en/File/Search#person|{pq.cognome}%20{pq.nome}|",
            "search_hint": f"Cercare '{pq.full_name}' con filtro nationality=Italy",
        },
        # Antenati SAN
        {
            "name": "Portale Antenati (SAN)",
            "url": f"https://www.antenati.san.beniculturali.it/?s={pq.cognome}+{pq.nome}",
            "search_hint": f"Cercare registri di leva per classe {pq.birth_year or '????'}",
        },
        # FamilySearch
        {
            "name": "FamilySearch",
            "url": f"https://www.familysearch.org/search/record/results?q.surname={pq.cognome}&q.givenName={pq.nome}",
            "search_hint": f"Cercare '{pq.full_name}' nato nel {pq.birth_year or '????'}",
        },
        # Pietre della Memoria
        {
            "name": "Pietre della Memoria",
            "url": f"https://www.pietredellamemoria.it/?s={pq.cognome}+{pq.nome}",
            "search_hint": f"Cercare '{pq.full_name}' nei monumenti ai caduti",
        },
        # Onore ai Caduti
        {
            "name": "Onore ai Caduti",
            "url": f"https://www.onoreaicaduti.it/?s={pq.cognome}+{pq.nome}",
            "search_hint": f"Cercare '{pq.full_name}' nell'elenco caduti",
        },
    ]

    for arch in archive_urls:
        matches.append(PersonMatch(
            source="web",
            source_detail=arch["name"],
            name=pq.full_name,
            url=arch["url"],
            confidence=0.1,  # low confidence — just a link to check
            raw_data=arch,
        ))

    return matches


# ─── Persistence ──────────────────────────────────────────────────────────────

def _persist_to_supabase(pq: PersonQuery, matches: List[PersonMatch]) -> bool:
    """Persist search results to Supabase for future reference.
    Creates a core.entities record and links found sources."""
    import os
    url = os.environ.get("SUPABASE_URL", "")
    key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")
    if not url or not key:
        return False

    rpc_url = f"{url}/rest/v1/rpc/exec_sql_returning"
    headers = {
        "apikey": key,
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
    }

    # Create entity if not exists
    stable_id = f"person:{pq.cognome.lower()}:{pq.nome.lower()}:{pq.birth_year or 'unknown'}"
    entity_sql = f"""
    INSERT INTO core.entities (stable_id, entity_type, canonical_name, verification_status, confidence, source_system, source_table)
    SELECT '{stable_id}', 'person', '{pq.full_name.replace("'", "''")}', 'candidate', 0.3, 'person_finder', 'auto_search'
    WHERE NOT EXISTS (SELECT 1 FROM core.entities WHERE stable_id = '{stable_id}')
    RETURNING id;
    """

    try:
        r = httpx.post(rpc_url, headers=headers, json={"query": entity_sql}, timeout=30)
        if r.status_code in (200, 201):
            data = r.json()
            if isinstance(data, list) and data and data[0]:
                entity_id = data[0].get("id") if isinstance(data[0], dict) else None
                if entity_id:
                    # Save external items for each match with a URL
                    for m in matches:
                        if not m.url:
                            continue
                        ei_sql = f"""
                        INSERT INTO archive.external_items (stable_id, provider_code, external_id, item_type, title, description, canonical_url, access_status, review_status)
                        SELECT 'pf:{stable_id}:{m.source_detail.replace("'", "''")}',
                               'person_finder', '{m.source_detail.replace("'", "''")}',
                               'person_record', '{m.name.replace("'", "''")}',
                               '{m.source}:{m.source_detail.replace("'", "''")}',
                               '{m.url.replace("'", "''")}', 'active', 'candidate'
                        WHERE NOT EXISTS (
                            SELECT 1 FROM archive.external_items WHERE canonical_url = '{m.url.replace("'", "''")}'
                        );
                        """
                        try:
                            httpx.post(rpc_url, headers=headers, json={"query": ei_sql}, timeout=15)
                        except Exception:
                            pass
                    return True
    except Exception as e:
        log.error("Persist error: %s", e)
    return False


# ─── Main orchestrator ────────────────────────────────────────────────────────

def find_person(
    raw_query: str,
    birth_year: Optional[int] = None,
    birth_place: str = "",
    conflict: str = "",
    *,
    search_local: bool = True,
    search_supabase: bool = True,
    search_federated: bool = True,
    search_web: bool = True,
    persist: bool = True,
) -> FindResult:
    """Find a person across all available sources.

    Args:
        raw_query: free-text query (e.g. "Siracusa Francesco classe 1886")
        birth_year: optional birth year override
        birth_place: optional birth place override
        conflict: optional conflict filter (ww1, ww2)
        search_local: search SQLite databases
        search_supabase: search Supabase tables
        search_federated: search 27 federated providers
        search_web: generate web search URLs
        persist: save results to Supabase

    Returns:
        FindResult with all matches from all sources
    """
    pq = parse_query(raw_query, birth_year=birth_year, birth_place=birth_place, conflict=conflict)
    log.info("PersonFinder: parsed '%s' → cognome=%s nome=%s year=%s place=%s conflict=%s",
             raw_query, pq.cognome, pq.nome, pq.birth_year, pq.birth_place, pq.conflict)

    result = FindResult(query=pq, found_locally=False)

    # Step 1: Local SQLite
    if search_local:
        local = _search_local_sqlite(pq)
        result.local_matches = local
        result.found_locally = len(local) > 0

    # Step 2: Supabase
    if search_supabase:
        supa = _search_supabase(pq)
        result.supabase_matches = supa
        if supa and not result.found_locally:
            result.found_locally = True

    # Step 3: Federated providers (only if not found locally, or always — configurable)
    if search_federated:
        fed = _search_federated(pq)
        result.federated_matches = fed

    # Step 4: Web search URLs
    if search_web:
        web = _search_web(pq)
        result.web_matches = web

    # Step 5: Persist to Supabase
    if persist and result.total_matches > 0:
        all_matches = result.local_matches + result.supabase_matches + result.federated_matches + result.web_matches
        result.persisted = _persist_to_supabase(pq, all_matches)

    # Step 6: Also use existing auto_index_if_not_found for research subject tracking
    if not result.found_locally:
        try:
            from research_to_index import auto_index_if_not_found
            rti_result = auto_index_if_not_found(pq.search_query)
            if rti_result.get("subject_id"):
                result.subject_id = rti_result["subject_id"]
        except Exception as e:
            log.debug("auto_index error: %s", e)

    log.info("PersonFinder: %s → local=%d supabase=%d federated=%d web=%d persisted=%s",
             pq.full_name, len(result.local_matches), len(result.supabase_matches),
             len(result.federated_matches), len(result.web_matches), result.persisted)

    return result


# ─── CLI ──────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import sys
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    if len(sys.argv) < 2:
        print("Usage: python person_finder.py 'Siracusa Francesco' --year 1886 --place Messina")
        sys.exit(1)
    query = sys.argv[1]
    year = None
    place = ""
    for i, arg in enumerate(sys.argv[2:], 2):
        if arg == "--year" and i + 1 < len(sys.argv):
            year = int(sys.argv[i + 1])
        elif arg == "--place" and i + 1 < len(sys.argv):
            place = sys.argv[i + 1]
    result = find_person(query, birth_year=year, birth_place=place)
    print(json.dumps(result.to_dict(), indent=2, ensure_ascii=False, default=str))

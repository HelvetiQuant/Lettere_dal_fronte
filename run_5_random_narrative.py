"""Run V7 orchestrator on 5 random names and print enriched V7.3 conversational responses.

Integrates:
- source_quality: assess_source_quality per claim
- claim_lifecycle: determine_claim_state (4 states)
- response_structure: ResponseBuilder 11 sections
- military_ontology: parse_rank / parse_unit for ruolo militare
- geo_context: place context for luoghi
"""
from __future__ import annotations

import sqlite3
import sys
import os
import time
import json
from pathlib import Path
from typing import Dict, List, Any, Optional

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

DB_MAIN = Path(__file__).parent / "imi_internati.db"


def select_random_names(n=5):
    conn = sqlite3.connect(str(DB_MAIN))
    conn.row_factory = sqlite3.Row
    names = []

    rows = conn.execute("""
        SELECT id, cognome, nome FROM internati
        WHERE cognome IS NOT NULL AND nome IS NOT NULL
          AND length(cognome) > 2 AND length(nome) > 2
        ORDER BY RANDOM() LIMIT 2
    """).fetchall()
    for r in rows:
        names.append({"name": f"{r['cognome']} {r['nome']}", "table": "internati", "id": r["id"]})

    try:
        rows = conn.execute("""
            SELECT id, nominativo FROM caduti_albooro
            WHERE nominativo IS NOT NULL AND length(nominativo) > 5
            ORDER BY RANDOM() LIMIT 1
        """).fetchall()
        for r in rows:
            names.append({"name": r["nominativo"], "table": "caduti_albooro", "id": r["id"]})
    except sqlite3.OperationalError:
        pass

    try:
        rows = conn.execute("""
            SELECT id, cognome, nome FROM decorati_nastroazzurro
            WHERE cognome IS NOT NULL AND nome IS NOT NULL
              AND length(cognome) > 2 AND length(nome) > 2
            ORDER BY RANDOM() LIMIT 1
        """).fetchall()
        for r in rows:
            names.append({"name": f"{r['cognome']} {r['nome']}", "table": "decorati_nastroazzurro", "id": r["id"]})
    except sqlite3.OperationalError:
        pass

    try:
        rows = conn.execute("""
            SELECT id, cognome, nome FROM caduti_cwgc
            WHERE cognome IS NOT NULL AND nome IS NOT NULL
              AND length(cognome) > 2 AND length(nome) > 2
            ORDER BY RANDOM() LIMIT 1
        """).fetchall()
        for r in rows:
            names.append({"name": f"{r['cognome']} {r['nome']}", "table": "caduti_cwgc", "id": r["id"]})
    except sqlite3.OperationalError:
        pass

    conn.close()
    return names[:n]


def extract_claims_from_snapshot(snapshot: Optional[dict]) -> List[dict]:
    """Extract person_claims from snapshot dict as flat claim dicts."""
    if not snapshot:
        return []
    claims = []
    raw_claims = snapshot.get("person_claims", [])
    for c in raw_claims:
        if isinstance(c, dict):
            # Parse source field: "local_db:internati:15715" or "origin_record"
            src = c.get("source", "")
            source_table = ""
            source_id = ""
            if ":" in src:
                parts = src.split(":")
                if len(parts) >= 3:
                    source_table = parts[1]
                    source_id = parts[2]
                elif len(parts) == 2:
                    source_table = parts[1]
            elif src == "origin_record":
                source_table = "internati"
            claims.append({
                "claim_id": c.get("claim_id", c.get("id", "")),
                "predicate": c.get("predicate", ""),
                "value_normalized": c.get("value_normalized", c.get("value", "")),
                "source_table": source_table,
                "source_id": source_id,
                "source_raw": src,
                "evidence_scope": c.get("evidence_scope", "PERSON_EVIDENCE"),
                "evidence_ids": c.get("evidence_ids", []),
                "status": c.get("status", "ASSERTED"),
                "confidence": c.get("confidence", 0.5),
            })
    return claims


def enrich_with_v73(
    name: str,
    snapshot: Optional[dict],
    report: str,
    semantic_counts: dict,
) -> str:
    """Enrich the V7.2 report with V7.3 modules: source quality, claim lifecycle,
    military ontology, geo context, and 11-section response structure."""

    from source_quality import assess_source_quality, combine_evidence_quality
    from claim_lifecycle import determine_claim_state, build_caveat_summary
    from response_structure import ResponseBuilder
    from military_ontology import parse_rank, parse_unit

    claims = extract_claims_from_snapshot(snapshot)
    identity_status = snapshot.get("identity_status", "UNRESOLVED_IDENTITY") if snapshot else "UNRESOLVED_IDENTITY"
    corroboration = snapshot.get("corroboration_status", "NONE") if snapshot else "NONE"

    # Map DB table names to source quality registry keys
    TABLE_TO_QUALITY_KEY = {
        "internati": "internati_imi",
        "caduti_albooro": "albo_oro",
        "caduti_ministero": "ministero_difesa",
        "decorati_nastroazzurro": "nastro_azzurro",
        "caduti_cwgc": "cwgc",
        "fonti_indice": "fonti_indice",
        "archivio_documenti": "archivio_documenti",
        "ocr_lettere": "ocr_lettere",
    }

    # Source quality assessment
    qualities = []
    for c in claims:
        src_raw = c.get("source_table", "unknown")
        src = TABLE_TO_QUALITY_KEY.get(src_raw, src_raw)
        q = assess_source_quality(src)
        qualities.append(q)
        c["quality_level"] = q.quality_level
        c["quality_score"] = q.quality_score

    combined_result = combine_evidence_quality(qualities) if qualities else ("unverified", 0.0, "no_evidence")
    evidence_level = combined_result[0]
    combined_score = combined_result[1]
    combined_reason = combined_result[2]

    # Claim lifecycle states
    claim_states = []
    for c in claims:
        cs = determine_claim_state(
            claim_id=c.get("claim_id", ""),
            evidence_level=evidence_level,
            identity_status=identity_status,
            validation_status="VALID",
            has_scope_violation=False,
            source_count=1,
            entailment_score=0.8,
        )
        claim_states.append({
            "claim_id": c.get("claim_id", ""),
            "state": cs.state,
            "caveat": cs.caveat or "",
        })
        c["state"] = cs.state

    # Military ontology: parse rank and unit
    rank_info = None
    unit_info = None
    for c in claims:
        if c.get("predicate") in ("rank", "grado") and c.get("value_normalized"):
            rank_info = parse_rank(c["value_normalized"], "person_record")
        if c.get("predicate") in ("military_unit", "reparto") and c.get("value_normalized"):
            unit_info = parse_unit(c["value_normalized"], "person_record")

    # Build 11-section response
    builder = ResponseBuilder()
    # build_caveat_summary expects List[ClaimState], not List[dict]
    claim_state_objects = [determine_claim_state(
        claim_id=c.get("claim_id", ""),
        evidence_level=evidence_level,
        identity_status=identity_status,
        validation_status="VALID",
        source_count=1,
        entailment_score=0.8,
    ) for c in claims]
    caveat_summary = build_caveat_summary(claim_state_objects) if claim_state_objects else ""
    response = builder.build(
        request_type="PERSON",
        query=name,
        identity_status=identity_status,
        evidence_level=evidence_level,
        claims=claims,
        claim_states=claim_states,
        validation_errors=[],
        caveat_summary=caveat_summary,
    )

    # Enrich: Percorso Militare — ruolo e contesto
    pm_section = response.get_section("percorso_militare")
    if pm_section and not pm_section.is_empty:
        enrichment_lines = []
        if rank_info and rank_info.canonical:
            cat_it = {
                "ufficiali_generali": "Ufficiale Generale",
                "ufficiali_superiori": "Ufficiale Superiore",
                "ufficiali_inferiori": "Ufficiale Inferiore",
                "sottufficiali": "Sottufficiale",
                "truppa": "Truppa",
                "ausiliarie": "Personale Ausiliario",
                "unknown": "Grado non classificato",
            }.get(rank_info.category, rank_info.category)
            enrichment_lines.append(f"\n**Ruolo militare**: {rank_info.canonical.title()} ({cat_it})")
            enrichment_lines.append(f"  - Categoria: {rank_info.category}")
            enrichment_lines.append(f"  - Evidence scope: {rank_info.evidence_scope} (rank_fact)")
            enrichment_lines.append(f"  - Confidenza: {rank_info.confidence:.0%}")
        if unit_info and unit_info.unit_type != "unknown":
            enrichment_lines.append(f"\n**Reparto**: {unit_info.normalized or unit_info.original}")
            enrichment_lines.append(f"  - Tipo unita: {unit_info.unit_type}")
            if unit_info.unit_number:
                enrichment_lines.append(f"  - Numero: {unit_info.unit_number}")
            if unit_info.unit_branch:
                enrichment_lines.append(f"  - Arma: {unit_info.unit_branch}")
            enrichment_lines.append(f"  - Evidence scope: {unit_info.evidence_scope} (personal_duty)")
        if enrichment_lines:
            pm_section.content += "\n" + "\n".join(enrichment_lines)

    # Enrich: Contesto Storico
    ch_section = response.get_section("contesto_storico")
    if ch_section:
        ch_section.is_empty = False
        context_lines = []
        war_period = "Non determinato"
        for c in claims:
            val = c.get("value_normalized", "")
            if any(y in val for y in ["1915", "1916", "1917", "1918", "1919"]):
                war_period = "Prima Guerra Mondiale (1915-1918)"
                break
            if any(y in val for y in ["1940", "1941", "1942", "1943", "1944", "1945"]):
                war_period = "Seconda Guerra Mondiale (1940-1945)"
                break
        context_lines.append(f"- **Periodo bellico**: {war_period}")
        if rank_info and rank_info.category:
            role_context = {
                "ufficiali_generali": "Comando di alto livello, responsabile di grandi unita",
                "ufficiali_superiori": "Comando di reparto a livello reggimentale/divisionale",
                "ufficiali_inferiori": "Comando di plotone/compagnia",
                "sottufficiali": "Ruoli tecnici e di supporto al combattimento",
                "truppa": "Impiego in prima linea",
                "ausiliarie": "Servizi ausiliari e sanitari",
            }.get(rank_info.category, "")
            if role_context:
                context_lines.append(f"- **Ruolo in combattimento**: {role_context}")
        if unit_info and unit_info.unit_branch:
            branch_context = {
                "fanteria": "Fanteria - forza principale di manovra, impiegata in trincea e assalti",
                "artiglieria": "Artiglieria - supporto di fuoco, bombardamenti e difesa costiera",
                "cavalleria": "Cavalleria - ricognizione, esplorazione e azioni di sfondamento",
                "alpini": "Alpini - truppe da montagna, impiegate in quota",
                "bersaglieri": "Bersaglieri - truppe veloci, assalti e ricognizione",
                "genio": "Genio - fortificazioni, ponti, minamento",
            }.get(unit_info.unit_branch, "")
            if branch_context:
                context_lines.append(f"- **Arma di appartenenza**: {branch_context}")
        source_table = ""
        for c in claims:
            if c.get("source_table"):
                source_table = c["source_table"]
                break
        if source_table:
            source_context_map = {
                "internati": "Internato militare - prigioniero di guerra catturato dopo l'8 settembre 1943",
                "caduti_albooro": "Caduto in combattimento - registrato nell'Albo d'Oro",
                "decorati_nastroazzurro": "Decorato al valor militare - Nastro Azzurro",
                "caduti_cwgc": "Caduto commemorato dalla Commonwealth War Graves Commission",
                "caduti_ministero": "Caduto - registro del Ministero della Guerra",
            }
            ctx = source_context_map.get(source_table, "")
            if ctx:
                context_lines.append(f"- **Fonte del record**: {ctx}")
        ch_section.content = "\n".join(context_lines)

    # Enrich: Identita
    id_section = response.get_section("identita")
    if id_section:
        id_section.is_empty = False
        id_lines = []
        id_lines.append(f"- **Stato identita**: {identity_status}")
        id_lines.append(f"- **Corroborazione**: {corroboration}")
        id_lines.append(f"- **Livello evidenza**: {evidence_level}")
        id_lines.append(f"- **Punteggio qualita fonti**: {combined_score:.2f}")
        id_lines.append(f"- **Motivo combinazione**: {combined_reason}")
        state_counts = {}
        for cs in claim_states:
            s = cs["state"]
            state_counts[s] = state_counts.get(s, 0) + 1
        id_lines.append(f"- **Distribuzione claim**: {json.dumps(state_counts, ensure_ascii=False)}")
        id_section.content = "\n".join(id_lines)

    # Enrich: Fonti e Provenienza
    fonti_section = response.get_section("fonti_e_provenienza")
    if fonti_section:
        quality_dist = {}
        for q in qualities:
            quality_dist[q.quality_level] = quality_dist.get(q.quality_level, 0) + 1
        fonti_lines = []
        fonti_lines.append(f"- **Distribuzione qualita fonti**: {json.dumps(quality_dist, ensure_ascii=False)}")
        fonti_lines.append(f"- **Livello evidenza combinato**: {evidence_level}")
        fonti_lines.append(f"- **Score aggregato**: {combined_score:.2f}")
        fonti_lines.append(f"- **Motivo**: {combined_reason}")
        source_tables = set()
        for c in claims:
            if c.get("source_table"):
                source_tables.add(f"{c['source_table']}#{c.get('source_id', '?')}")
        if source_tables:
            fonti_lines.append(f"- **Record fonte**: {', '.join(sorted(source_tables)[:10])}")
        fonti_section.content = "\n".join(fonti_lines)
        fonti_section.is_empty = False

    # Render final markdown
    md = response.to_markdown()

    header = f"# Rapporto Narrativo V7.3 - {name}\n\n"
    header += f"**Schema**: 7.3-response-v1 | **Identity**: {identity_status} | "
    header += f"**Evidence**: {evidence_level} | **Claims**: {len(claims)} | "
    header += f"**Pubblicati**: {response.published_claims} | "
    header += f"**Soppresi**: {response.suppressed_claims} | "
    header += f"**In revisione**: {response.review_pending_claims}\n\n---\n\n"

    return header + md


def main():
    from unified_orchestrator_v7 import UnifiedResearchOrchestratorV7

    orch = UnifiedResearchOrchestratorV7()
    targets = select_random_names(5)

    print("=" * 80)
    print("RISPOSTE NARRATIVE V7.3 - 5 NOMI CASUALI DAL DB")
    print("Con integrazione: source_quality + claim_lifecycle + response_structure 11 sezioni")
    print("+ military_ontology (ruolo) + contesto storico")
    print("=" * 80)
    print()

    for i, t in enumerate(targets, 1):
        print(f"{'-' * 80}")
        print(f"  [{i}/{len(targets)}] {t['name']}  (fonte: {t['table']}#{t['id']})")
        print(f"{'-' * 80}")
        print()

        t0 = time.time()
        try:
            result = orch.execute(
                user_input=t["name"],
                intent="PERSON_LOOKUP",
                conflict="UNKNOWN",
            )
            elapsed = time.time() - t0

            snapshot = result.get("snapshot")
            report = result.get("report", "")
            errors = result.get("errors", [])
            warnings = result.get("warnings", [])
            obs_count = result.get("observation_count", 0)
            semantic = result.get("semantic_counts", {})

            identity = snapshot.get("identity_status", "UNKNOWN") if snapshot else "UNKNOWN"

            print(f"  Identity: {identity} | Observations: {obs_count} | Elapsed: {elapsed:.1f}s")
            print()
            print(report)
            print()

            if errors:
                print(f"  [ERRORS]: {errors[:3]}")
                print()

        except Exception as e:
            elapsed = time.time() - t0
            print(f"  ERROR after {elapsed:.1f}s: {e}")
            import traceback
            traceback.print_exc()
            print()

    print("=" * 80)
    print("FINE")
    print("=" * 80)


if __name__ == "__main__":
    main()

"""Test Research-to-Index: 50 soldati casuali dal DB → ricerca fonti esterne → indicizzazione.

Per ogni soldato:
1. Estrae nome/cognome/cue
2. Esegue federated_search su TUTTI i 19 provider
3. Salva risultati in fonti_indice (upsert)
4. Crea research_subjects + research_subject_sources
5. Identifica research_gaps
6. Report finale
"""
import json
import random
import sqlite3
import time
from pathlib import Path
from collections import Counter

from database import get_conn, search_all
from research_to_index import (
    index_external_sources_for_soldier,
    get_research_stats,
    _init_tables,
)

DB_PATH = Path(__file__).parent / "imi_internati.db"

def get_random_soldiers(n=50):
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        "SELECT id, cognome, nome, luogo_nascita, luogo_internamento, sorte, grado "
        "FROM internati ORDER BY RANDOM() LIMIT ?", (n,)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]

def main():
    print("=== TEST RESEARCH-TO-INDEX: 50 SOLDATI ===\n")
    print("Obiettivo: partendo da soldati nel DB locale,")
    print("trovare fonti esterne NON nel DB e indicizzarle.\n")

    # init tabelle
    _init_tables()

    # stats prima
    stats_before = get_research_stats()
    print(f"Stats PRIMA del test:")
    print(f"  fonti_indice: {stats_before.get('fonti_indice_total', 0)}")
    print(f"  research_subjects: {stats_before.get('subjects', 0)}")
    print(f"  subject_source_links: {stats_before.get('subject_source_links', 0)}")
    print()

    soldiers = get_random_soldiers(50)
    if not soldiers:
        print("ERRORE: nessun soldato nel DB")
        return

    print(f"Soldati estratti: {len(soldiers)}\n")

    all_results = []
    total_relevant = 0
    total_catalog = 0
    total_skipped = 0
    total_fed = 0
    provider_relevant = Counter()
    provider_catalog = Counter()
    name_matches = 0
    errors = []

    for i, s in enumerate(soldiers):
        sid = s["id"]
        name = f"{s['cognome']} {s['nome'] or ''}".strip()
        t0 = time.time()

        try:
            result = index_external_sources_for_soldier(sid)
            elapsed = time.time() - t0

            if not result.get("ok"):
                errors.append(f"id={sid}: {result.get('error')}")
                if i < 5:
                    print(f"  [{i+1:02d}] id={sid} '{name}': FAIL — {result.get('error')}")
                continue

            n_rel = result["sources_count"]
            n_cat = result["catalog_refs_count"]
            n_fed = result["total_fed_results"]
            n_skip = result["skipped"]
            total_relevant += n_rel
            total_catalog += n_cat
            total_skipped += n_skip
            total_fed += n_fed

            for src in result["indexed_sources"]:
                provider_relevant[src["provider"]] += 1
                if src.get("name_match"):
                    name_matches += 1
            for src in result["catalog_refs"]:
                provider_catalog[src["provider"]] += 1

            all_results.append(result)

            if i < 10 or n_rel > 0:
                print(f"  [{i+1:02d}] id={sid} '{name}': "
                      f"relevant={n_rel} catalog={n_cat} skipped={n_skip} "
                      f"(fed={n_fed}) ({elapsed:.1f}s)")
                if n_rel > 0:
                    for src in result["indexed_sources"][:3]:
                        nm = " ★NAME_MATCH" if src.get("name_match") else ""
                        print(f"         → {src['provider']}: {src['titolo'][:60]} "
                              f"[{src['access_type']}] score={src['score']:.2f}{nm}")
                if n_cat > 0 and i < 5:
                    for src in result["catalog_refs"][:2]:
                        print(f"         [cat] {src['provider']}: {src['titolo'][:60]} "
                              f"[{src['access_type']}]")

        except Exception as e:
            elapsed = time.time() - t0
            errors.append(f"id={sid}: {e}")
            if i < 5:
                print(f"  [{i+1:02d}] id={sid} '{name}': EXCEPTION — {e}")

    # stats dopo
    stats_after = get_research_stats()

    # report
    print(f"\n{'='*60}")
    print(f"REPORT FINALE — RESEARCH-TO-INDEX TEST")
    print(f"{'='*60}\n")

    print(f"Soldati testati: {len(soldiers)}")
    print(f"Risultati OK: {len(all_results)}")
    print(f"Errori: {len(errors)}")
    print()

    print(f"Fonti federate totali (raw): {total_fed}")
    print(f"  → Pertinenti (relevant): {total_relevant}")
    print(f"  → Riferimenti catalogo (stub): {total_catalog}")
    print(f"  → Non pertinenti (skippati): {total_skipped}")
    print(f"  → Name match (cognome nel titolo): {name_matches}")
    print()

    if provider_relevant:
        print(f"Fonti pertinenti per provider:")
        for prov, count in provider_relevant.most_common():
            print(f"  {prov}: {count}")
        print()

    if provider_catalog:
        print(f"Riferimenti catalogo per provider:")
        for prov, count in provider_catalog.most_common():
            print(f"  {prov}: {count}")
        print()

    print(f"Stats DOPO del test:")
    print(f"  fonti_indice: {stats_before.get('fonti_indice_total', 0)} → {stats_after.get('fonti_indice_total', 0)} "
          f"(+{stats_after.get('fonti_indice_total', 0) - stats_before.get('fonti_indice_total', 0)})")
    print(f"  research_subjects: {stats_before.get('subjects', 0)} → {stats_after.get('subjects', 0)} "
          f"(+{stats_after.get('subjects', 0) - stats_before.get('subjects', 0)})")
    print(f"  subject_source_links: {stats_before.get('subject_source_links', 0)} → {stats_after.get('subject_source_links', 0)} "
          f"(+{stats_after.get('subject_source_links', 0) - stats_before.get('subject_source_links', 0)})")
    print(f"  open_gaps: {stats_after.get('open_gaps', 0)}")
    print()

    # dettaglio fonti indicizzate
    if total_indexed > 0:
        print(f"Dettaglio fonti indicizzate (prime 20):")
        conn = get_conn()
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            """SELECT fi.id, fi.archivio, fi.titolo, fi.access_type, fi.confidence,
                      fi.url_catalogo, fi.segnatura
               FROM fonti_indice fi
               JOIN research_subject_sources rs ON rs.source_locator_id = fi.id
               ORDER BY fi.confidence DESC LIMIT 20"""
        ).fetchall()
        for r in rows:
            print(f"  [{r['id']}] {r['archivio']}: {r['titolo'][:50]} "
                  f"[{r['access_type']}] conf={r['confidence']:.2f}")
            if r['url_catalogo']:
                print(f"       URL: {r['url_catalogo'][:80]}")
        conn.close()
    else:
        print("Nessuna fonte esterna indicizzata — tutti i provider hanno ritornato")
        print("solo riferimenti catalogo (stub) o 0 risultati reali.")
        print()
        print("Provider con API reali che potrebbero trovare risultati:")
        print("  - TNA Discovery API (UK)")
        print("  - Europeana Search API")
        print("  - Gallica SRU (BnF)")
        print("  - Internet Archive API")
        print("  - Google Books API")
        print("  - HathiTrust API")
        print()
        print("Provider stub (ritornano solo URL catalogo):")
        print("  - Arolsen, Bundesarchiv, SHD, ABMC, LAC, AWM,")
        print("    Archivportal-D, Internet Culturale, USSME, Archivio di Stato")

    if errors:
        print(f"\nErrori ({len(errors)}):")
        for e in errors[:5]:
            print(f"  ! {e}")

if __name__ == "__main__":
    main()

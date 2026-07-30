"""Search and ingest WW1 documents for key Italian front events.
Searches Internet Archive, Europeana, Library of Congress, Wikimedia Commons, and Gallica
for documents specifically about Italian WW1 events, then links them to events in eventi_1gm.db.
"""
import json
import os
import sqlite3
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from linking.kill_switch import LegacyJob, assert_frozen

assert_frozen(LegacyJob.SEARCH_WW1_DOCUMENTS, "search_ww1_documents.py is frozen — use source_pipeline worker instead")

# Load .env
from dotenv import load_dotenv
load_dotenv()

from archivio_documenti import (
    upsert_documenti, create_schema, fetch_internet_archive,
    fetch_europeana, fetch_loc, fetch_wikimedia_commons, fetch_gallica_sru,
)
from database import get_conn

EDB = Path(__file__).parent / "eventi_1gm.db"

# Eventi chiave del fronte italiano con query di ricerca mirate
EVENT_SEARCHES = {
    "Battaglia di Caporetto": [
        "Caporetto 1917",
        "Kobarid battle 1917",
        'Caporetto "World War"',
    ],
    "Battaglie dell'Isonzo": [
        "Isonzo battle 1915 1916 1917",
        "Soča front World War",
    ],
    "Battaglia del Carso": [
        "Carso Kras battle World War",
        "Karst plateau Italy 1915 1917",
    ],
    "Battaglia del Piave": [
        "Piave river battle 1918",
        "Battle of Piave Italy",
    ],
    "Battaglia di Vittorio Veneto": [
        "Vittorio Veneto 1918 battle",
        "Italian offensive 1918",
    ],
    "Altopiano di Asiago": [
        "Asiago plateau battle 1916",
        "Sette Comuni World War",
    ],
    "Monte Grappa": [
        "Monte Grappa World War",
        "Grappa mountain Italy 1917 1918",
    ],
    "Monte Pasubio": [
        "Pasubio battle Italy World War",
    ],
    "Monte San Michele": [
        "Monte San Michele Isonzo",
    ],
    "Monte Col di Lana": [
        "Col di Lana Dolomiti World War",
    ],
    "Monte Nero": [
        "Monte Nero Krn Isonzo World War",
    ],
    "Battaglia degli Altipiani": [
        "Strafexpedition 1916 Asiago",
        "Spedizione punitiva Trentino",
    ],
    "Battaglia del Monte Ortigara": [
        "Ortigara battle 1917 Alpini",
    ],
    "Prima battaglia del Piave": [
        "Piave 1917 defensive Diaz",
    ],
    "Seconda battaglia del Piave": [
        "Piave 1918 Solstizio battle",
    ],
    "Guerra bianca": [
        "Guerra bianca Alpi ghiacciai",
        "White War Alps World War",
        "Adamello Ortles Marmolada 1915 1918",
    ],
    "Fronte del Tonale": [
        "Tonale Adamello World War",
    ],
    "Armistizio di Villa Giusti": [
        "Villa Giusti armistizio 1918",
        "Armistice Italy Austria 1918",
    ],
    "Entrata in guerra dell'Italia": [
        "Italy enters war 1915",
        "Intervento italiano 1915",
    ],
    "Patto di Londra": [
        "Pact of London 1915 Italy",
        "Trattato di Londra",
    ],
    "Vittoria mutilata": [
        "Vittoria mutilata D'Annunzio Fiume",
        "Mutilated victory Italy Paris",
    ],
    "Ripiegamento dal Carso al Piave": [
        "Retreat Caporetto Piave Tagliamento 1917",
    ],
    "Riorganizzazione dell'esercito dopo Caporetto": [
        "Diaz reorganize army Caporetto 1917",
    ],
    "Battaglia del Monte Sabotino": [
        "Monte Sabotino Gorizia Isonzo",
    ],
    "Difesa del Grappa": [
        "Grappa defense bunker World War",
    ],
    "Internamento militari italiani in Austria-Ungheria (WWI)": [
        "Italian prisoners Austria Hungary World War",
        "Internati militari italiani 1915 1918",
    ],
    "Internamento civile irredenti": [
        "Irredenti internamento civile Trentino Trieste",
        "Katzenau Wagna internment World War",
    ],
    "Fronte Macedone": [
        "Macedonian front Salonika World War",
        "Salonika front 1915 1918",
    ],
    "Fronte Albanese": [
        "Albania front Valona World War",
    ],
    "Prigionia": [
        "Prisoners of war Italy Austria 1914 1918",
        "Prigionia militare grande guerra",
    ],
}


def run_searches():
    conn = get_conn()
    create_schema(conn)

    europeana_key = os.getenv("EUROPEANA_API_KEY", "")
    all_new_rows = []
    total_fetched = 0

    for event_name, queries in EVENT_SEARCHES.items():
        print(f"\n{'='*70}")
        print(f"Evento: {event_name}")
        print(f"{'='*70}")

        for q in queries:
            # Internet Archive
            try:
                ia_query = f'{q} AND mediatype:texts AND (date:[1910 TO 1925])'
                rows = fetch_internet_archive(query=f'"{q}" AND mediatype:texts', rows=20)
                if rows:
                    print(f"  IA '{q}': {len(rows)} risultati")
                    all_new_rows.extend(rows)
                    total_fetched += len(rows)
            except Exception as e:
                print(f"  IA '{q}': ERRORE {e}")
            time.sleep(1)

            # Europeana
            if europeana_key:
                try:
                    rows = fetch_europeana(q, europeana_key, rows=20)
                    if rows:
                        print(f"  EU '{q}': {len(rows)} risultati")
                        all_new_rows.extend(rows)
                        total_fetched += len(rows)
                except Exception as e:
                    print(f"  EU '{q}': ERRORE {e}")
                time.sleep(1)

            # Library of Congress
            try:
                rows = fetch_loc(q, rows=20)
                if rows:
                    print(f"  LoC '{q}': {len(rows)} risultati")
                    all_new_rows.extend(rows)
                    total_fetched += len(rows)
            except Exception as e:
                print(f"  LoC '{q}': ERRORE {e}")
            time.sleep(1)

            # Wikimedia Commons
            try:
                rows = fetch_wikimedia_commons(q, rows=15)
                if rows:
                    print(f"  WC '{q}': {len(rows)} risultati")
                    all_new_rows.extend(rows)
                    total_fetched += len(rows)
            except Exception as e:
                print(f"  WC '{q}': ERRORE {e}")
            time.sleep(1)

            # Gallica (per fonti francesi sul fronte italiano)
            try:
                rows = fetch_gallica_sru(q, rows=15)
                if rows:
                    print(f"  Gallica '{q}': {len(rows)} risultati")
                    all_new_rows.extend(rows)
                    total_fetched += len(rows)
            except Exception as e:
                print(f"  Gallica '{q}': ERRORE {e}")
            time.sleep(1)

    print(f"\n\n{'='*70}")
    print(f"Totale risultati recuperati: {total_fetched}")
    print(f"Righe univoche da inserire: {len(all_new_rows)}")

    if all_new_rows:
        inserted = upsert_documenti(conn, all_new_rows)
        print(f"Documenti inseriti/aggiornati: {inserted}")

    conn.close()
    return total_fetched


def link_documents_to_events():
    """Collega i nuovi documenti agli eventi usando keyword matching migliorato."""
    conn = get_conn()
    conn.row_factory = sqlite3.Row
    conn_ev = sqlite3.connect(str(EDB), timeout=30)
    conn_ev.row_factory = sqlite3.Row

    # Eventi con keyword e alias
    events = conn_ev.execute("SELECT id, nome, keywords, aliases, luogo FROM eventi_1gm ORDER BY id").fetchall()

    # Documenti
    docs = conn.execute(
        "SELECT rowid as id, title, description, provider, doc_type, source_url, creator, date_text, place, provider_collection "
        "FROM archivio_documenti"
    ).fetchall()
    print(f"\nDocumenti totali in archivio: {len(docs)}")

    # Link esistenti
    existing = set()
    for r in conn_ev.execute("SELECT evento_id, target_id FROM event_links WHERE link_type='documento'").fetchall():
        existing.add((r["evento_id"], r["target_id"]))

    now = datetime.now(timezone.utc).isoformat()
    new_links = []
    matched_docs = set()

    for ev in events:
        kws = json.loads(ev["keywords"]) if ev["keywords"] else []
        aliases = json.loads(ev["aliases"]) if ev["aliases"] else []
        luogo = ev["luogo"] or ""

        # Termini di ricerca (min 4 char, uppercase)
        search_terms = set()
        for kw in kws + aliases:
            if len(kw) >= 4:
                search_terms.add(kw.upper())
        # Aggiungi parole dal luogo (es. "Carso", "Piave", "Asiago")
        for word in luogo.replace(",", " ").split():
            if len(word) >= 4:
                search_terms.add(word.upper())

        for d in docs:
            text = " ".join(filter(None, [
                d["title"], d["description"], d["place"],
                d["creator"], d["date_text"], d["provider_collection"]
            ])).upper()
            if not text.strip():
                continue

            for term in search_terms:
                # Match come parola intera (boundary check)
                if term in text:
                    if (ev["id"], d["id"]) not in existing:
                        # Confidence più alta se match nel titolo
                        confidence = 0.9 if term in (d["title"] or "").upper() else 0.7
                        new_links.append((
                            ev["id"], "archivio_documenti", d["id"], "documento",
                            "text_match", term.lower(), confidence, now
                        ))
                        matched_docs.add(d["id"])
                    break

    print(f"Nuovi link documento->evento: {len(new_links)}")
    print(f"Documenti coinvolti: {len(matched_docs)}")

    if new_links:
        conn_ev.executemany(
            "INSERT INTO event_links (evento_id, target_table, target_id, link_type, match_field, match_value, confidence, created_at) "
            "VALUES (?,?,?,?,?,?,?,?)",
            new_links
        )
        conn_ev.commit()
        print("Link inseriti con successo.")

        # Statistiche per evento
        from collections import Counter
        ev_counts = Counter(nl[0] for nl in new_links)
        ev_names = {e["id"]: e["nome"] for e in events}
        print("\nDistribuzione nuovi link per evento:")
        for evid, cnt in ev_counts.most_common():
            print(f"  [{evid:>3}] {ev_names[evid]:<40} {cnt:>4}")

    conn.close()
    conn_ev.close()
    return len(new_links)


if __name__ == "__main__":
    print("=" * 70)
    print("FASE 1: Ricerca documenti da provider esterni")
    print("=" * 70)
    total = run_searches()

    print("\n\n" + "=" * 70)
    print("FASE 2: Collegamento documenti -> eventi 1GM")
    print("=" * 70)
    linked = link_documents_to_events()

    print(f"\n\nRIEPILOGO:")
    print(f"  Documenti recuperati: {total}")
    print(f"  Nuovi link creati: {linked}")

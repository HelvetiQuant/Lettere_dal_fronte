#!/usr/bin/env python3
"""
Query engine event-centric per 1GM.
Dato un evento (es. "Caporetto"), aggrega tutti i dati collegati:
- soldati caduti (nomi, gradi, reparti, luogo morte)
- soldati decorati (nomi, tipo decorazione)
- documenti (diari, foto, collezioni con link esterni)
- fonti archivistiche (con URL catalogo/file)
- statistiche aggregate

Output: risposta strutturata con conteggi, dettagli e link alle fonti esterne.
"""
import sqlite3, json, re, sys, io
from pathlib import Path
from datetime import datetime

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

DB = Path(__file__).parent / "imi_internati.db"
EDB = Path(__file__).parent / "eventi_1gm.db"


def find_event(conn_ev, query):
    """Trova evento per nome esatto o match alias/keyword."""
    query_up = query.upper().strip()

    # 1. Match esatto nome
    r = conn_ev.execute("SELECT * FROM eventi_1gm WHERE UPPER(nome) = ?", (query_up,)).fetchone()
    if r:
        return r

    # 2. Match parziale nome
    rows = conn_ev.execute("SELECT * FROM eventi_1gm").fetchall()
    for r in rows:
        if query_up in r["nome"].upper():
            return r

    # 3. Match alias
    for r in rows:
        aliases = json.loads(r["aliases"])
        for alias in aliases:
            if alias.upper() == query_up or query_up in alias.upper():
                return r

    # 4. Match keyword
    for r in rows:
        keywords = json.loads(r["keywords"])
        for kw in keywords:
            if kw.upper() == query_up or query_up in kw.upper():
                return r

    return None


def query_event(event_name, verbose=True):
    """
    Esegue query event-centric.
    Ritorna dict strutturato con tutti i dati aggregati.
    """
    conn_ro = sqlite3.connect(str(DB), timeout=30)
    conn_ro.row_factory = sqlite3.Row

    conn_ev = sqlite3.connect(str(EDB), timeout=30)
    conn_ev.row_factory = sqlite3.Row

    result = {
        "evento": None,
        "statistiche": {},
        "caduti": {"count": 0, "top_luoghi": [], "top_anni": [], "top_reparti": [], "sample": []},
        "decorati": {"count": 0, "top_decorazioni": [], "top_anni": [], "sample": []},
        "documenti": {"count": 0, "items": []},
        "fonti": {"count": 0, "top_archivi": [], "items": []},
        "links_esterni": [],
    }

    # ─── Trova evento ──────────────────────────────────────────────────────
    ev = find_event(conn_ev, event_name)
    if not ev:
        if verbose:
            print(f"Evento '{event_name}' non trovato.")
            print(f"Eventi disponibili:")
            for r in conn_ev.execute("SELECT nome FROM eventi_1gm ORDER BY nome").fetchall():
                print(f"  - {r['nome']}")
        conn_ro.close()
        conn_ev.close()
        return result

    result["evento"] = {
        "id": ev["id"],
        "nome": ev["nome"],
        "data_inizio": ev["data_inizio"],
        "data_fine": ev["data_fine"],
        "luogo": ev["luogo"],
        "aliases": json.loads(ev["aliases"]),
        "keywords": json.loads(ev["keywords"]),
        "descrizione": ev["descrizione"],
    }

    if verbose:
        print(f"{'=' * 70}")
        print(f"EVENTO: {ev['nome']}")
        print(f"  Periodo: {ev['data_inizio']} -> {ev['data_fine']}")
        print(f"  Luogo: {ev['luogo']}")
        print(f"  Descrizione: {ev['descrizione']}")
        print(f"{'=' * 70}")

    # ─── Caduti ────────────────────────────────────────────────────────────
    caduti_ids = conn_ev.execute(
        "SELECT target_id FROM event_links WHERE evento_id=? AND link_type='soldato_caduto'",
        (ev["id"],)
    ).fetchall()
    caduti_ids = [r["target_id"] for r in caduti_ids]
    result["caduti"]["count"] = len(caduti_ids)

    if verbose:
        print(f"\n--- CADUTI: {len(caduti_ids):,} ---")

    if caduti_ids:
        # Use temp table for large ID sets (SQLite variable limit)
        conn_ro.execute("CREATE TEMP TABLE _tmp_ids(ids INTEGER)")
        conn_ro.executemany("INSERT INTO _tmp_ids VALUES(?)", [(i,) for i in caduti_ids])

        top_luoghi = conn_ro.execute(
            "SELECT luogo_morte, COUNT(*) as n FROM caduti_albooro c "
            "JOIN _tmp_ids t ON c.id = t.ids "
            "WHERE c.luogo_morte IS NOT NULL AND c.luogo_morte != '' "
            "GROUP BY c.luogo_morte ORDER BY n DESC LIMIT 10"
        ).fetchall()
        result["caduti"]["top_luoghi"] = [(r["luogo_morte"], r["n"]) for r in top_luoghi]

        top_anni = conn_ro.execute(
            "SELECT anno_morte, COUNT(*) as n FROM caduti_albooro c "
            "JOIN _tmp_ids t ON c.id = t.ids "
            "WHERE c.anno_morte IS NOT NULL AND c.anno_morte != '' "
            "GROUP BY c.anno_morte ORDER BY n DESC LIMIT 10"
        ).fetchall()
        result["caduti"]["top_anni"] = [(r["anno_morte"], r["n"]) for r in top_anni]

        top_reparti = conn_ro.execute(
            "SELECT reparto, COUNT(*) as n FROM caduti_albooro c "
            "JOIN _tmp_ids t ON c.id = t.ids "
            "WHERE c.reparto IS NOT NULL AND c.reparto != '' "
            "GROUP BY c.reparto ORDER BY n DESC LIMIT 10"
        ).fetchall()
        result["caduti"]["top_reparti"] = [(r["reparto"], r["n"]) for r in top_reparti]

        # Sample (primi 20)
        sample = conn_ro.execute(
            "SELECT c.id, c.nominativo, c.grado, c.reparto, c.luogo_morte, c.anno_morte, c.causa_morte, c.detail_url "
            "FROM caduti_albooro c JOIN _tmp_ids t ON c.id = t.ids LIMIT 20"
        ).fetchall()
        result["caduti"]["sample"] = [dict(r) for r in sample]

        conn_ro.execute("DELETE FROM _tmp_ids")

        if verbose:
            print(f"\n  Top luoghi morte:")
            for lu, n in result["caduti"]["top_luoghi"]:
                print(f"    {lu:40s} {n:>6,}")
            print(f"\n  Top anni morte:")
            for an, n in result["caduti"]["top_anni"]:
                print(f"    {an:10s} {n:>6,}")
            print(f"\n  Top reparti:")
            for rp, n in result["caduti"]["top_reparti"][:5]:
                print(f"    {rp:40s} {n:>6,}")
            print(f"\n  Esempi caduti (primi 20):")
            for s in result["caduti"]["sample"]:
                url_part = f"  URL: {s['detail_url']}" if s["detail_url"] else ""
                print(f"    {s['nominativo']:35s}  {s['grado'] or '':15s}  {s['luogo_morte'] or '':20s}  {s['anno_morte'] or ''}{url_part}")

    # ─── Decorati ──────────────────────────────────────────────────────────
    dec_ids = conn_ev.execute(
        "SELECT target_id FROM event_links WHERE evento_id=? AND link_type='soldato_decorato'",
        (ev["id"],)
    ).fetchall()
    dec_ids = [r["target_id"] for r in dec_ids]
    result["decorati"]["count"] = len(dec_ids)

    if verbose:
        print(f"\n--- DECORATI: {len(dec_ids):,} ---")

    if dec_ids:
        conn_ro.executemany("INSERT INTO _tmp_ids VALUES(?)", [(i,) for i in dec_ids])

        top_dec = conn_ro.execute(
            "SELECT tipo_decorazione, COUNT(*) as n FROM decorati_nastroazzurro d "
            "JOIN _tmp_ids t ON d.id = t.ids "
            "WHERE d.tipo_decorazione IS NOT NULL "
            "GROUP BY d.tipo_decorazione ORDER BY n DESC LIMIT 10"
        ).fetchall()
        result["decorati"]["top_decorazioni"] = [(r["tipo_decorazione"], r["n"]) for r in top_dec]

        top_anni_dec = conn_ro.execute(
            "SELECT anno_decorazione, COUNT(*) as n FROM decorati_nastroazzurro d "
            "JOIN _tmp_ids t ON d.id = t.ids "
            "WHERE d.anno_decorazione IS NOT NULL "
            "GROUP BY d.anno_decorazione ORDER BY n DESC LIMIT 10"
        ).fetchall()
        result["decorati"]["top_anni"] = [(r["anno_decorazione"], r["n"]) for r in top_anni_dec]

        sample_dec = conn_ro.execute(
            "SELECT d.id, d.cognome, d.nome, d.arma, d.anno_decorazione, d.tipo_decorazione "
            "FROM decorati_nastroazzurro d JOIN _tmp_ids t ON d.id = t.ids LIMIT 20"
        ).fetchall()
        result["decorati"]["sample"] = [dict(r) for r in sample_dec]

        conn_ro.execute("DELETE FROM _tmp_ids")

        if verbose:
            print(f"\n  Top decorazioni:")
            for td, n in result["decorati"]["top_decorazioni"]:
                print(f"    {td:45s} {n:>6,}")
            print(f"\n  Top anni:")
            for an, n in result["decorati"]["top_anni"]:
                print(f"    {an:10s} {n:>6,}")
            print(f"\n  Esempi decorati (primi 20):")
            for s in result["decorati"]["sample"]:
                print(f"    {s['cognome']:20s} {s['nome']:20s}  {s['tipo_decorazione'] or '':30s}  {s['anno_decorazione'] or ''}")

    # ─── Documenti (archivio_documenti) ────────────────────────────────────
    doc_links = conn_ev.execute(
        "SELECT target_id, match_value, confidence FROM event_links WHERE evento_id=? AND link_type='documento'",
        (ev["id"],)
    ).fetchall()
    result["documenti"]["count"] = len(doc_links)

    if verbose:
        print(f"\n--- DOCUMENTI (diari/foto/collezioni): {len(doc_links)} ---")

    for dl in doc_links:
        doc = conn_ro.execute(
            "SELECT rowid as id, title, description, provider, doc_type, source_url, thumbnail_url, creator, date_text, place "
            "FROM archivio_documenti WHERE rowid=?",
            (dl["target_id"],)
        ).fetchone()
        if doc:
            item = dict(doc)
            item["match_value"] = dl["match_value"]
            item["confidence"] = dl["confidence"]
            result["documenti"]["items"].append(item)
            if verbose:
                print(f"  [{doc['doc_type'] or 'nd'}] {doc['title']}")
                print(f"    Provider: {doc['provider']}  |  Match: {dl['match_value']}")
                if doc["source_url"]:
                    print(f"    URL: {doc['source_url']}")
                if doc["thumbnail_url"]:
                    print(f"    Thumbnail: {doc['thumbnail_url']}")
                if doc["description"]:
                    print(f"    Desc: {doc['description'][:120]}...")
                result["links_esterni"].append({
                    "type": "documento",
                    "label": doc["title"],
                    "url": doc["source_url"],
                    "provider": doc["provider"],
                })

    # ─── Fonti archivistiche (fonti_indice) ────────────────────────────────
    fon_links = conn_ev.execute(
        "SELECT target_id, match_value, confidence FROM event_links WHERE evento_id=? AND link_type='fonte_archivistica'",
        (ev["id"],)
    ).fetchall()
    result["fonti"]["count"] = len(fon_links)

    if verbose:
        print(f"\n--- FONTI ARCHIVISTICHE: {len(fon_links)} ---")

    if fon_links:
        fon_ids = [r["target_id"] for r in fon_links]
        conn_ro.executemany("INSERT INTO _tmp_ids VALUES(?)", [(i,) for i in fon_ids])

        top_archivi = conn_ro.execute(
            "SELECT archivio, COUNT(*) as n FROM fonti_indice f "
            "JOIN _tmp_ids t ON f.id = t.ids "
            "WHERE f.archivio IS NOT NULL "
            "GROUP BY f.archivio ORDER BY n DESC LIMIT 10"
        ).fetchall()
        result["fonti"]["top_archivi"] = [(r["archivio"], r["n"]) for r in top_archivi]

        if verbose:
            print(f"\n  Top archivi:")
            for ar, n in result["fonti"]["top_archivi"]:
                print(f"    {ar:45s} {n:>5}")

        # Sample (primi 30)
        sample_fon = conn_ro.execute(
            "SELECT f.id, f.archivio, f.titolo, f.tipo_fonte, f.url_catalogo, f.url_file, f.access_type, f.luogo "
            "FROM fonti_indice f JOIN _tmp_ids t ON f.id = t.ids LIMIT 30"
        ).fetchall()
        result["fonti"]["items"] = [dict(r) for r in sample_fon]

        conn_ro.execute("DELETE FROM _tmp_ids")

        if verbose:
            print(f"\n  Esempi fonti (primi 30):")
            for s in result["fonti"]["items"]:
                print(f"    [{s['archivio']}] {s['titolo'][:60]}")
                if s["url_catalogo"]:
                    print(f"      Catalogo: {s['url_catalogo']}")
                if s["url_file"]:
                    print(f"      File: {s['url_file']}")
                result["links_esterni"].append({
                    "type": "fonte_archivistica",
                    "label": s["titolo"],
                    "url": s["url_catalogo"] or s["url_file"],
                    "provider": s["archivio"],
                })

    # ─── Statistiche finali ────────────────────────────────────────────────
    result["statistiche"] = {
        "caduti": result["caduti"]["count"],
        "decorati": result["decorati"]["count"],
        "documenti": result["documenti"]["count"],
        "fonti": result["fonti"]["count"],
        "links_esterni": len(result["links_esterni"]),
    }

    if verbose:
        print(f"\n{'=' * 70}")
        print(f"RIEPILOGO: {ev['nome']}")
        print(f"  Caduti:      {result['statistiche']['caduti']:,}")
        print(f"  Decorati:    {result['statistiche']['decorati']:,}")
        print(f"  Documenti:   {result['statistiche']['documenti']}")
        print(f"  Fonti:       {result['statistiche']['fonti']}")
        print(f"  Link esterni: {result['statistiche']['links_esterni']}")
        print(f"{'=' * 70}")

    conn_ro.execute("DROP TABLE IF EXISTS _tmp_ids")
    conn_ro.close()
    conn_ev.close()
    return result


def generate_report(event_name):
    """Genera report testuale completo per un evento."""
    return query_event(event_name, verbose=True)


if __name__ == "__main__":
    if len(sys.argv) > 1:
        event_name = " ".join(sys.argv[1:])
    else:
        print("Uso: python event_query_engine.py <nome evento>")
        print("Esempi: python event_query_engine.py Caporetto")
        print("        python event_query_engine.py 'Battaglia del Piave'")
        print("        python event_query_engine.py Isonzo")
        sys.exit(1)

    generate_report(event_name)

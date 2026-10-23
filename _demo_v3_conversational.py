"""Query 6 real names and 3 real events, run V3 LinkDecisionEngine, print conversational results."""
import sqlite3
import json
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from source_authority_registry import SourceAuthorityRegistry, LinkDecisionEngine, RULE_VERSION, TIER_NAMES

DB = os.path.join(os.path.dirname(__file__), "imi_internati.db")
EDB = os.path.join(os.path.dirname(__file__), "eventi_1gm.db")

# ─── Connect ──────────────────────────────────────────────────────────────────
conn = sqlite3.connect(DB, timeout=30)
conn.row_factory = sqlite3.Row
conn_ev = sqlite3.connect(EDB, timeout=30)
conn_ev.row_factory = sqlite3.Row

registry = SourceAuthorityRegistry(conn_ev)
engine = LinkDecisionEngine(registry)

# ─── Pick 6 real names from internati ─────────────────────────────────────────
print("=" * 80)
print("V3 SOURCE AUTHORITY — RISULTATI CONVERSAZIONALI SU 6 NOMI E 3 EVENTI")
print("=" * 80)

internati = conn.execute("""
    SELECT id, cognome, nome, data_nascita, luogo_nascita, matricola, grado,
           luogo_cattura, data_cattura, luogo_internamento, sorte, residenza
    FROM internati
    WHERE cognome IS NOT NULL AND cognome != '' AND LENGTH(cognome) > 2
    ORDER BY RANDOM() LIMIT 6
""").fetchall()

# ─── For each name: try to match against caduti_albooro and caduti_ministero ──
for idx, person in enumerate(internati, 1):
    p = dict(person)
    cognome = (p.get("cognome") or "").strip().upper()
    nome = (p.get("nome") or "").strip().upper()

    print(f"\n{'─' * 80}")
    print(f"NOME {idx}/6: {cognome} {nome}")
    print(f"  Fonte: internati (ID={p['id']})")
    print(f"  Nato: {p.get('data_nascita','?')} a {p.get('luogo_nascita','?')}")
    print(f"  Matricola: {p.get('matricola','?')}")
    print(f"  Grado: {p.get('grado','?')} | Residenza: {p.get('residenza','?')}")
    print(f"  Cattura: {p.get('data_cattura','?')} a {p.get('luogo_cattura','?')}")
    print(f"  Internamento: {p.get('luogo_internamento','?')}")
    print(f"  Sorte: {p.get('sorte','?')}")

    # Search candidates in caduti_albooro
    candidates_albo = conn.execute(
        "SELECT id, nominativo, anno_morte, luogo_morte, classe, grado "
        "FROM caduti_albooro WHERE nominativo LIKE ? LIMIT 10",
        (f"{cognome} {nome}%",) if nome else (f"{cognome}%",)
    ).fetchall()

    # Search candidates in caduti_ministero
    candidates_min = conn.execute(
        "SELECT id, cognome, nome, data_nascita, data_decesso, comune_nascita, paternita "
        "FROM caduti_ministero WHERE cognome = ? AND nome LIKE ? LIMIT 10",
        (cognome, f"{nome}%") if nome else (cognome, "%")
    ).fetchall()

    all_results = []

    # Evaluate against caduti_albooro
    for cand in candidates_albo:
        c = dict(cand)
        nom_parts = (c.get("nominativo") or "").split()
        c["cognome"] = nom_parts[0] if nom_parts else ""
        c["nome"] = " ".join(nom_parts[1:]) if len(nom_parts) > 1 else ""
        c["data_nascita"] = c.get("classe", "")
        c["data_decesso"] = c.get("anno_morte", "")
        c["luogo_nascita"] = ""
        c["matricola"] = ""

        decision = engine.evaluate_record_link(
            p, c, source_key="internati_imi", target_key="albo_oro",
            extraction_confidence=0.90
        )
        all_results.append(("caduti_albooro", c["id"], c.get("nominativo",""), decision))

    # Evaluate against caduti_ministero
    for cand in candidates_min:
        c = dict(cand)
        decision = engine.evaluate_record_link(
            p, c, source_key="internati_imi", target_key="ministero_difesa",
            extraction_confidence=0.90
        )
        all_results.append(("caduti_ministero", c["id"], f"{c.get('cognome','')} {c.get('nome','')}", decision))

    if not all_results:
        print(f"\n  ⚠ NESSUN candidato trovato in caduti_albooro o caduti_ministero")
        print(f"  → STATUS: unverified | MOTIVO: nessuna corrispondenza nominativa")
        continue

    for table, cid, nominativo, dec in all_results:
        status_icon = {
            "verified": "✅",
            "probable": "🟢",
            "possible": "🟡",
            "unverified": "⚪",
            "conflicting": "🔴",
            "rejected": "❌",
            "needs_review": "🔍",
        }.get(dec.status, "❓")

        print(f"\n  → Match: {table}#{cid} — {nominativo}")
        print(f"    {status_icon} STATUS: {dec.status}")
        print(f"    AUTHORITY: {dec.source_authority}")
        print(f"    MATCH CONFIDENCE: {dec.match_confidence:.2f}")
        print(f"    EXTRACTION CONFIDENCE: {dec.extraction_confidence:.2f}")
        print(f"    CONFLICT CODE: {dec.conflict_code or 'nessuno'}")
        print(f"    NEEDS REVIEW: {'SÌ' if dec.needs_review else 'no'}")
        print(f"    DECISION REASON: {dec.decision_reason}")
        if dec.evidence:
            ev_str = json.dumps(dec.evidence, ensure_ascii=False, indent=6)
            for line in ev_str.split("\n"):
                print(f"    {line}")

# ─── Pick 3 real events ───────────────────────────────────────────────────────
print(f"\n{'=' * 80}")
print(f"3 EVENTI — COLLEGAMENTO CON FONTI")
print(f"{'=' * 80}")

events = conn_ev.execute("""
    SELECT id, nome, data_inizio, data_fine, luogo, aliases, keywords, descrizione
    FROM eventi_1gm
    WHERE data_inizio IS NOT NULL AND data_inizio != ''
    ORDER BY RANDOM() LIMIT 3
""").fetchall()

for idx, ev in enumerate(events, 1):
    e = dict(ev)
    print(f"\n{'─' * 80}")
    print(f"EVENTO {idx}/3: {e['nome']}")
    print(f"  Periodo: {e.get('data_inizio','?')} → {e.get('data_fine','?')}")
    print(f"  Luogo: {e.get('luogo','?')}")
    aliases = json.loads(e.get("aliases") or "[]")
    keywords = json.loads(e.get("keywords") or "[]")
    print(f"  Alias: {', '.join(aliases[:5])}")
    print(f"  Keywords: {', '.join(keywords[:5])}")

    # Test against 5 random caduti_albooro
    caduti = conn.execute(
        "SELECT id, luogo_morte, anno_morte, grado, reparto FROM caduti_albooro LIMIT 5"
    ).fetchall()

    for c in caduti:
        c_dict = dict(c)
        c_dict["data_morte"] = c_dict.get("anno_morte", "")

        decision = engine.evaluate_event_link(
            e, c_dict, target_source_key="albo_oro", extraction_confidence=0.90
        )

        status_icon = {
            "verified": "✅", "probable": "🟢", "possible": "🟡",
            "unverified": "⚪", "conflicting": "🔴", "rejected": "❌",
            "needs_review": "🔍",
        }.get(decision.status, "❓")

        print(f"\n  → caduti_albooro#{c['id']} | morte={c_dict.get('luogo_morte','?')} ({c_dict.get('anno_morte','?')})")
        print(f"    {status_icon} STATUS: {decision.status}")
        print(f"    AUTHORITY: {decision.source_authority}")
        print(f"    MATCH CONFIDENCE: {decision.match_confidence:.2f}")
        print(f"    CONFLICT CODE: {decision.conflict_code or 'nessuno'}")
        print(f"    DECISION: {decision.decision_reason}")

    # Test against 3 random archivio_documenti
    docs = conn.execute(
        "SELECT rowid as id, title, description, place, year_start, provider FROM archivio_documenti LIMIT 3"
    ).fetchall()

    for d in docs:
        d_dict = dict(d)
        d_dict["titolo"] = d_dict.get("title", "")
        d_dict["note"] = d_dict.get("description", "")

        decision = engine.evaluate_event_link(
            e, d_dict, target_source_key="archivio_documenti", extraction_confidence=0.80
        )

        status_icon = {
            "verified": "✅", "probable": "🟢", "possible": "🟡",
            "unverified": "⚪", "conflicting": "🔴", "rejected": "❌",
            "needs_review": "🔍",
        }.get(decision.status, "❓")

        print(f"\n  → archivio_documenti#{d['id']} | {d_dict.get('title','?')[:60]}")
        print(f"    {status_icon} STATUS: {decision.status}")
        print(f"    AUTHORITY: {decision.source_authority}")
        print(f"    MATCH CONFIDENCE: {decision.match_confidence:.2f}")
        print(f"    CONFLICT CODE: {decision.conflict_code or 'nessuno'}")
        print(f"    DECISION: {decision.decision_reason}")

# ─── Summary ──────────────────────────────────────────────────────────────────
print(f"\n{'=' * 80}")
print(f"REGOLE APPLICATE (rule_version={RULE_VERSION})")
print(f"{'=' * 80}")
print(f"  1. Data ufficiale = veto hard (TEMPORAL_VETO_OFFICIAL_DATE)")
print(f"  2. Match solo nome → needs_review (NAME_ONLY_NO_DISCRIMINATOR)")
print(f"  3. Fonte web non sovrascrive dati ufficiali")
print(f"  4. Due fonti ufficiali in conflitto → conflicting + needs_review")
print(f"  5. Fonti fuori periodo → rejected (TEMPORAL_OUT_OF_PERIOD)")
print(f"  6. Fonti web non ufficiali → lead only (unverified)")

conn.close()
conn_ev.close()

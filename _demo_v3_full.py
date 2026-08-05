"""Demo V3 con 6 nomi con dati completi e 3 eventi — output conversazionale."""
import sqlite3, json, os, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from source_authority_registry import SourceAuthorityRegistry, LinkDecisionEngine, RULE_VERSION

DB = os.path.join(os.path.dirname(__file__), "imi_internati.db")
EDB = os.path.join(os.path.dirname(__file__), "eventi_1gm.db")

conn = sqlite3.connect(DB, timeout=30)
conn.row_factory = sqlite3.Row
conn_ev = sqlite3.connect(EDB, timeout=30)
conn_ev.row_factory = sqlite3.Row

registry = SourceAuthorityRegistry(conn_ev)
engine = LinkDecisionEngine(registry)

print("=" * 80)
print("V3 SOURCE AUTHORITY - RISULTATI CONVERSAZIONALI")
print("6 NOMI CON DATI COMPLETI + 3 EVENTI")
print("=" * 80)

# ─── 6 nomi: 3 da caduti_ministero (dati ricchi) match vs caduti_albooro
#            3 da internati con data_nascita/luogo match vs caduti_ministero
# ─────────────────────────────────────────────────────────────────────────────

# 3 nomi da caduti_ministero con data_nascita + comune_nascita + paternita
min_names = conn.execute("""
    SELECT id, cognome, nome, data_nascita, data_decesso, comune_nascita,
           provincia_nascita, paternita, maternita
    FROM caduti_ministero
    WHERE cognome IS NOT NULL AND cognome != ''
      AND data_nascita IS NOT NULL AND data_nascita != ''
      AND comune_nascita IS NOT NULL AND comune_nascita != ''
      AND paternita IS NOT NULL AND paternita != ''
    ORDER BY RANDOM() LIMIT 3
""").fetchall()

# 3 nomi da internati con data_nascita + luogo_nascita
int_names = conn.execute("""
    SELECT id, cognome, nome, data_nascita, luogo_nascita, matricola, grado,
           luogo_cattura, data_cattura, luogo_internamento, sorte, residenza
    FROM internati
    WHERE cognome IS NOT NULL AND cognome != ''
      AND data_nascita IS NOT NULL AND data_nascita != ''
      AND luogo_nascita IS NOT NULL AND luogo_nascita != ''
    ORDER BY RANDOM() LIMIT 3
""").fetchall()

all_people = []

# ─── Person 1-3: caduti_ministero → caduti_albooro ──────────────────────────
for idx, m in enumerate(min_names, 1):
    d = dict(m)
    cognome = (d.get("cognome") or "").strip().upper()
    nome = (d.get("nome") or "").strip().upper()
    print(f"\n{'=' * 80}")
    print(f"NOME {idx}/6: {cognome} {nome}")
    print(f"  Fonte: caduti_ministero (ID={d['id']}) [TIER 1 - UFFICIALE]")
    print(f"  Nato: {d['data_nascita']} a {d['comune_nascita']} ({d.get('provincia_nascita','')})")
    print(f"  Padre: {d.get('paternita','?')}")
    print(f"  Madre: {d.get('maternita','?')}")
    print(f"  Deceduto: {d.get('data_decesso','?')}")

    # Search in caduti_albooro
    candidates = conn.execute(
        "SELECT id, nominativo, anno_morte, luogo_morte, classe, grado "
        "FROM caduti_albooro WHERE nominativo LIKE ? LIMIT 10",
        (f"{cognome} {nome}%",) if nome else (f"{cognome}%",)
    ).fetchall()

    if not candidates:
        print(f"\n  NESSUN candidato in caduti_albooro")
        print(f"  -> STATUS: unverified | MOTIVO: nessuna corrispondenza nell'albo d'oro")
        continue

    for c in candidates:
        c_dict = dict(c)
        parts = (c_dict.get("nominativo") or "").split()
        c_dict["cognome"] = parts[0] if parts else ""
        c_dict["nome"] = " ".join(parts[1:]) if len(parts) > 1 else ""
        c_dict["data_nascita"] = c_dict.get("classe", "")
        c_dict["data_decesso"] = c_dict.get("anno_morte", "")
        c_dict["luogo_nascita"] = ""
        c_dict["paternita"] = ""
        c_dict["matricola"] = ""

        decision = engine.evaluate_record_link(
            d, c_dict, source_key="ministero_difesa", target_key="albo_oro",
            extraction_confidence=0.90
        )

        icon = {"verified":"OK","probable":"OK","possible":"?","unverified":"--",
                "conflicting":"!!","rejected":"NO","needs_review":"REV"}.get(decision.status, "??")

        print(f"\n  -> caduti_albooro#{c['id']} | {c_dict.get('nominativo','?')} | morte={c_dict.get('luogo_morte','?')} ({c_dict.get('anno_morte','?')})")
        print(f"    [{icon}] STATUS: {decision.status}")
        print(f"    AUTHORITY: {decision.source_authority}")
        print(f"    MATCH CONFIDENCE: {decision.match_confidence:.2f}")
        print(f"    EXTRACTION CONFIDENCE: {decision.extraction_confidence:.2f}")
        print(f"    CONFLICT CODE: {decision.conflict_code or 'nessuno'}")
        print(f"    NEEDS REVIEW: {'SI' if decision.needs_review else 'no'}")
        print(f"    DECISION: {decision.decision_reason}")
        if decision.evidence:
            for k, v in decision.evidence.items():
                print(f"    EVIDENCE[{k}]: {v}")

# ─── Person 4-6: internati → caduti_ministero ───────────────────────────────
for idx, p in enumerate(int_names, 4):
    d = dict(p)
    cognome = (d.get("cognome") or "").strip().upper()
    nome = (d.get("nome") or "").strip().upper()
    print(f"\n{'=' * 80}")
    print(f"NOME {idx}/6: {cognome} {nome}")
    print(f"  Fonte: internati (ID={d['id']}) [TIER 2 - PRIMARIO]")
    print(f"  Nato: {d['data_nascita']} a {d['luogo_nascita']}")
    print(f"  Matricola: {d.get('matricola','?')}")
    print(f"  Grado: {d.get('grado','?')}")
    print(f"  Residenza: {d.get('residenza','?')}")
    print(f"  Cattura: {d.get('data_cattura','?')} a {d.get('luogo_cattura','?')}")
    print(f"  Internamento: {d.get('luogo_internamento','?')}")
    print(f"  Sorte: {d.get('sorte','?')}")

    # Search in caduti_ministero
    candidates = conn.execute(
        "SELECT id, cognome, nome, data_nascita, data_decesso, comune_nascita, paternita "
        "FROM caduti_ministero WHERE cognome = ? AND nome LIKE ? LIMIT 10",
        (cognome, f"{nome}%") if nome else (cognome, "%")
    ).fetchall()

    if not candidates:
        # Also try caduti_albooro
        candidates_albo = conn.execute(
            "SELECT id, nominativo, anno_morte, luogo_morte, classe, grado "
            "FROM caduti_albooro WHERE nominativo LIKE ? LIMIT 10",
            (f"{cognome} {nome}%",) if nome else (f"{cognome}%",)
        ).fetchall()
        if not candidates_albo:
            print(f"\n  NESSUN candidato in caduti_ministero o caduti_albooro")
            print(f"  -> STATUS: unverified | MOTIVO: nessuna corrispondenza negli albi ufficiali")
            continue
        for c in candidates_albo:
            c_dict = dict(c)
            parts = (c_dict.get("nominativo") or "").split()
            c_dict["cognome"] = parts[0] if parts else ""
            c_dict["nome"] = " ".join(parts[1:]) if len(parts) > 1 else ""
            c_dict["data_nascita"] = c_dict.get("classe", "")
            c_dict["data_decesso"] = c_dict.get("anno_morte", "")
            c_dict["luogo_nascita"] = ""
            c_dict["paternita"] = ""
            c_dict["matricola"] = ""

            decision = engine.evaluate_record_link(
                d, c_dict, source_key="internati_imi", target_key="albo_oro",
                extraction_confidence=0.85
            )
            icon = {"verified":"OK","probable":"OK","possible":"?","unverified":"--",
                    "conflicting":"!!","rejected":"NO","needs_review":"REV"}.get(decision.status, "??")
            print(f"\n  -> caduti_albooro#{c['id']} | {c_dict.get('nominativo','?')} | morte={c_dict.get('luogo_morte','?')} ({c_dict.get('anno_morte','?')})")
            print(f"    [{icon}] STATUS: {decision.status}")
            print(f"    AUTHORITY: {decision.source_authority}")
            print(f"    MATCH CONFIDENCE: {decision.match_confidence:.2f}")
            print(f"    CONFLICT CODE: {decision.conflict_code or 'nessuno'}")
            print(f"    NEEDS REVIEW: {'SI' if decision.needs_review else 'no'}")
            print(f"    DECISION: {decision.decision_reason}")
            if decision.evidence:
                for k, v in decision.evidence.items():
                    print(f"    EVIDENCE[{k}]: {v}")
        continue

    for c in candidates:
        c_dict = dict(c)
        decision = engine.evaluate_record_link(
            d, c_dict, source_key="internati_imi", target_key="ministero_difesa",
            extraction_confidence=0.85
        )
        icon = {"verified":"OK","probable":"OK","possible":"?","unverified":"--",
                "conflicting":"!!","rejected":"NO","needs_review":"REV"}.get(decision.status, "??")
        print(f"\n  -> caduti_ministero#{c['id']} | {c_dict.get('cognome','')} {c_dict.get('nome','')} | nato={c_dict.get('data_nascita','?')} a {c_dict.get('comune_nascita','?')}")
        print(f"    [{icon}] STATUS: {decision.status}")
        print(f"    AUTHORITY: {decision.source_authority}")
        print(f"    MATCH CONFIDENCE: {decision.match_confidence:.2f}")
        print(f"    CONFLICT CODE: {decision.conflict_code or 'nessuno'}")
        print(f"    NEEDS REVIEW: {'SI' if decision.needs_review else 'no'}")
        print(f"    DECISION: {decision.decision_reason}")
        if decision.evidence:
            for k, v in decision.evidence.items():
                print(f"    EVIDENCE[{k}]: {v}")

# ─── 3 EVENTI ────────────────────────────────────────────────────────────────
print(f"\n{'=' * 80}")
print(f"3 EVENTI - COLLEGAMENTO CON FONTI")
print(f"{'=' * 80}")

events = conn_ev.execute("""
    SELECT id, nome, data_inizio, data_fine, luogo, aliases, keywords, descrizione
    FROM eventi_1gm
    WHERE data_inizio IS NOT NULL AND data_inizio != ''
    ORDER BY RANDOM() LIMIT 3
""").fetchall()

for idx, ev in enumerate(events, 1):
    e = dict(ev)
    print(f"\n{'=' * 80}")
    print(f"EVENTO {idx}/3: {e['nome']}")
    print(f"  Periodo: {e.get('data_inizio','?')} -> {e.get('data_fine','?')}")
    print(f"  Luogo: {e.get('luogo','?')}")
    aliases = json.loads(e.get("aliases") or "[]")
    keywords = json.loads(e.get("keywords") or "[]")
    print(f"  Alias: {', '.join(aliases[:5])}")
    print(f"  Keywords: {', '.join(keywords[:5])}")

    # 8 caduti_albooro random
    caduti = conn.execute(
        "SELECT id, luogo_morte, anno_morte, grado FROM caduti_albooro ORDER BY RANDOM() LIMIT 8"
    ).fetchall()

    for c in caduti:
        c_dict = dict(c)
        c_dict["data_morte"] = c_dict.get("anno_morte", "")
        decision = engine.evaluate_event_link(
            e, c_dict, target_source_key="albo_oro", extraction_confidence=0.90
        )
        icon = {"verified":"OK","probable":"OK","possible":"?","unverified":"--",
                "conflicting":"!!","rejected":"NO","needs_review":"REV"}.get(decision.status, "??")
        print(f"\n  -> caduti_albooro#{c['id']} | morte={c_dict.get('luogo_morte','?')} ({c_dict.get('anno_morte','?')})")
        print(f"    [{icon}] STATUS: {decision.status}")
        print(f"    AUTHORITY: {decision.source_authority}")
        print(f"    MATCH CONFIDENCE: {decision.match_confidence:.2f}")
        print(f"    CONFLICT CODE: {decision.conflict_code or 'nessuno'}")
        print(f"    DECISION: {decision.decision_reason}")

    # 3 archivio_documenti random
    docs = conn.execute(
        "SELECT rowid as id, title, description, place, year_start, provider FROM archivio_documenti ORDER BY RANDOM() LIMIT 3"
    ).fetchall()
    for d in docs:
        d_dict = dict(d)
        d_dict["titolo"] = d_dict.get("title", "")
        d_dict["note"] = d_dict.get("description", "")
        decision = engine.evaluate_event_link(
            e, d_dict, target_source_key="archivio_documenti", extraction_confidence=0.80
        )
        icon = {"verified":"OK","probable":"OK","possible":"?","unverified":"--",
                "conflicting":"!!","rejected":"NO","needs_review":"REV"}.get(decision.status, "??")
        title_short = (d_dict.get("title","") or "")[:50]
        print(f"\n  -> archivio_documenti#{d['id']} | {title_short}")
        print(f"    [{icon}] STATUS: {decision.status}")
        print(f"    AUTHORITY: {decision.source_authority}")
        print(f"    MATCH CONFIDENCE: {decision.match_confidence:.2f}")
        print(f"    CONFLICT CODE: {decision.conflict_code or 'nessuno'}")
        print(f"    DECISION: {decision.decision_reason}")

print(f"\n{'=' * 80}")
print(f"REGOLE V3 (rule_version={RULE_VERSION})")
print(f"{'=' * 80}")
conn.close()
conn_ev.close()

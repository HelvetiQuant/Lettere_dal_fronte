"""Grafo record-to-record: collega soldati che partecipano allo stesso evento/luogo/anno,
poi collega fonti personali (diari, foto) ai singoli soldati.
Tabella: record_links (from_table, from_id, to_table, to_id, link_type, confidence).
"""
import sqlite3, os, re, time
from datetime import datetime

DB = os.path.join(os.path.dirname(__file__), "imi_internati.db")
conn = sqlite3.connect(DB)
conn.row_factory = sqlite3.Row
conn.execute("PRAGMA journal_mode=WAL")
now = datetime.now().isoformat(timespec="seconds")
ANNO_RE = re.compile(r"\b(191[4-9])\b")

# Schema
conn.execute("""CREATE TABLE IF NOT EXISTS record_links (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    from_table TEXT NOT NULL, from_id INTEGER NOT NULL,
    to_table TEXT NOT NULL, to_id INTEGER NOT NULL,
    link_type TEXT NOT NULL, confidence REAL DEFAULT 0.5,
    elaborato_il TEXT,
    UNIQUE(from_table, from_id, to_table, to_id, link_type)
)""")
conn.commit()

existing = set()
for r in conn.execute("SELECT from_table, from_id, to_table, to_id, link_type FROM record_links").fetchall():
    existing.add((r["from_table"], r["from_id"], r["to_table"], r["to_id"], r["link_type"]))
print(f"[PRE] record_links esistenti: {len(existing)}")

# Pulisci vecchi link fonte_personale (basati solo su cognome, rischiosi)
deleted = conn.execute("DELETE FROM record_links WHERE link_type='fonte_personale'").rowcount
conn.commit()
existing = set()
for r in conn.execute("SELECT from_table, from_id, to_table, to_id, link_type FROM record_links").fetchall():
    existing.add((r["from_table"], r["from_id"], r["to_table"], r["to_id"], r["link_type"]))
print(f"[CLEAN] Rimossi {deleted} vecchi link fonte_personale (match solo cognome)")
print(f"[PRE] record_links dopo cleanup: {len(existing)}")

def _add(ft, fi, tt, ti, lt, conf=0.5):
    k = (ft, fi, tt, ti, lt)
    if k in existing:
        return False
    existing.add(k)
    conn.execute("INSERT OR IGNORE INTO record_links (from_table,from_id,to_table,to_id,link_type,confidence,elaborato_il) VALUES (?,?,?,?,?,?,?)",
                 (ft, fi, tt, ti, lt, conf, now))
    return True

# ─── PASSO 1: Soldati stesso evento/luogo/anno ─────────────────────────────
# Raggruppa caduti_albooro per (anno_morte, luogo_morte) → link tra loro
print("\n[PASSO 1] caduti_albooro: link soldati stesso evento/luogo/anno")
t0 = time.time()
groups = conn.execute("""
    SELECT anno_morte, luogo_morte, COUNT(*) as n, GROUP_CONCAT(id) as ids
    FROM caduti_albooro
    WHERE anno_morte IS NOT NULL AND anno_morte != '' AND luogo_morte IS NOT NULL AND luogo_morte != '-'
    GROUP BY anno_morte, luogo_morte
    HAVING n > 1 AND n <= 500
""").fetchall()
print(f"  Gruppi (anno+luogo): {len(groups)}")
added = 0
for g in groups:
    ids = [int(x) for x in g["ids"].split(",") if x]
    anno = g["anno_morte"]
    luogo = g["luogo_morte"]
    # Link ogni soldato al gruppo (star topology: primo soldato come hub)
    hub = ids[0]
    for sid in ids[1:]:
        if _add("caduti_albooro", sid, "caduti_albooro", hub, "stesso_evento_luogo", 0.9):
            added += 1
    if added % 50000 == 0 and added > 0:
        conn.commit()
        print(f"    {added} link ({time.time()-t0:.0f}s)")
conn.commit()
print(f"  DONE: {added} link soldati-stesso-evento ({time.time()-t0:.0f}s)")

# ─── PASSO 2: Decorati stesso anno+evento ──────────────────────────────────
print("\n[PASSO 2] decorati_nastroazzurro: link decorati stesso anno")
t0 = time.time()
groups2 = conn.execute("""
    SELECT anno_decorazione, COUNT(*) as n, GROUP_CONCAT(id) as ids
    FROM decorati_nastroazzurro
    WHERE anno_decorazione IS NOT NULL AND anno_decorazione != ''
    GROUP BY anno_decorazione HAVING n > 1 AND n <= 500
""").fetchall()
print(f"  Gruppi (anno): {len(groups2)}")
added2 = 0
for g in groups2:
    ids = [int(x) for x in g["ids"].split(",") if x]
    hub = ids[0]
    for sid in ids[1:]:
        if _add("decorati_nastroazzurro", sid, "decorati_nastroazzurro", hub, "stesso_anno_decorazione", 0.7):
            added2 += 1
    if added2 % 50000 == 0 and added2 > 0:
        conn.commit()
        print(f"    {added2} link ({time.time()-t0:.0f}s)")
conn.commit()
print(f"  DONE: {added2} link decorati-stesso-anno ({time.time()-t0:.0f}s)")

# ─── PASSO 3: Soldati ↔ documenti evento/luogo ─────────────────────────────
print("\n[PASSO 3] caduti_albooro ↔ archivio_documenti (match anno+luogo)")
t0 = time.time()
docs = conn.execute("SELECT rowid, provider, external_id, title, year_start, place FROM archivio_documenti").fetchall()
print(f"  Documenti: {len(docs)}")
added3 = 0
# Pre-carica luoghi documenti
for doc in docs:
    doc_year = doc["year_start"]
    doc_place = (doc["place"] or "").lower()
    doc_title = (doc["title"] or "").lower()
    # Match per anno
    if doc_year and 1914 <= doc_year <= 1919:
        # Soldati morti quell'anno
        soldati = conn.execute(
            "SELECT id FROM caduti_albooro WHERE anno_morte LIKE ? LIMIT 50",
            (f"%{doc_year}%",)
        ).fetchall()
        for s in soldati:
            if _add("caduti_albooro", s["id"], "archivio_documenti", doc["rowid"], "documento_evento", 0.6):
                added3 += 1
    # Match per luogo nel titolo
    if doc_place and len(doc_place) >= 4:
        soldati_l = conn.execute(
            "SELECT id FROM caduti_albooro WHERE LOWER(luogo_morte) LIKE ? LIMIT 50",
            (f"%{doc_place[:20]}%",)
        ).fetchall()
        for s in soldati_l:
            if _add("caduti_albooro", s["id"], "archivio_documenti", doc["rowid"], "documento_luogo", 0.65):
                added3 += 1
conn.commit()
print(f"  DONE: {added3} link soldati-documenti ({time.time()-t0:.0f}s)")

# ─── PASSO 4: Soldati ↔ fonti_indice (match COGNOME + NOME) ────────────────
# ANTI-OMONIMIA: match su cognome+nome intero, non solo cognome.
# Strategia inversa: per ogni soldato, cerca "Cognome Nome" nei titoli fonti.
print("\n[PASSO 4] caduti_albooro ↔ fonti_indice (match COGNOME+NOME)")
t0 = time.time()
# Pre-carica tutte le fonti in memoria (titolo+note UPPER) per ricerca veloce
fonti_all = []
for f in conn.execute("SELECT id, titolo, note FROM fonti_indice WHERE titolo IS NOT NULL").fetchall():
    haystack = ((f["titolo"] or "") + " " + (f["note"] or "")).upper()
    if len(haystack) >= 5:
        fonti_all.append((f["id"], haystack))
print(f"  Fonti in memoria: {len(fonti_all)}")
# Pre-carica nomi soldati: (id, cognome, nome_completo_upper)
# caduti_albooro.nominativo è "COGNOME Nome" o simile
soldati_names = conn.execute("SELECT id, nominativo FROM caduti_albooro WHERE nominativo IS NOT NULL").fetchall()
print(f"  Soldati da cercare: {len(soldati_names)}")
added4 = 0
batch = 0
for s in soldati_names:
    nom = (s["nominativo"] or "").strip()
    if len(nom) < 5:
        continue
    nom_up = nom.upper()
    # Estrai cognome (prima parola) e nome (resto)
    parts = nom_up.split()
    if len(parts) < 2:
        continue  # solo cognome, skip per evitare omonimia
    cognome = parts[0]
    nome = parts[1] if len(parts) > 1 else ""
    # Match: cerca "COGNOME NOME" (almeno cognome + primo nome) nel haystack
    search_key = f"{cognome} {nome}"
    if len(cognome) < 3 or len(nome) < 2:
        continue
    for fid, haystack in fonti_all:
        if search_key in haystack:
            # Verifica aggiuntiva: almeno cognome E nome presenti
            if cognome in haystack and nome in haystack:
                if _add("caduti_albooro", s["id"], "fonti_indice", fid, "fonte_personale", 0.8):
                    added4 += 1
    batch += 1
    if batch % 50000 == 0:
        conn.commit()
        print(f"    {batch}/{len(soldati_names)} soldati, {added4} link ({time.time()-t0:.0f}s)")
conn.commit()
print(f"  DONE: {added4} link soldati-fonti ({time.time()-t0:.0f}s)")

# ─── PASSO 5: Decorati ↔ fonti_indice (match COGNOME + NOME) ────────────────
print("\n[PASSO 5] decorati_nastroazzurro ↔ fonti_indice (match COGNOME+NOME)")
t0 = time.time()
decorati_names = conn.execute("SELECT id, cognome, nome FROM decorati_nastroazzurro WHERE cognome IS NOT NULL AND nome IS NOT NULL").fetchall()
print(f"  Decorati da cercare: {len(decorati_names)}")
added5 = 0
batch = 0
for d in decorati_names:
    cognome = (d["cognome"] or "").strip().upper()
    nome = (d["nome"] or "").strip().upper()
    if len(cognome) < 3 or len(nome) < 2:
        continue
    search_key = f"{cognome} {nome}"
    for fid, haystack in fonti_all:
        if search_key in haystack:
            if cognome in haystack and nome in haystack:
                if _add("decorati_nastroazzurro", d["id"], "fonti_indice", fid, "fonte_personale", 0.8):
                    added5 += 1
    batch += 1
    if batch % 50000 == 0:
        conn.commit()
        print(f"    {batch}/{len(decorati_names)} decorati, {added5} link ({time.time()-t0:.0f}s)")
conn.commit()
print(f"  DONE: {added5} link decorati-fonti ({time.time()-t0:.0f}s)")

# ─── PASSO 6: CWGC WW1 ↔ archivio_documenti (match anno) ───────────────────
print("\n[PASSO 6] caduti_cwgc WW1 ↔ archivio_documenti (match anno)")
t0 = time.time()
added6 = 0
for doc in docs:
    doc_year = doc["year_start"]
    if doc_year and 1914 <= doc_year <= 1919:
        soldati = conn.execute(
            "SELECT id FROM caduti_cwgc WHERE guerra='World War 1' AND data_morte LIKE ? LIMIT 50",
            (f"%{doc_year}%",)
        ).fetchall()
        for s in soldati:
            if _add("caduti_cwgc", s["id"], "archivio_documenti", doc["rowid"], "documento_evento", 0.6):
                added6 += 1
conn.commit()
print(f"  DONE: {added6} link cwgc-documenti ({time.time()-t0:.0f}s)")

# ─── VERIFICHE ──────────────────────────────────────────────────────────────
print(f"\n{'='*60}")
print("VERIFICHE")
print(f"{'='*60}")

total = conn.execute("SELECT COUNT(*) FROM record_links").fetchone()[0]
print(f"\nTotale record_links: {total}")

print("\nPer link_type:")
for r in conn.execute("SELECT link_type, COUNT(*) as n FROM record_links GROUP BY link_type ORDER BY n DESC").fetchall():
    print(f"  {r['link_type']:30s} {r['n']:>8}")

print("\nPer from_table → to_table:")
for r in conn.execute("SELECT from_table, to_table, COUNT(*) as n FROM record_links GROUP BY from_table, to_table ORDER BY n DESC LIMIT 15").fetchall():
    print(f"  {r['from_table']:20s} → {r['to_table']:20s} {r['n']:>8}")

# Sample
print("\nSample record_links:")
for lt in ["stesso_evento_luogo", "documento_evento", "fonte_personale"]:
    rows = conn.execute("SELECT * FROM record_links WHERE link_type=? LIMIT 3", (lt,)).fetchall()
    print(f"\n  {lt}:")
    for r in rows:
        print(f"    {r['from_table']}#{r['from_id']} → {r['to_table']}#{r['to_id']} (conf={r['confidence']})")

conn.close()
print(f"\nDONE")

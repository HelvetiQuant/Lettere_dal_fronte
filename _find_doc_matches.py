import sqlite3, json

conn = sqlite3.connect("imi_internati.db")
conn.row_factory = sqlite3.Row
conn_ev = sqlite3.connect("eventi_1gm.db")
conn_ev.row_factory = sqlite3.Row

# Tutti i documenti
docs = conn.execute(
    "SELECT rowid as id, title, description, provider, doc_type, source_url, creator, date_text, place "
    "FROM archivio_documenti"
).fetchall()
print(f"Documenti totali: {len(docs)}")

# Eventi
events = conn_ev.execute("SELECT id, nome, keywords, aliases FROM eventi_1gm ORDER BY id").fetchall()

# Link esistenti
existing = set()
for r in conn_ev.execute("SELECT evento_id, target_id FROM event_links WHERE link_type='documento'").fetchall():
    existing.add((r["evento_id"], r["target_id"]))

# Match per ogni evento
new_links = []
for ev in events:
    kws = json.loads(ev["keywords"]) if ev["keywords"] else []
    aliases = json.loads(ev["aliases"]) if ev["aliases"] else []
    search_terms = set()
    for kw in kws + aliases:
        if len(kw) >= 4:
            search_terms.add(kw.upper())
    
    for d in docs:
        text = " ".join(filter(None, [d["title"], d["description"], d["place"], d["creator"], d["date_text"]])).upper()
        if not text.strip():
            continue
        for term in search_terms:
            if term in text:
                if (ev["id"], d["id"]) not in existing:
                    new_links.append((ev["id"], d["id"], term, d["title"][:50]))
                break  # un match basta per questo documento-evento

print(f"\nNuovi link documento->evento trovati: {len(new_links)}")
print(f"\nDistribuzione per evento:")
from collections import Counter
ev_counts = Counter(nl[0] for nl in new_links)
ev_names = {e["id"]: e["nome"] for e in events}
for evid, cnt in ev_counts.most_common():
    print(f"  [{evid:>3}] {ev_names[evid]:<40} {cnt:>4} nuovi link")

print(f"\nPrimi 30 nuovi link:")
for nl in new_links[:30]:
    print(f"  ev={nl[0]} doc={nl[1]} match='{nl[2]}' title='{nl[3]}'")

conn.close()
conn_ev.close()

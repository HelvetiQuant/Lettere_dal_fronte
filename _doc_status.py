import sqlite3, json

# 1. Documenti totali in archivio_documenti
conn = sqlite3.connect("imi_internati.db")
conn.row_factory = sqlite3.Row
total_docs = conn.execute("SELECT COUNT(*) as n FROM archivio_documenti").fetchone()["n"]
print(f"Documenti totali in archivio_documenti: {total_docs}")

# 2. Documenti collegati ad eventi 1GM
conn_ev = sqlite3.connect("eventi_1gm.db")
conn_ev.row_factory = sqlite3.Row
doc_links = conn_ev.execute(
    "SELECT evento_id, target_id, match_value, confidence FROM event_links WHERE link_type='documento' ORDER BY evento_id"
).fetchall()
print(f"Link documento->evento: {len(doc_links)}")

# 3. Eventi con almeno 1 documento
eventi_con_doc = set(r["evento_id"] for r in doc_links)
print(f"Eventi con almeno 1 documento collegato: {len(eventi_con_doc)}")

# 4. Dettaglio per evento
print("\n" + "=" * 100)
print(f"{'EvID':<5}{'Nome evento':<40}{'#Doc':>6}  Esempi")
print("=" * 100)

for ev in conn_ev.execute("SELECT id, nome FROM eventi_1gm ORDER BY id").fetchall():
    docs_for_ev = [r for r in doc_links if r["evento_id"] == ev["id"]]
    if docs_for_ev:
        # Recupera titoli
        titles = []
        for dl in docs_for_ev[:3]:
            d = conn.execute(
                "SELECT title, provider, doc_type FROM archivio_documenti WHERE rowid=?",
                (dl["target_id"],)
            ).fetchone()
            if d:
                titles.append(f"[{d['doc_type'] or 'nd'}] {d['title'][:40]} ({d['provider']})")
        print(f"{ev['id']:<5}{ev['nome']:<40}{len(docs_for_ev):>6}  {' | '.join(titles)}")
    else:
        print(f"{ev['id']:<5}{ev['nome']:<40}{'0':>6}  —")

# 5. Provider dei documenti collegati
print("\n" + "=" * 100)
print("Provider dei documenti collegati:")
for r in conn.execute(
    "SELECT a.provider, COUNT(*) as n FROM archivio_documenti a "
    "JOIN event_links el ON a.rowid = el.target_id AND el.link_type='documento' "
    "GROUP BY a.provider ORDER BY n DESC"
).fetchall():
    print(f"  {r['provider']:<30} {r['n']:>6}")

# 6. Tipologie documenti
print("\nTipologie (doc_type) dei documenti collegati:")
for r in conn.execute(
    "SELECT a.doc_type, COUNT(*) as n FROM archivio_documenti a "
    "JOIN event_links el ON a.rowid = el.target_id AND el.link_type='documento' "
    "GROUP BY a.doc_type ORDER BY n DESC"
).fetchall():
    print(f"  {r['doc_type'] or 'non specificato':<30} {r['n']:>6}")

conn.close()
conn_ev.close()

import sqlite3, json

conn = sqlite3.connect("eventi_1gm.db")
conn.row_factory = sqlite3.Row

print("Keyword e alias per eventi senza documenti:")
print("=" * 120)
for ev in conn.execute("SELECT id, nome, keywords, aliases, luogo FROM eventi_1gm ORDER BY id").fetchall():
    kws = json.loads(ev["keywords"]) if ev["keywords"] else []
    aliases = json.loads(ev["aliases"]) if ev["aliases"] else []
    doc_count = conn.execute(
        "SELECT COUNT(*) as n FROM event_links WHERE evento_id=? AND link_type='documento'",
        (ev["id"],)
    ).fetchone()["n"]
    if doc_count == 0:
        print(f"\n[{ev['id']}] {ev['nome']} (luogo: {ev['luogo']})")
        print(f"  Keywords: {kws}")
        print(f"  Aliases:  {aliases}")

conn.close()

import sqlite3
c = sqlite3.connect("validazioni_ai.db")
c.row_factory = sqlite3.Row
total = c.execute("SELECT COUNT(*) FROM record_link_validations").fetchone()[0]
print(f"Total validations: {total}")
for r in c.execute(
    "SELECT ai_provider, COUNT(*) as n, "
    "SUM(CASE WHEN verdict='VALID' THEN 1 ELSE 0 END) as v, "
    "SUM(CASE WHEN verdict='INVALID' THEN 1 ELSE 0 END) as iv, "
    "SUM(CASE WHEN verdict='UNCERTAIN' THEN 1 ELSE 0 END) as u "
    "FROM record_link_validations GROUP BY ai_provider ORDER BY ai_provider"
).fetchall():
    print(f"  {r['ai_provider']:12s}  n={r['n']:>3}  VALID={r['v']:>3}  INVALID={r['iv']:>3}  UNCERTAIN={r['u']:>3}")
for r in c.execute(
    "SELECT cycle, COUNT(*) as n FROM record_link_validations GROUP BY cycle ORDER BY cycle"
).fetchall():
    print(f"  Cycle {r['cycle']}: {r['n']} validations")
c.close()

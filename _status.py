"""Status check — no hard-coded totals, all counts from live DB."""
import sys
from database import get_conn

c = get_conn()
n = c.execute("SELECT COUNT(*) FROM populate_progress WHERE status='done'").fetchone()[0]
total = c.execute("SELECT COUNT(*) FROM internati").fetchone()[0]
t = c.execute("SELECT COUNT(*) FROM fonti_indice").fetchone()[0]

if total == 0:
    print("ERROR: internati table is empty or DB not found")
    sys.exit(1)

pct = 100 * n // total if total > 0 else 0
print(f"processati={n}/{total} ({pct}%) | fonti_indice={t} | mancanti={total-n}")
c.close()

from database import get_conn
c = get_conn()
n = c.execute("SELECT COUNT(*) FROM populate_progress WHERE status='done'").fetchone()[0]
total = c.execute("SELECT COUNT(*) FROM internati").fetchone()[0]
t = c.execute("SELECT COUNT(*) FROM fonti_indice").fetchone()[0]
print(f"processati={n}/{total} ({100*n//total}%) | fonti_indice={t} | mancanti={total-n}")
c.close()

from database import get_conn
c = get_conn()
n = c.execute("SELECT COUNT(*) FROM populate_progress WHERE status='done'").fetchone()[0]
t = c.execute("SELECT COUNT(*) FROM fonti_indice").fetchone()[0]
print(f"processati={n}/20464 ({100*n//20464}%) | fonti_indice={t} | mancanti={20464-n}")
c.close()

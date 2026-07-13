from database import get_conn
conn = get_conn()
conn.row_factory = lambda c,r: dict(zip([col[0] for col in c.description],r))

print("=== ENTITA PER TIPO ===")
rows = conn.execute("SELECT tipo, COUNT(*) as n FROM entita GROUP BY tipo ORDER BY n DESC LIMIT 20").fetchall()
for r in rows: print(r)

print("\n=== TOP ARBEITSKOMMANDO IN INTERNATI ===")
reps = conn.execute("SELECT arbeitskommando, COUNT(*) as n FROM internati WHERE arbeitskommando IS NOT NULL AND arbeitskommando != '' GROUP BY arbeitskommando ORDER BY n DESC LIMIT 15").fetchall()
for r in reps: print(r)

print("\n=== TOP GRADO IN INTERNATI ===")
gradi = conn.execute("SELECT grado, COUNT(*) as n FROM internati WHERE grado IS NOT NULL AND grado != '' GROUP BY grado ORDER BY n DESC LIMIT 10").fetchall()
for g in gradi: print(g)

print("\n=== TOP LUOGO_INTERNAMENTO ===")
luo = conn.execute("SELECT luogo_internamento, COUNT(*) as n FROM internati WHERE luogo_internamento IS NOT NULL AND luogo_internamento != '' GROUP BY luogo_internamento ORDER BY n DESC LIMIT 10").fetchall()
for l in luo: print(l)

print("\n=== CAMPIONE EVENTI ===")
events = conn.execute("SELECT valore, contesto, fonte_tabella FROM entita WHERE tipo='evento' LIMIT 20").fetchall()
for e in events: print(e)

print("\n=== CAMPIONE UNITA ===")
unita = conn.execute("SELECT valore, contesto, fonte_tabella FROM entita WHERE tipo='unita' LIMIT 20").fetchall()
for u in unita: print(u)

print("\n=== FONTI_INDICE per archivio ===")
fonti = conn.execute("SELECT archivio, COUNT(*) as n FROM fonti_indice GROUP BY archivio ORDER BY n DESC").fetchall()
for f in fonti: print(f)

conn.close()

import sqlite3
conn = sqlite3.connect('imi_internati.db')
c = conn.cursor()
fn = c.execute('SELECT COUNT(*) FROM fonti_narrative').fetchone()[0]
ent = c.execute("SELECT COUNT(*) FROM entita WHERE fonte_tabella='fonti_narrative'").fetchone()[0]
coll = c.execute("SELECT COUNT(*) FROM collegamenti WHERE tabella_origine='fonti_narrative'").fetchone()[0]
print(f'fonti_narrative: {fn}')
print(f'entita da fonti_narrative: {ent}')
print(f'collegamenti fonti_narrative: {coll}')
status = c.execute('PRAGMA quick_check').fetchone()
print(f'db integrity: {status}')
conn.close()

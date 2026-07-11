import sqlite3
conn = sqlite3.connect('imi_internati.db')
print('lettere_personali', conn.execute('SELECT COUNT(*) FROM lettere_personali').fetchone()[0])
print('entita lettere', conn.execute("SELECT COUNT(*) FROM entita WHERE fonte_tabella='lettere_personali'").fetchone()[0])
print('collegamenti lettere', conn.execute("SELECT COUNT(*) FROM collegamenti WHERE tabella_origine='lettere_personali'").fetchone()[0])
for row in conn.execute("SELECT id, filename, mittente, destinatario, luogo FROM lettere_personali").fetchall():
    print(row)
conn.close()

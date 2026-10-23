import sqlite3
conn = sqlite3.connect('imi_internati.db')
cols = [r[1] for r in conn.execute('PRAGMA table_info(internati)').fetchall()]
print("internati columns:", cols)
conn.close()

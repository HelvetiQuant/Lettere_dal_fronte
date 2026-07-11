from database import get_conn
conn = get_conn()
wars = conn.execute("SELECT DISTINCT guerra FROM caduti_cwgc").fetchall()
print("CWGC guerre presenti:", [r[0] for r in wars])
last = conn.execute("SELECT search_query, elaborato_il FROM documenti_nara_catalog ORDER BY elaborato_il DESC LIMIT 3").fetchall()
for r in last:
    print("nara_cat last:", r[0], "|", r[1])
conn.close()

from database import get_conn
c = get_conn()
r = c.execute("SELECT guerra, COUNT(*) FROM caduti_cwgc GROUP BY guerra").fetchall()
print("Per guerra:")
for row in r:
    print(f"  {row[0]}: {row[1]:,}")

r2 = c.execute("SELECT nationality, COUNT(*) as cnt FROM caduti_cwgc WHERE nationality='United Kingdom' GROUP BY nationality").fetchall()
print(f"\nUK totale: {r2[0][1]:,}" if r2 else "UK: 0")

# Check how many UK records are there by year
r3 = c.execute("SELECT substr(data_morte,-4) as yr, COUNT(*) FROM caduti_cwgc WHERE nationality='United Kingdom' GROUP BY yr ORDER BY yr").fetchall()
print("\nUK per anno di morte:")
for row in r3[:20]:
    print(f"  {row[0]}: {row[1]:,}")

c.close()

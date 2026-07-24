import requests, json
s = requests.Session()
s.post('http://127.0.0.1:8123/api/rc/auth/login', json={'username':'admin','password':'admin'})

# Check candidate 104 current state
r = s.get('http://127.0.0.1:8123/api/rc/candidates/104')
c = r.json()
print(f"=== Candidato {c['id']}: {c['cognome']} {c['nome']} ===")
print(f"  Grado: {c.get('grado')}, Conflitto: {c.get('conflitto')}, Stato: {c.get('stato')}")

# Check practice documents
r2 = s.get('http://127.0.0.1:8123/api/rc/candidates/104/practice-documents')
print(f"\n=== Practice documents: {r2.status_code} ===")
try:
    docs = r2.json()
    print(f"  Count: {len(docs) if isinstance(docs, list) else docs}")
    if isinstance(docs, list):
        for d in docs:
            print(f"  - id={d.get('id')} titolo={d.get('titolo')} categoria={d.get('categoria_documentale')} stato={d.get('stato_verifica')}")
except:
    print(f"  Body: {r2.text[:300]}")

# Check ext practices
r3 = s.get('http://127.0.0.1:8123/api/rc/candidates/104/ext-practices')
print(f"\n=== Ext practices: {r3.status_code} ===")
try:
    pr = r3.json()
    print(f"  Count: {len(pr) if isinstance(pr, list) else pr}")
    if isinstance(pr, list):
        for p in pr:
            print(f"  - id={p.get('id')} stato={p.get('stato')} protocollo={p.get('protocollo')}")
except:
    print(f"  Body: {r3.text[:300]}")

# Run new AI analysis
print(f"\n=== New AI Analysis ===")
r4 = s.post('http://127.0.0.1:8123/api/rc/candidates/104/ai-analysis')
print(f"Status: {r4.status_code}")
if r4.status_code == 200:
    ai = r4.json()
    # Cross-check
    print("\n--- Cross-check ---")
    cc = ai.get('cross_check', {})
    for source, info in cc.items():
        print(f"  {source}: {info['count']} match")
        for m in info.get('matches', [])[:3]:
            print(f"    - {m}")
    # Process logic
    print("\n--- Process logic (full) ---")
    pl = ai.get('processo_logico', '')
    print(pl[:4000])
    # Honors
    print("\n--- Onorificenze ---")
    for h in ai.get('onorificenze_analizzate', []):
        print(f"  {h['onorificenza']}: {h['percentuale_stimata']}%")
    # Fattori
    print("\n--- Fattori ---")
    for f in ai.get('fattori', []):
        print(f"  [{f.get('tipo')}] {f.get('descrizione')}")
    # Raccomandazioni
    print("\n--- Raccomandazioni ---")
    for r in ai.get('raccomandazioni', []):
        print(f"  {r}")
else:
    print(f"Body: {r4.text[:500]}")

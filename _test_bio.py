import urllib.request, json

# 1. Test search-validated
r = urllib.request.urlopen('http://localhost:8000/api/search-validated?q=Gaiaschi&limit=5&external=false', timeout=15)
d = json.loads(r.read())
print("=== SEARCH VALIDATED ===")
print("status:", d.get('status'))
print("records:", d.get('summary', {}).get('total_records', 0))
print("confirmations:", len(d.get('confirmations', [])))
s = d.get('results', d).get('internati', [])
for x in s:
    print(f"  {x.get('cognome')} {x.get('nome')} | nascita: {x.get('luogo_nascita')} {x.get('data_nascita')} | cattura: {x.get('luogo_cattura')} {x.get('data_cattura')}")

# 2. Test biography generation (AI)
print("\n=== BIOGRAPHY GENERATION (AI) ===")
try:
    req = urllib.request.Request(
        'http://localhost:8000/api/biography',
        data=json.dumps({"subject_type": "soldier", "soldier_id": 22808, "provider": "perplexity"}).encode(),
        headers={'Content-Type': 'application/json'},
        method='POST'
    )
    r2 = urllib.request.urlopen(req, timeout=120)
    bio = json.loads(r2.read())
    print("ok:", bio.get('ok'))
    print("provider:", bio.get('provider'))
    print("model:", bio.get('model'))
    print("online_sources:", len(bio.get('online_sources', [])))
    for os in bio.get('online_sources', [])[:5]:
        print(f"  [{os.get('title','')[:60]}] {os.get('url','')[:80]}")
    print("\nrisposta (first 1000 chars):")
    print((bio.get('risposta') or '')[:1000])
except Exception as e:
    print(f"Error: {e}")
    import traceback
    traceback.print_exc()

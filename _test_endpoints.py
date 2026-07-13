import requests, json

BASE = 'http://127.0.0.1:8000'

for rid, name in [(2344, 'ALTA Antonio'), (2350, 'ARTI Saverio')]:
    print(f'=== {name} (id={rid}) ===')

    # Test /fonti
    r = requests.get(f'{BASE}/api/internati/{rid}/fonti')
    d = r.json()
    archives = d.get('archives', [])
    total = d.get('total', 0)
    print(f'  /fonti  HTTP {r.status_code}  ok={d.get("ok")}  total={total}  archives={archives}')
    for arch, items in list((d.get('by_archive') or {}).items())[:2]:
        primo = items[0]['titolo'][:50] if items else '-'
        print(f'    {arch}: {len(items)} fonti, prima="{primo}"')

    # Test /opengraph
    r2 = requests.get(f'{BASE}/api/internati/{rid}/opengraph')
    d2 = r2.json()
    print(f'  /opengraph  HTTP {r2.status_code}  ok={d2.get("ok")}')
    if d2.get('ok'):
        og = d2.get('og', {})
        card = d2.get('card', {})
        print(f'    title: {og.get("title", "")[:80]}')
        print(f'    desc:  {og.get("description", "")[:110]}')
        print(f'    fonti_count={card.get("fonti_count")}  grado={card.get("grado")}  sorte={card.get("sorte")}')
    print()

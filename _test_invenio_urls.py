import requests
requests.packages.urllib3.disable_warnings()
urls=[
    'https://invenio.bundesarchiv.de/invenio/switch.xhtml',
    'https://invenio.bundesarchiv.de/invenio/search.xhtml',
    'https://invenio.bundesarchiv.de/invenio/suche.xhtml',
    'https://invenio.bundesarchiv.de/invenio/start.xhtml',
    'https://invenio.bundesarchiv.de/invenio/index.xhtml',
]
with open('_invenio_url_test.txt','w') as out:
    for u in urls:
        try:
            r = requests.get(u, timeout=20, verify=False, headers={'User-Agent':'Mozilla/5.0'})
            out.write(f'{r.status_code} | {u} | ct={r.headers.get("content-type","")} | len={len(r.text)}\n')
        except Exception as e:
            out.write(f'ERR | {u} | {e}\n')
print('Done')

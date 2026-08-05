import requests
r = requests.post('http://127.0.0.1:8000/research/reports/testv6/conversations', json={
    'snapshot': {
        'snapshot_id': 'test', 'schema_version': '6', 'intent': 'PERSON_LOOKUP',
        'target': {'display_name': 'TEST', 'conflict': 'WWI'},
        'origin': {'presence': 'ABSENT', 'provenance': 'UNVERIFIED'},
        'identity_resolution': 'UNRESOLVED', 'manifest_hash': 'test'
    }
})
d = r.json()
print('Create:', r.status_code, d)
cid = d.get('conversation_id', '')
r2 = requests.get(f'http://127.0.0.1:8000/research/conversations/{cid}/versions')
print('Versions:', r2.status_code, r2.json())

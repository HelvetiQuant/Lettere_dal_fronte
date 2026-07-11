"""Test rapido provider WikiTree."""
import warnings
warnings.filterwarnings('ignore')

from source_providers.wikitree import ProviderWikiTree

p = ProviderWikiTree()

# Test 1: nome italiano comune
print("=== Test 1: 'Rossi Mario' ===")
results = p.search('Rossi Mario')
print(f"Risultati: {len(results)}")
for r in results[:5]:
    print(f"  {r['titolo'][:60]}")
    print(f"    {r['description'][:80]}")
    print(f"    conf={r['confidence']} URL={r['catalog_url']}")
    print()

# Test 2: nome dal DB IMI
print("=== Test 2: 'Bramuso Alfredo' ===")
results = p.search('Bramuso Alfredo')
print(f"Risultati: {len(results)}")
for r in results[:5]:
    print(f"  {r['titolo'][:60]}")
    print(f"    {r['description'][:80]}")
    print(f"    conf={r['confidence']} URL={r['catalog_url']}")
    print()

# Test 3: solo cognome
print("=== Test 3: 'Bramuso' (solo cognome) ===")
results = p.search('Bramuso')
print(f"Risultati: {len(results)}")
for r in results[:5]:
    print(f"  {r['titolo'][:60]}")
    print(f"    {r['description'][:80]}")
    print()

# Test 4: nome storico militare
print("=== Test 4: 'Mussolini Benito' ===")
results = p.search('Mussolini Benito')
print(f"Risultati: {len(results)}")
for r in results[:5]:
    print(f"  {r['titolo'][:60]}")
    print(f"    {r['description'][:80]}")
    print(f"    conf={r['confidence']} URL={r['catalog_url']}")
    print()

# Test 5: verifica registry
print("=== Test 5: registry federation ===")
from source_providers.federation import list_providers
providers = list_providers()
print(f"Provider totali: {len(providers)}")
wt = [p for p in providers if p['name'] == 'wikitree']
if wt:
    print(f"WikiTree registrato: {wt[0]}")
else:
    print("WikiTree NON registrato!")

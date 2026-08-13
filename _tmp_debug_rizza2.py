"""Debug RIZZA GIOVANNI — dump claims and observations."""
import sqlite3, json, time
from unified_orchestrator_v7 import UnifiedResearchOrchestratorV7

orch = UnifiedResearchOrchestratorV7()
t0 = time.time()
result = orch.execute("RIZZA GIOVANNI", intent="PERSON_LOOKUP")
elapsed = time.time() - t0

# Extract snapshot
snap = None
if hasattr(result, 'evidence_snapshot'):
    snap = result.evidence_snapshot
elif isinstance(result, dict):
    snap = result.get('evidence_snapshot')

if snap:
    print(f"Identity Status: {snap.identity_status}")
    print(f"Corroboration: {snap.corroboration_status}")
    print(f"Person Claims: {len(snap.person_claims)}")
    print(f"Context Claims: {len(snap.context_claims)}")
    print(f"Provider Ledger: {len(snap.provider_ledger)} observations")

    print(f"\n=== PERSON CLAIMS (ALL) ===")
    for i, c in enumerate(snap.person_claims):
        if hasattr(c, '__dict__'):
            d = c.__dict__
        elif isinstance(c, dict):
            d = c
        else:
            print(f"  [{i}] {c}")
            continue
        # Print key fields
        claim_id = d.get('claim_id', d.get('id', '?'))
        predicate = d.get('predicate', '?')
        value = d.get('value_raw', d.get('value', '?'))
        status = d.get('verification_status', d.get('status', '?'))
        source = d.get('source_table', d.get('source', '?'))
        print(f"  [{i}] id={claim_id} pred={predicate} val={value} status={status} src={source}")

    print(f"\n=== PROVIDER LEDGER (first 20) ===")
    for i, obs in enumerate(snap.provider_ledger[:20]):
        if hasattr(obs, '__dict__'):
            d = obs.__dict__
        elif isinstance(obs, dict):
            d = obs
        else:
            print(f"  [{i}] {obs}")
            continue
        provider = d.get('provider', d.get('source_table', '?'))
        entity = d.get('entity_label', d.get('entity', '?'))
        print(f"  [{i}] provider={provider} entity={entity}")

    # Check target
    print(f"\n=== TARGET ===")
    if snap.target:
        if hasattr(snap.target, '__dict__'):
            print(snap.target.__dict__)
        else:
            print(snap.target)

# Check what tables contributed
print(f"\n=== OBSERVATIONS BY TABLE ===")
if snap and hasattr(snap, 'provider_ledger'):
    tables = {}
    for obs in snap.provider_ledger:
        if hasattr(obs, '__dict__'):
            t = obs.__dict__.get('source_table', obs.__dict__.get('provider', '?'))
        elif isinstance(obs, dict):
            t = obs.get('source_table', obs.get('provider', '?'))
        else:
            t = '?'
        tables[t] = tables.get(t, 0) + 1
    for t, c in sorted(tables.items(), key=lambda x: -x[1]):
        print(f"  {t}: {c}")

print(f"\nElapsed: {elapsed:.1f}s")

import json
import memory_router

memory_router._init_tables()

TEST_QUERIES = [
    "Rossi Mario 64 reggimento fanteria Grecia 1943",
    "Lagebericht 117 Jager Division Balcani",
    "diario storico NARA T315 1944",
    "caduti Bologna 1917",
    "internati militari italiani campo Sandbostel",
    "cavaleria",   # vaga
]

for q in TEST_QUERIES:
    r = memory_router.route_query(q)
    print(f"\n{'='*60}")
    print(f"QUERY: {q}")
    print(f"  cues:       {json.dumps({k:v for k,v in r['cues'].items() if v and k != 'raw'})}")
    print(f"  route:      {r['route']}")
    print(f"  ms:         {r['response_ms']}")
    print(f"  confidence: {r['confidence']}")
    print(f"  sources:    {len(r['sources_found'])} (verified={len(r['verified_sources'])}, image_only={len(r['image_only_sources'])})")
    print(f"  need_cloud: {r['need_cloud_ai']}")
    if r['suggested_next_steps']:
        for s in r['suggested_next_steps']:
            print(f"  → {s}")
    for src in r['sources_found'][:2]:
        tbl = src.get('table')
        score = src.get('score_final', 0)
        d = src.get('data', {})
        label = d.get('valore') or d.get('cognome') or d.get('titolo_documento') or d.get('nominativo') or tbl
        print(f"    [{score:.2f}] {src['source']}:{tbl} — {str(label)[:60]}")

print(f"\n{'='*60}")
print(f"Traces salvate: {memory_router.count_traces()}")
print(f"Consolidated:   {len(memory_router.get_consolidated())}")

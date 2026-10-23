# Evidence Snapshot Persistente — Memorizzazione e Riproducibilità

**Versione**: 1.0  
**Data**: 2026-08-17  
**Modulo di riferimento**: `evidence_snapshot_service.py`  
**Schema di riferimento**: `linking/schema_v2.py` (tabella `evidence_snapshots`)

---

## 1. Modello

```
EvidenceSnapshotV7 (in-memory)
       │
       ↓ save_snapshot()
       │
evidence_snapshots (DB)
  ├── id (TEXT PK)
  ├── query (TEXT)
  ├── intent (TEXT)
  ├── created_at (TEXT)
  ├── pipeline_version (TEXT)
  ├── algorithm_versions (JSON)
  ├── source_ids (JSON array)
  ├── evidence_ids (JSON array)
  ├── claim_ids (JSON array)
  ├── relation_ids (JSON array)
  ├── rejected_candidates (JSON)
  ├── conflicts (JSON)
  ├── context_hash (SHA-256)
  ├── answer_hash (SHA-256)
  └── snapshot_json (TEXT — full serialization)
       │
       ↓ load_snapshot()
       │
EvidenceSnapshotV7 (reconstructed)
```

### Principi

1. **Immutabile**: una volta salvato, `snapshot_json` non può essere modificato
2. **Riproducibile**: ogni risposta storica significativa deve essere ricostruibile dal suo snapshot
3. **Integrità**: `context_hash` verifica che il contenuto non sia stato alterato
4. **Tracciabilità**: `answer_hash` lega la risposta AI a uno specifico bundle di evidence
5. **Idempotente**: salvare lo stesso snapshot due volte non crea duplicati

---

## 2. Hash di Integrità

### `context_hash`

SHA-256 della serializzazione JSON completa del snapshot (sort_keys=True). Garantisce che il contenuto non sia stato alterato.

### `answer_hash`

SHA-256 di `context_hash + answer_text`. Lega la risposta AI al bundle di evidence specifico.

### Verifica

```python
service = EvidenceSnapshotService(conn)
is_valid, violations = service.verify_integrity(snapshot_id)
```

Ricalcola `context_hash` dal `snapshot_json` e verifica che corrisponda al valore memorizzato.

---

## 3. API di Utilizzo

```python
from evidence_snapshot_service import EvidenceSnapshotService

service = EvidenceSnapshotService(conn)

# Save snapshot
snap_id = service.save_snapshot(
    snapshot,
    answer_text="Rossi Mario nacque a Roma...",
    algorithm_versions={"linking": "2.0.0", "narrator": "7.2"},
)

# Load snapshot
loaded = service.load_snapshot(snap_id)

# List snapshots
snapshots = service.list_snapshots(intent="PERSON_LOOKUP", limit=50)

# Link relations
service.link_relations(snap_id, ["rel_1", "rel_2"])

# Verify integrity
is_valid, violations = service.verify_integrity(snap_id)

# Stats
stats = service.get_stats()

# Find by hash
found = service.get_by_context_hash(context_hash)

# Delete (with relation unlink)
service.delete_snapshot(snap_id)
```

---

## 4. Modifiche Apportate (Fase 6)

### Modulo nuovo

- `evidence_snapshot_service.py` — `EvidenceSnapshotService` class:
  - `save_snapshot()`: serializza + persiste con hash
  - `load_snapshot()`: deserializza → EvidenceSnapshotV7
  - `list_snapshots()`: query con filtri (intent, date)
  - `link_relations()`: collega relazioni via FK
  - `verify_integrity()`: verifica context_hash
  - `get_by_context_hash()`: lookup per hash
  - `get_stats()`: statistiche
  - `delete_snapshot()`: eliminazione sicura (unlink + delete)

### Test

- 10/10 test PASS: save, load, idempotency, integrity, list, filter, link, stats, hash lookup, delete

---

*Fase 6 completata — pronto per Fase 7: Event Ontology gerarchica*

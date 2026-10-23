# Event Ontology Gerarchica — Gestione Persistente

**Versione**: 1.0  
**Data**: 2026-08-17  
**Modulo di riferimento**: `event_ontology_service.py`  
**Schema di riferimento**: `event_schema.py` (colonna `parent_event_id`, tabella `event_aliases`)

---

## 1. Modello Gerarchico

```
Campaign (livello 0)
  └── Battle (livello 1)
       └── Phase (livello 2)
            └── Skirmish (livello 3)
```

### Esempio: Fronte Isonzo

```
Battaglie dell'Isonzo (campaign, 1915-06-23 → 1917-11-12)
  ├── Battaglia di Caporetto (battle, 1917-10-24 → 1917-11-12)
  │    └── Settore di Tolmino (phase, 1917-10-24 → 1917-11-12)
  └── Settore di Tolmino (phase, 1915-06-23 → 1917-11-12)
```

### Regole

1. **Contenimento temporale**: il figlio deve iniziare ≥ del genitore e finire ≤ del genitore
2. **Niente cicli**: un evento non può essere antenato di se stesso
3. **Gerarchia tipi**: campaign > battle > phase > skirmish (warning se violata)
4. **Alias multipli**: ogni evento può avere nomi alternativi (`event_aliases`)
5. **Persistenza**: `parent_event_id` in `eventi_1gm`, alias in `event_aliases`

---

## 2. API di Utilizzo

```python
from event_ontology_service import EventOntologyService

service = EventOntologyService(events_conn)

# Hierarchy queries
event = service.get_event(event_id)
children = service.get_children(event_id)
descendants = service.get_descendants(event_id, max_depth=10)
ancestors = service.get_ancestors(event_id)
siblings = service.get_siblings(event_id)
tree = service.get_full_tree()

# Hierarchy management
success, msg = service.set_parent(child_id, parent_id)
success, msg = service.remove_parent(event_id)

# Alias management
service.add_alias(event_id, "Isonzo", alias_type="alias")
aliases = service.get_aliases(event_id)
service.remove_alias(event_id, "Isonzo")

# Validation
violations = service.validate_hierarchy()

# Bootstrap from event_resolver.py HIERARCHY dict
stats = service.bootstrap_from_resolver(dry_run=True)

# Stats
stats = service.get_stats()
```

---

## 3. Validazioni

### `set_parent` — controlli pre-inserimento

| Check | Esito |
|-------|-------|
| Evento non trovato | ❌ Error |
| Self-parenting | ❌ Error |
| Ciclo (evento è antenato del genitore) | ❌ Error |
| Contenimento temporale violato | ❌ Error |
| Tipo figlio ≤ tipo genitore | ⚠️ Warning (permesso) |

### `validate_hierarchy` — validazione globale

| Violation | Descrizione |
|-----------|-------------|
| `invalid_parent_id` | `parent_event_id` non è un intero valido |
| `parent_not_found` | L'evento genitore non esiste nel DB |
| `temporal_start_before_parent` | Il figlio inizia prima del genitore |
| `temporal_end_after_parent` | Il figlio finisce dopo il genitore |

---

## 4. Integrazione con `event_resolver.py`

Il metodo `bootstrap_from_resolver()` popola `parent_event_id` dalla mappa `HIERARCHY` hardcoded in `event_resolver.py`, con validazione temporale e rilevamento cicli.

```python
stats = service.bootstrap_from_resolver(dry_run=True)
# → {"matched": 5, "set": 8, "skipped": 2, "errors": 0}
```

---

## 5. Modifiche Apportate (Fase 7)

### Modulo nuovo

- `event_ontology_service.py` — `EventOntologyService` class:
  - `get_event()`, `get_event_by_stable_id()`
  - `get_children()`, `get_descendants()`, `get_ancestors()`, `get_siblings()`
  - `get_full_tree()`
  - `set_parent()`, `remove_parent()`
  - `add_alias()`, `get_aliases()`, `remove_alias()`
  - `validate_hierarchy()`
  - `bootstrap_from_resolver()`
  - `get_stats()`
  - `EventNode` dataclass
  - `EVENT_TYPE_HIERARCHY` mapping (campaign > battle > phase > skirmish)

### Test

- 15/15 test PASS: get event, set parent, get children, descendants, ancestors, siblings, cycle detection, temporal violation, aliases (add/get/remove), full tree, hierarchy validation, stats, remove parent

---

*Fase 7 completata — pronto per Fase 8: Migration batch legacy → V2*

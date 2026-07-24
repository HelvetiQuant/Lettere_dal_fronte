# Percorso Riconoscimenti — Documentazione Tecnica e Operativa

Modulo per l'identificazione di potenziali candidati a riconoscimenti, decorazioni e onorificenze sulla base di fonti storiche documentate.

## Avvertenza fondamentale

Il sistema **non attribuisce** riconoscimenti. Utilizza sempre espressioni come:
- "potenziale candidato"
- "riconoscimento ipotizzato"
- "procedura potenzialmente praticabile"
- "verifica amministrativa necessaria"
- "nessuna garanzia di concessione"

Nessuna valutazione generata dall'AI è considerata decisione definitiva.

---

## Avvio

Il modulo è integrato nell'app FastAPI esistente. Avviare il server:

```bash
python -m uvicorn app:app --host 127.0.0.1 --port 8123
```

Accesso:
- **Frontend operatori**: `http://127.0.0.1:8123/riconoscimenti`
- **API**: `http://127.0.0.1:8123/api/rc/`
- **Credenziali default**: admin / admin

---

## Ruoli e permessi

| Ruolo | Permessi |
|---|---|
| **Amministratore** | Accesso completo, gestione utenti, catalogo riconoscimenti, audit |
| **Ricercatore storico** | Creazione candidati, caricamento fonti, ricostruzione eventi |
| **Revisore amministrativo** | Valutazione requisiti, approvazione contatti familiari |
| **Genealogista** | Ricostruzione parentela, gestione discendenti |
| **Operatore pratiche** | Preparazione fascicolo, gestione comunicazioni, monitoraggio pratiche |
| **Discendente** | Accesso solo al proprio fascicolo via invito |

---

## Workflow

```
Fonte storica → estrazione nominativo → creazione candidato → identificazione
→ ricostruzione evento → verifica fonti → ipotesi riconoscimento
→ valutazione storica → valutazione amministrativa
→ autorizzazione ricerca discendenti → ricostruzione genealogica
→ contatto mediato → adesione famiglia → verifica discendenza
→ preparazione fascicolo → approvazione → trasmissione
→ monitoraggio → esito
```

### State machine (25 stati)

BOZZA → IDENTIFICAZIONE_IN_CORSO → IDENTITA_VERIFICATA → FONTI_IN_VERIFICA → VALUTAZIONE_STORICA → VALUTAZIONE_AMMINISTRATIVA → PROCEDURA_POTENZIALMENTE_PRATICABILE → RICERCA_DISCENDENTI_AUTORIZZATA → DISCENDENTI_IN_RICERCA → POSSIBILE_DISCENDENTE_INDIVIDUATO → CONTATTO_DA_APPROVARE → CONTATTO_INOLTRATO → FAMIGLIA_ADERENTE → DISCENDENZA_VERIFICATA → FASCICOLO_IN_PREPARAZIONE → FASCICOLO_DA_APPROVARE → PRATICA_TRASMESSA → RICONOSCIMENTO_CONCESSO → PRATICA_ARCHIVIATA

Stati alternativi: DOCUMENTAZIONE_INSUFFICIENTE, PROCEDURA_NON_PRATICABILE, RICONOSCIMENTO_GIA_CONCESSO, FAMIGLIA_NON_INTERESSATA, INTEGRAZIONE_RICHIESTA, PRATICA_RESPINTA.

---

## Schema database

14 tabelle con prefisso `rc_` nel DB esistente `imi_internati.db`:

| Tabella | Descrizione |
|---|---|
| `rc_candidates` | Candidati con stato workflow |
| `rc_historical_events` | Eventi storici collegati |
| `rc_sources` | Fonti documentali |
| `rc_recognition_types` | Catalogo riconoscimenti (12 voci seed) |
| `rc_recognition_assessments` | Valutazioni riconoscimento |
| `rc_family_persons` | Persone famiglia (con visibilità limitata) |
| `rc_kinship_links` | Rapporti parentela |
| `rc_contact_attempts` | Tentativi contatto (con approvazione) |
| `rc_descendant_cases` | Casi discendenti |
| `rc_administrative_cases` | Pratiche amministrative |
| `rc_audit_log` | Log audit completo |
| `rc_state_transitions` | Storico transizioni stato |
| `rc_invitations` | Inviti area discendente |
| `rc_documents` | Documenti caricati |

Tabelle auth: `rc_users`, `rc_sessions`.

---

## API reference

### Auth
- `POST /api/rc/auth/login` — Login (set cookie)
- `POST /api/rc/auth/logout` — Logout
- `GET /api/rc/auth/me` — Utente corrente
- `GET /api/rc/auth/users` — Lista utenti (admin)
- `POST /api/rc/auth/users` — Crea utente (admin)
- `PUT /api/rc/auth/users/{uid}` — Aggiorna utente
- `DELETE /api/rc/auth/users/{uid}` — Elimina utente (admin)

### Candidati
- `GET /api/rc/candidates` — Lista con filtri
- `GET /api/rc/candidates/{cid}` — Dettaglio
- `POST /api/rc/candidates` — Crea
- `PUT /api/rc/candidates/{cid}` — Aggiorna
- `POST /api/rc/candidates/{cid}/transition` — Cambia stato
- `GET /api/rc/candidates/{cid}/history` — Cronologia
- `POST /api/rc/candidates/{cid}/dossier` — Genera PDF

### Fonti
- `GET /api/rc/candidates/{cid}/sources`
- `POST /api/rc/candidates/{cid}/sources`
- `PUT /api/rc/sources/{sid}`
- `POST /api/rc/sources/{sid}/upload` — Upload file

### Valutazioni
- `GET /api/rc/candidates/{cid}/assessments`
- `POST /api/rc/candidates/{cid}/assessments`

### Genealogia
- `GET /api/rc/candidates/{cid}/family`
- `POST /api/rc/candidates/{cid}/family`
- `GET /api/rc/candidates/{cid}/kinship`
- `POST /api/rc/kinship`

### Contatti
- `GET /api/rc/candidates/{cid}/contacts`
- `POST /api/rc/candidates/{cid}/contacts`
- `POST /api/rc/contacts/{coid}/approve`

### Discendenti
- `GET /api/rc/candidates/{cid}/descendant-cases`
- `POST /api/rc/candidates/{cid}/descendant-cases`
- `POST /api/rc/descendant-cases/{dcid}/invitation`

### Pratiche
- `GET /api/rc/candidates/{cid}/admin-cases`
- `POST /api/rc/candidates/{cid}/admin-cases`
- `PUT /api/rc/admin-cases/{acid}`

### Catalogo
- `GET /api/rc/recognition-types`
- `POST /api/rc/recognition-types` (admin)
- `PUT /api/rc/recognition-types/{rid}` (admin)

### Dashboard & Audit
- `GET /api/rc/dashboard`
- `GET /api/rc/audit`
- `GET /api/rc/states`

### Pubblico (discendenti)
- `GET /api/rc/public/invitation/{token}` — Visualizza invito
- `POST /api/rc/public/invitation/{token}/accept` — Accetta invito
- `GET /api/rc/public/case/{dcid}` — Visualizza caso
- `POST /api/rc/public/case/{dcid}/upload` — Upload documento
- `POST /api/rc/public/case/{dcid}/consent` — Gestione consenso
- `POST /api/rc/public/recognize` — Modulo pubblico "Riconosci questo nominativo?"

---

## Variabili d'ambiente

```
RC_SECRET_KEY=          # Firma sessioni (default: rc-dev-secret-change-in-prod)
RC_SESSION_TTL_HOURS=24 # Durata sessione
```

---

## Privacy e sicurezza

- **Privacy by design**: dati persone viventi non esposti (data_nascita, luogo_nascita)
- **Controllo accessi per ruolo**: 6 ruoli con permessi differenziati
- **Sessioni**: cookie HttpOnly, token casuale, scadenza configurabile
- **Audit log**: ogni azione registrata con utente, timestamp, valore precedente/successivo
- **Contatto mediato**: nessun invio automatico, approvazione umana obbligatoria
- **Portale discendente**: accesso via token invito, solo fonti verificate

### Da approvare con DPO/consulente privacy
1. Base giuridica per contatto discendenti (configurabile)
2. Conservazione dati e cancellazione
3. Valutazione d'impatto DPIA
4. Registro trattamenti
5. Data breach log

---

## Test

```bash
python -m pytest tests/test_rc_master.py -v
```

25 test: auth, state machine, schema, privacy, dossier, workflow completo.

---

## File creati

| File | Descrizione |
|---|---|
| `auth.py` | Autenticazione session-based, 6 ruoli |
| `rc_schema.py` | Schema DB, 14 tabelle, seed catalogo |
| `rc_state_machine.py` | State machine 25 stati, transizioni, audit |
| `rc_api.py` | Router FastAPI con tutti gli endpoint |
| `rc_dossier.py` | Generazione fascicolo PDF (reportlab) |
| `templates/rc.html` | Frontend SPA operatori |
| `tests/test_rc_master.py` | Test master (25 test) |

## File modificati

| File | Modifica |
|---|---|
| `app.py` | Import auth/rc_schema/rc_api, init tabelle in lifespan, route `/riconoscimenti` |
| `requirements.txt` | Aggiunto bcrypt, reportlab |

---

## Rischi residui

1. **Cifratura a riposo**: SQLite non cifra nativamente; valutare SQLCipher
2. **Rate limiting**: non implementato; aggiungere slowapi
3. **Antivirus upload**: non disponibile; documentare come funzionalità rinviata
4. **URL firmati per file**: da implementare con token temporanei
5. **Email reali**: template predisposto, invio manuale nell'MVP
6. **DOCX export**: solo PDF nell'MVP

## Funzionalità rinviate

- Connettori API esterne (Normattiva, Gazzetta Ufficiale)
- OCR automatico con AI (usa infrastruttura esistente, approvazione manuale)
- Notifiche email automatiche
- Export DOCX
- DPIA formale
- Data breach log workflow

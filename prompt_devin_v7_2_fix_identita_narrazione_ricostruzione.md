# PROMPT DEVIN — V7.2: separazione delle identità e vera ricostruzione narrativa

Agisci come principal backend engineer, information-retrieval engineer, data architect e historical-research systems engineer sul repository corrente.

Devi correggere la pipeline V7.1 realmente attiva, senza creare moduli paralleli lasciati fuori dal call path. Parti dai file dichiarati nel documento V7.1 Pipeline — Metodologia, Logica e Fonti di Ricerca, individua gli endpoint pubblici che li chiamano e modifica quel percorso. Il lavoro deve essere generale: i nomi del canary sono esclusivamente sentinelle di regressione; sono vietati hardcode, eccezioni nominative e soglie tarate sui singoli casi.

L'obiettivo non è rendere il report più lungo. È produrre una risposta storica leggibile che:

- racconti soltanto i dati attribuibili alla stessa persona;
- distingua fatti personali, contesto storico e ipotesi;
- ricostruisca cronologicamente ciò che le fonti consentono;
- conservi tutti i dettagli tecnici nel ledger, senza riversarli nel testo;
- usi le maggiori informazioni disponibili senza trasformare omonimi, snippet e contesto in fatti personali.

---

## 0. Vincoli non negoziabili

1. Non leggere, stampare, modificare o copiare `.env`.
2. Non eseguire `_check_keys.py`.
3. Non modificare dati grezzi o OCR d'origine; usa overlay versionati e tracciabili.
4. Non promuovere un risultato di ricerca a evidenza senza FETCH, estrazione, locator e gate identitario.
5. Non considerare due provider AI come due fonti indipendenti se citano la stessa pagina o lo stesso record.
6. Non dichiarare RESOLVED quando più record con lo stesso nome completo non sono separabili con identificatori discriminanti.
7. Non esporre nel report utente ID interni, codici enum, numero di osservazioni, scarti per solo cognome, confidence grezze o reason code.
8. OpenAI, Mistral, Claude, Gemini e gli altri modelli possono narrare lo stesso snapshot validato; nessun LLM decide identità, stato dei claim o indipendenza delle fonti.
9. Il fallback deterministico deve rispettare lo stesso contratto narrativo dell'output AI.
10. Non dichiarare superato il canary con fixture sintetiche, endpoint non pubblici o snapshot costruiti a mano.

---

## 1. Diagnosi da correggere nel sistema esistente

### 1.1 Il resolver premia il cognome e sceglie comunque un vincitore

La V7.1 documenta questo comportamento:

- discovery locale con `LIKE cognome%`, fino a 20 righe per tabella;
- cognome esatto +0.5, nome esatto +0.4;
- il miglior punteggio diventa `resolved_identity`;
- gli altri candidati con score > 0.3 diventano omonimi;
- il controllo discriminante usa quasi soltanto anno e luogo di nascita.

Questo algoritmo è logicamente insufficiente. Un record con nome diverso ma cognome uguale raggiunge già 0.5; più record con lo stesso nome completo raggiungono tutti 0.9, ma l'ordine del database può eleggere arbitrariamente il primo. Il risultato viene poi narrato come identità risolta.

**Correzione obbligatoria:**

- la ricerca per prefisso del cognome resta ammessa solo come discovery recall;
- un nome diverso non è un omonimo del target completo: classificalo `SURNAME_ONLY_NON_CANDIDATE` e non mostrarlo all'utente;
- non scegliere mai il primo record in caso di parità;
- il nome completo può creare un cluster candidato, ma non risolve da solo l'identità se esiste più di un record compatibile;
- usa come discriminanti data/anno e luogo di nascita, paternità/maternità, comune, distretto, matricola, grado, reparto con periodo, data/luogo di morte, record d'origine e locator archivistico;
- la mancanza di un discriminante non è accordo;
- un conflitto su reparto, anno o luogo di morte tra record omonimi deve prima generare split di identità, non `conflicting_claims` sulla stessa persona.

### 1.2 La fusione non è vincolata al cluster identitario

Ogni osservazione e ogni claim devono avere obbligatoriamente:

- `target_id`
- `origin_record_id | null`
- `identity_cluster_id`
- `subject_fingerprint`
- `evidence_scope`
- `source_id`
- `source_locator`

`FusionEngine.fuse()` deve ricevere soltanto le osservazioni del `resolved_identity_cluster_id`. Le osservazioni degli altri cluster vanno in `candidate_identities[]`; non devono mai entrare in `accepted_claims`, `asserted_claims` o `conflicting_claims` del target.

**Invariante bloccante:**

```python
assert all(
    claim.identity_cluster_id == snapshot.resolved_identity_cluster_id
    for claim in snapshot.person_claims
)
```

Se l'invariante fallisce, lo snapshot è invalido e la narrazione non parte.

### 1.3 Lo stato RESOLVED è usato in modo semanticamente falso

Sostituisci il modello attuale con stati espliciti:

- `ANCHORED_RECORD`
- `RESOLVED_IDENTITY`
- `AMBIGUOUS_IDENTITY`
- `PARTIAL_IDENTITY`
- `UNRESOLVED_IDENTITY`

**ANCHORED_RECORD**: l'utente parte da uno specifico record locale; si può raccontare cosa quel record riporta, anche senza corroborazione esterna.

**RESOLVED_IDENTITY**: un solo cluster è compatibile e possiede almeno un discriminante forte o un locator nominativo univoco.

**AMBIGUOUS_IDENTITY**: due o più cluster con lo stesso nome completo restano plausibili.

**PARTIAL_IDENTITY**: esiste un record candidato, ma non abbastanza discriminanti per collegarlo ad altre fonti.

**UNRESOLVED_IDENTITY**: nessun record nominativo utilizzabile.

Non usare contemporaneamente `RESOLVED | PARTIAL` senza spiegare a quale dimensione si riferiscono. Se servono due assi, chiamali esplicitamente:

- `identity_status`
- `corroboration_status`

### 1.4 La pipeline chiama "FETCH" una fase che non apre le fonti

La V7.1 dichiara che FETCH non effettua richieste HTTP e trasforma snippet/excerpt in `METADATA_ONLY`. Questo impedisce di ricavare più informazioni e locator affidabili.

Implementa un vero ciclo:

```
DISCOVER lead
→ FETCH pagina/PDF consentito
→ EXTRACT testo + layout
→ LOCATE nome/record
→ IDENTITY GATE
→ CLAIM EXTRACTION
```

Per ogni fonte acquisisci almeno:

- URL canonico o identificativo archivistico stabile;
- ente, fondo/serie, documento, pagina;
- locator testuale e, per PDF/OCR tabellari, pagina + bounding box/row index;
- breve estratto probatorio;
- content hash e timestamp;
- stato `OPENED | METADATA_ONLY | FAILED` e motivo reale.

Uno snippet del motore di ricerca resta `LEAD`, mai `SOURCE_RECORD`.

Per OCR con elenchi a colonne non associare una descrizione a un nome in base alla sola sequenza del testo estratto. Ricostruisci il layout della pagina e lega nome e sorte tramite coordinate; se non è possibile, conserva `ROW_ALIGNMENT_UNCERTAIN` e non creare il claim.

### 1.5 "Archivio diverso" non significa "fonte indipendente"

Due pagine o database possono ripubblicare lo stesso Albo, lo stesso elenco o lo stesso OCR. La dipendenza deve usare:

- document fingerprint e content similarity;
- fondo/serie/volume/pagina;
- citation chain e `derived_from`;
- record d'origine comune;
- URL canonico e mirror relationship.

È vietata la regola `different archive => independence_score 1.0`. L'accordo fra modelli o motori di ricerca non aumenta la corroborazione storica.

### 1.6 Il validatore richiede impropriamente un URL assoluto

Un record locale o archivistico può essere valido con fondo, serie, busta, pagina e locator, anche senza URL pubblico. Sostituisci il requisito "URL assoluto verificato" con:

```
stable_source_reference AND precise_locator AND immutable_origin_hash
```

---

## 2. Separare fatti personali e contesto storico

Introduci due insiemi distinti:

- `PERSON_EVIDENCE`
- `CONTEXT_EVIDENCE`

`PERSON_EVIDENCE` può sostenere frasi su nascita, servizio, cattura, internamento, morte e sepoltura della persona.

`CONTEXT_EVIDENCE` può descrivere reparto, evento, campo, luogo o fase bellica, ma non prova che l'individuo abbia partecipato a ogni azione del reparto o vissuto ogni caratteristica del campo.

**Esempio corretto:**

> La scheda d'origine attribuisce Egineti Arturo al 220° Reggimento fanteria e colloca la morte nel 1917 durante il ripiegamento al Piave. Il 220° apparteneva alla Brigata Sele; le fonti sulla brigata permettono di inquadrare il reparto, ma non documentano da sole il percorso individuale di Egineti.

**Esempio vietato:**

> Egineti combatté in tutte le azioni della Brigata Sele e morì durante una specifica battaglia.

Ogni frase contestuale deve avere `scope = UNIT | EVENT | PLACE | CAMP | PERIOD` e il validatore deve bloccare l'attribuzione automatica al soggetto.

---

## 3. Nuovo contratto del report: discorsivo, selettivo, ricostruttivo

Il ledger tecnico resta completo. Il report visibile non è il dump dello snapshot.

### 3.1 Struttura visibile

Usa questa struttura, adattandola ai dati realmente disponibili:

1. **Apertura narrativa**: 2–4 frasi che dicano chi compare nelle fonti e qual è il livello reale di identificazione.
2. **Ricostruzione**: 2–5 brevi paragrafi in ordine cronologico; integra fatti personali e contesto esplicitamente distinto.
3. **Incertezze decisive**: massimo 2–5 punti, soltanto quelli che cambiano l'identità o l'interpretazione.
4. **Ricerca successiva mirata**: massimo 2–4 azioni specifiche, motivate dai dati già emersi.
5. **Fonti**: elenco compatto con titolo/ente, locator e link quando disponibile.

**Nascondi in un pannello tecnico opzionale:**

- `source_id`, `claim_id`, `observation_id`;
- codici come `AXIS_ONLY`, `CONFLICTING`, `ASSERTED`;
- conteggi "43 observations";
- provider ledger e timings;
- candidati con nome diverso;
- elenco automatico dei 21 campi mancanti.

### 3.2 Regole editoriali

- Scrivi "Seconda guerra mondiale — Internati Militari Italiani", non `AXIS_ONLY`.
- Scrivi "la scheda d'origine riporta", "una fonte esterna documenta", "il contesto del reparto mostra".
- Non usare formule vuote come "figura associata al conflitto", "significative lacune limitano la comprensione" o "identità risolta con successo".
- Non ripetere in conclusione gli stessi campi già elencati.
- Non elencare tutti i dati mancanti: seleziona quelli che permetterebbero di distinguere la persona o completare la vicenda.
- Non trasformare l'assenza di risultati web in prova che un dato non esista.
- Lunghezza orientativa: 180–350 parole per record scarso; 350–700 quando esistono fatti e contesto sufficienti. Non riempire con boilerplate.
- Se l'identità è ambigua, mostra candidati separati in una tabella compatta e chiedi il discriminante necessario; non costruire una biografia unica.

### 3.3 JSON interno strutturato

Il narratore deve produrre JSON validato, non Markdown libero:

```json
{
  "identity_status": "ANCHORED_RECORD|RESOLVED_IDENTITY|AMBIGUOUS_IDENTITY|PARTIAL_IDENTITY|UNRESOLVED_IDENTITY",
  "opening": [{"text": "...", "claim_refs": ["..."]}],
  "reconstruction": [
    {
      "text": "...",
      "kind": "PERSON_FACT|CONTEXT|INFERENCE",
      "claim_refs": ["..."],
      "source_refs": ["..."]
    }
  ],
  "decisive_uncertainties": ["..."],
  "next_steps": [{"action": "...", "why": "...", "source_route": "..."}],
  "sources": ["..."]
}
```

**Regole:**

- `PERSON_FACT` richiede un claim dello stesso `identity_cluster_id`.
- `CONTEXT` richiede un context claim e non può contenere un verbo che attribuisca un'azione alla persona, salvo person evidence separata.
- `INFERENCE` deve essere esplicitamente formulata come ipotesi e non può cambiare `identity_status`.
- Il renderer risolve gli ID in citazioni leggibili e non mostra gli ID.
- Ogni frase senza riferimento viene respinta, eccetto connettivi puramente editoriali.

---

## 4. Comportamento atteso sui sei canary

### CAIS Arduino

- Non mostrare CAIS Fioravante: ha un nome diverso ed è un risultato per solo cognome.
- Se la richiesta parte dal record locale, usare `ANCHORED_RECORD` e raccontare con chiarezza che la scheda riporta il decesso.
- Non convertire l'assenza di corroborazione web in "non esistono altre informazioni".
- Non riversare l'elenco dei 21 gap; indicare soltanto i discriminanti utili, per esempio data/luogo di nascita e documento sulla sorte.

### BROGNARA Cristino

- Non elencare Luigi, Mario, Achille, Angelo e gli altri record con nome diverso.
- "Rimpatriato" resta un'affermazione della scheda d'origine finché non è collegata a un locator documentario.
- Indirizzare la ricerca verso gli elenchi nominativi IMI e archivi pertinenti senza inventare un risultato.

### TONIOLI Pasquale

- Non fondere quattro osservazioni locali come se fossero quattro destini della stessa persona.
- L'elenco dell'Archivio di Stato di Bolzano contiene il nome a pagina 59, ma nomi e descrizioni OCR devono essere riallineati con coordinate di pagina prima di attribuire una sorte.
- Fino a quel controllo, usare `PARTIAL_IDENTITY` o `ANCHORED_RECORD` con `ROW_ALIGNMENT_UNCERTAIN`, non "fato conflittuale".

### DEVINCENZI Giovanni

- I record con 1° Alpini, 7° Alpini e 14° Fanteria, anni e luoghi di morte diversi devono diventare cluster separati.
- Senza data/luogo di nascita, paternità o comune discriminante, lo stato corretto è `AMBIGUOUS_IDENTITY`.
- Non concludere genericamente "errori di trascrizione": prima ipotizzare omonimia e chiedere il discriminante.

### EGINETI Arturo

- Il record d'origine è coerente e va narrato, anche se non corroborato esternamente.
- Aggiungere contesto del 220° Fanteria/Brigata Sele soltanto come contesto di reparto.
- Non trasformare la storia della brigata in azioni individuali di Egineti.
- La risposta deve essere discorsiva: dal record, al reparto, alla fase del ripiegamento, quindi ai limiti documentari.

### RIGAMONTI Pietro

- Lo stato `RESOLVED` è vietato finché i candidati non vengono separati.
- Esiste almeno un profilo pubblico nato il 14 aprile 1887, figlio di Davide e Giuseppa Rigamonti, soldato dell'89° Fanteria; esiste inoltre un ricordo nominativo "RIGAMONTI PIETRO FU G. BATTISTA". Questi dati indicano almeno due identità possibili.
- Non unire 263° Fanteria, 9° Artiglieria, 5° Alpini, 79° e 89° Fanteria in una sola carriera.
- Presentare candidati separati e richiedere luogo/anno di nascita, paternità o comune.

---

## 5. Modifiche richieste ai moduli V7.1

Intervieni almeno su:

- **`semantic_query_plan.py`**: target ancorato a `origin_record_id`; query manifest con discriminanti immutabili.
- **`v7_provider_adapters.py`**: exact full-name query primaria; prefisso cognome solo discovery; classificazione `SURNAME_ONLY_NON_CANDIDATE`.
- **`v7_identity_model.py`**: cluster, tie handling, stati nuovi, separazione di record omonimi.
- **`unified_orchestrator_v7.py`**: vero FETCH/LOCATE; blocco prima di FUSE quando l'identità è ambigua.
- **`v7_fusion_engine.py`**: fusione limitata al cluster; source lineage reale; separazione person/context evidence.
- **`evidence_snapshot_v7.py`**: nuovi stati, cluster ID obbligatori, candidate identities, context claims e invarianti.
- **`v7_narrator.py`**: JSON strutturato, nuovo renderer discorsivo, massimo delle incertezze e rimozione dati tecnici.
- **`run_canary_v7.py`**: stessi target congelati, chiamata all'endpoint pubblico e oracle semantici sotto descritti.

Se i nomi o i file attivi sono cambiati, modifica gli equivalenti effettivamente attraversati dall'endpoint e documenta il call path; non duplicare classi con suffisso V8.

---

## 6. Test obbligatori

### 6.1 Identity isolation

- Due record stesso cognome ma nome diverso: zero candidate identities visibili e zero claim condivisi.
- Due record stesso nome completo ma reparti/anni incompatibili: `AMBIGUOUS_IDENTITY`, due cluster, zero fusion cross-cluster.
- Parità di score: nessun vincitore basato su ordine DB.
- Rerun con ordine righe invertito: stesso output e stesso snapshot hash.
- Target avviato da record detail: `origin_record_id` resta l'anchor in tutte le fasi.

### 6.2 Evidence and context

- Uno snippet senza fetch non entra in person evidence.
- Un documento OCR multi-colonna senza coordinate non produce un claim di sorte.
- Una storia di reparto entra solo in context evidence.
- Due provider che citano la stessa pagina contano come una famiglia documentaria.
- Un locator archivistico stabile senza URL pubblico è accettato.

### 6.3 Narrative contract

- Zero ID o enum interni nel testo visibile.
- Zero elenchi di persone con solo cognome in comune.
- Massimo cinque incertezze e quattro prossimi passi.
- Ogni frase sostanziale mappa a person claim o context claim.
- Nessuna frase contestuale attribuisce automaticamente azioni alla persona.
- Il fallback deterministico supera gli stessi test dell'output AI.
- Il report non ripete i campi in una conclusione boilerplate.

### 6.4 Canary end-to-end

Esegui i sei prompt esatti:

1. Dammi più informazioni possibili su CAIS Arduino
2. Dammi più informazioni possibili su BROGNARA Cristino
3. Dammi più informazioni possibili su TONIOLI Pasquale
4. Dammi più informazioni possibili su DEVINCENZI GIOVANNI
5. Dammi più informazioni possibili su EGINETI ARTURO
6. Dammi più informazioni possibili su RIGAMONTI PIETRO

Devono attraversare l'endpoint pubblico e il call path reale. Salva request, manifest, provider ledger, cluster identity, snapshot, JSON narrativo interno e Markdown finale. Non costruire snapshot manuali.

---

## 7. Gate di accettazione

Il lavoro è approvabile solo con:

```
cross_identity_claims = 0
surname_only_candidates_visible = 0
exact_name_multi_record_resolved = 0
unlocated_ocr_person_claims = 0
internal_tokens_visible = 0
unsupported_narrative_sentences = 0
context_misattributed_to_person = 0
row_order_dependent_results = 0
```

Inoltre:

- CAIS e BROGNARA non devono più mostrare liste di cognomi;
- TONIOLI non deve mostrare un falso conflitto prodotto dall'OCR;
- DEVINCENZI e RIGAMONTI devono risultare ambigui e avere cluster separati;
- EGINETI deve produrre una ricostruzione leggibile con contesto di reparto chiaramente distinto;
- una risposta AI non validata è fallimento AI, anche se il fallback funziona;
- il canary non passa se il testo è corretto ma lo snapshot contiene contaminazione nascosta.

---

## 8. Deliverable obbligatori

Consegna:

1. `V7_2_ACTIVE_CALL_PATH.md`, con endpoint → funzioni → file realmente attraversati;
2. diff dei moduli attivi modificati;
3. migrazione/schema per `identity_cluster_id`, evidence scope e locator;
4. test unitari, integration test e output con exit code;
5. `CANARY_V7_2_RESULTS.json` e `CANARY_V7_2_REPORT.md`;
6. confronto prima/dopo delle sei risposte;
7. una risposta completa di esempio per EGINETI e una risposta ambigua di esempio per RIGAMONTI;
8. inventario di eventuali snapshot/report precedenti contaminati e piano di invalidazione/versionamento;
9. elenco dei limiti rimasti, senza dichiarazioni generiche di "successo".

---

## 9. Riferimenti pubblici usati come oracle del canary

Questi riferimenti servono a verificare la logica, non autorizzano l'attribuzione automatica al target:

- **Archivio di Stato di Bolzano**, elenco IMI lettera T, pagina 59:  
  https://archiviodistatobolzano.cultura.gov.it/fileadmin/risorse/PDF/IMI-CAR/IMI_OCR/Elenchi_OCR/ASBZ_CG_022_Elenco_T.pdf

- **LeBI**, ricerca nominativa IMI e campi:  
  https://www.lessicobiograficoimi.it/frontend_prodimi.php/maps/list

- **Arolsen Archives**, ambito delle richieste nominative e limiti delle raccolte:  
  https://arolsen-archives.org/it/archivio/richiesta/

- **Brigata Sele, 219° e 220° Fanteria**:  
  https://www.frontedelpiave.info/public/modules/Fronte_del_Piave_article/Fronte_del_Piave_view_article.php?app_l2=397&app_l3=496&id_a=496&sito=Fronte-del-Piave&titolo=Brigata-Sele

- **Monumenti e lapidi 14–18**, record "RIGAMONTI PIETRO FU G. BATTISTA":  
  https://www.14-18.it/lapide/SBAS_LC_S27/36/01

- **Costa Masnaga Story**, candidato Rigamonti nato nel 1887 e 89° Fanteria:  
  https://www.costamasnaga.altervista.org/patrioti.htm

Le fonti contestuali non diventano person evidence senza un locator nominativo e un identity gate superato.

---

## 10. Ordine di esecuzione

1. Congela i sei target e acquisisci baseline end-to-end.
2. Dimostra il call path attivo.
3. Introduci identity cluster e gate bloccante prima della fusione.
4. Implementa FETCH/LOCATE reale e layout-aware OCR.
5. Separa person evidence e context evidence.
6. Migra snapshot e invalida i derivati contaminati.
7. Implementa JSON narrativo e renderer discorsivo.
8. Esegui test e canary con AI disponibile e AI_OFF.
9. Confronta prima/dopo e blocca il batch esteso finché tutti i gate non sono a zero.

Non proporre come fix l'aumento del prompt o del numero di token. La causa primaria è la contaminazione identitaria prima della narrazione; la seconda è il renderer che espone il ledger invece di trasformarlo in una ricostruzione storica controllata.

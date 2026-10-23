# TODO — Post-Sessione 27 Luglio 2026

## 🔴 Alta priorità

### 1. Rigenerare report AI per tutti gli eventi
- [x] Rigenerare "Battaglia del Carso" con GPT-4.1 (panoramica + punti_di_vista)
- [x] Verificare che le fonti reali (NARA, Internet Archive, Archivio di Stato) appaiano nei tab
- [x] Verificare che il summary di 5 righe sia visibile nelle SourceCard
- [x] Rigenerare report per alcuni dei 27 nuovi eventi WWI (Caporetto, Sesta Isonzo, Strafexpedition)
- [x] Testare il tab "Punti di vista" senza crash
- [x] Fix bug: `disambiguate_event` importava `DB` (imi_internati.db) invece di `EDB` (eventi_1gm.db)
- [x] Fix bug: `Claim.to_dict()` mancavano campi `fatto` e `fonti` per frontend
- [x] Fix bug: `Source` dataclass mancava campo `summary` in event_evidence_pipeline.py
- [x] Fix bug: claim con `concordance="verificata"` non classificati come concordanti

### 2. Provider non funzionanti
- [ ] **Perplexity**: quota esaurita — rinnovare piano su https://www.perplexity.ai/settings/api
- [ ] **Anthropic Claude**: credito insufficiente — ricaricare su https://console.anthropic.com/settings/billing
- [ ] Verificare se Mistral ha ancora quota sufficiente per fallback

### 3. Collegamento eventi-caduti per nuovi eventi
- [x] Eseguito linking per 27 nuovi eventi WWI (ID 38-64)
- [x] 72112 caduti Albo d'Oro collegati (luogo_morte match)
- [x] 574037 decorati Nastro Azzurro collegati (anno match)
- [x] 16 documenti archivio collegati (text match)
- [x] 607 fonti indice collegate (titolo/luogo/soggetti)
- [ ] Verificare che gli alias siano cercabili dal frontend (da testare manualmente)

## 🟡 Media priorità

### 4. Provider federati — test reali
- [ ] Testare effettivamente `gallica`, `hathitrust`, `googlebooks`, `internetculturale` con query reali
- [ ] Verificare che non restituiscano errori 403/timeout
- [ ] Se un provider non risponde, gestire gracefully (già fatto con `try/except` ma verificare log)

### 5. Frontend — miglioramenti UX
- [ ] Il tab "Punti di vista" ora mostra dati strutturati — valutare se mostrare anche il testo discorsivo AI
- [ ] Aggiungere indicator visivo del provider AI usato nel report
- [ ] Considerare modalità "parallel" per confrontare GPT vs Mistral

### 6. Prompt AI — validazione qualità
- [ ] Verificare che la panoramica sia effettivamente discorsiva (600-1200 parole, niente elenchi)
- [ ] Verificare che "punti di vista" sia analisi comparativa (500-1000 parole)
- [ ] Se l'AI ignora le istruzioni, rafforzare il system prompt

### 7. Context limit
- [ ] Verificare che 30000 caratteri di contesto non causino timeout o costi eccessivi
- [ ] Considerare increase a 50000 se GPT-4.1 lo supporta (limite contesto 1M token)

## 🟢 Bassa priorità

### 8. Pulizia
- [ ] Rimuovere `add_wwi_events.py` dopo aver verificato che i dati sono stabili
- [ ] Aggiornare `.env.example` con `OPENAI_MODEL=gpt-4.1` come default
- [ ] Documentare i 49 eventi nel README o docs

### 9. Testing
- [ ] Test unitario su `_build_source_summary()` (vari casi: descrizione piena, vuota, breve)
- [ ] Test su `_normalize_ia_item()` con dati reali Internet Archive
- [ ] Test frontend: SourceCard con e senza summary, con e senza fonti

### 10. Espansioni future
- [ ] Aggiungere eventi WWII mancanti (es. Resistenza, Liberazione, eccidi)
- [ ] Aggiungere eventi pre-WWI (guerra italo-turca 1911, colonie)
- [ ] Considerare eventi post-WWII (guerra fredda, Balcani)
- [ ] Integrare fonti geografiche (cartine storiche, foto d'epoca) dai nuovi provider

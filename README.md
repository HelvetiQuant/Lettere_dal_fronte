# IMI Extractor - Internati Militari Italiani

App per l'estrazione dati dagli elenchi degli Internati Militari Italiani (IMI) dall'Archivio di Stato di Bolzano.

## Fonte
https://archiviodistatobolzano.cultura.gov.it/il-patrimonio-archivistico/centro-assistenza-rimpatriati-car/documentazione-sugli-internati-militari-italiani

## Funzionalita

- Download automatico di 20 PDF (lettere A-Z) dall'Archivio di Stato di Bolzano
- Estrazione testo da PDF con pdfplumber
- Parsing intelligente con OpenAI GPT-4o (text + Vision fallback per pagine illeggibili)
- Salvataggio in database SQLite locale
- Export in Excel (.xlsx) e CSV (importabile in Excel)
- Interfaccia web con monitoraggio progresso in tempo reale

## Colonne estratte

cognome, nome, data di nascita, luogo di nascita, residenza, grado, luogo di cattura, data di cattura, luogo di internamento, matricola, arbeitskommando, mansione svolta da internato, deceduto/disperso/altro, data, documenti

## Avvio

```bash
cd C:\Users\eryma\CascadeProjects\imi_extractor
pip install -r requirements.txt
python -m uvicorn app:app --host 127.0.0.1 --port 8020
```

Apri il browser su `http://localhost:8020`.

## Utilizzo

1. Clicca "Scarica Tutti i PDF" per downloadare i 20 elenchi
2. Clicca su una lettera per estrarre i dati di quel singolo elenco, oppure "Estrai Tutte le Lettere"
3. Monitora il progresso in tempo reale (aggiornamento automatico ogni 5 secondi)
4. Al termine, clicca "Export Excel" o "Export CSV" per scaricare i dati

## Note

- L'estrazione usa l'API OpenAI (GPT-4o). La chiave viene letta automaticamente dal file `.env` del progetto "lettere dal fronte" sul Desktop
- L'estrazione puo essere interrotta e ripresa: il sistema salta le pagine gia processate
- I PDF sono gia OCRizzati dall'archivio, ma la qualita dell'OCR e variabile. GPT-4o corregge errori comuni e struttura i dati
- Per pagine con testo illeggibile, viene usato GPT-4o Vision sull'immagine della pagina

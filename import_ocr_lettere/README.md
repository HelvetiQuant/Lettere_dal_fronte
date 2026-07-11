# OCR Lettere dal Fronte

App per l'estrazione dati da lettere scritte a macchina tramite OCR con OpenAI GPT-4o Vision.

## Funzionalita

- Upload immagini (JPG, PNG, BMP, TIFF, WEBP)
- OCR con OpenAI GPT-4o Vision API
- Estrazione dati strutturati: mittente, destinatario, data, luogo, corpo testo, note
- Salvataggio in database SQLite locale
- Export in Excel (.xlsx)
- Interfaccia web per gestione completa

## Avvio

```bash
cd C:\Users\eryma\CascadeProjects\ocr_lettere
pip install -r requirements.txt
python -m uvicorn app:app --host 0.0.0.0 --port 8000
```

Apri il browser su `http://localhost:8000`.

## Configurazione API

L'app legge automaticamente `OPENAI_API_KEY` da:
1. Variabile d'ambiente
2. File `.env` nel progetto `lettere dal fronte` sul Desktop

## Struttura

- `app.py` - Server FastAPI con endpoint REST
- `ocr_engine.py` - Logica OCR con OpenAI Vision
- `database.py` - SQLite + export Excel
- `templates/index.html` - Frontend web
- `uploads/` - Directory immagini caricate
- `ocr_lettere.db` - Database SQLite

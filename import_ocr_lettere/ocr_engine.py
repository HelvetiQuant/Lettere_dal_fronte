import base64
import json
import os
from pathlib import Path
from typing import Optional

from openai import OpenAI
from PIL import Image


def _load_api_key() -> str:
    key = os.environ.get("OPENAI_API_KEY", "")
    if key:
        return key
    env_paths = [
        Path.home() / "Desktop" / "lettere dal fronte backup_2026-06-28" / ".env",
        Path.cwd() / ".env",
    ]
    for p in env_paths:
        if p.exists():
            for line in p.read_text(encoding="utf-8", errors="ignore").splitlines():
                if line.startswith("OPENAI_API_KEY="):
                    return line.split("=", 1)[1].strip().strip('"').strip("'")
    raise RuntimeError("OPENAI_API_KEY non trovata. Impostala come variabile d'ambiente o nel file .env")


def _encode_image(path: Path) -> str:
    img = Image.open(path)
    if img.mode != "RGB":
        img = img.convert("RGB")
    max_dim = 2048
    if max(img.size) > max_dim:
        ratio = max_dim / max(img.size)
        img = img.resize((int(img.width * ratio), int(img.height * ratio)))
    import io
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=90)
    return base64.b64encode(buf.getvalue()).decode("utf-8")


SYSTEM_PROMPT = (
    "Sei un esperto di archiviazione storica e OCR specializzato in lettere dal fronte della "
    "Prima e Seconda Guerra Mondiale. Analizza l'immagine di un foglio scritto a macchina e "
    "estrai TUTTI i dati leggibili. Restituisci ESCLUSIVAMENTE un oggetto JSON valido con "
    "questi campi:\n"
    "{\n"
    '  "mittente": "nome e cognome del mittente se leggibile, altrimenti null",\n'
    '  "destinatario": "nome e cognome del destinatario se leggibile, altrimenti null",\n'
    '  "data_lettera": "data riportata sulla lettera (formato YYYY-MM-DD se possibile, altrimenti testo originale)",\n'
    '  "luogo": "luogo da cui scritta la lettera",\n'
    '  "oggetto": "eventuale oggetto/intestazione",\n'
    '  "corpo_testo": "testo completo della lettera trascritto fedelmente",\n'
    '  "note": "eventuali annotazioni a margine, timbri, o osservazioni",\n'
    '  "confidenza": "valore numerico da 0 a 1 sulla qualita della lettura",\n'
    '  "lingua": "lingua del testo (it, de, fr, ecc.)"\n'
    "}\n"
    "Se un campo non e leggibile o assente, usa null. Non aggiungere commenti fuori dal JSON."
)


def run_ocr(image_path: str) -> dict:
    path = Path(image_path)
    if not path.exists():
        raise FileNotFoundError(f"Immagine non trovata: {path}")

    api_key = _load_api_key()
    client = OpenAI(api_key=api_key)

    b64 = _encode_image(path)

    response = client.chat.completions.create(
        model="gpt-4o",
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": "Analizza questa immagine di una lettera scritta a macchina ed estrai i dati strutturati come JSON.",
                    },
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:image/jpeg;base64,{b64}",
                            "detail": "high",
                        },
                    },
                ],
            },
        ],
        max_tokens=4096,
        temperature=0.1,
    )

    raw = response.choices[0].message.content.strip()

    # Pulisci eventuali markdown code fences
    if raw.startswith("```"):
        raw = raw.split("\n", 1)[1] if "\n" in raw else raw[3:]
    if raw.endswith("```"):
        raw = raw.rsplit("```", 1)[0]
    raw = raw.strip()
    if raw.startswith("json"):
        raw = raw[4:].strip()

    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        data = {
            "mittente": None,
            "destinatario": None,
            "data_lettera": None,
            "luogo": None,
            "oggetto": None,
            "corpo_testo": raw,
            "note": "Errore parsing JSON - testo grezzo salvato",
            "confidenza": 0.0,
            "lingua": None,
        }

    data["_source_file"] = path.name
    data["_raw_response"] = raw
    return data

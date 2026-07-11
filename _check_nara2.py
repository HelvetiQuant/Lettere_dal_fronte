"""Mostra testo_ocr raw dei frame con errore parsing per capire il pattern"""
from database import get_conn
import json
import re

conn = get_conn()
rows = conn.execute(
    "SELECT frame, testo_ocr, note FROM documenti_nara_t315 WHERE note LIKE '%Errore parsing%' ORDER BY frame LIMIT 5"
).fetchall()
conn.close()

for frame, raw, note in rows:
    print(f"\n{'='*60}")
    print(f"FRAME {frame}")
    print(f"RAW TEXT (primi 600 chars):\n{(raw or '')[:600]}")
    print()
    # Prova a parsare
    txt = (raw or "").strip()
    # Rimuovi backticks
    if txt.startswith("```"):
        lines = txt.split("\n")
        txt = "\n".join(lines[1:]) if len(lines) > 1 else txt[3:]
    if txt.endswith("```"):
        txt = txt.rsplit("```", 1)[0]
    txt = txt.strip()
    if txt.startswith("json"):
        txt = txt[4:].strip()
    try:
        parsed = json.loads(txt, strict=False)
        print(f"  -> PARSABILE ORA: tipo={parsed.get('tipo_documento')}, data={parsed.get('data_documento')}")
    except Exception as e:
        print(f"  -> ANCORA ERRORE: {e}")
        # Cerca JSON embedded
        m = re.search(r'\{.*\}', txt, re.DOTALL)
        if m:
            try:
                parsed2 = json.loads(m.group(), strict=False)
                print(f"  -> JSON EMBEDDED: tipo={parsed2.get('tipo_documento')}")
            except:
                print(f"  -> JSON embedded anche fallisce")
        print(f"  Prime 100 chars raw: {repr(txt[:100])}")

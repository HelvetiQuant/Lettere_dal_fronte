"""Fix in-place dei 93 frame NARA con 'Errore parsing JSON'.
Strategia:
1. Rimuove commenti JS (// ...) dal JSON
2. Tenta json.loads con strict=False
3. Per JSON troncati: estrae i campi scalari prima del troncamento con regex
4. Aggiorna il record nel DB con i dati estratti (senza richiamare Mistral)
"""
import json
import re
from database import get_conn


def _strip_js_comments(text: str) -> str:
    """Rimuove commenti // fino a fine riga dal JSON."""
    result = []
    in_string = False
    i = 0
    while i < len(text):
        c = text[i]
        if c == '"' and (i == 0 or text[i-1] != '\\'):
            in_string = not in_string
        if not in_string and c == '/' and i + 1 < len(text) and text[i+1] == '/':
            # Salta fino a fine riga
            while i < len(text) and text[i] != '\n':
                i += 1
            continue
        result.append(c)
        i += 1
    return ''.join(result)


def _try_parse(raw: str) -> dict | None:
    """Tenta vari metodi di parsing, ritorna dict o None."""
    if not raw:
        return None

    # Pulizia backtick
    text = raw.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1] if "\n" in text else text[3:]
    if text.endswith("```"):
        text = text.rsplit("```", 1)[0]
    text = text.strip()
    if text.lower().startswith("json"):
        text = text[4:].strip()

    # Tentativo 1: JSON diretto
    try:
        return json.loads(text, strict=False)
    except Exception:
        pass

    # Tentativo 2: rimuovi commenti JS
    try:
        clean = _strip_js_comments(text)
        return json.loads(clean, strict=False)
    except Exception:
        pass

    # Tentativo 3: JSON troncato — chiudi le parentesi aperte e riprova
    try:
        clean = _strip_js_comments(text)
        # Conta { e } e [ e ]
        opens_brace = clean.count('{') - clean.count('}')
        opens_bracket = clean.count('[') - clean.count(']')
        # Tronca all'ultimo campo completo rimuovendo l'ultima virgola pendente
        truncated = clean.rstrip().rstrip(',')
        # Chiudi array e oggetto
        for _ in range(max(0, opens_bracket)):
            truncated += ']'
        for _ in range(max(0, opens_brace)):
            truncated += '}'
        return json.loads(truncated, strict=False)
    except Exception:
        pass

    # Tentativo 4: estrazione regex campi scalari
    result = {}
    scalar_fields = [
        "tipo_documento", "data_raw", "data_documento",
        "numero_documento", "mittente", "destinatario",
        "perdite", "lingua", "confidenza", "note"
    ]
    for field in scalar_fields:
        m = re.search(rf'"{field}"\s*:\s*("(?:[^"\\]|\\.)*"|null|-?\d+(?:\.\d+)?)', text)
        if m:
            try:
                result[field] = json.loads(m.group(1))
            except Exception:
                result[field] = m.group(1).strip('"')

    # Estrai liste con regex semplice
    for listfield in ("unita_citate", "luoghi_citati"):
        m = re.search(rf'"{listfield}"\s*:\s*\[([^\]]*)', text, re.DOTALL)
        if m:
            items = re.findall(r'"([^"]+)"', m.group(1))
            result[listfield] = items

    # Estrai testo_ocr (può essere lungo)
    m = re.search(r'"testo_ocr"\s*:\s*"((?:[^"\\]|\\.)*)', text, re.DOTALL)
    if m:
        result["testo_ocr"] = m.group(1).replace('\\"', '"').replace('\\n', '\n')

    return result if result.get("tipo_documento") else None


def _to_str(val):
    if val is None:
        return None
    if isinstance(val, list):
        return ", ".join(str(v) for v in val if v)
    if isinstance(val, dict):
        return json.dumps(val, ensure_ascii=False)
    return str(val)


def fix_parsing_errors():
    conn = get_conn()
    rows = conn.execute(
        "SELECT frame, testo_ocr FROM documenti_nara_t315 WHERE note LIKE '%Errore parsing%' ORDER BY frame"
    ).fetchall()
    print(f"Frame con errore parsing: {len(rows)}")

    fixed = 0
    still_bad = []

    for frame, raw_text in rows:
        parsed = _try_parse(raw_text or "")
        if parsed is None:
            still_bad.append(frame)
            continue

        # Normalizza perdite se dict
        perdite = parsed.get("perdite")
        if isinstance(perdite, dict):
            perdite = json.dumps(perdite, ensure_ascii=False)
        elif perdite is not None:
            perdite = _to_str(perdite)

        # Normalizza liste
        unita = parsed.get("unita_citate") or []
        luoghi = parsed.get("luoghi_citati") or []
        if not isinstance(unita, list):
            unita = [unita] if unita else []
        if not isinstance(luoghi, list):
            luoghi = [luoghi] if luoghi else []

        conn.execute("""
            UPDATE documenti_nara_t315 SET
                tipo_documento = ?,
                data_raw = ?,
                data_documento = ?,
                numero_documento = ?,
                mittente = ?,
                destinatario = ?,
                unita_citate = ?,
                luoghi_citati = ?,
                perdite = ?,
                lingua = ?,
                confidenza = ?,
                note = ?
            WHERE frame = ?
        """, (
            _to_str(parsed.get("tipo_documento")),
            _to_str(parsed.get("data_raw")),
            _to_str(parsed.get("data_documento")),
            _to_str(parsed.get("numero_documento")),
            _to_str(parsed.get("mittente")),
            _to_str(parsed.get("destinatario")),
            json.dumps(unita, ensure_ascii=False) if unita else None,
            json.dumps(luoghi, ensure_ascii=False) if luoghi else None,
            perdite,
            _to_str(parsed.get("lingua", "de")),
            parsed.get("confidenza"),
            f"[re-parsed] {_to_str(parsed.get('note')) or ''}".strip(),
            frame,
        ))
        fixed += 1
        tipo = parsed.get("tipo_documento", "?")
        data = parsed.get("data_documento") or parsed.get("data_raw", "?")
        print(f"  Frame {frame:04d}: fixato -> {tipo} | {data}")

    conn.commit()
    conn.close()

    print(f"\nFixati: {fixed}/{len(rows)}")
    if still_bad:
        print(f"Ancora non parsabili ({len(still_bad)}): {still_bad}")


if __name__ == "__main__":
    fix_parsing_errors()

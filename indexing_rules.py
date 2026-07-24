"""Regole di normalizzazione per l'indicizzazione anagrafica.

Implementazione delle "Linee guida per l'indicizzazione" (portale Antenati —
Direzione Generale Archivi / FamilySearch International, ed. 9 luglio 2024).
Ogni funzione richiama nel docstring la sezione del manuale da cui deriva.

Principio cardine (sez. 1.2 "Scrivi ciò che vedi"): il *valore memorizzato* deve
restare fedele all'originale. Le funzioni di questo modulo servono quindi a due
scopi distinti, chiaramente separati:

  * chiave di *matching/ricerca* normalizzata (``normalize_match_key``,
    ``fold_variants``, ``expand_or_variants``) — per aumentare recall e
    deduplicare, NON per riscrivere il dato originale;
  * pulizia/normalizzazione *strutturata* di campi specifici
    (``clean_toponym``, ``normalize_age``, ``titlecase_name``,
    ``strip_titles``) — da applicare in fase di preparazione dei record.
"""
from __future__ import annotations

import re
from typing import List, Optional

# ─── Placeholder di campo vuoto (sez. 1.3.1.1.4, 1.3.8.2, guide campo 3.x) ──────
# "N.", "N.N.", "Enne", "Nessun Nome", "sconosciuto", ... → campo vuoto (Ctrl+B).
EMPTY_PLACEHOLDERS = {
    "", "n", "n n", "nn", "enne", "nessun nome", "nessunnome",
    "sconosciuto", "sconosciuta", "sconosciuti", "ignoto", "ignota",
    "non so", "non noto", "non nota", "s n", "sn",
    "-", "--", "n d", "nd", "n a", "na", "null", "unknown", "ni",
}

# ─── Titoli da NON indicizzare come parte del nome (sez. 1.3.1.1.5, 1.4.6) ──────
TITLES = {
    "signore", "signor", "sig", "sigg", "signora", "sigra", "signorina",
    "don", "donna", "cavaliere", "cav", "dottore", "dottor", "dott", "dr",
    "professore", "prof", "reverendo", "rev", "vedova", "ved", "monsignore",
    "mons", "conte", "contessa", "marchese", "barone", "nobile",
}

# ─── Preposizioni parte del cognome (sez. 1.3.7): iniziale sempre maiuscola ─────
NAME_PARTICLES = {
    "da", "de", "di", "dal", "dai", "del", "dei", "della", "delle", "dello",
    "degli", "lo", "la", "le", "li", "d", "mc", "mac", "van", "von", "der",
    "den", "ten", "ter", "san", "santa", "santo", "sant",
}

# ─── Qualificatori di luogo da rimuovere (sez. 1.4.9.1) ─────────────────────────
PLACE_QUALIFIERS = (
    "nei pressi di", "vicino a", "attorno a", "presso",
    "frazione di", "frazione", "localita di", "località di", "localita",
    "località", "comune di", "comune", "citta di", "città di",
    "provincia di", "provincia", "regione di", "regione",
    "stato di", "stato", "contea di", "contea", "cantone di", "cantone",
    "cascina", "colonnello",
)

# Eccezioni: la qualifica È parte integrante del toponimo (sez. 1.4.9.1).
PLACE_EXCEPTIONS = {
    "citta di castello", "città di castello",
    "citta della pieve", "città della pieve",
    "citta sant'angelo", "città sant'angelo",
    "citta del messico", "città del messico",
}

_APOS_RE = re.compile(r"[’`´ʼ]")
_NON_KEY_RE = re.compile(r"[^\w\s'\-]", re.UNICODE)
_WS_RE = re.compile(r"\s+")


def _unify_apostrophes(value: str) -> str:
    return _APOS_RE.sub("'", value)


def normalize_match_key(value: object) -> str:
    """Chiave normalizzata per matching/dedup (sez. 1.3.1.1, 1.3.2).

    Regole applicate:
      * minuscolo e spazi collassati;
      * punteggiatura rimossa TRANNE apostrofi e trattini che fanno parte del
        nome (mantenuti senza spaziatura, sez. 1.3.1.1.1 / 2.4.6);
      * i vari trattini tipografici (– — ―) fungono da separatore;
      * i placeholder di campo vuoto restituiscono stringa vuota (sez. 1.3.1.1.4).

    NB: non altera accenti/segni diacritici (sez. 2.4.2), fedeli all'originale.
    """
    if value is None:
        return ""
    s = _unify_apostrophes(str(value).strip().lower())
    if not s:
        return ""
    s = s.replace("_", " ")
    s = _NON_KEY_RE.sub(" ", s)
    s = _WS_RE.sub(" ", s).strip()
    # trattini/apostrofi isolati (residui di separatori) non sono nome
    if s in EMPTY_PLACEHOLDERS or s in {"'", "-"}:
        return ""
    return s


def is_empty_value(value: object) -> bool:
    """True se il campo va considerato vuoto (sez. 1.3.1.1.4, 1.3.8.2)."""
    return normalize_match_key(value) == ""


def strip_titles(value: object) -> str:
    """Rimuove i titoli iniziali ("signore", "don", ...) dal nome (sez. 1.4.6).

    Restituisce il valore originale privato dei soli token-titolo in testa.
    """
    if not value:
        return ""
    tokens = str(value).split()
    i = 0
    while i < len(tokens):
        bare = re.sub(r"[^\w]", "", tokens[i].lower())
        if bare in TITLES:
            i += 1
            continue
        break
    return " ".join(tokens[i:]).strip()


def expand_or_variants(value: object) -> List[str]:
    """Espande le varianti separate dalla lettera "O" = oppure (sez. 1.4.5).

    Esempio: "Giuseppe O Pino O il Magro" → ["Giuseppe", "Pino", "il Magro"].
    Ritorna una singola voce se non vi sono separatori.
    """
    if not value:
        return []
    parts = re.split(r"\s+[Oo]\s+", str(value).strip())
    return [p.strip() for p in parts if p.strip()]


def fold_variants(value: object) -> List[str]:
    """Chiavi di matching per tutte le varianti "O" di un valore (sez. 1.4.5)."""
    keys = [normalize_match_key(v) for v in expand_or_variants(value)]
    seen, out = set(), []
    for k in keys:
        if k and k not in seen:
            seen.add(k)
            out.append(k)
    return out


def _cap_token(tok: str) -> str:
    if not tok:
        return tok
    # gestione Mc / Mac (sez. 1.3.7): McGregor, MacDonald
    low = tok.lower()
    if low.startswith("mc") and len(tok) > 2:
        return "Mc" + _cap_token(tok[2:])
    if low.startswith("mac") and len(tok) > 3:
        return "Mac" + _cap_token(tok[3:])
    # capitalizza dopo apostrofo/trattino: D'Amico, Sant'Angelo, Jean-Marie
    out = []
    cap_next = True
    for ch in tok:
        if cap_next and ch.isalpha():
            out.append(ch.upper())
            cap_next = False
        else:
            out.append(ch)
        if ch in "'-":
            cap_next = True
    return "".join(out)


def titlecase_name(value: object) -> str:
    """Applica maiuscole/minuscole come da programma Antenati (sez. 1.3.7).

    Iniziale maiuscola per ogni parola, incluse le preposizioni del cognome
    (Da, De, Di, Del...), e dopo apostrofi/trattini (D'Amico, McGregor).
    Non altera il contenuto testuale, solo il casing.
    """
    if not value:
        return ""
    s = _WS_RE.sub(" ", str(value).strip())
    if not s:
        return ""
    return " ".join(_cap_token(tok) for tok in s.split(" "))


def clean_toponym(value: object) -> str:
    """Rimuove qualificatori descrittivi da un toponimo (sez. 1.4.9.1).

    Es.: "frazione di Canneto" → "Canneto"; "comune di Milano" → "Milano".
    Mantiene le eccezioni in cui la qualifica è parte del nome
    (es. "Città di Castello"). Non moderniza il toponimo (sez. 1.3.1.2.1).
    """
    if not value:
        return ""
    s = str(value).strip()
    if normalize_match_key(s) in PLACE_EXCEPTIONS:
        return s
    changed = True
    while changed:
        changed = False
        low = s.lower()
        for q in PLACE_QUALIFIERS:
            if low.startswith(q + " "):
                s = s[len(q):].strip(" .,")
                changed = True
                break
    return s


_AGE_INT_RE = re.compile(r"\d+")


def normalize_age(value: object) -> Optional[int]:
    """Normalizza l'età secondo le regole del manuale (sez. 1.4.11).

      * arrotonda per difetto all'anno ("5 anni e 8 mesi" → 5);
      * età < 1 anno → 0 (solo mesi/settimane/giorni, o "nato morto");
      * intervalli ("65-67") → prima età;
      * "circa 14" → 14; "più di 21" → 21;
      * età assente/non numerica → None (NON calcolarla, sez. 1.4.11.6).
    """
    if value is None:
        return None
    s = str(value).strip().lower()
    if not s:
        return None
    if "nato morto" in s or "nata morta" in s or "nato-morto" in s:
        return 0
    has_year = bool(re.search(r"ann", s))
    has_sub_year = bool(re.search(r"mes|settiman|giorn", s))
    if re.search(r"(meno di un anno|inferiore a un anno)", s):
        return 0
    m = _AGE_INT_RE.search(s)
    if not m:
        return None
    n = int(m.group())
    # solo unità inferiori all'anno (senza "anni") → 0
    if has_sub_year and not has_year:
        return 0
    return n

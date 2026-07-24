"""State machine per il workflow dei candidati del Percorso Riconoscimenti.

24 stati con transizioni validate e audit.
Nessuna transizione automatica: ogni cambio di stato richiede azione umana.
"""
from datetime import datetime
from typing import Optional

from database import get_conn

# ─── Stati ───────────────────────────────────────────────────────────────────

STATES = [
    "BOZZA",
    "IDENTIFICAZIONE_IN_CORSO",
    "IDENTITA_VERIFICATA",
    "FONTI_IN_VERIFICA",
    "DOCUMENTAZIONE_INSUFFICIENTE",
    "VALUTAZIONE_STORICA",
    "VALUTAZIONE_AMMINISTRATIVA",
    "PROCEDURA_POTENZIALMENTE_PRATICABILE",
    "PROCEDURA_NON_PRATICABILE",
    "RICONOSCIMENTO_GIA_CONCESSO",
    "RICERCA_DISCENDENTI_AUTORIZZATA",
    "DISCENDENTI_IN_RICERCA",
    "POSSIBILE_DISCENDENTE_INDIVIDUATO",
    "CONTATTO_DA_APPROVARE",
    "CONTATTO_INOLTRATO",
    "FAMIGLIA_ADERENTE",
    "FAMIGLIA_NON_INTERESSATA",
    "DISCENDENZA_VERIFICATA",
    "FASCICOLO_IN_PREPARAZIONE",
    "FASCICOLO_DA_APPROVARE",
    "PRATICA_TRASMESSA",
    "INTEGRAZIONE_RICHIESTA",
    "RICONOSCIMENTO_CONCESSO",
    "PRATICA_RESPINTA",
    "PRATICA_ARCHIVIATA",
]

# ─── Transizioni valide ──────────────────────────────────────────────────────
# Mappa: stato_corrente -> [stati_destinazione_ammessi]

VALID_TRANSITIONS = {
    "BOZZA": [
        "IDENTIFICAZIONE_IN_CORSO",
        "DOCUMENTAZIONE_INSUFFICIENTE",
        "PRATICA_ARCHIVIATA",
    ],
    "IDENTIFICAZIONE_IN_CORSO": [
        "IDENTITA_VERIFICATA",
        "DOCUMENTAZIONE_INSUFFICIENTE",
        "BOZZA",
    ],
    "IDENTITA_VERIFICATA": [
        "FONTI_IN_VERIFICA",
        "VALUTAZIONE_STORICA",
        "DOCUMENTAZIONE_INSUFFICIENTE",
    ],
    "FONTI_IN_VERIFICA": [
        "VALUTAZIONE_STORICA",
        "DOCUMENTAZIONE_INSUFFICIENTE",
        "IDENTITA_VERIFICATA",
    ],
    "DOCUMENTAZIONE_INSUFFICIENTE": [
        "IDENTIFICAZIONE_IN_CORSO",
        "FONTI_IN_VERIFICA",
        "PRATICA_ARCHIVIATA",
    ],
    "VALUTAZIONE_STORICA": [
        "VALUTAZIONE_AMMINISTRATIVA",
        "DOCUMENTAZIONE_INSUFFICIENTE",
        "RICONOSCIMENTO_GIA_CONCESSO",
        "FONTI_IN_VERIFICA",
    ],
    "VALUTAZIONE_AMMINISTRATIVA": [
        "PROCEDURA_POTENZIALMENTE_PRATICABILE",
        "PROCEDURA_NON_PRATICABILE",
        "RICONOSCIMENTO_GIA_CONCESSO",
        "VALUTAZIONE_STORICA",
    ],
    "PROCEDURA_POTENZIALMENTE_PRATICABILE": [
        "RICERCA_DISCENDENTI_AUTORIZZATA",
        "PROCEDURA_NON_PRATICABILE",
        "VALUTAZIONE_AMMINISTRATIVA",
    ],
    "PROCEDURA_NON_PRATICABILE": [
        "PRATICA_ARCHIVIATA",
        "VALUTAZIONE_AMMINISTRATIVA",
    ],
    "RICONOSCIMENTO_GIA_CONCESSO": [
        "PRATICA_ARCHIVIATA",
    ],
    "RICERCA_DISCENDENTI_AUTORIZZATA": [
        "DISCENDENTI_IN_RICERCA",
        "PROCEDURA_POTENZIALMENTE_PRATICABILE",
    ],
    "DISCENDENTI_IN_RICERCA": [
        "POSSIBILE_DISCENDENTE_INDIVIDUATO",
        "RICERCA_DISCENDENTI_AUTORIZZATA",
        "PROCEDURA_NON_PRATICABILE",
    ],
    "POSSIBILE_DISCENDENTE_INDIVIDUATO": [
        "CONTATTO_DA_APPROVARE",
        "DISCENDENTI_IN_RICERCA",
    ],
    "CONTATTO_DA_APPROVARE": [
        "CONTATTO_INOLTRATO",
        "POSSIBILE_DISCENDENTE_INDIVIDUATO",
    ],
    "CONTATTO_INOLTRATO": [
        "FAMIGLIA_ADERENTE",
        "FAMIGLIA_NON_INTERESSATA",
        "CONTATTO_DA_APPROVARE",
    ],
    "FAMIGLIA_ADERENTE": [
        "DISCENDENZA_VERIFICATA",
        "FAMIGLIA_NON_INTERESSATA",
    ],
    "FAMIGLIA_NON_INTERESSATA": [
        "PRATICA_ARCHIVIATA",
        "DISCENDENTI_IN_RICERCA",
    ],
    "DISCENDENZA_VERIFICATA": [
        "FASCICOLO_IN_PREPARAZIONE",
        "FAMIGLIA_ADERENTE",
    ],
    "FASCICOLO_IN_PREPARAZIONE": [
        "FASCICOLO_DA_APPROVARE",
        "DISCENDENZA_VERIFICATA",
    ],
    "FASCICOLO_DA_APPROVARE": [
        "PRATICA_TRASMESSA",
        "FASCICOLO_IN_PREPARAZIONE",
    ],
    "PRATICA_TRASMESSA": [
        "INTEGRAZIONE_RICHIESTA",
        "RICONOSCIMENTO_CONCESSO",
        "PRATICA_RESPINTA",
    ],
    "INTEGRAZIONE_RICHIESTA": [
        "FASCICOLO_IN_PREPARAZIONE",
        "PRATICA_TRASMESSA",
    ],
    "RICONOSCIMENTO_CONCESSO": [
        "PRATICA_ARCHIVIATA",
    ],
    "PRATICA_RESPINTA": [
        "PRATICA_ARCHIVIATA",
        "FASCICOLO_IN_PREPARAZIONE",
    ],
    "PRATICA_ARCHIVIATA": [],
}

# ─── Stati terminali ─────────────────────────────────────────────────────────

TERMINAL_STATES = {"PRATICA_ARCHIVIATA"}

# ─── Stati che richiedono approvazione ───────────────────────────────────────

APPROVAL_REQUIRED = {
    "CONTATTO_DA_APPROVARE": "approvazione_revisore",
    "FASCICOLO_DA_APPROVARE": "approvazione_operatore",
}

# ─── Permessi per transizione ────────────────────────────────────────────────

TRANSITION_PERMISSIONS = {
    "RICERCA_DISCENDENTI_AUTORIZZATA": "rc:contact:approve",
    "CONTATTO_DA_APPROVARE": "rc:contact:approve",
    "FASCICOLO_DA_APPROVARE": "rc:case:write",
}


def is_valid_transition(from_state: str, to_state: str) -> bool:
    if from_state not in VALID_TRANSITIONS:
        return False
    return to_state in VALID_TRANSITIONS[from_state]


def get_valid_transitions(state: str) -> list:
    return VALID_TRANSITIONS.get(state, [])


def is_terminal(state: str) -> bool:
    return state in TERMINAL_STATES


def transition(candidate_id: int, new_state: str, user: dict,
               motivazione: str = None, allegati: str = None) -> dict:
    """Esegue una transizione di stato con audit.
    
    Ritorna il record aggiornato del candidato.
    Solleva ValueError se la transizione non è valida.
    """
    if new_state not in STATES:
        raise ValueError(f"Stato non valido: {new_state}")
    
    conn = get_conn()
    now = datetime.now().isoformat()
    
    candidate = conn.execute(
        "SELECT * FROM rc_candidates WHERE id = ?", (candidate_id,)
    ).fetchone()
    if not candidate:
        conn.close()
        raise ValueError(f"Candidato non trovato: id={candidate_id}")
    
    old_state = candidate["stato"]
    if old_state == new_state:
        conn.close()
        raise ValueError("Lo stato è già quello richiesto")
    
    if not is_valid_transition(old_state, new_state):
        conn.close()
        raise ValueError(
            f"Transizione non valida: {old_state} -> {new_state}. "
            f"Transizioni ammesse da {old_state}: {get_valid_transitions(old_state)}"
        )
    
    # Verifica permessi per la transizione
    required_perm = TRANSITION_PERMISSIONS.get(new_state)
    if required_perm:
        from auth import has_permission
        if not has_permission(user.get("role", ""), required_perm):
            conn.close()
            raise PermissionError(
                f"Permesso insufficiente per transizione a {new_state}. "
                f"Richiesto: {required_perm}"
            )
    
    # Registra transizione
    approval = 1 if new_state in APPROVAL_REQUIRED else 0
    conn.execute(
        """INSERT INTO rc_state_transitions
           (candidate_id, stato_precedente, stato_successivo, autore,
            data_ora, motivazione, allegati, approvazione_richiesta)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        (candidate_id, old_state, new_state, user.get("username", ""),
         now, motivazione, allegati, approval),
    )
    
    # Aggiorna candidato
    conn.execute(
        "UPDATE rc_candidates SET stato = ?, updated_at = ? WHERE id = ?",
        (new_state, now, candidate_id),
    )
    
    # Audit log
    conn.execute(
        """INSERT INTO rc_audit_log
           (user_id, username, azione, entita, entita_id,
            valore_precedente, valore_successivo, motivazione, created_at)
           VALUES (?, ?, 'state_transition', 'candidate', ?, ?, ?, ?, ?)""",
        (user.get("id"), user.get("username", ""), candidate_id,
         old_state, new_state, motivazione, now),
    )
    
    conn.commit()
    updated = conn.execute(
        "SELECT * FROM rc_candidates WHERE id = ?", (candidate_id,)
    ).fetchone()
    conn.close()
    return dict(updated)


def get_transition_history(candidate_id: int) -> list:
    conn = get_conn()
    rows = conn.execute(
        """SELECT * FROM rc_state_transitions
           WHERE candidate_id = ? ORDER BY data_ora DESC""",
        (candidate_id,),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]

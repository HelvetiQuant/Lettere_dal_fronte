"""Analisi AI per il Percorso Riconoscimenti.

Per ogni potenziale candidato, l'AI deve dettagliare:
1. Processo logico che ha portato all'identificazione
2. Fonti consultate (con livello di attendibilita')
3. Onorificenze ipotizzabili (con requisiti e base normativa)
4. % stimata di concessione per ogni onorificenza
5. Precedenti storici (attribuzioni simili nel DB)
6. Fattori favorevoli e sfavorevoli
7. Raccomandazioni
"""
import json
from datetime import datetime
from typing import Optional

from database import get_conn


def _get_candidate_full(cid: int) -> dict:
    """Recupera tutti i dati di un candidato per l'analisi."""
    conn = get_conn()
    cand = conn.execute("SELECT * FROM rc_candidates WHERE id = ?", (cid,)).fetchone()
    if not cand:
        conn.close()
        raise ValueError(f"Candidato non trovato: id={cid}")
    data = dict(cand)
    data["sources"] = [dict(r) for r in conn.execute(
        "SELECT * FROM rc_sources WHERE candidate_id = ?", (cid,)
    ).fetchall()]
    data["events"] = [dict(r) for r in conn.execute(
        "SELECT * FROM rc_historical_events WHERE candidate_id = ?", (cid,)
    ).fetchall()]
    data["assessments"] = [dict(r) for r in conn.execute(
        "SELECT a.*, r.denominazione as recognition_name, r.categoria, r.autorita_concedente, "
        "r.ente_istruttore, r.base_normativa, r.requisiti, r.procedura_attiva "
        "FROM rc_recognition_assessments a "
        "LEFT JOIN rc_recognition_types r ON a.recognition_type_id = r.id "
        "WHERE a.candidate_id = ?", (cid,)
    ).fetchall()]
    data["recognition_types"] = [dict(r) for r in conn.execute(
        "SELECT * FROM rc_recognition_types ORDER BY denominazione"
    ).fetchall()]
    data["practice_documents"] = [dict(r) for r in conn.execute(
        "SELECT * FROM rc_practice_documents WHERE candidate_id = ? AND archiviato = 0 ORDER BY data_caricamento DESC",
        (cid,)
    ).fetchall()]
    data["ext_practices"] = [dict(r) for r in conn.execute(
        "SELECT p.*, r.denominazione as recognition_name "
        "FROM rc_practices p "
        "LEFT JOIN rc_recognition_types r ON p.recognition_type_id = r.id "
        "WHERE p.candidate_id = ? ORDER BY p.created_at DESC",
        (cid,)
    ).fetchall()]
    data["descendant_contacts"] = [dict(r) for r in conn.execute(
        "SELECT id, nome, cognome, rapporto_parentela_presunto, stato_verifica, "
        "livello_attendibilita, consenso_acquisito, visibilita_limitata "
        "FROM rc_descendant_contacts WHERE candidate_id = ?",
        (cid,)
    ).fetchall()]
    conn.close()
    return data


def _cross_check_sources(conn, candidate: dict) -> dict:
    """Cross-check del candidato su tutte le fonti storiche del DB.
    Cerca per cognome+nome in tutte le tabelle disponibili."""
    cognome = (candidate.get("cognome") or "").strip().upper()
    nome = (candidate.get("nome") or "").strip().upper()
    if not cognome:
        return {}
    results = {}

    # 1. caduti_albooro (342K) - caduti 1GM
    try:
        q = "SELECT * FROM caduti_albooro WHERE UPPER(nominativo) LIKE ?"
        rows = conn.execute(q, (f"%{cognome}%",)).fetchall()
        if nome:
            rows = [r for r in rows if nome in (r["nominativo"] or "").upper()]
        if rows:
            results["caduti_albooro"] = {
                "count": len(rows),
                "matches": [{"id": r["id"], "nominativo": r["nominativo"], "grado": r["grado"],
                             "reparto": r["reparto"], "anno_morte": r["anno_morte"],
                             "luogo_morte": r["luogo_morte"], "causa_morte": r["causa_morte"],
                             "detail_url": r["detail_url"]} for r in rows[:10]],
            }
    except:
        pass

    # 2. internati (20K) - IMI 2GM
    try:
        q = "SELECT * FROM internati WHERE UPPER(cognome) LIKE ?"
        params = [f"%{cognome}%"]
        if nome:
            q += " AND UPPER(nome) LIKE ?"
            params.append(f"%{nome}%")
        rows = conn.execute(q, params).fetchall()
        if rows:
            results["internati_imi"] = {
                "count": len(rows),
                "matches": [{"id": r["id"], "cognome": r["cognome"], "nome": r["nome"],
                             "grado": r.get("grado"), "reparto": r.get("reparto"),
                             "luogo_prigionia": r.get("luogo_prigionia") or r.get("luogo_internamento"),
                             "data_prigionia": r.get("data_prigionia"),
                             "lettera": r.get("lettera")} for r in rows[:10]],
            }
    except:
        pass

    # 3. decorati_nastroazzurro (280K) - decorazioni 1GM
    try:
        q = "SELECT * FROM decorati_nastroazzurro WHERE UPPER(cognome) LIKE ?"
        params = [f"%{cognome}%"]
        if nome:
            q += " AND UPPER(nome) LIKE ?"
            params.append(f"%{nome}%")
        rows = conn.execute(q, params).fetchall()
        if rows:
            results["decorati_nastroazzurro"] = {
                "count": len(rows),
                "matches": [{"id": r["id"], "cognome": r["cognome"], "nome": r["nome"],
                             "arma": r["arma"], "tipo_decorazione": r["tipo_decorazione"],
                             "anno_decorazione": r["anno_decorazione"]} for r in rows[:10]],
            }
    except:
        pass

    # 4. decorati (1.3K) - decorati vari
    try:
        q = "SELECT * FROM decorati WHERE UPPER(cognome) LIKE ?"
        params = [f"%{cognome}%"]
        if nome:
            q += " AND UPPER(nome) LIKE ?"
            params.append(f"%{nome}%")
        rows = conn.execute(q, params).fetchall()
        if rows:
            results["decorati_albo"] = {
                "count": len(rows),
                "matches": [{"id": r["id"], "cognome": r["cognome"], "nome": r["nome"],
                             "decorazione": r["decorazione"], "guerra": r["guerra"],
                             "grado": r["grado"], "luogo_morte": r["luogo_morte"],
                             "url_scheda": r["url_scheda"]} for r in rows[:10]],
            }
    except:
        pass

    # 5. caduti_ministero (162K) - caduti Ministero Difesa
    try:
        q = "SELECT * FROM caduti_ministero WHERE UPPER(cognome) LIKE ?"
        params = [f"%{cognome}%"]
        if nome:
            q += " AND UPPER(nome) LIKE ?"
            params.append(f"%{nome}%")
        rows = conn.execute(q, params).fetchall()
        if rows:
            results["caduti_ministero"] = {
                "count": len(rows),
                "matches": [{"id": r["id"], "cognome": r["cognome"], "nome": r["nome"],
                             "data_nascita": r["data_nascita"], "data_decesso": r["data_decesso"],
                             "comune_nascita": r["comune_nascita"],
                             "nazione_decesso": r["nazione_decesso"],
                             "luogo_sepoltura": r["luogo_sepoltura"],
                             "scheda_url": r["scheda_url"]} for r in rows[:10]],
            }
    except:
        pass

    # 6. caduti_cwgc (506K) - caduti Commonwealth
    try:
        q = "SELECT * FROM caduti_cwgc WHERE UPPER(cognome) LIKE ? AND nationality = 'Italian'"
        params = [f"%{cognome}%"]
        rows = conn.execute(q, params).fetchall()
        if nome:
            rows = [r for r in rows if nome in (r["cognome"] or "").upper() or nome in (r["nome"] or "").upper()]
        if rows:
            results["caduti_cwgc"] = {
                "count": len(rows),
                "matches": [{"id": r["id"], "cognome": r["cognome"], "nome": r["nome"],
                             "rank": r["rank"], "regiment": r["regiment"],
                             "data_morte": r["data_morte"], "cimitero": r["cimitero"],
                             "paese_cimitero": r["paese_cimitero"], "guerra": r["guerra"]} for r in rows[:10]],
            }
    except:
        pass

    # 7. fonti_indice (35K) - fonti d'archivio indicizzate
    try:
        q = "SELECT * FROM fonti_indice WHERE persone_possibili LIKE ? OR soggetti_collegati LIKE ?"
        rows = conn.execute(q, (f"%{cognome}%", f"%{cognome}%")).fetchall()
        if nome:
            # Filter: keep only rows where nome also appears in the same text field
            rows = [r for r in rows if nome in (r["persone_possibili"] or "").upper() or nome in (r["soggetti_collegati"] or "").upper()]
        if rows:
            results["fonti_indice"] = {
                "count": len(rows),
                "matches": [{"id": r["id"], "archivio": r["archivio"], "fondo": r["fondo"],
                             "titolo": r["titolo"], "tipo_fonte": r["tipo_fonte"],
                             "url_catalogo": r["url_catalogo"],
                             "data_inizio": r["data_inizio"], "data_fine": r["data_fine"]} for r in rows[:10]],
            }
    except:
        pass

    # 8. fondi_archivistici (4.8K) - fondi esplorati
    try:
        q = "SELECT * FROM fondi_archivistici WHERE raw_text LIKE ? OR titolo LIKE ?"
        rows = conn.execute(q, (f"%{cognome}%", f"%{cognome}%")).fetchall()
        if nome:
            rows = [r for r in rows if nome in (r["raw_text"] or "").upper() or nome in (r["titolo"] or "").upper()]
        if rows:
            results["fondi_archivistici"] = {
                "count": len(rows),
                "matches": [{"id": r["id"], "codice_fondo": r["codice_fondo"], "titolo": (r["titolo"] or "")[:200],
                             "file_pdf": r["file_pdf"], "url": r["url"],
                             "periodo": r["periodo"], "luoghi": r["luoghi"]} for r in rows[:10]],
            }
    except:
        pass

    # 9. documenti_nara_t315 - documenti americani sui campi di prigionia
    try:
        q = "SELECT * FROM documenti_nara_t315 WHERE testo_ocr LIKE ? OR unita_citate LIKE ?"
        rows = conn.execute(q, (f"%{cognome}%", f"%{cognome}%")).fetchall()
        if nome:
            rows = [r for r in rows if nome in (r["testo_ocr"] or "").upper() or nome in (r["unita_citate"] or "").upper()]
        if rows:
            results["nara_t315"] = {
                "count": len(rows),
                "matches": [{"id": r["id"], "roll": r["roll"], "frame": r["frame"],
                             "tipo_documento": r["tipo_documento"],
                             "data_documento": r["data_documento"],
                             "unita_citate": (r["unita_citate"] or "")[:200],
                             "luoghi_citati": (r["luoghi_citati"] or "")[:200]} for r in rows[:10]],
            }
    except:
        pass

    return results


def _count_precedenti(conn, denominazione: str, conflitto: Optional[str] = None) -> dict:
    """Conta precedenti attribuzioni dello stesso tipo nel DB."""
    stats = {}
    # Decorati Albo d'Oro
    try:
        q = "SELECT COUNT(*) as c FROM decorati WHERE decorazione LIKE ?"
        params = [f"%{denominazione}%"]
        if conflitto:
            q += " AND guerra LIKE ?"
            params.append(f"%{conflitto}%")
        r = conn.execute(q, params).fetchone()
        stats["albo_oro"] = r["c"]
    except:
        stats["albo_oro"] = 0

    # Decorati Nastro Azzurro
    try:
        q = "SELECT COUNT(*) as c FROM decorati_nastroazzurro WHERE tipo_decorazione LIKE ?"
        params = [f"%{denominazione}%"]
        r = conn.execute(q, params).fetchone()
        stats["nastro_azzurro"] = r["c"]
    except:
        stats["nastro_azzurro"] = 0

    # Totale decorati
    try:
        r = conn.execute("SELECT COUNT(*) as c FROM decorati").fetchone()
        stats["total_decorati"] = r["c"]
    except:
        stats["total_decorati"] = 0

    # Totale Nastro Azzurro
    try:
        r = conn.execute("SELECT COUNT(*) as c FROM decorati_nastroazzurro").fetchone()
        stats["total_nastro"] = r["c"]
    except:
        stats["total_nastro"] = 0

    return stats


def _estimate_concession_percentage(recognition_name: str, candidate: dict,
                                    precedenti: dict, events: list) -> float:
    """Stima la % di concessione basata su criteri oggettivi e precedenti."""
    base = 0.0

    # Se gia' concesso, 100%
    if candidate.get("stato") == "RICONOSCIMENTO_GIA_CONCESSO":
        return 100.0

    # Se procedura non praticabile, 0%
    if candidate.get("stato") == "PROCEDURA_NON_PRATICABILE":
        return 0.0

    # Fattori di base per tipo riconoscimento
    r_lower = recognition_name.lower()

    if "medaglia d'oro" in r_lower or "medaglia d oro" in r_lower:
        base = 5.0  # Molto rara
    elif "medaglia d'argento" in r_lower:
        base = 15.0
    elif "medaglia di bronzo" in r_lower:
        base = 30.0
    elif "croce di guerra" in r_lower:
        base = 40.0
    elif "merito di guerra" in r_lower:
        base = 50.0
    elif "medaglia d'onore" in r_lower or "deportati" in r_lower:
        base = 60.0  # Procedura piu' standardizzata
    elif "valor civile" in r_lower:
        base = 25.0
    elif "omri" in r_lower or "merito" in r_lower:
        base = 35.0
    else:
        base = 20.0

    # Fattori che aumentano la %
    boost = 0.0

    # Fonti verificate
    verified_sources = [s for s in candidate.get("_sources_list", []) if s.get("stato_verifica") == "verificata"]
    if len(verified_sources) >= 2:
        boost += 15.0
    elif len(verified_sources) >= 1:
        boost += 8.0

    # Eventi documentati con attendibilita' alta
    high_conf_events = [e for e in events if e.get("grado_attendibilita") == "alta"]
    if len(high_conf_events) >= 1:
        boost += 10.0

    # Grado militare noto
    if candidate.get("grado"):
        boost += 5.0

    # Deceduto in servizio (per valor militare)
    if candidate.get("stato") and "deceduto" in str(candidate.get("note_interne", "")).lower():
        boost += 10.0

    # Conflitto noto
    if candidate.get("conflitto"):
        boost += 3.0

    # Fattori che riducono la %
    penalty = 0.0

    # Fonti non verificate
    unverified = [s for s in candidate.get("_sources_list", []) if s.get("stato_verifica") != "verificata"]
    if len(unverified) > 3:
        penalty += 10.0

    # Eventi a bassa attendibilita'
    low_conf = [e for e in events if e.get("grado_attendibilita") == "bassa"]
    if len(low_conf) > len(high_conf_events):
        penalty += 15.0

    # Livello certezza del candidato
    if candidate.get("livello_certezza") == "da_verificare":
        penalty += 10.0
    elif candidate.get("livello_certezza") == "basso":
        penalty += 20.0

    # Precedenti storici: se ci sono molti precedenti, la procedura e' piu' standardizzata
    total_precedenti = precedenti.get("albo_oro", 0) + precedenti.get("nastro_azzurro", 0)
    if total_precedenti > 100:
        boost += 5.0  # Procedura ben stabilita
    elif total_precedenti < 5:
        penalty += 5.0  # Procedura rara o innovativa

    # Documenti di pratica verificati
    practice_docs = candidate.get("_practice_docs", [])
    verified_docs = [d for d in practice_docs if d.get("stato_verifica") == "verificata"]
    if len(verified_docs) >= 3:
        boost += 10.0
    elif len(verified_docs) >= 1:
        boost += 5.0
    # Foglio matricolare presente
    if any(d.get("categoria_documentale") == "FOGLIO_MATRICOLARE" for d in practice_docs):
        boost += 5.0
    # Documenti caricati ma non verificati
    unverified_docs = [d for d in practice_docs if d.get("stato_verifica") != "verificata"]
    if len(unverified_docs) > 2:
        penalty += 5.0

    # Cross-check fonti storiche
    cross_check = candidate.get("_cross_check", {})
    if cross_check.get("caduti_albooro"):
        boost += 8.0  # Conferma in Albo d'Oro
    if cross_check.get("internati_imi"):
        boost += 10.0  # Conferma come IMI
    if cross_check.get("decorati_nastroazzurro"):
        boost += 8.0  # Gia' decorato
    if cross_check.get("decorati_albo"):
        boost += 8.0
    if cross_check.get("caduti_ministero"):
        boost += 5.0
    if cross_check.get("caduti_cwgc"):
        boost += 3.0
    if cross_check.get("fonti_indice") or cross_check.get("fondi_archivistici"):
        boost += 3.0
    if cross_check.get("nara_t315"):
        boost += 5.0
    if not cross_check:
        penalty += 5.0  # Nessun riscontro in fonti storiche

    pct = base + boost - penalty
    return max(0.0, min(95.0, pct))


def _explain_document(ocr_text: str, categoria: str, doc: dict) -> dict:
    """Analizza il testo OCR di un documento e ne determina tipologia, riassunto, valore probatorio e dati chiave."""
    text_upper = ocr_text.upper()
    text_lower = ocr_text.lower()
    result = {"tipologia": "", "riassunto": "", "valore": "", "dati_chiave": {}}

    # Detect document type
    if "FOGLIO MATRICOL" in text_upper or "MATRICOLA" in text_upper or "RUOLO MATRICOLARE" in text_upper:
        result["tipologia"] = "Foglio Matricolare / Ruolo Matricolare"
        result["riassunto"] = "Documento militare ufficiale che registra l'arruolamento, il grado, il reparto di assegnazione, i trasferimenti e lo stato di servizio del soggetto."
        result["valore"] = "PROVA PRIMARIA - Certifica l'identita' militare del soggetto, il grado rivestito, il reparto e il periodo di servizio. Documento fondamentale per dimostrare la qualita' di militare e l'appartenenza a un'unita' combattente."
        # Extract key data
        import re
        for line in ocr_text.split('\n'):
            line_u = line.upper()
            if 'GRADO' in line_u or any(g in line_u for g in ['SOLDATO', 'SOLDATO SEMPLICE', 'CAPORALE', 'SERGENTE', 'MAGGIORE', 'TENENTE', 'CAPITANO', 'COLONNELLO', 'SOTTOTENENTE', 'MARESCIALLO']):
                result["dati_chiave"]["Grado indicato"] = line.strip()[:100]
            if 'REGGIMENT' in line_u or 'BATTAGLIONE' in line_u or 'BRIGATA' in line_u or 'DIVISIONE' in line_u or 'COMPAGNIA' in line_u:
                result["dati_chiave"]["Reparto indicato"] = line.strip()[:100]
            if 'MATRICOLA' in line_u or 'N.' in line_u or 'NUMERO' in line_u:
                result["dati_chiave"]["Numero matricola"] = line.strip()[:100]
            if 'NATO' in line_u or 'NASCITA' in line_u:
                result["dati_chiave"]["Dati nascita"] = line.strip()[:100]
            if 'ARRUOL' in line_u or 'ARRUOLAMENTO' in line_u or 'INCORPORATO' in line_u:
                result["dati_chiave"]["Data arruolamento"] = line.strip()[:100]
            if 'CONGED' in line_u or 'RIPRESO' in line_u or 'RIMPATRI' in line_u:
                result["dati_chiave"]["Congedo/Rimpatrio"] = line.strip()[:100]

    elif "CERTIFICATO" in text_upper and ("MORTE" in text_upper or "DECED" in text_upper or "DECESSO" in text_upper):
        result["tipologia"] = "Certificato di Morte"
        result["riassunto"] = "Certificato ufficiale che attesta il decesso del soggetto, con data, luogo e causa di morte."
        result["valore"] = "PROVA PRIMARIA - Certifica il decesso, elemento essenziale per riconoscimenti postumi (es. Vittima del Dovere, Medaglia d'Onore)."
        for line in ocr_text.split('\n'):
            line_u = line.upper()
            if 'DATA' in line_u and ('MORT' in line_u or 'DECESS' in line_u or 'DECED' in line_u):
                result["dati_chiave"]["Data decesso"] = line.strip()[:100]
            if 'CAUSA' in line_u or 'CAUSE' in line_u:
                result["dati_chiave"]["Causa morte"] = line.strip()[:100]
            if 'LUOGO' in line_u and ('MORT' in line_u or 'DECESS' in line_u):
                result["dati_chiave"]["Luogo decesso"] = line.strip()[:100]

    elif "CERTIFICATO" in text_upper and ("NASCITA" in text_upper):
        result["tipologia"] = "Certificato di Nascita"
        result["riassunto"] = "Certificato anagrafico che attesta la data e il luogo di nascita del soggetto."
        result["valore"] = "PROVA SECONDARIA - Conferma l'identita' anagrafica del soggetto, utile per distinguere omonimi e stabilire l'eta' al momento degli eventi."
        for line in ocr_text.split('\n'):
            if 'NATO' in line.upper() or 'DATA' in line.upper():
                result["dati_chiave"]["Dati nascita"] = line.strip()[:100]

    elif "STATO DI SERVIZIO" in text_upper or "SCHEDA DI SERVIZIO" in text_upper:
        result["tipologia"] = "Stato di Servizio"
        result["riassunto"] = "Documento che riassume la carriera militare del soggetto: arruolamento, gradi, reparti, campagne, decorazioni e congedo."
        result["valore"] = "PROVA PRIMARIA - Documento sintetico che certifica l'intero percorso militare. Essenziale per dimostrare la partecipazione a operazioni belliche e l'assegnazione a reparti combattenti."
        for line in ocr_text.split('\n'):
            line_u = line.upper()
            if any(g in line_u for g in ['SOLDATO', 'CAPORALE', 'SERGENTE', 'TENENTE', 'CAPITANO', 'MAGGIORE', 'COLONNELLO']):
                result["dati_chiave"]["Grado"] = line.strip()[:100]
            if 'DECORAZ' in line_u or 'MEDAGLIA' in line_u or 'CROCE' in line_u:
                result["dati_chiave"]["Decorazioni"] = line.strip()[:100]
            if 'CAMPAGNA' in line_u or 'GUERRA' in line_u or 'OPERAZ' in line_u:
                result["dati_chiave"]["Campagne/Operazioni"] = line.strip()[:100]

    elif "PRIGION" in text_upper or "INTERNAT" in text_upper or "CAMPO" in text_upper or "LAGER" in text_upper or "STALAG" in text_upper or "OFLAG" in text_upper:
        result["tipologia"] = "Documento di Prigionia/Internamento"
        result["riassunto"] = "Documento relativo alla cattura, internamento o prigionia del soggetto in campo di prigionia."
        result["valore"] = "PROVA PRIMARIA - Certifica lo status di IMI (Internato Militare Italiano) o prigioniero di guerra, elemento essenziale per riconoscimenti specifici (es. Medaglia d'Onore agli IMI)."
        for line in ocr_text.split('\n'):
            line_u = line.upper()
            if 'STALAG' in line_u or 'OFLAG' in line_u or 'CAMPO' in line_u or 'LAGER' in line_u:
                result["dati_chiave"]["Campo di prigionia"] = line.strip()[:100]
            if 'CATTURA' in line_u or 'PRESO' in line_u or 'PRIGION' in line_u:
                result["dati_chiave"]["Data/luogo cattura"] = line.strip()[:100]
            if 'RIMPATRI' in line_u or 'RIPATRIA' in line_u or 'LIBER' in line_u:
                result["dati_chiave"]["Rimpatrio/liberazione"] = line.strip()[:100]

    elif "DECORAZ" in text_upper or "MEDAGLIA" in text_upper or "CROCE" in text_upper or "MOTIVAZIONE" in text_upper:
        result["tipologia"] = "Documento di Decorazione/Onorificenza"
        result["riassunto"] = "Documento che attesta il conferimento di una decorazione o onorificenza al soggetto, con eventuale motivazione."
        result["valore"] = "PROVA PRIMARIA - Certifica direttamente il conferimento di un'onorificenza, prova decisiva per il riconoscimento."
        for line in ocr_text.split('\n'):
            line_u = line.upper()
            if 'MEDAGLIA' in line_u or 'CROCE' in line_u or 'DECORAZ' in line_u:
                result["dati_chiave"]["Decorazione"] = line.strip()[:100]
            if 'MOTIVAZ' in line_u or 'PER AVER' in line_u or 'CON LA SEGUENTE' in line_u:
                result["dati_chiave"]["Motivazione"] = line.strip()[:150]

    elif "CONGEDO" in text_upper or "CONGEDAMENTO" in text_upper:
        result["tipologia"] = "Certificato di Congedo"
        result["riassunto"] = "Documento che attesta il congedo del soggetto dalle forze armate, con data e motivazione."
        result["valore"] = "PROVA SECONDARIA - Certifica la fine del servizio militare e le condizioni del congedo."

    elif "LETTERA" in text_upper or "CORRISPONDENZA" in text_upper or "COMUNICAZIONE" in text_upper:
        result["tipologia"] = "Lettera/Corrispondenza"
        result["riassunto"] = "Corrispondenza originale che puo' contenere informazioni su eventi, luoghi, date o circostanze relative al soggetto."
        result["valore"] = "PROVA INDIZIARIA - Fornisce contesto storico e elementi circostanziali. Non sostituisce documenti ufficiali ma puo' supportare la ricostruzione degli eventi."

    elif "FOTO" in text_upper or "FOTOGRAFIA" in text_upper or "IMMAGINE" in text_upper:
        result["tipologia"] = "Fotografia"
        result["riassunto"] = "Material fotografico che documenta il soggetto o contesti correlati."
        result["valore"] = "PROVA INDIZIARIA - Supporto visivo per identificazione e contestualizzazione."

    else:
        # Generic analysis based on category
        cat_map = {
            "FOGLIO_MATRICOLARE": "Foglio Matricolare",
            "STATO_SERVIZIO": "Stato di Servizio",
            "CERTIFICATO_MORTE": "Certificato di Morte",
            "CERTIFICATO_NASCITA": "Certificato di Nascita",
            "DOCUMENTO_PRIGIONIA": "Documento di Prigionia",
            "DECORAZIONE": "Documento di Decorazione",
            "CARTA_IDENTITA": "Carta d'Identita'",
            "PASSAPORTO": "Passaporto",
            "ATTO_NOTORIO": "Atto di Notorieta'",
            "CERTIFICATO_STATO_CIVILE": "Certificato Stato Civile",
            "ALTRO": "Documento non classificato",
        }
        result["tipologia"] = cat_map.get(categoria, f"Documento categoria {categoria}")
        # Summarize first 300 chars
        summary = ocr_text[:300].replace('\n', ' ').strip()
        if len(ocr_text) > 300:
            summary += " [...]"
        result["riassunto"] = f"Contenuto testuale: {summary}"
        result["valore"] = "Documento da valutare nel contesto della pratica. Il contenuto OCR e' disponibile per analisi approfondita."

    return result


def _build_process_logic(candidate: dict, events: list, sources: list,
                         recognition_types: list, practice_docs: list = None,
                         ext_practices: list = None, cross_check: dict = None) -> str:
    """Costruisce il processo logico dettagliato."""
    practice_docs = practice_docs or []
    ext_practices = ext_practices or []
    cross_check = cross_check or {}
    steps = []
    steps.append("PROCESSO LOGICO DI IDENTIFICAZIONE DEL CANDIDATO")
    steps.append("=" * 60)
    steps.append("")

    # Step 1: Identificazione
    steps.append("1. IDENTIFICAZIONE DEL NOMINATIVO")
    nome = candidate.get("nome", "")
    cognome = candidate.get("cognome", "")
    steps.append(f"   Soggetto: {cognome} {nome}")
    if candidate.get("grado"):
        steps.append(f"   Grado: {candidate['grado']}")
    if candidate.get("reparto"):
        steps.append(f"   Reparto: {candidate['reparto']}")
    if candidate.get("conflitto"):
        steps.append(f"   Conflitto: {candidate['conflitto']}")
    if candidate.get("data_nascita"):
        steps.append(f"   Data nascita: {candidate['data_nascita']}")
    if candidate.get("luogo_nascita"):
        steps.append(f"   Luogo nascita: {candidate['luogo_nascita']}")
    steps.append(f"   Livello certezza identificazione: {candidate.get('livello_certezza', 'da_verificare')}")
    steps.append("")

    # Step 2: Fonti
    steps.append("2. FONTI CONSULTATE E LORO VALUTAZIONE")
    if sources:
        for i, s in enumerate(sources, 1):
            steps.append(f"   Fonte {i}: {s.get('titolo', 'Senza titolo')}")
            steps.append(f"     - Tipologia: {s.get('tipologia', 'non specificata')}")
            steps.append(f"     - Ente: {s.get('ente_conservatore', 'non specificato')}")
            steps.append(f"     - Attendibilita': {s.get('livello_attendibilita', 'da_verificare')}")
            steps.append(f"     - Stato verifica: {s.get('stato_verifica', 'non_verificata')}")
            if s.get("url_istituzionale"):
                steps.append(f"     - URL: {s['url_istituzionale']}")
    else:
        steps.append("   Nessuna fonte registrata. IDENTIFICAZIONE PRELIMINARE.")
    steps.append("")

    # Step 3: Eventi storici
    steps.append("3. RICOSTRUZIONE DEGLI EVENTI STORICI")
    if events:
        for i, e in enumerate(events, 1):
            steps.append(f"   Evento {i}: {e.get('tipo_evento', 'Non specificato')}")
            steps.append(f"     - Periodo: {e.get('data_inizio', '')} - {e.get('data_fine', '')}")
            steps.append(f"     - Luogo: {e.get('luogo', 'non specificato')}")
            if e.get("descrizione_verificata"):
                steps.append(f"     - Descrizione: {e['descrizione_verificata']}")
            if e.get("condotta_individuale"):
                steps.append(f"     - Condotta: {e['condotta_individuale']}")
            steps.append(f"     - Attendibilita': {e.get('grado_attendibilita', 'da_verificare')}")
    else:
        steps.append("   Nessun evento storico ricostruito.")
    steps.append("")

    # Step 3b: Documenti di pratica
    steps.append("3b. DOCUMENTI DI PRATICA CARICATI")
    if practice_docs:
        for i, d in enumerate(practice_docs, 1):
            steps.append(f"   Documento {i}: {d.get('titolo', 'Senza titolo')}")
            steps.append(f"     - Categoria: {d.get('categoria_documentale', 'non specificata')}")
            steps.append(f"     - Verifica: {d.get('stato_verifica', 'non_verificata')}")
            steps.append(f"     - Versione: {d.get('versione', 1)}")
            steps.append(f"     - Caricato il: {d.get('data_caricamento', '')}")
            if d.get('ente_produttore'):
                steps.append(f"     - Ente produttore: {d['ente_produttore']}")
            if d.get('fonte'):
                steps.append(f"     - Fonte: {d['fonte']}")
            if d.get('data_documento'):
                steps.append(f"     - Data documento: {d['data_documento']}")
            if d.get('protocollo'):
                steps.append(f"     - Protocollo: {d['protocollo']}")
            if d.get('segnatura'):
                steps.append(f"     - Segnatura: {d['segnatura']}")
            # OCR content
            ocr_text = (d.get('ocr_text') or '').strip()
            ocr_status = d.get('ocr_status') or 'pending'
            if ocr_status == 'done' and ocr_text:
                steps.append(f"     - OCR: elaborato ({d.get('ocr_pages', 0)} pagine, {len(ocr_text)} caratteri)")
                # Explain what the document is
                cat = (d.get('categoria_documentale') or '').upper()
                doc_desc = _explain_document(ocr_text, cat, d)
                steps.append(f"     - TIPOLOGIA DOCUMENTO: {doc_desc['tipologia']}")
                steps.append(f"     - RIASSUNTO CONTENUTO: {doc_desc['riassunto']}")
                steps.append(f"     - VALORE PER IL RICONOSCIMENTO: {doc_desc['valore']}")
                # Include key extracted data
                if doc_desc['dati_chiave']:
                    steps.append(f"     - DATI CHIAVE ESTRATTI:")
                    for k, v in doc_desc['dati_chiave'].items():
                        steps.append(f"       * {k}: {v}")
                # Include relevant excerpt (first 500 chars)
                excerpt = ocr_text[:500].replace('\n', ' ').strip()
                if len(ocr_text) > 500:
                    excerpt += " [...]"
                steps.append(f"     - ESTRATTO OCR: {excerpt}")
            elif ocr_status == 'error':
                steps.append(f"     - OCR: errore durante l'elaborazione")
            else:
                steps.append(f"     - OCR: non ancora elaborato")
    else:
        steps.append("   Nessun documento di pratica caricato.")
    steps.append("")

    # Step 3c: Pratiche estese
    steps.append("3c. PRATICHE ESTESE")
    if ext_practices:
        for i, p in enumerate(ext_practices, 1):
            steps.append(f"   Pratica {i}: {p.get('recognition_name', 'Non specificata')}")
            steps.append(f"     - Stato: {p.get('stato', '—')}")
            steps.append(f"     - Protocollo: {p.get('protocollo', '—')}")
            if p.get('esito'):
                steps.append(f"     - Esito: {p['esito']}")
    else:
        steps.append("   Nessuna pratica estesa registrata.")
    steps.append("")

    # Step 3d: Cross-check su fonti storiche del DB
    steps.append("3d. CROSS-CHECK SU FONTI STORICHE DEL DATABASE")
    if cross_check:
        source_labels = {
            "caduti_albooro": "Albo d'Oro caduti (1GM)",
            "internati_imi": "IMI - Internati Militari Italiani (2GM)",
            "decorati_nastroazzurro": "Decorati Nastro Azzurro",
            "decorati_albo": "Decorati vari",
            "caduti_ministero": "Caduti Ministero Difesa",
            "caduti_cwgc": "Caduti CWGC (italiani)",
            "fonti_indice": "Fonti d'archivio indicizzate",
            "fondi_archivistici": "Fondi archivistici",
            "nara_t315": "Documenti NARA T315 (prigionia)",
        }
        for key, info in cross_check.items():
            label = source_labels.get(key, key)
            steps.append(f"   {label}: {info['count']} match trovati")
            for m in info["matches"][:3]:
                if key == "caduti_albooro":
                    steps.append(f"     - {m['nominativo']}, {m['grado'] or ''}, morto {m['anno_morte'] or ''} a {m['luogo_morte'] or ''}")
                elif key == "internati_imi":
                    steps.append(f"     - {m['cognome']} {m['nome']}, {m['grado'] or ''}, prigionia: {m['luogo_prigionia'] or 'non specificata'}")
                elif key == "decorati_nastroazzurro":
                    steps.append(f"     - {m['cognome']} {m['nome']}, {m['tipo_decorazione']}, {m['anno_decorazione'] or ''}")
                elif key == "decorati_albo":
                    steps.append(f"     - {m['cognome']} {m['nome']}, {m['decorazione']}, {m['guerra'] or ''}")
                elif key == "caduti_ministero":
                    steps.append(f"     - {m['cognome']} {m['nome']}, nato {m['data_nascita'] or ''} a {m['comune_nascita'] or ''}")
                elif key == "caduti_cwgc":
                    steps.append(f"     - {m['cognome']} {m['nome']}, {m['rank'] or ''}, {m['data_morte'] or ''}, {m['cimitero'] or ''}")
                elif key == "fonti_indice":
                    steps.append(f"     - {m['archivio']}, fondo {m['fondo']}, {m['titolo'][:60] if m['titolo'] else ''}")
                elif key == "fondi_archivistici":
                    steps.append(f"     - {m['codice_fondo']}, {(m['titolo'] or '')[:60]}")
                elif key == "nara_t315":
                    steps.append(f"     - {m['roll']} frame {m['frame']}, {(m['unita_citate'] or '')[:60]}")
    else:
        steps.append("   Nessun match trovato nelle fonti storiche del database.")
    steps.append("")

    # Step 4: Valutazione riconoscimenti
    steps.append("4. VALUTAZIONE RICONOSCIMENTI IPOTIZZABILI")
    steps.append("   Sulla base dei dati raccolti, si ipotizzano i seguenti riconoscimenti:")
    steps.append("")

    return "\n".join(steps)


def _build_honor_analysis(candidate: dict, events: list, sources: list,
                          recognition_types: list, conn,
                          practice_docs: list = None, ext_practices: list = None,
                          cross_check: dict = None) -> list:
    """Costruisce l'analisi dettagliata per ogni onorificenza ipotizzabile."""
    practice_docs = practice_docs or []
    ext_practices = ext_practices or []
    cross_check = cross_check or {}
    analyses = []
    conflitto = candidate.get("conflitto", "")

    for rt in recognition_types:
        denom = rt["denominazione"]
        # Salta riconoscimenti chiaramente non pertinenti
        if not _is_relevant_honor(denom, candidate, events):
            continue

        # Conta precedenti
        precedenti = _count_precedenti(conn, denom, conflitto)

        # Stima %
        candidate_copy = dict(candidate)
        candidate_copy["_sources_list"] = sources
        candidate_copy["_practice_docs"] = practice_docs
        candidate_copy["_cross_check"] = cross_check
        pct = _estimate_concession_percentage(denom, candidate_copy, precedenti, events)

        # Livello confidenza
        if pct >= 70:
            conf = "alto"
        elif pct >= 40:
            conf = "medio"
        else:
            conf = "basso"

        # Fattori favorevoli
        fav = []
        if candidate.get("grado"):
            fav.append("Grado militare accertato")
        if any(s.get("stato_verifica") == "verificata" for s in sources):
            fav.append("Almeno una fonte verificata")
        if any(e.get("grado_attendibilita") == "alta" for e in events):
            fav.append("Eventi storici ad alta attendibilita'")
        if candidate.get("data_nascita") or candidate.get("luogo_nascita"):
            fav.append("Dati anagrafici parzialmente noti")
        if precedenti.get("albo_oro", 0) + precedenti.get("nastro_azzurro", 0) > 10:
            fav.append(f"Precedenti storici numerosi ({precedenti['albo_oro'] + precedenti['nastro_azzurro']} attribuzioni)")
        if "deceduto" in str(candidate.get("note_interne", "")).lower() and "onore" in denom.lower():
            fav.append("Decesso in prigionia (requisito per Medaglia d'Onore L.96/2007)")
        # Practice documents factors
        verified_docs = [d for d in practice_docs if d.get("stato_verifica") == "verificata"]
        if len(verified_docs) >= 3:
            fav.append(f"Documenti di pratica verificati ({len(verified_docs)})")
        elif len(verified_docs) >= 1:
            fav.append(f"Almeno un documento di pratica verificato ({len(verified_docs)})")
        has_foglio_matricolare = any(d.get("categoria_documentale") == "FOGLIO_MATRICOLARE" for d in practice_docs)
        if has_foglio_matricolare:
            fav.append("Foglio matricolare caricato (documento chiave)")
        has_stato_servizio = any(d.get("categoria_documentale") == "STATO_SERVIZIO" for d in practice_docs)
        if has_stato_servizio:
            fav.append("Stato di servizio caricato (documento probatorio)")
        # Extended practice factors
        practice_inviata = any(p.get("stato") in ("inviata", "in_istruttoria") for p in ext_practices)
        if practice_inviata:
            fav.append("Pratica gia' trasmessa all'ente istruttore")
        # Cross-check factors from historical DB sources
        if cross_check.get("caduti_albooro"):
            fav.append(f"Trovato in Albo d'Oro caduti ({cross_check['caduti_albooro']['count']} match)")
        if cross_check.get("internati_imi"):
            fav.append(f"Confermato come IMI - Internato Militare ({cross_check['internati_imi']['count']} match)")
        if cross_check.get("decorati_nastroazzurro"):
            fav.append(f"Gia' decorato (Nastro Azzurro: {cross_check['decorati_nastroazzurro']['count']} match)")
        if cross_check.get("decorati_albo"):
            fav.append(f"Gia' decorato ({cross_check['decorati_albo']['count']} match)")
        if cross_check.get("caduti_ministero"):
            fav.append(f"Registrato nei caduti del Ministero Difesa ({cross_check['caduti_ministero']['count']} match)")
        if cross_check.get("caduti_cwgc"):
            fav.append(f"Registrato CWGC ({cross_check['caduti_cwgc']['count']} match)")
        if cross_check.get("fonti_indice"):
            fav.append(f"Fonti d'archivio collegate ({cross_check['fonti_indice']['count']} match)")
        if cross_check.get("fondi_archivistici"):
            fav.append(f"Fondi archivistici menzionano il nominativo ({cross_check['fondi_archivistici']['count']} match)")
        if cross_check.get("nara_t315"):
            fav.append(f"Documenti NARA T315 menzionano il nominativo ({cross_check['nara_t315']['count']} match)")

        # Fattori sfavorevoli
        sfav = []
        if candidate.get("livello_certezza") == "da_verificare":
            sfav.append("Identificazione del soggetto da verificare")
        if all(s.get("stato_verifica") != "verificata" for s in sources):
            sfav.append("Nessuna fonte verificata")
        if not events:
            sfav.append("Nessun evento storico ricostruito")
        if not candidate.get("grado"):
            sfav.append("Grado militare non noto")
        if not candidate.get("data_nascita"):
            sfav.append("Data di nascita non nota")
        if rt.get("procedura_attiva") == "da_verificare":
            sfav.append("Procedura amministrativa da verificare")
        if pct < 20:
            sfav.append("Percentuale di concessione storicamente molto bassa")
        # Practice documents negative factors
        if not practice_docs:
            sfav.append("Nessun documento di pratica caricato")
        else:
            unverified_docs = [d for d in practice_docs if d.get("stato_verifica") != "verificata"]
            if len(unverified_docs) > len(verified_docs):
                sfav.append(f"Documenti non verificati ({len(unverified_docs)} su {len(practice_docs)})")
        if not has_foglio_matricolare and not has_stato_servizio:
            sfav.append("Foglio matricolare e stato di servizio mancanti")
        # Cross-check negative factors
        if not cross_check:
            sfav.append("Nessun match in alcuna fonte storica del database (Albo d'Oro, IMI, Nastro Azzurro, ecc.)")

        # Onorificenze alternative
        alternatives = []
        for alt_rt in recognition_types:
            if alt_rt["id"] == rt["id"]:
                continue
            if _is_relevant_honor(alt_rt["denominazione"], candidate, events):
                alternatives.append(alt_rt["denominazione"])

        analysis = {
            "onorificenza": denom,
            "categoria": rt.get("categoria", ""),
            "autorita_concedente": rt.get("autorita_concedente", ""),
            "ente_istruttore": rt.get("ente_istruttore", ""),
            "base_normativa": rt.get("base_normativa", ""),
            "requisiti": rt.get("requisiti", ""),
            "procedura_attiva": rt.get("procedura_attiva", "da_verificare"),
            "percentuale_stimata": round(pct, 1),
            "livello_confidenza": conf,
            "precedenti_storici": precedenti,
            "fattori_favorevoli": fav,
            "fattori_sfavorevoli": sfav,
            "onorificenze_alternative": alternatives,
        }
        analyses.append(analysis)

    # Ordina per % decrescente
    analyses.sort(key=lambda x: -x["percentuale_stimata"])
    return analyses


def _is_relevant_honor(denom: str, candidate: dict, events: list) -> bool:
    """Determina se un'onorificenza e' rilevante per il candidato."""
    d = denom.lower()
    note = str(candidate.get("note_interne", "")).lower()
    conflitto = (candidate.get("conflitto") or "").lower()

    # Medaglia d'Onore per deportati: solo internati/deportati
    if "onore" in d and "deportat" in d:
        return "deceduto" in note or "intern" in note or "prig" in note or "2gm" in conflitto

    # Valor militare: per caduti/deceduti in combattimento o prigionia
    if "valor militare" in d:
        return True  # Generico, applicabile a militari

    # Valor civile: per non militari o atti civili
    if "valor civile" in d or "civile" in d:
        return True

    # Croce di guerra
    if "croce di guerra" in d:
        return True

    # Merito di guerra
    if "merito" in d:
        return True

    # OMRI
    if "omri" in d or "repubblica" in d:
        return True  # Generico

    return False


def generate_ai_analysis(cid: int) -> dict:
    """Genera l'analisi AI completa per un candidato."""
    data = _get_candidate_full(cid)
    conn = get_conn()

    candidate = data
    sources = data["sources"]
    events = data["events"]
    recognition_types = data["recognition_types"]
    practice_docs = data.get("practice_documents", [])
    ext_practices = data.get("ext_practices", [])
    desc_contacts = data.get("descendant_contacts", [])

    # Cross-check su tutte le fonti storiche del DB
    cross_check = _cross_check_sources(conn, candidate)

    # Processo logico
    processo = _build_process_logic(candidate, events, sources, recognition_types,
                                    practice_docs=practice_docs, ext_practices=ext_practices,
                                    cross_check=cross_check)

    # Analisi per ogni onorificenza
    honor_analyses = _build_honor_analysis(candidate, events, sources, recognition_types, conn,
                                           practice_docs=practice_docs, ext_practices=ext_practices,
                                           cross_check=cross_check)

    # Riepilogo esecutivo
    top_honor = honor_analyses[0] if honor_analyses else None
    riepilogo = _build_executive_summary(candidate, top_honor, honor_analyses)

    # Fonti consultate (strutturato)
    fonti_json = json.dumps([
        {
            "titolo": s.get("titolo", ""),
            "tipologia": s.get("tipologia", ""),
            "ente": s.get("ente_conservatore", ""),
            "attendibilita": s.get("livello_attendibilita", "da_verificare"),
            "stato_verifica": s.get("stato_verifica", "non_verificata"),
            "url": s.get("url_istituzionale", ""),
        }
        for s in sources
    ], ensure_ascii=False, indent=2)

    # Onorificenze ipotizzabili (strutturato)
    onorificenze_json = json.dumps([
        {
            "onorificenza": h["onorificenza"],
            "percentuale": h["percentuale_stimata"],
            "confidenza": h["livello_confidenza"],
            "base_normativa": h["base_normativa"],
            "autorita": h["autorita_concedente"],
        }
        for h in honor_analyses
    ], ensure_ascii=False, indent=2)

    # Percentuali stimate (strutturato)
    percentuali_json = json.dumps([
        {"onorificenza": h["onorificenza"], "percentuale": h["percentuale_stimata"],
         "confidenza": h["livello_confidenza"]}
        for h in honor_analyses
    ], ensure_ascii=False, indent=2)

    # Precedenti (strutturato)
    precedenti_json = json.dumps([
        {"onorificenza": h["onorificenza"], "precedenti": h["precedenti_storici"]}
        for h in honor_analyses
    ], ensure_ascii=False, indent=2)

    # Fattori
    all_fav = list(set(f for h in honor_analyses for f in h["fattori_favorevoli"]))
    all_sfav = list(set(f for h in honor_analyses for f in h["fattori_sfavorevoli"]))

    # Raccomandazioni
    raccomandazioni = _build_recommendations(candidate, honor_analyses, sources, events,
                                             practice_docs=practice_docs, ext_practices=ext_practices,
                                             cross_check=cross_check)

    # Livello confidenza globale
    if top_honor:
        global_conf = top_honor["livello_confidenza"]
    else:
        global_conf = "basso"

    # Salva nel DB
    now = datetime.now().isoformat()
    conn.execute(
        """INSERT INTO rc_ai_analyses
           (candidate_id, tipo_analisi, riepilogo_esecutivo,
            processo_logico_dettagliato, fonti_consultate_json,
            onorificenze_ipotizzabili_json, percentuali_stimate_json,
            precedenti_attribuzioni_json, fattori_favorevoli, fattori_sfavorevoli,
            raccomandazioni, livello_confidenza, modello_ai, versione_modello,
            created_at, updated_at)
           VALUES (?, 'identificazione_completa', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'rule_based', '1.0', ?, ?)""",
        (cid, riepilogo, processo, fonti_json, onorificenze_json,
         percentuali_json, precedenti_json,
         "\n".join(f"- {f}" for f in all_fav),
         "\n".join(f"- {f}" for f in all_sfav),
         raccomandazioni, global_conf, now, now),
    )

    # Aggiorna le valutazioni esistenti con i nuovi campi AI
    for h in honor_analyses:
        rt_row = conn.execute(
            "SELECT id FROM rc_recognition_types WHERE denominazione = ?", (h["onorificenza"],)
        ).fetchone()
        if rt_row:
            rt_id = rt_row["id"]
            # Check if assessment esiste
            existing = conn.execute(
                "SELECT id FROM rc_recognition_assessments WHERE candidate_id = ? AND recognition_type_id = ?",
                (cid, rt_id),
            ).fetchone()
            if existing:
                conn.execute(
                    """UPDATE rc_recognition_assessments SET
                       processo_logico = ?, fonti_consultate = ?,
                       percentuale_stimata_concessione = ?,
                       precedenti_storici = ?,
                       fattori_favorevoli = ?, fattori_sfavorevoli = ?,
                       onorificenze_alternative = ?, livello_confidenza = ?,
                       updated_at = ?
                       WHERE id = ?""",
                    (processo[:500], fonti_json[:2000], h["percentuale_stimata"],
                     json.dumps(h["precedenti_storici"], ensure_ascii=False),
                     "\n".join(f"- {f}" for f in h["fattori_favorevoli"]),
                     "\n".join(f"- {f}" for f in h["fattori_sfavorevoli"]),
                     ", ".join(h["onorificenze_alternative"]),
                     h["livello_confidenza"], now, existing["id"]),
                )

    conn.commit()
    conn.close()

    return {
        "candidate_id": cid,
        "riepilogo_esecutivo": riepilogo,
        "processo_logico": processo,
        "onorificenze_analizzate": honor_analyses,
        "fonti_consultate": json.loads(fonti_json),
        "raccomandazioni": raccomandazioni,
        "livello_confidenza": global_conf,
    }


def _build_executive_summary(candidate: dict, top_honor: Optional[dict],
                             all_honors: list) -> str:
    """Costruisce il riepilogo esecutivo."""
    lines = []
    lines.append("RIEPILOGO ESECUTIVO ANALISI CANDIDATO")
    lines.append("=" * 60)
    lines.append("")
    lines.append(f"Candidato: {candidate.get('cognome','')} {candidate.get('nome','')}")
    if candidate.get("grado"):
        lines.append(f"Grado: {candidate['grado']}")
    if candidate.get("conflitto"):
        lines.append(f"Conflitto: {candidate['conflitto']}")
    lines.append(f"Stato attuale: {candidate.get('stato','BOZZA')}")
    lines.append(f"Livello certezza: {candidate.get('livello_certezza','da_verificare')}")
    lines.append("")

    if candidate.get("stato") == "RICONOSCIMENTO_GIA_CONCESSO":
        lines.append("Il candidato ha gia' ottenuto un riconoscimento (confermato da fonte istituzionale).")
        lines.append("Nessuna ulteriore procedura necessaria se non documentazione archivistica.")
        return "\n".join(lines)

    if not all_honors:
        lines.append("Non sono state identificate onorificenze ipotizzabili sulla base dei dati disponibili.")
        lines.append("Sono necessarie ulteriori fonti documentali per procedere.")
        return "\n".join(lines)

    lines.append(f"Onorificenze ipotizzabili: {len(all_honors)}")
    lines.append("")
    lines.append("Top 3 per probabilita' di concessione:")
    for i, h in enumerate(all_honors[:3], 1):
        lines.append(f"  {i}. {h['onorificenza']}")
        lines.append(f"     % stimata: {h['percentuale_stimata']}% (confidenza: {h['livello_confidenza']})")
        lines.append(f"     Autorita': {h['autorita_concedente']}")
        lines.append(f"     Base normativa: {h['base_normativa'][:80]}...")
    lines.append("")
    lines.append("AVVERTENZA: Le percentuali sono stime basate su criteri oggettivi")
    lines.append("e precedenti storici. Non costituiscono garanzia di concessione.")
    lines.append("Il riconoscimento e' ipotizzato e la procedura e' potenzialmente")
    lines.append("praticabile, in attesa di verifica amministrativa.")

    return "\n".join(lines)


def _build_recommendations(candidate: dict, honors: list, sources: list, events: list,
                           practice_docs: list = None, ext_practices: list = None,
                           cross_check: dict = None) -> str:
    """Costruisce le raccomandazioni operative."""
    practice_docs = practice_docs or []
    ext_practices = ext_practices or []
    cross_check = cross_check or {}
    lines = []
    lines.append("RACCOMANDAZIONI OPERATIVE")
    lines.append("=" * 60)
    lines.append("")

    if candidate.get("stato") == "RICONOSCIMENTO_GIA_CONCESSO":
        lines.append("1. Riconoscimento gia' concesso. Documentare in archivio.")
        lines.append("2. Verificare se esistono ulteriori riconoscimenti cumulabili.")
        return "\n".join(lines)

    if not honors:
        lines.append("1. Raccogliere ulteriori fonti documentali.")
        lines.append("2. Verificare l'identificazione del soggetto.")
        lines.append("3. Ricostruire gli eventi storici pertinenti.")
        return "\n".join(lines)

    top = honors[0]
    lines.append(f"1. Onorificenza prioritaria: {top['onorificenza']} ({top['percentuale_stimata']}%)")
    lines.append(f"   Autorita' concedente: {top['autorita_concedente']}")
    lines.append(f"   Ente istruttore: {top['ente_istruttore']}")
    lines.append("")

    # Verifiche necessarie
    lines.append("2. Verifiche necessarie prima di procedere:")
    if not sources or all(s.get("stato_verifica") != "verificata" for s in sources):
        lines.append("   a. Verificare le fonti documentali (stato attuale: non verificate)")
    if not events:
        lines.append("   b. Ricostruire gli eventi storici pertinenti")
    if candidate.get("livello_certezza") == "da_verificare":
        lines.append("   c. Confermare l'identificazione del soggetto (data nascita, luogo, paternita')")
    if top.get("procedura_attiva") == "da_verificare":
        lines.append(f"   d. Verificare lo stato della procedura amministrativa per {top['onorificenza']}")
    lines.append("")

    # Fonti aggiuntive
    lines.append("3. Fonti aggiuntive raccomandate:")
    lines.append("   a. Archivio di Stato (matricole, fogli matricolari)")
    lines.append("   b. Archivio Centrale dello Stato (fascicoli personali)")
    if "deceduto" in str(candidate.get("note_interne", "")).lower():
        lines.append("   c. Certificato di morte / documentazione prigionia")
        lines.append("   d. Elenco IMI (già consultato se presente)")
    lines.append("   e. Albo d'Oro e Nastro Azzurro (per precedenti)")
    lines.append("")

    # Procedura
    lines.append("4. Procedura suggerita:")
    lines.append("   a. Completare la verifica delle fonti")
    lines.append("   b. Validare storicamente gli eventi")
    lines.append("   c. Ottenere validazione amministrativa")
    lines.append("   d. Solo dopo validazione: autorizzare ricerca discendenti")
    lines.append("   e. Preparare fascicolo e trasmettere all'ente istruttore")
    lines.append("")

    # Documenti di pratica
    lines.append("5. Documenti di pratica:")
    if not practice_docs:
        lines.append("   a. CARICARE documenti fondamentali: foglio matricolare, stato di servizio")
        lines.append("   b. Verificare disponibilita' di certificati e atti")
    else:
        unverified = [d for d in practice_docs if d.get("stato_verifica") != "verificata"]
        if unverified:
            lines.append(f"   a. Verificare {len(unverified)} documenti non ancora verificati")
        has_foglio = any(d.get("categoria_documentale") == "FOGLIO_MATRICOLARE" for d in practice_docs)
        has_stato = any(d.get("categoria_documentale") == "STATO_SERVIZIO" for d in practice_docs)
        if not has_foglio:
            lines.append("   b. Recuperare e caricare il foglio matricolare")
        if not has_stato:
            lines.append("   c. Recuperare e caricare lo stato di servizio")
        if not unverified and has_foglio and has_stato:
            lines.append("   a. Tutti i documenti chiave sono verificati. Pratica documentalmente solida.")
    lines.append("")

    # Cross-check fonti storiche
    lines.append("6. Verifiche su fonti storiche del database:")
    if cross_check:
        if cross_check.get("caduti_albooro"):
            lines.append(f"   a. Confermato in Albo d'Oro caduti ({cross_check['caduti_albooro']['count']} match) - verificare coerenza dati")
        if cross_check.get("internati_imi"):
            lines.append(f"   b. Confermato come IMI ({cross_check['internati_imi']['count']} match) - recuperare scheda prigionia")
        if cross_check.get("decorati_nastroazzurro"):
            lines.append(f"   c. Gia' decorato Nastro Azzurro ({cross_check['decorati_nastroazzurro']['count']} match) - verificare cumulo")
        if cross_check.get("decorati_albo"):
            lines.append(f"   d. Gia' decorato ({cross_check['decorati_albo']['count']} match) - verificare cumulo")
        if cross_check.get("caduti_ministero"):
            lines.append(f"   e. Registrato caduti Ministero Difesa ({cross_check['caduti_ministero']['count']} match)")
        if cross_check.get("caduti_cwgc"):
            lines.append(f"   f. Registrato CWGC ({cross_check['caduti_cwgc']['count']} match) - verificare dati sepoltura")
        if cross_check.get("fonti_indice"):
            lines.append(f"   g. Fonti d'archivio collegate ({cross_check['fonti_indice']['count']} match) - consultare documenti")
        if cross_check.get("fondi_archivistici"):
            lines.append(f"   h. Fondi archivistici ({cross_check['fondi_archivistici']['count']} match) - esaminare raw text")
        if cross_check.get("nara_t315"):
            lines.append(f"   i. Documenti NARA T315 ({cross_check['nara_t315']['count']} match) - recuperare documentazione prigionia")
    else:
        lines.append("   a. NESSUN match nelle fonti storiche - approfondire ricerca manuale")
        lines.append("   b. Verificare manualmente in Albo d'Oro, Nastro Azzurro, elenchi IMI")
        lines.append("   c. Cercare in archivi locali e diaristici")
    lines.append("")
    lines.append("AVVERTENZA: Nessuna comunicazione ai discendenti senza")
    lines.append("preventiva approvazione del revisore amministrativo.")

    return "\n".join(lines)


def get_ai_analyses(cid: int) -> list:
    """Recupera le analisi AI salvate per un candidato."""
    conn = get_conn()
    rows = conn.execute(
        "SELECT * FROM rc_ai_analyses WHERE candidate_id = ? ORDER BY created_at DESC",
        (cid,),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]

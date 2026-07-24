"""Generazione fascicolo PDF per il Percorso Riconoscimenti.

Usa reportlab per generare un PDF strutturato con 16 sezioni.
Ogni affermazione della relazione deve poter essere collegata a una fonte.
"""
from datetime import datetime
from pathlib import Path
from typing import Optional

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import cm, mm
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
    PageBreak, ListFlowable, ListItem,
)
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_JUSTIFY

from database import get_conn

DOSSIER_DIR = Path(__file__).parent / "outputs" / "dossiers"
DOSSIER_DIR.mkdir(parents=True, exist_ok=True)


def _get_candidate_data(cid: int) -> dict:
    conn = get_conn()
    cand = conn.execute("SELECT * FROM rc_candidates WHERE id = ?", (cid,)).fetchone()
    if not cand:
        conn.close()
        raise ValueError(f"Candidato non trovato: id={cid}")
    data = dict(cand)
    data["events"] = [dict(r) for r in conn.execute(
        "SELECT * FROM rc_historical_events WHERE candidate_id = ? ORDER BY data_inizio", (cid,)
    ).fetchall()]
    data["sources"] = [dict(r) for r in conn.execute(
        "SELECT * FROM rc_sources WHERE candidate_id = ? ORDER BY id", (cid,)
    ).fetchall()]
    data["assessments"] = [dict(r) for r in conn.execute(
        """SELECT a.*, r.denominazione as recognition_name
           FROM rc_recognition_assessments a
           LEFT JOIN rc_recognition_types r ON a.recognition_type_id = r.id
           WHERE a.candidate_id = ? ORDER BY a.created_at""", (cid,)
    ).fetchall()]
    data["family"] = [dict(r) for r in conn.execute(
        "SELECT * FROM rc_family_persons WHERE candidate_id = ? ORDER BY id", (cid,)
    ).fetchall()]
    data["transitions"] = [dict(r) for r in conn.execute(
        "SELECT * FROM rc_state_transitions WHERE candidate_id = ? ORDER BY data_ora", (cid,)
    ).fetchall()]
    data["admin_cases"] = [dict(r) for r in conn.execute(
        """SELECT a.*, r.denominazione as recognition_name
           FROM rc_administrative_cases a
           LEFT JOIN rc_recognition_types r ON a.recognition_type_id = r.id
           WHERE a.candidate_id = ? ORDER BY a.created_at""", (cid,)
    ).fetchall()]
    data["descendant_cases"] = [dict(r) for r in conn.execute(
        "SELECT * FROM rc_descendant_cases WHERE candidate_id = ?", (cid,)
    ).fetchall()]
    conn.close()
    return data


def generate_pdf_dossier(cid: int) -> Path:
    """Genera il fascicolo PDF completo per un candidato."""
    data = _get_candidate_data(cid)
    pdf_path = DOSSIER_DIR / f"fascicolo_{cid}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"

    doc = SimpleDocTemplate(
        str(pdf_path), pagesize=A4,
        leftMargin=2 * cm, rightMargin=2 * cm,
        topMargin=2 * cm, bottomMargin=2 * cm,
        title=f"Fascicolo Riconoscimento - {data.get('cognome', '')} {data.get('nome', '')}",
    )

    styles = getSampleStyleSheet()
    style_title = ParagraphStyle("CustomTitle", parent=styles["Title"],
                                 fontSize=20, spaceAfter=20, alignment=TA_CENTER)
    style_h1 = ParagraphStyle("CustomH1", parent=styles["Heading1"],
                              fontSize=14, spaceBefore=16, spaceAfter=8,
                              textColor=colors.HexColor("#1a1a2e"))
    style_h2 = ParagraphStyle("CustomH2", parent=styles["Heading2"],
                              fontSize=12, spaceBefore=10, spaceAfter=6)
    style_body = ParagraphStyle("CustomBody", parent=styles["Normal"],
                                fontSize=10, leading=14, alignment=TA_JUSTIFY)
    style_small = ParagraphStyle("Small", parent=styles["Normal"],
                                 fontSize=8, leading=10, textColor=colors.grey)
    style_note = ParagraphStyle("Note", parent=styles["Normal"],
                                fontSize=9, leading=12, textColor=colors.HexColor("#666666"),
                                spaceAfter=6)

    story = []

    # ─── 1. Copertina ─────────────────────────────────────────────────────
    story.append(Spacer(1, 6 * cm))
    story.append(Paragraph("PERCORSO RICONOSCIMENTI", style_title))
    story.append(Paragraph("Lettere dal Fronte", ParagraphStyle(
        "Subtitle", parent=styles["Normal"], fontSize=14, alignment=TA_CENTER,
        textColor=colors.grey, spaceAfter=30)))
    story.append(Paragraph(
        f"Fascicolo n. {cid}", ParagraphStyle(
            "FascNum", parent=styles["Normal"], fontSize=16, alignment=TA_CENTER,
            spaceAfter=10)))
    story.append(Paragraph(
        f"<b>{data.get('cognome', '')} {data.get('nome', '')}</b>",
        ParagraphStyle("CandName", parent=styles["Normal"], fontSize=18,
                       alignment=TA_CENTER, spaceAfter=6)))
    if data.get("grado"):
        story.append(Paragraph(f"{data['grado']}", style_small))
    if data.get("conflitto"):
        story.append(Paragraph(f"Conflitto: {data['conflitto']}", style_small))
    story.append(Spacer(1, 4 * cm))
    story.append(Paragraph(
        f"Generato il {datetime.now().strftime('%d/%m/%Y alle %H:%M')}",
        ParagraphStyle("Date", parent=styles["Normal"], fontSize=10,
                       alignment=TA_CENTER, textColor=colors.grey)))
    story.append(Paragraph(
        "Documento non costituisce garanzia di concessione. "
        "Il riconoscimento è ipotizzato e la procedura è potenzialmente praticabile, "
        "in attesa di verifica amministrativa.",
        ParagraphStyle("Disclaimer", parent=styles["Normal"], fontSize=8,
                       alignment=TA_CENTER, textColor=colors.red, spaceBefore=20)))
    story.append(PageBreak())

    # ─── 2. Indice ────────────────────────────────────────────────────────
    story.append(Paragraph("Indice", style_h1))
    indice_items = [
        "1. Dati identificativi del candidato",
        "2. Cronologia del procedimento",
        "3. Relazione storico-documentale",
        "4. Descrizione del fatto",
        "5. Riconoscimento ipotizzato",
        "6. Inquadramento normativo",
        "7. Tabella requisiti / prove",
        "8. Genealogia essenziale",
        "9. Documenti di parentela",
        "10. Elenco delle fonti",
        "11. Elenco allegati",
        "12. Istanza / segnalazione",
        "13. Delega",
        "14. Dichiarazioni e firme",
    ]
    for item in indice_items:
        story.append(Paragraph(item, style_body))
    story.append(PageBreak())

    # ─── 3. Dati identificativi ───────────────────────────────────────────
    story.append(Paragraph("1. Dati identificativi del candidato", style_h1))
    fields = [
        ("Nome", data.get("nome")),
        ("Cognome", data.get("cognome")),
        ("Varianti nominativi", data.get("varianti_nominativi")),
        ("Paternità", data.get("paternita")),
        ("Maternità", data.get("maternita")),
        ("Data di nascita", data.get("data_nascita")),
        ("Luogo di nascita", data.get("luogo_nascita")),
        ("Data di morte", data.get("data_morte")),
        ("Luogo di morte", data.get("luogo_morte")),
        ("Comune di residenza", data.get("comune_residenza")),
        ("Grado", data.get("grado")),
        ("Reparto", data.get("reparto")),
        ("Forza armata", data.get("forza_armata")),
        ("Matricola", data.get("matricola")),
        ("Conflitto/periodo", data.get("conflitto")),
        ("Stato del workflow", data.get("stato")),
        ("Livello di certezza", data.get("livello_certezza")),
    ]
    table_data = [[Paragraph(f"<b>{label}</b>", style_body),
                   Paragraph(str(val or "—"), style_body)] for label, val in fields]
    t = Table(table_data, colWidths=[5 * cm, 11 * cm])
    t.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("LINEBELOW", (0, 0), (-1, -1), 0.25, colors.HexColor("#cccccc")),
    ]))
    story.append(t)
    story.append(PageBreak())

    # ─── 4. Cronologia ────────────────────────────────────────────────────
    story.append(Paragraph("2. Cronologia del procedimento", style_h1))
    if data["transitions"]:
        trans_data = [["Data", "Stato precedente", "Stato successivo", "Autore", "Motivazione"]]
        for tr in data["transitions"]:
            trans_data.append([
                tr.get("data_ora", "")[:19],
                tr.get("stato_precedente", ""),
                tr.get("stato_successivo", ""),
                tr.get("autore", ""),
                Paragraph(tr.get("motivazione") or "", style_small),
            ])
        t2 = Table(trans_data, colWidths=[3 * cm, 3.5 * cm, 3.5 * cm, 2.5 * cm, 4 * cm])
        t2.setStyle(TableStyle([
            ("FONTSIZE", (0, 0), (-1, 0), 8),
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1a1a2e")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("FONTSIZE", (0, 1), (-1, -1), 8),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#cccccc")),
        ]))
        story.append(t2)
    else:
        story.append(Paragraph("Nessuna transizione registrata.", style_note))
    story.append(PageBreak())

    # ─── 5. Relazione storico-documentale ─────────────────────────────────
    story.append(Paragraph("3. Relazione storico-documentale", style_h1))
    story.append(Paragraph(
        "La presente relazione è basata esclusivamente su fonti documentali verificate. "
        "Ogni affermazione è collegata alla fonte di riferimento indicata nell'elenco fonti (sezione 10).",
        style_note))
    if data["events"]:
        for i, ev in enumerate(data["events"], 1):
            story.append(Paragraph(f"Evento {i}: {ev.get('tipo_evento', 'Non specificato')}", style_h2))
            story.append(Paragraph(f"<b>Periodo:</b> {ev.get('data_inizio', '')} – {ev.get('data_fine', '')}", style_body))
            story.append(Paragraph(f"<b>Luogo:</b> {ev.get('luogo', '—')}", style_body))
            if ev.get("descrizione_verificata"):
                story.append(Paragraph(f"<b>Descrizione verificata:</b> {ev['descrizione_verificata']}", style_body))
            if ev.get("condotta_individuale"):
                story.append(Paragraph(f"<b>Condotta individuale:</b> {ev['condotta_individuale']}", style_body))
            if ev.get("rischio_affrontato"):
                story.append(Paragraph(f"<b>Rischio affrontato:</b> {ev['rischio_affrontato']}", style_body))
            if ev.get("conseguenze"):
                story.append(Paragraph(f"<b>Conseguenze:</b> {ev['conseguenze']}", style_body))
            story.append(Paragraph(f"<b>Attendibilità:</b> {ev.get('grado_attendibilita', 'da_verificare')}", style_small))
            story.append(Spacer(1, 6))
    else:
        story.append(Paragraph("Nessun evento storico registrato.", style_note))
    story.append(PageBreak())

    # ─── 6. Riconoscimento ipotizzato ─────────────────────────────────────
    story.append(Paragraph("5. Riconoscimento ipotizzato", style_h1))
    story.append(Paragraph(
        "<b>AVVERTENZA:</b> Il riconoscimento qui indicato è ipotizzato. "
        "Nessuna garanzia di concessione. Verifica amministrativa necessaria.",
        ParagraphStyle("Warning", parent=style_body, textColor=colors.red, spaceAfter=10)))
    if data["assessments"]:
        for a in data["assessments"]:
            story.append(Paragraph(f"<b>{a.get('recognition_name', 'Riconoscimento')}</b>", style_h2))
            story.append(Paragraph(f"Riconoscimento ipotizzato: {a.get('riconoscimento_ipotizzato', '—')}", style_body))
            story.append(Paragraph(f"Procedura: {a.get('procedura', 'da_verificare')}", style_body))
            if a.get("requisiti_presenti"):
                story.append(Paragraph(f"Requisiti presenti: {a['requisiti_presenti']}", style_body))
            if a.get("requisiti_mancanti"):
                story.append(Paragraph(f"Requisiti mancanti: {a['requisiti_mancanti']}", style_body))
            if a.get("elementi_contrari"):
                story.append(Paragraph(f"Elementi contrari: {a['elementi_contrari']}", style_body))
            if a.get("motivazione"):
                story.append(Paragraph(f"Motivazione: {a['motivazione']}", style_body))
            story.append(Paragraph(
                f"Validazione storica: {'Sì' if a.get('validazione_storica') else 'No'} | "
                f"Validazione amministrativa: {'Sì' if a.get('validazione_amministrativa') else 'No'}",
                style_small))
            story.append(Spacer(1, 8))
    else:
        story.append(Paragraph("Nessuna valutazione di riconoscimento registrata.", style_note))
    story.append(PageBreak())

    # ─── 7. Inquadramento normativo ───────────────────────────────────────
    story.append(Paragraph("6. Inquadramento normativo", style_h1))
    if data["assessments"]:
        conn = get_conn()
        for a in data["assessments"]:
            if a.get("recognition_type_id"):
                rt = conn.execute(
                    "SELECT * FROM rc_recognition_types WHERE id = ?",
                    (a["recognition_type_id"],),
                ).fetchone()
                if rt:
                    story.append(Paragraph(f"<b>{rt['denominazione']}</b>", style_h2))
                    story.append(Paragraph(f"Categoria: {rt.get('categoria', '—')}", style_body))
                    story.append(Paragraph(f"Autorità concedente: {rt.get('autorita_concedente', '—')}", style_body))
                    story.append(Paragraph(f"Ente istruttore: {rt.get('ente_istruttore', '—')}", style_body))
                    story.append(Paragraph(f"Base normativa: {rt.get('base_normativa', '—')}", style_body))
                    story.append(Paragraph(f"Procedura: {rt.get('procedura_attiva', 'da_verificare')}", style_body))
                    if rt.get("requisiti"):
                        story.append(Paragraph(f"Requisiti: {rt['requisiti']}", style_body))
                    story.append(Spacer(1, 8))
        conn.close()
    else:
        story.append(Paragraph("Nessun inquadramento normativo disponibile.", style_note))
    story.append(PageBreak())

    # ─── 8. Genealogia essenziale ─────────────────────────────────────────
    story.append(Paragraph("8. Genealogia essenziale", style_h1))
    if data["family"]:
        fam_data = [["Nome", "Cognome", "Rapporto", "Stato vita", "Certezza"]]
        for fp in data["family"]:
            fam_data.append([
                fp.get("nome", "—"),
                fp.get("cognome", "—"),
                fp.get("rapporto_candidato", "—"),
                fp.get("stato_vita", "—"),
                fp.get("livello_certezza", "—"),
            ])
        t3 = Table(fam_data, colWidths=[3 * cm, 3 * cm, 3 * cm, 3 * cm, 3 * cm])
        t3.setStyle(TableStyle([
            ("FONTSIZE", (0, 0), (-1, -1), 9),
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1a1a2e")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#cccccc")),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ]))
        story.append(t3)
        story.append(Paragraph(
            "I dati delle persone viventi sono limitati per tutela della privacy. "
            "Date e luoghi di nascita non sono esposti per persone viventi o non accertate.",
            style_note))
    else:
        story.append(Paragraph("Nessuna genealogia registrata.", style_note))
    story.append(PageBreak())

    # ─── 9. Elenco fonti ──────────────────────────────────────────────────
    story.append(Paragraph("10. Elenco delle fonti", style_h1))
    if data["sources"]:
        for i, src in enumerate(data["sources"], 1):
            story.append(Paragraph(
                f"[Fonte {i}] {src.get('titolo', 'Senza titolo')}", style_h2))
            story.append(Paragraph(f"Tipologia: {src.get('tipologia', '—')}", style_small))
            story.append(Paragraph(f"Ente conservatore: {src.get('ente_conservatore', '—')}", style_small))
            if src.get("segnatura_completa"):
                story.append(Paragraph(f"Segnatura: {src['segnatura_completa']}", style_small))
            if src.get("url_istituzionale"):
                story.append(Paragraph(f"URL: {src['url_istituzionale']}", style_small))
            story.append(Paragraph(f"Attendibilità: {src.get('livello_attendibilita', 'da_verificare')}", style_small))
            story.append(Paragraph(f"Stato verifica: {src.get('stato_verifica', 'non_verificata')}", style_small))
            story.append(Spacer(1, 6))
    else:
        story.append(Paragraph("Nessuna fonte registrata.", style_note))
    story.append(PageBreak())

    # ─── 10. Pratiche amministrative ──────────────────────────────────────
    story.append(Paragraph("11. Pratiche amministrative", style_h1))
    if data["admin_cases"]:
        for ac in data["admin_cases"]:
            story.append(Paragraph(f"<b>{ac.get('recognition_name', 'Pratica')}</b>", style_h2))
            story.append(Paragraph(f"Ente destinatario: {ac.get('ente_destinatario', '—')}", style_body))
            story.append(Paragraph(f"Ufficio: {ac.get('ufficio', '—')}", style_body))
            story.append(Paragraph(f"Protocollo: {ac.get('protocollo', '—')}", style_body))
            story.append(Paragraph(f"Data invio: {ac.get('data_invio', '—')}", style_body))
            story.append(Paragraph(f"Stato: {ac.get('stato', '—')}", style_body))
            if ac.get("esito"):
                story.append(Paragraph(f"Esito: {ac['esito']}", style_body))
            story.append(Spacer(1, 8))
    else:
        story.append(Paragraph("Nessuna pratica amministrativa registrata.", style_note))

    story.append(Spacer(1, 20))
    story.append(Paragraph(
        "Il presente fascicolo è generato dal sistema Percorso Riconoscimenti "
        "del progetto Lettere dal Fronte. Non costituisce titolo né garanzia di riconoscimento. "
        "Tutte le informazioni sono suscettibili di verifica e integrazione.",
        ParagraphStyle("Footer", parent=style_small, alignment=TA_CENTER)))

    doc.build(story)
    return pdf_path

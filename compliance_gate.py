"""Compliance Gate — motore centralizzato di valutazione conformità.
Nessun modulo deve scaricare, pubblicare, esportare o inviare dati senza passare di qui."""
import json
from datetime import datetime
from database import get_conn

# Classificazioni risorsa
METADATA_ONLY = "METADATA_ONLY"
PUBLIC_VIEW = "PUBLIC_VIEW"
PUBLIC_DOWNLOAD = "PUBLIC_DOWNLOAD"
REQUEST_REQUIRED = "REQUEST_REQUIRED"
AUTHORIZATION_REQUIRED = "AUTHORIZATION_REQUIRED"
RESTRICTED = "RESTRICTED"
RIGHTS_UNKNOWN = "RIGHTS_UNKNOWN"
UNREACHABLE = "UNREACHABLE"

# Azioni controllate
ACTIONS = [
    "INDEX_METADATA", "GENERATE_LINKS", "DOWNLOAD_FILE", "RUN_OCR",
    "EXTRACT_PERSONAL_DATA", "SHOW_TO_AUTHENTICATED_USER", "SHOW_PUBLICLY",
    "INCLUDE_IN_DOSSIER", "EXPORT", "DELETE", "REFRESH_SOURCE",
]

# Decisioni
ALLOW = "ALLOW"
ALLOW_WITH_LIMITATIONS = "ALLOW_WITH_LIMITATIONS"
REQUIRE_REVIEW = "REQUIRE_REVIEW"
REQUIRE_AUTHORIZATION = "REQUIRE_AUTHORIZATION"
DENY = "DENY"


def _now():
    return datetime.now().isoformat()


def get_policy_for_domain(domain: str) -> dict | None:
    conn = get_conn()
    row = conn.execute(
        "SELECT * FROM source_policies WHERE domain = ? ORDER BY updated_at DESC LIMIT 1",
        (domain,),
    ).fetchone()
    conn.close()
    return dict(row) if row else None


def get_policy_for_provider(provider: str) -> dict | None:
    conn = get_conn()
    row = conn.execute(
        "SELECT * FROM source_policies WHERE provider = ? ORDER BY updated_at DESC LIMIT 1",
        (provider,),
    ).fetchone()
    conn.close()
    return dict(row) if row else None


def _log_decision(source_record_id, digital_object_id, action, decision,
                  policy_id, rule_code, reason, limitations=None,
                  authorization_id=None, decided_by="system",
                  decision_source="automatic_policy"):
    conn = get_conn()
    conn.execute(
        """INSERT INTO compliance_decisions
           (source_record_id, digital_object_id, requested_action, decision,
            policy_id, rule_code, reason, limitations_json, authorization_id,
            decided_by, decision_source, created_at)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
        (source_record_id, digital_object_id, action, decision,
         policy_id, rule_code, reason,
         json.dumps(limitations) if limitations else None,
         authorization_id, decided_by, decision_source, _now()),
    )
    conn.commit()
    conn.close()


def _check_authorization(policy_id, record_id, action):
    conn = get_conn()
    row = conn.execute(
        """SELECT * FROM compliance_authorizations
           WHERE source_policy_id = ? AND record_id = ?
             AND revoked = 0 AND valid_until > ?
           ORDER BY created_at DESC LIMIT 1""",
        (policy_id, record_id, _now()),
    ).fetchone()
    conn.close()
    return dict(row) if row else None


def evaluate(resource: dict, requested_action: str, user_role: str = "operator") -> dict:
    """Punto unico di valutazione. Restituisce decisione, regola, motivazione, condizioni."""
    classification = resource.get("classification", RIGHTS_UNKNOWN)
    domain = resource.get("domain", "")
    provider = resource.get("provider", "")
    record_id = resource.get("record_id", "")
    digital_object_id = resource.get("digital_object_id", "")
    life_status = resource.get("life_status", "deceased")
    has_health_data = resource.get("has_health_data", False)

    policy = get_policy_for_domain(domain) or get_policy_for_provider(provider)
    policy_id = policy["id"] if policy else None
    policy_status = policy["policy_status"] if policy else "unknown"

    result = {
        "decision": DENY,
        "rule_code": "",
        "reason": "",
        "conditions": [],
        "authorization_required": False,
        "policy_id": policy_id,
        "classification": classification,
        "timestamp": _now(),
        "policy_version": "1.0",
    }

    # Regola 0: azione non riconosciuta
    if requested_action not in ACTIONS:
        result["decision"] = DENY
        result["rule_code"] = "UNKNOWN_ACTION"
        result["reason"] = f"Azione '{requested_action}' non riconosciuta"
        _log_decision(record_id, digital_object_id, requested_action, result["decision"],
                      policy_id, result["rule_code"], result["reason"])
        return result

    # Regola 1: UNREACHABLE
    if classification == UNREACHABLE:
        result["decision"] = DENY
        result["rule_code"] = "UNREACHABLE"
        result["reason"] = "Fonte non raggiungibile. Conservare record e pianificare verifica."
        _log_decision(record_id, digital_object_id, requested_action, result["decision"],
                      policy_id, result["rule_code"], result["reason"])
        return result

    # Regola 2: RESTRICTED
    if classification == RESTRICTED:
        result["decision"] = DENY
        result["rule_code"] = "RESTRICTED"
        result["reason"] = "Risorsa riservata. Esclusa da download, OCR, pubblicazione, API pubbliche."
        _log_decision(record_id, digital_object_id, requested_action, result["decision"],
                      policy_id, result["rule_code"], result["reason"])
        return result

    # Regola 3: RIGHTS_UNKNOWN o policy unknown/changed/suspended
    if classification == RIGHTS_UNKNOWN or policy_status in ("unknown", "changed", "suspended"):
        if requested_action in ("INDEX_METADATA", "GENERATE_LINKS"):
            result["decision"] = ALLOW_WITH_LIMITATIONS
            result["rule_code"] = "RIGHTS_UNKNOWN_METADATA_ONLY"
            result["reason"] = "Diritti non chiari: solo metadati minimi e link diretto."
            result["conditions"] = ["metadata_minimal_only", "direct_link_only", "no_download", "no_copy"]
        else:
            result["decision"] = REQUIRE_REVIEW
            result["rule_code"] = "RIGHTS_UNKNOWN_REVIEW"
            result["reason"] = "Diritti non chiari: richiesta revisione umana."
            _add_to_review_queue(record_id, policy_id, "rights_unknown", "high")
        _log_decision(record_id, digital_object_id, requested_action, result["decision"],
                      policy_id, result["rule_code"], result["reason"], result["conditions"])
        return result

    # Regola 4: dati sanitari
    if has_health_data:
        if requested_action in ("SHOW_PUBLICLY", "EXPORT", "INCLUDE_IN_DOSSIER"):
            result["decision"] = DENY
            result["rule_code"] = "HEALTH_DATA_PROTECTED"
            result["reason"] = "Dati sanitari: esclusione automatica da pubblicazione, export, dossier."
            _log_decision(record_id, digital_object_id, requested_action, result["decision"],
                          policy_id, result["rule_code"], result["reason"])
            return result
        if requested_action in ("RUN_OCR", "EXTRACT_PERSONAL_DATA"):
            result["decision"] = REQUIRE_AUTHORIZATION
            result["rule_code"] = "HEALTH_DATA_AUTH_REQUIRED"
            result["reason"] = "Dati sanitari: autorizzazione richiesta per OCR/estrazione."
            result["authorization_required"] = True
            _add_to_review_queue(record_id, policy_id, "health_data", "high")
            _log_decision(record_id, digital_object_id, requested_action, result["decision"],
                          policy_id, result["rule_code"], result["reason"],
                          authorization_required=True)
            return result

    # Regola 5: persona potenzialmente vivente
    if life_status in ("possibly_living", "unknown"):
        if requested_action in ("SHOW_PUBLICLY", "EXPORT", "INCLUDE_IN_DOSSIER"):
            result["decision"] = REQUIRE_REVIEW
            result["rule_code"] = "POSSIBLY_LIVING_REVIEW"
            result["reason"] = "Soggetto potenzialmente vivente: revisione obbligatoria."
            _add_to_review_queue(record_id, policy_id, "possibly_living", "high")
            _log_decision(record_id, digital_object_id, requested_action, result["decision"],
                          policy_id, result["rule_code"], result["reason"])
            return result

    # Regola 6: METADATA_ONLY
    if classification == METADATA_ONLY:
        if requested_action in ("INDEX_METADATA", "GENERATE_LINKS"):
            result["decision"] = ALLOW_WITH_LIMITATIONS
            result["rule_code"] = "METADATA_ONLY_OK"
            result["reason"] = "Metadati e collegamenti consentiti. No download, no copia."
            result["conditions"] = ["no_download", "no_image_copy", "direct_link_only"]
        elif requested_action == "SHOW_TO_AUTHENTICATED_USER":
            result["decision"] = ALLOW_WITH_LIMITATIONS
            result["rule_code"] = "METADATA_ONLY_VIEW"
            result["reason"] = "Visualizzazione metadati per utenti autenticati."
            result["conditions"] = ["no_download", "direct_link_only"]
        else:
            result["decision"] = DENY
            result["rule_code"] = "METADATA_ONLY_BLOCKED"
            result["reason"] = "Classificazione METADATA_ONLY: azione non consentita."
        _log_decision(record_id, digital_object_id, requested_action, result["decision"],
                      policy_id, result["rule_code"], result["reason"], result["conditions"])
        return result

    # Regola 7: PUBLIC_VIEW
    if classification == PUBLIC_VIEW:
        if requested_action in ("INDEX_METADATA", "GENERATE_LINKS"):
            result["decision"] = ALLOW
            result["rule_code"] = "PUBLIC_VIEW_OK"
            result["reason"] = "Visualizzazione pubblica: indicizzazione e link consentiti."
        elif requested_action == "SHOW_TO_AUTHENTICATED_USER":
            result["decision"] = ALLOW
            result["rule_code"] = "PUBLIC_VIEW_AUTH_OK"
            result["reason"] = "Visualizzazione per utenti autenticati."
        elif requested_action == "SHOW_PUBLICLY":
            result["decision"] = ALLOW_WITH_LIMITATIONS
            result["rule_code"] = "PUBLIC_VIEW_LINK_ONLY"
            result["reason"] = "Link al visualizzatore esterno. Non presumere download autorizzato."
            result["conditions"] = ["link_to_external_viewer", "no_local_copy"]
        elif requested_action == "DOWNLOAD_FILE":
            result["decision"] = DENY
            result["rule_code"] = "PUBLIC_VIEW_NO_DOWNLOAD"
            result["reason"] = "Visualizzazione pubblica non implica download autorizzato."
        else:
            result["decision"] = REQUIRE_REVIEW
            result["rule_code"] = "PUBLIC_VIEW_REVIEW"
            result["reason"] = "Azione non standard su risorsa PUBLIC_VIEW."
        _log_decision(record_id, digital_object_id, requested_action, result["decision"],
                      policy_id, result["rule_code"], result["reason"], result["conditions"])
        return result

    # Regola 8: PUBLIC_DOWNLOAD
    if classification == PUBLIC_DOWNLOAD:
        if not policy or not policy.get("document_download_allowed"):
            result["decision"] = REQUIRE_REVIEW
            result["rule_code"] = "PUBLIC_DOWNLOAD_POLICY_MISSING"
            result["reason"] = "Download pubblico ma policy non verificata."
            _add_to_review_queue(record_id, policy_id, "download_policy_missing", "medium")
        elif requested_action in ("INDEX_METADATA", "GENERATE_LINKS", "SHOW_TO_AUTHENTICATED_USER",
                                    "SHOW_PUBLICLY", "DOWNLOAD_FILE"):
            result["decision"] = ALLOW
            result["rule_code"] = "PUBLIC_DOWNLOAD_OK"
            result["reason"] = "Download pubblico autorizzato con policy verificata."
            if policy.get("attribution_required"):
                result["conditions"] = [f"attribution_required: {policy.get('required_credit_line', '')}"]
        else:
            result["decision"] = ALLOW_WITH_LIMITATIONS
            result["rule_code"] = "PUBLIC_DOWNLOAD_LIMITED"
            result["reason"] = "Azione consentita con limitazioni."
        _log_decision(record_id, digital_object_id, requested_action, result["decision"],
                      policy_id, result["rule_code"], result["reason"], result["conditions"])
        return result

    # Regola 9: REQUEST_REQUIRED
    if classification == REQUEST_REQUIRED:
        if requested_action in ("INDEX_METADATA", "GENERATE_LINKS"):
            result["decision"] = ALLOW_WITH_LIMITATIONS
            result["rule_code"] = "REQUEST_REQUIRED_METADATA"
            result["reason"] = "Metadati e link consentiti. Documento disponibile su richiesta."
            result["conditions"] = ["show_archive_contact", "show_segnatura", "no_download"]
        else:
            result["decision"] = DENY
            result["rule_code"] = "REQUEST_REQUIRED_BLOCKED"
            result["reason"] = "Documento su richiesta: nessun download automatico."
        _log_decision(record_id, digital_object_id, requested_action, result["decision"],
                      policy_id, result["rule_code"], result["reason"], result["conditions"])
        return result

    # Regola 10: AUTHORIZATION_REQUIRED
    if classification == AUTHORIZATION_REQUIRED:
        auth = _check_authorization(policy_id, record_id, requested_action) if policy_id else None
        if auth:
            result["decision"] = ALLOW_WITH_LIMITATIONS
            result["rule_code"] = "AUTHORIZATION_VALID"
            result["reason"] = f"Autorizzazione valida (protocollo: {auth.get('protocol', 'N/A')})."
            result["conditions"] = [auth.get("limitations", "")] if auth.get("limitations") else []
            result["authorization_id"] = auth["id"]
        else:
            result["decision"] = REQUIRE_AUTHORIZATION
            result["rule_code"] = "AUTHORIZATION_MISSING"
            result["reason"] = "Autorizzazione richiesta e non presente."
            result["authorization_required"] = True
            _add_to_review_queue(record_id, policy_id, "authorization_missing", "high")
        _log_decision(record_id, digital_object_id, requested_action, result["decision"],
                      policy_id, result["rule_code"], result["reason"],
                      result.get("conditions"), result.get("authorization_id"))
        return result

    # Fallback: negare per principio prudenziale
    result["decision"] = DENY
    result["rule_code"] = "FALLBACK_DENY"
    result["reason"] = "Classificazione non gestita: principio prudenziale."
    _log_decision(record_id, digital_object_id, requested_action, result["decision"],
                  policy_id, result["rule_code"], result["reason"])
    return result


def _add_to_review_queue(record_id, policy_id, reason, priority):
    conn = get_conn()
    conn.execute(
        """INSERT INTO compliance_review_queue
           (item_type, record_id, source_policy_id, reason, priority, status, created_at)
           VALUES ('compliance', ?, ?, ?, ?, 'pending', ?)""",
        (record_id, policy_id, reason, priority, _now()),
    )
    conn.commit()
    conn.close()


def get_review_queue(status="pending"):
    conn = get_conn()
    rows = conn.execute(
        "SELECT * FROM compliance_review_queue WHERE status = ? ORDER BY created_at DESC",
        (status,),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def resolve_review(item_id, decision, motivation, reviewed_by):
    conn = get_conn()
    conn.execute(
        """UPDATE compliance_review_queue
           SET status = 'resolved', decision = ?, motivation = ?,
               reviewed_by = ?, reviewed_at = ?
           WHERE id = ?""",
        (decision, motivation, reviewed_by, _now(), item_id),
    )
    conn.commit()
    conn.close()


def seed_source_policies():
    """Pre-popolare le policy per le fonti Croce Rossa."""
    from datetime import datetime, timedelta
    now = _now()
    review_due = (datetime.now() + timedelta(days=90)).isoformat()

    policies = [
        {
            "provider": "icrc_ww1",
            "domain": "grandeguerre.icrc.org",
            "source_name": "ICRC — Prisoners of the First World War (1914-1918)",
            "terms_url": "https://grandeguerre.icrc.org/en/File/DetailHelp",
            "privacy_url": "https://www.icrc.org/en/privacy-policy",
            "robots_url": "https://grandeguerre.icrc.org/robots.txt",
            "archive_regulation_url": "https://www.icrc.org/en/document/access-icrcs-agency-archives",
            "metadata_license": "unknown",
            "digital_object_license": "unknown",
            "commercial_use_allowed": 0,
            "automated_access_allowed": 0,
            "metadata_indexing_allowed": 1,
            "document_download_allowed": 0,
            "republication_allowed": 0,
            "attribution_required": 1,
            "required_credit_line": "© ICRC Archives — Prisoners of the First World War",
            "request_contact": "archives@icrc.org",
            "policy_status": "partially_verified",
            "notes": "Accesso libero per consultazione. Scansione schede online. "
                     "Nessuna indicazione di licenza aperta sui metadati o oggetti digitali. "
                     "Applicare METADATA_ONLY per default. Link diretto alle schede.",
        },
        {
            "provider": "cri_milano",
            "domain": "cri-mi.archimista.com",
            "source_name": "Archivio Storico Croce Rossa Italiana — Comitato di Milano",
            "terms_url": "https://cri-mi.archimista.com/",
            "privacy_url": None,
            "robots_url": "https://cri-mi.archimista.com/robots.txt",
            "archive_regulation_url": None,
            "metadata_license": "unknown",
            "digital_object_license": "unknown",
            "commercial_use_allowed": 0,
            "automated_access_allowed": 0,
            "metadata_indexing_allowed": 1,
            "document_download_allowed": 0,
            "republication_allowed": 0,
            "attribution_required": 1,
            "required_credit_line": "Archivio Storico CRI — Comitato di Milano",
            "request_contact": "archivio@crimi.it",
            "policy_status": "unknown",
            "notes": "Catalogo su piattaforma archimista. Metadati pubblici via web. "
                     "Documenti fisici su richiesta. Nessuna licenza esplicita. "
                     "Applicare METADATA_ONLY. Contiene dati personali (corrispondenza dispersi).",
        },
        {
            "provider": "cri_trieste",
            "domain": "archiviodistatotrieste.it",
            "source_name": "CRI Trieste — Ufficio Prigionieri, ricerche e servizi vari",
            "terms_url": "https://archiviodistatotrieste.it/",
            "privacy_url": None,
            "robots_url": "https://archiviodistatotrieste.it/robots.txt",
            "archive_regulation_url": None,
            "metadata_license": "unknown",
            "digital_object_license": "unknown",
            "commercial_use_allowed": 0,
            "automated_access_allowed": 0,
            "metadata_indexing_allowed": 1,
            "document_download_allowed": 0,
            "republication_allowed": 0,
            "attribution_required": 1,
            "required_credit_line": "Archivio di Stato di Trieste — Ufficio Prigionieri CRI",
            "request_contact": "archivio@archiviodistatotrieste.it",
            "policy_status": "unknown",
            "notes": "~34.000 schede ricerche persone scomparse 2GM. Parzialmente digitalizzato. "
                     "Contiene dati personali sensibili (familiari, corrispondenti). "
                     "Applicare METADATA_ONLY. Documenti su richiesta.",
        },
        {
            "provider": "lebi",
            "domain": "lessicobiograficoimi.it",
            "source_name": "LeBI — Lessico Biografico degli Internati Militari Italiani (ANRP)",
            "terms_url": "https://www.lessicobiograficoimi.it/frontend_prodimi.php/page/2/il-progetto",
            "privacy_url": "https://www.lessicobiograficoimi.it/frontend_prodimi.php/page/4/normativa-privacy",
            "robots_url": "https://www.lessicobiograficoimi.it/robots.txt",
            "archive_regulation_url": None,
            "metadata_license": "unknown",
            "digital_object_license": "unknown",
            "commercial_use_allowed": 0,
            "automated_access_allowed": 0,
            "metadata_indexing_allowed": 1,
            "document_download_allowed": 1,
            "republication_allowed": 0,
            "attribution_required": 1,
            "required_credit_line": "ANRP — LeBI, Lessico Biografico degli Internati Militari Italiani",
            "request_contact": "anrp@anrp.it",
            "policy_status": "partially_verified",
            "notes": "Banca dati pubblica ANRP con oltre 305K nominativi IMI. "
                     "Schede biografiche consultabili pubblicamente. PDF scaricabile. "
                     "Dati di persone decedute (1943-1945). "
                     "Indicizzazione metadati consentita. Download PDF pubblico. "
                     "Attribuzione obbligatoria. Uso commerciale non autorizzato.",
        },
    ]

    conn = get_conn()
    for p in policies:
        existing = conn.execute(
            "SELECT id FROM source_policies WHERE domain = ?", (p["domain"],)
        ).fetchone()
        if existing:
            conn.execute(
                """UPDATE source_policies SET
                   provider=?, source_name=?, terms_url=?, privacy_url=?, robots_url=?,
                   archive_regulation_url=?, metadata_license=?, digital_object_license=?,
                   commercial_use_allowed=?, automated_access_allowed=?,
                   metadata_indexing_allowed=?, document_download_allowed=?,
                   republication_allowed=?, attribution_required=?,
                   required_credit_line=?, request_contact=?, policy_status=?,
                   notes=?, updated_at=?
                 WHERE id=?""",
                (p["provider"], p["source_name"], p["terms_url"], p["privacy_url"],
                 p["robots_url"], p["archive_regulation_url"], p["metadata_license"],
                 p["digital_object_license"], p["commercial_use_allowed"],
                 p["automated_access_allowed"], p["metadata_indexing_allowed"],
                 p["document_download_allowed"], p["republication_allowed"],
                 p["attribution_required"], p["required_credit_line"],
                 p["request_contact"], p["policy_status"], p["notes"], now, existing["id"]),
            )
        else:
            conn.execute(
                """INSERT INTO source_policies
                   (provider, domain, source_name, terms_url, privacy_url, robots_url,
                    archive_regulation_url, metadata_license, digital_object_license,
                    commercial_use_allowed, automated_access_allowed,
                    metadata_indexing_allowed, document_download_allowed,
                    republication_allowed, attribution_required, required_credit_line,
                    request_contact, policy_status, notes, valid_from, review_due_at,
                    created_at, updated_at)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (p["provider"], p["domain"], p["source_name"], p["terms_url"],
                 p["privacy_url"], p["robots_url"], p["archive_regulation_url"],
                 p["metadata_license"], p["digital_object_license"],
                 p["commercial_use_allowed"], p["automated_access_allowed"],
                 p["metadata_indexing_allowed"], p["document_download_allowed"],
                 p["republication_allowed"], p["attribution_required"],
                 p["required_credit_line"], p["request_contact"], p["policy_status"],
                 p["notes"], now, review_due, now, now),
            )
    conn.commit()
    conn.close()

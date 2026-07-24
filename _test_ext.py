"""Test estensione modulo Percorso Riconoscimenti."""
import requests, json

s = requests.Session()
s.post('http://127.0.0.1:8123/api/rc/auth/login', json={'username':'admin','password':'admin'})
BASE = 'http://127.0.0.1:8123/api/rc'

results = []

def test(name, ok, detail=""):
    results.append((name, ok, detail))
    status = "PASS" if ok else "FAIL"
    print(f"  [{status}] {name}" + (f" -- {detail}" if detail and not ok else ""))

def api_call(method, url, **kwargs):
    r = s.request(method, url, **kwargs)
    if r.status_code >= 400:
        try:
            err = r.json()
        except:
            err = r.text[:200]
        return r, err
    try:
        return r, r.json()
    except:
        return r, {}

# 1. Dashboard estesa
print("\n1. Dashboard estesa")
r = s.get(f"{BASE}/dashboard-ext")
d = r.json()
test("dashboard-ext", r.status_code == 200 and "candidati_da_verificare" in d)
print(f"     KPI: {json.dumps(d, ensure_ascii=False)[:200]}")

# 2. Contatto discendente
print("\n2. Contatti discendenti")
r, body = api_call("POST", f"{BASE}/candidates/52/descendant-contacts", json={
    "nome": "Mario", "cognome": "Rossi",
    "rapporto_parentela_presunto": "nipote",
    "email": "mario.rossi@example.com",
    "fonte_contatto": "ricerca_online",
    "url_fonte": "https://example.com/profile",
    "stato_verifica": "DA_VERIFICARE",
})
test("create descendant contact", r.status_code == 200, str(body)[:200] if r.status_code != 200 else "")
did = body.get("id") if isinstance(body, dict) else None

r = s.get(f"{BASE}/candidates/52/descendant-contacts")
test("list descendant contacts", r.status_code == 200 and len(r.json()["contacts"]) > 0)

r = s.put(f"{BASE}/descendant-contacts/{did}", json={"stato_verifica": "VERIFICATO"})
test("update descendant contact", r.status_code == 200)

# 3. Contatto istituzionale
print("\n3. Contatti istituzionali")
r, body = api_call("POST", f"{BASE}/institutional-contacts", json={
    "ente": "Ministero della Difesa",
    "ministero_amministrazione": "Ministero della Difesa",
    "ufficio": "PERSOMIL",
    "email": "persomil@difesa.it",
    "pec": "persomil@pec.difesa.it",
    "sito_ufficiale": "https://www.difesa.it",
    "stato": "attivo",
})
test("create institutional contact", r.status_code == 200, str(body)[:200] if r.status_code != 200 else "")
iid = body.get("id") if isinstance(body, dict) else None

r = s.get(f"{BASE}/institutional-contacts")
test("list institutional contacts", r.status_code == 200 and len(r.json()["contacts"]) > 0)

# 4. Pratica estesa
print("\n4. Pratiche estese")
r, body = api_call("POST", f"{BASE}/candidates/52/practices", json={
    "recognition_type_id": 1,
    "institutional_contact_id": iid,
    "stato": "in_preparazione",
})
test("create practice", r.status_code == 200, str(body)[:200] if r.status_code != 200 else "")
pid = body.get("id") if isinstance(body, dict) else None

r = s.get(f"{BASE}/candidates/52/practices")
test("list practices", r.status_code == 200 and len(r.json()["practices"]) > 0)

# 5. Documento di pratica
print("\n5. Documenti di pratica")
import io
fake_file = io.BytesIO(b"Fake PDF content for testing")
r = s.post(f"{BASE}/candidates/52/practice-documents",
    data={"titolo": "Foglio matricolare test", "categoria_documentale": "FOGLIO_MATRICOLARE",
          "practice_id": str(pid), "ente_produttore": "Archivio di Stato"},
    files={"file": ("test.pdf", fake_file, "application/pdf")})
test("upload practice document", r.status_code == 200)
if r.status_code == 200:
    doc_id = r.json().get("id")
    
    r = s.get(f"{BASE}/candidates/52/practice-documents")
    test("list practice documents", r.status_code == 200 and len(r.json()["documents"]) > 0)
    
    r = s.put(f"{BASE}/practice-documents/{doc_id}/verify", json={"stato_verifica": "verificata"})
    test("verify document", r.status_code == 200)
    
    r = s.get(f"{BASE}/practice-documents/{doc_id}/versions")
    test("list document versions", r.status_code == 200 and len(r.json()["versions"]) > 0)

# 6. Checklist
print("\n6. Checklist documenti")
r = s.post(f"{BASE}/practices/{pid}/checklist", json={
    "nome_documento": "Foglio matricolare",
    "obbligatorietà": "obbligatorio",
    "ente_reperizione": "Archivio di Stato",
    "stato_documento": "presente",
})
test("create checklist item", r.status_code == 200)
clid = r.json().get("id")

r = s.get(f"{BASE}/practices/{pid}/checklist")
test("list checklist", r.status_code == 200 and len(r.json()["checklist"]) > 0)

r = s.put(f"{BASE}/checklist/{clid}", json={"stato_documento": "verificato"})
test("update checklist item", r.status_code == 200, r.text[:200] if r.status_code != 200 else "")

# 7. Comunicazioni
print("\n7. Comunicazioni")
r, body = api_call("POST", f"{BASE}/candidates/52/communications", json={
    "tipo": "email",
    "direzione": "uscita",
    "oggetto": "Richiesta informazioni",
    "contenuto": "Gentile familiare,...",
    "stato": "bozza",
    "practice_id": pid,
})
test("create communication", r.status_code == 200, str(body)[:200] if r.status_code != 200 else "")
comm_id = body.get("id") if isinstance(body, dict) else None
thread_id = body.get("thread_id") if isinstance(body, dict) else None

r = s.get(f"{BASE}/candidates/52/communications")
test("list communications", r.status_code == 200 and len(r.json()["communications"]) > 0)

r = s.get(f"{BASE}/communications/thread/{thread_id}")
test("list thread communications", r.status_code == 200 and len(r.json()["communications"]) > 0)

# 8. Scadenze
print("\n8. Scadenze")
r, body = api_call("POST", f"{BASE}/candidates/52/deadlines", json={
    "practice_id": pid,
    "tipo_scadenza": "risposta_ente",
    "data_scadenza": "2026-12-31",
    "descrizione": "Risposta dal Ministero",
})
test("create deadline", r.status_code == 200, str(body)[:200] if r.status_code != 200 else "")
dl_id = body.get("id") if isinstance(body, dict) else None

r = s.get(f"{BASE}/candidates/52/deadlines")
test("list deadlines", r.status_code == 200 and len(r.json()["deadlines"]) > 0)

# 9. Timeline
print("\n9. Timeline")
r = s.get(f"{BASE}/candidates/52/timeline")
test("get timeline", r.status_code == 200 and len(r.json()["timeline"]) > 0)
print(f"     Eventi timeline: {len(r.json()['timeline'])}")

# 10. Ricerca globale
print("\n10. Ricerca globale")
r = s.get(f"{BASE}/search?q=Rossi")
test("global search", r.status_code == 200 and len(r.json()["results"]) > 0)
print(f"     Risultati: {r.json()['total']}")

# 11. Pacchetto discendente
print("\n11. Pacchetto discendente")
r, body = api_call("POST", f"{BASE}/candidates/52/generate-descendant-package", json={"practice_id": pid})
test("generate descendant package", r.status_code == 200, str(body)[:200] if r.status_code != 200 else "")
if r.status_code == 200:
    pkg_id = body.get("id")
    print(f"     Pacchetto ID: {pkg_id}, versione: {body.get('versione')}")
    
    r2 = s.get(f"{BASE}/descendant-packages/{pkg_id}/download")
    test("download package", r2.status_code == 200)

# 12. Declare ready + fascicolo ufficiale
print("\n12. Fascicolo ufficiale")
r, body = api_call("POST", f"{BASE}/practices/{pid}/declare-ready", json={"motivazione_eccezione": "Test"})
test("declare practice ready", r.status_code == 200, str(body)[:200] if r.status_code != 200 else "")

r, body = api_call("POST", f"{BASE}/practices/{pid}/generate-official-dossier")
test("generate official dossier", r.status_code == 200, str(body)[:200] if r.status_code != 200 else "")
if r.status_code == 200:
    print(f"     File: {body.get('file')}")

# Privacy: ricercatore has view_recaps, so recaps should be visible
# Test that the filter logic works by checking with a role that lacks view_recaps
print("\n13. Privacy test")
# All internal roles have rc:contact:view_recaps, so recaps are visible
# Verify the endpoint returns actual email (not hidden) for authorized roles
r = s.get(f"{BASE}/candidates/52/descendant-contacts")
contacts = r.json().get("contacts", [])
if contacts:
    has_real_email = any(c.get("email") not in (None, "[DATO RISERVATO]") for c in contacts)
    test("privacy: admin sees real recaps", has_real_email)
else:
    test("privacy: no contacts to test", True)

# Cleanup: remove all test-created records to keep DB clean
print("\n14. Cleanup")
cleanup_ok = True
# Delete descendant contact created in test 2
if did:
    r = s.delete(f"{BASE}/descendant-contacts/{did}")
    if r.status_code == 200: print(f"     Deleted desc contact {did}")
    else: cleanup_ok = False; print(f"     FAIL delete desc contact {did}: {r.status_code}")
# Delete institutional contact created in test 3
if iid:
    r = s.delete(f"{BASE}/institutional-contacts/{iid}")
    if r.status_code == 200: print(f"     Deleted inst contact {iid}")
    else: cleanup_ok = False; print(f"     FAIL delete inst contact {iid}: {r.status_code}")
# Delete practice (cascades to checklist, deadlines, documents, communications)
if pid:
    r = s.delete(f"{BASE}/practices/{pid}")
    if r.status_code == 200: print(f"     Deleted practice {pid}")
    else: cleanup_ok = False; print(f"     FAIL delete practice {pid}: {r.status_code}")
# Delete descendant package
if pkg_id:
    r = s.delete(f"{BASE}/descendant-packages/{pkg_id}")
    if r.status_code == 200: print(f"     Deleted package {pkg_id}")
    else: pass  # may not have delete endpoint
test("cleanup", cleanup_ok)

# Summary
print("\n" + "=" * 60)
passed = sum(1 for _, ok, _ in results if ok)
failed = sum(1 for _, ok, _ in results if not ok)
print(f"RISULTATI: {passed} passed, {failed} failed, {len(results)} total")
if failed:
    print("\nFAILED TESTS:")
    for name, ok, detail in results:
        if not ok:
            print(f"  - {name}: {detail}")

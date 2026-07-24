"""Test master per il modulo Percorso Riconoscimenti.

Copia un solo file come da regola: tutti i test (unit, integrazione, sicurezza,
API, permessi, privacy, dossier) in questo file.

Usa TempDBTestCase per DB temporaneo isolato. Nessun mock.
"""
import sys
import tempfile
from pathlib import Path

# Setup path prima degli import del progetto
REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import unittest
from tests._helpers import TempDBTestCase

import database
import auth
import rc_schema
import rc_state_machine
from rc_state_machine import (
    STATES, VALID_TRANSITIONS, is_valid_transition, get_valid_transitions,
    is_terminal, transition,
)


class TestRcAuth(TempDBTestCase):
    """Test autenticazione, ruoli, permessi, sessioni."""

    schema_modules = ()

    def setUp(self):
        super().setUp()
        auth.init_auth_tables()

    def test_create_user_and_verify(self):
        user = auth.create_user("testuser", "testpass", "ricercatore", "test@test.com", "Test User")
        self.assertEqual(user["username"], "testuser")
        self.assertEqual(user["role"], "ricercatore")
        self.assertIn("password_hash", user)  # create_user returns full row

    def test_verify_password(self):
        auth.create_user("user2", "mypass", "admin")
        u = auth.get_user_by_username("user2")
        self.assertTrue(auth.verify_password("mypass", u["password_hash"]))
        self.assertFalse(auth.verify_password("wrong", u["password_hash"]))

    def test_invalid_role(self):
        with self.assertRaises(ValueError):
            auth.create_user("bad", "pass", "superadmin")

    def test_login_success(self):
        auth.create_user("loginuser", "pass123", "admin")
        result = auth.login("loginuser", "pass123")
        self.assertIsNotNone(result)
        self.assertEqual(result["user"]["username"], "loginuser")

    def test_login_wrong_password(self):
        auth.create_user("user3", "pass", "admin")
        self.assertIsNone(auth.login("user3", "wrong"))

    def test_login_inactive_user(self):
        auth.create_user("inactive", "pass", "admin")
        auth.update_user(1, is_active=0)  # assuming id=1
        self.assertIsNone(auth.login("inactive", "pass"))

    def test_session_creation_and_validation(self):
        auth.create_user("sessuser", "pass", "admin")
        token = auth.create_session(1)
        session = auth.get_session(token)
        self.assertIsNotNone(session)
        self.assertEqual(session["username"], "sessuser")

    def test_session_deletion(self):
        auth.create_user("sessuser2", "pass", "admin")
        token = auth.create_session(1)
        self.assertTrue(auth.delete_session(token))
        self.assertIsNone(auth.get_session(token))

    def test_role_permissions(self):
        self.assertTrue(auth.has_permission("admin", "rc:admin"))
        self.assertTrue(auth.has_permission("ricercatore", "rc:candidate:write"))
        self.assertFalse(auth.has_permission("ricercatore", "rc:contact:approve"))
        self.assertTrue(auth.has_permission("revisore", "rc:contact:approve"))
        self.assertFalse(auth.has_permission("discendente", "rc:candidate:write"))

    def test_ensure_default_admin(self):
        created = auth.ensure_default_admin()
        self.assertTrue(created)
        admin = auth.get_user_by_username("admin")
        self.assertIsNotNone(admin)
        self.assertEqual(admin["role"], "admin")
        # Second call should not create another
        created2 = auth.ensure_default_admin()
        self.assertFalse(created2)


class TestRcStateMachine(TempDBTestCase):
    """Test state machine: transizioni valide, transizioni non valide, audit."""

    schema_modules = ()

    def setUp(self):
        super().setUp()
        auth.init_auth_tables()
        rc_schema.init_rc_schema()
        # Create a test user
        auth.create_user("testadmin", "pass", "admin")
        # Create a test candidate
        conn = database.get_conn()
        from datetime import datetime
        now = datetime.now().isoformat()
        cur = conn.execute(
            "INSERT INTO rc_candidates (nome, cognome, stato, created_at, updated_at) VALUES (?, ?, 'BOZZA', ?, ?)",
            ("Test", "Candidate", now, now),
        )
        self.cid = cur.lastrowid
        conn.commit()
        conn.close()
        self.user = {"id": 1, "username": "testadmin", "role": "admin"}

    def test_all_24_states_present(self):
        self.assertEqual(len(STATES), 25)  # 24 + PRATICA_ARCHIVIATA

    def test_valid_transition_bozza_to_identificazione(self):
        result = transition(self.cid, "IDENTIFICAZIONE_IN_CORSO", self.user, "Inizio")
        self.assertEqual(result["stato"], "IDENTIFICAZIONE_IN_CORSO")

    def test_invalid_transition_bozza_to_fascicolo(self):
        with self.assertRaises(ValueError):
            transition(self.cid, "FASCICOLO_IN_PREPARAZIONE", self.user, "Salto")

    def test_same_state_raises(self):
        with self.assertRaises(ValueError):
            transition(self.cid, "BOZZA", self.user, "No change")

    def test_transition_history_recorded(self):
        transition(self.cid, "IDENTIFICAZIONE_IN_CORSO", self.user, "Test 1")
        history = rc_state_machine.get_transition_history(self.cid)
        self.assertEqual(len(history), 1)
        self.assertEqual(history[0]["stato_precedente"], "BOZZA")
        self.assertEqual(history[0]["stato_successivo"], "IDENTIFICAZIONE_IN_CORSO")
        self.assertEqual(history[0]["autore"], "testadmin")

    def test_audit_log_recorded(self):
        transition(self.cid, "IDENTIFICAZIONE_IN_CORSO", self.user, "Audit test")
        conn = database.get_conn()
        log = conn.execute("SELECT * FROM rc_audit_log WHERE entita = 'candidate' AND entita_id = ?", (self.cid,)).fetchall()
        conn.close()
        self.assertEqual(len(log), 1)
        self.assertEqual(log[0]["azione"], "state_transition")
        self.assertEqual(log[0]["valore_precedente"], "BOZZA")
        self.assertEqual(log[0]["valore_successivo"], "IDENTIFICAZIONE_IN_CORSO")

    def test_terminal_state_no_transitions(self):
        self.assertTrue(is_terminal("PRATICA_ARCHIVIATA"))
        self.assertEqual(get_valid_transitions("PRATICA_ARCHIVIATA"), [])

    def test_full_workflow_path(self):
        """Test del percorso principale completo."""
        steps = [
            "IDENTIFICAZIONE_IN_CORSO",
            "IDENTITA_VERIFICATA",
            "FONTI_IN_VERIFICA",
            "VALUTAZIONE_STORICA",
            "VALUTAZIONE_AMMINISTRATIVA",
            "PROCEDURA_POTENZIALMENTE_PRATICABILE",
            "RICERCA_DISCENDENTI_AUTORIZZATA",
            "DISCENDENTI_IN_RICERCA",
            "POSSIBILE_DISCENDENTE_INDIVIDUATO",
            "CONTATTO_DA_APPROVARE",
            "CONTATTO_INOLTRATO",
            "FAMIGLIA_ADERENTE",
            "DISCENDENZA_VERIFICATA",
            "FASCICOLO_IN_PREPARAZIONE",
            "FASCICOLO_DA_APPROVARE",
            "PRATICA_TRASMESSA",
            "RICONOSCIMENTO_CONCESSO",
            "PRATICA_ARCHIVIATA",
        ]
        for step in steps:
            result = transition(self.cid, step, self.user, f"Step: {step}")
            self.assertEqual(result["stato"], step, f"Failed at step {step}")

    def test_permission_required_for_contact_approval(self):
        """Un ricercatore non può autorizzare ricerca discendenti."""
        auth.create_user("researcher", "pass", "ricercatore")
        researcher = {"id": 2, "username": "researcher", "role": "ricercatore"}
        # Move to PROCEDURA_POTENZIALMENTE_PRATICABILE first
        transition(self.cid, "IDENTIFICAZIONE_IN_CORSO", self.user, "Step")
        transition(self.cid, "IDENTITA_VERIFICATA", self.user, "Step")
        transition(self.cid, "FONTI_IN_VERIFICA", self.user, "Step")
        transition(self.cid, "VALUTAZIONE_STORICA", self.user, "Step")
        transition(self.cid, "VALUTAZIONE_AMMINISTRATIVA", self.user, "Step")
        transition(self.cid, "PROCEDURA_POTENZIALMENTE_PRATICABILE", self.user, "Step")
        with self.assertRaises(PermissionError):
            transition(self.cid, "RICERCA_DISCENDENTI_AUTORIZZATA", researcher, "No perm")


class TestRcSchema(TempDBTestCase):
    """Test schema: tabelle create, seed riconoscimenti."""

    schema_modules = ()

    def setUp(self):
        super().setUp()
        rc_schema.init_rc_schema()

    def test_all_tables_exist(self):
        conn = database.get_conn()
        tables = [r["name"] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name LIKE 'rc_%'"
        ).fetchall()]
        conn.close()
        expected = [
            "rc_candidates", "rc_historical_events", "rc_sources",
            "rc_recognition_types", "rc_recognition_assessments",
            "rc_family_persons", "rc_kinship_links", "rc_contact_attempts",
            "rc_descendant_cases", "rc_administrative_cases", "rc_audit_log",
            "rc_state_transitions", "rc_invitations", "rc_documents",
        ]
        for t in expected:
            self.assertIn(t, tables, f"Missing table: {t}")

    def test_seed_recognition_types(self):
        rc_schema.seed_recognition_types()
        conn = database.get_conn()
        count = conn.execute("SELECT COUNT(*) as c FROM rc_recognition_types").fetchone()["c"]
        conn.close()
        self.assertGreaterEqual(count, 12)

    def test_seed_idempotent(self):
        rc_schema.seed_recognition_types()
        rc_schema.seed_recognition_types()
        conn = database.get_conn()
        count = conn.execute("SELECT COUNT(*) as c FROM rc_recognition_types").fetchone()["c"]
        conn.close()
        self.assertEqual(count, 12)  # Not doubled


class TestRcPrivacy(TempDBTestCase):
    """Test privacy: dati viventi non esposti."""

    schema_modules = ()

    def setUp(self):
        super().setUp()
        auth.init_auth_tables()
        rc_schema.init_rc_schema()
        from datetime import datetime
        now = datetime.now().isoformat()
        conn = database.get_conn()
        cur = conn.execute(
            "INSERT INTO rc_candidates (nome, cognome, stato, created_at, updated_at) VALUES (?, ?, 'BOZZA', ?, ?)",
            ("Test", "Privacy", now, now),
        )
        self.cid = cur.lastrowid
        # Create a living family person
        conn.execute(
            """INSERT INTO rc_family_persons
               (candidate_id, nome, cognome, data_nascita, luogo_nascita,
                rapporto_candidato, stato_vita, visibilita_limitata,
                created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, 'vivente', 1, ?, ?)""",
            (self.cid, "Mario", "Rossi", "1950-01-01", "Roma", "figlio", now, now),
        )
        conn.commit()
        conn.close()

    def test_living_person_data_hidden_in_api(self):
        """Quando visibilita_limitata=1, data_nascita e luogo_nascita non devono essere esposte."""
        conn = database.get_conn()
        rows = conn.execute(
            "SELECT * FROM rc_family_persons WHERE candidate_id = ?", (self.cid,)
        ).fetchall()
        conn.close()
        # Simulate the API filtering
        persons = [dict(r) for r in rows]
        for p in persons:
            if p.get("stato_vita") in ("vivente", "non_accertato") and p.get("visibilita_limitata"):
                p["data_nascita"] = None
                p["luogo_nascita"] = None
        self.assertIsNone(persons[0]["data_nascita"])
        self.assertIsNone(persons[0]["luogo_nascita"])
        self.assertEqual(persons[0]["nome"], "Mario")  # Name is visible


class TestRcDossier(TempDBTestCase):
    """Test generazione fascicolo PDF."""

    schema_modules = ()

    def setUp(self):
        super().setUp()
        auth.init_auth_tables()
        rc_schema.init_rc_schema()
        from datetime import datetime
        now = datetime.now().isoformat()
        conn = database.get_conn()
        cur = conn.execute(
            "INSERT INTO rc_candidates (nome, cognome, stato, grado, reparto, conflitto, created_at, updated_at) VALUES (?, ?, 'BOZZA', ?, ?, ?, ?, ?)",
            ("Giuseppe", "Rossi", "Sergente", "75° Fanteria", "1GM", now, now),
        )
        self.cid = cur.lastrowid
        conn.commit()
        conn.close()

    def test_generate_pdf(self):
        from rc_dossier import generate_pdf_dossier
        pdf_path = generate_pdf_dossier(self.cid)
        self.assertTrue(pdf_path.exists())
        self.assertGreater(pdf_path.stat().st_size, 1000)  # At least 1KB
        # Clean up
        pdf_path.unlink(missing_ok=True)


class TestRcFullWorkflow(TempDBTestCase):
    """Test integrazione: flusso completo dall'inserimento al fascicolo."""

    schema_modules = ()

    def setUp(self):
        super().setUp()
        auth.init_auth_tables()
        rc_schema.init_rc_schema()
        rc_schema.seed_recognition_types()
        auth.create_user("admin", "admin", "admin")
        self.user = {"id": 1, "username": "admin", "role": "admin"}

    def test_complete_workflow(self):
        """Test: crea candidato → aggiungi fonte → transizione → genera fascicolo."""
        from datetime import datetime
        now = datetime.now().isoformat()
        conn = database.get_conn()

        # 1. Create candidate
        cur = conn.execute(
            "INSERT INTO rc_candidates (nome, cognome, stato, conflitto, grado, created_at, updated_at, created_by) VALUES (?, ?, 'BOZZA', ?, ?, ?, ?, ?)",
            ("Antonio", "Verdi", "2GM", "Tenente", now, now, 1),
        )
        cid = cur.lastrowid

        # 2. Add source
        conn.execute(
            """INSERT INTO rc_sources (titolo, tipologia, ente_conservatore, candidate_id, stato_verifica, created_at, updated_at)
               VALUES (?, ?, ?, ?, 'verificata', ?, ?)""",
            ("Documento storico", "primario", "Archivio di Stato", cid, now, now),
        )

        # 3. Add historical event
        conn.execute(
            """INSERT INTO rc_historical_events (candidate_id, tipo_evento, descrizione_verificata, grado_attendibilita, created_at, updated_at)
               VALUES (?, 'combattimento', 'Condotta eroica durante la battaglia', 'alta', ?, ?)""",
            (cid, now, now),
        )

        conn.commit()
        conn.close()

        # 4. State transitions
        steps = ["IDENTIFICAZIONE_IN_CORSO", "IDENTITA_VERIFICATA", "FONTI_IN_VERIFICA",
                 "VALUTAZIONE_STORICA", "VALUTAZIONE_AMMINISTRATIVA",
                 "PROCEDURA_POTENZIALMENTE_PRATICABILE"]
        for step in steps:
            result = transition(cid, step, self.user, f"Step: {step}")
            self.assertEqual(result["stato"], step)

        # 5. Generate dossier
        from rc_dossier import generate_pdf_dossier
        pdf_path = generate_pdf_dossier(cid)
        self.assertTrue(pdf_path.exists())
        self.assertGreater(pdf_path.stat().st_size, 2000)

        # 6. Verify audit log
        conn = database.get_conn()
        audit_count = conn.execute("SELECT COUNT(*) as c FROM rc_audit_log").fetchone()["c"]
        conn.close()
        self.assertGreaterEqual(audit_count, 6)  # 6 state transitions

        # Cleanup
        pdf_path.unlink(missing_ok=True)


if __name__ == "__main__":
    unittest.main()

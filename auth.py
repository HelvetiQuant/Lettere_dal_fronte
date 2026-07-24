"""Modulo di autenticazione session-based per il Percorso Riconoscimenti.

Implementa:
- 6 ruoli (admin, ricercatore, revisore, genealogista, operatore, discendente)
- Password hash con bcrypt
- Sessioni server-side in SQLite con token casuale
- Middleware FastAPI: get_current_user, require_role
- Endpoint: login, logout, me

Nessuna dipendenza esterna oltre a bcrypt.
"""
import os
import secrets
import hashlib
from datetime import datetime, timedelta
from typing import Optional

import bcrypt
from fastapi import Request, HTTPException, Depends
from fastapi.responses import JSONResponse

from database import get_conn

# ─── Configurazione ──────────────────────────────────────────────────────────

RC_SECRET_KEY = os.environ.get("RC_SECRET_KEY", "rc-dev-secret-change-in-prod")
RC_SESSION_TTL_HOURS = int(os.environ.get("RC_SESSION_TTL_HOURS", "24"))
RC_COOKIE_NAME = "rc_session"

# ─── Ruoli ───────────────────────────────────────────────────────────────────

ROLES = [
    "admin",
    "ricercatore",
    "revisore",
    "genealogista",
    "operatore",
    "discendente",
]

# Permessi per ruolo
ROLE_PERMISSIONS = {
    "admin": [
        "rc:admin", "rc:candidate:read", "rc:candidate:write",
        "rc:source:read", "rc:source:write",
        "rc:assessment:read", "rc:assessment:write",
        "rc:genealogy:read", "rc:genealogy:write",
        "rc:contact:read", "rc:contact:write", "rc:contact:approve",
        "rc:case:read", "rc:case:write",
        "rc:recognition:read", "rc:recognition:write",
        "rc:audit:read",
        # Permessi estensione
        "rc:contact:view_recaps", "rc:contact:edit_recaps", "rc:contact:export_recaps",
        "rc:doc:view_identity", "rc:doc:view_genealogy_proofs",
        "rc:doc:upload", "rc:doc:verify", "rc:doc:delete",
        "rc:comm:approve", "rc:comm:register_send",
        "rc:pkg:generate_descendant", "rc:pkg:generate_official",
        "rc:practice:declare_ready", "rc:practice:register_outcome",
        "rc:practice:archive", "rc:practice:delete",
        "rc:institutional:read", "rc:institutional:write",
        "rc:checklist:read", "rc:checklist:write",
        "rc:search:global",
    ],
    "ricercatore": [
        "rc:candidate:read", "rc:candidate:write",
        "rc:source:read", "rc:source:write",
        "rc:assessment:read",
        "rc:genealogy:read",
        "rc:contact:read",
        "rc:case:read",
        "rc:recognition:read",
        # Estensione
        "rc:contact:view_recaps",
        "rc:doc:upload", "rc:doc:view_genealogy_proofs",
        "rc:institutional:read", "rc:checklist:read",
        "rc:search:global",
    ],
    "revisore": [
        "rc:candidate:read",
        "rc:source:read",
        "rc:assessment:read", "rc:assessment:write",
        "rc:contact:read", "rc:contact:approve",
        "rc:case:read",
        "rc:recognition:read",
        # Estensione
        "rc:contact:view_recaps",
        "rc:doc:verify",
        "rc:comm:approve", "rc:comm:register_send",
        "rc:pkg:generate_official",
        "rc:practice:declare_ready", "rc:practice:register_outcome",
        "rc:practice:archive",
        "rc:institutional:read", "rc:checklist:read",
        "rc:search:global",
    ],
    "genealogista": [
        "rc:candidate:read",
        "rc:source:read",
        "rc:genealogy:read", "rc:genealogy:write",
        "rc:contact:read",
        "rc:case:read",
        # Estensione
        "rc:contact:view_recaps",
        "rc:doc:view_genealogy_proofs", "rc:doc:upload",
        "rc:institutional:read", "rc:checklist:read",
        "rc:search:global",
    ],
    "operatore": [
        "rc:candidate:read",
        "rc:source:read",
        "rc:assessment:read",
        "rc:genealogy:read",
        "rc:contact:read", "rc:contact:write",
        "rc:case:read", "rc:case:write",
        "rc:recognition:read",
        # Estensione
        "rc:contact:view_recaps", "rc:contact:edit_recaps",
        "rc:doc:upload",
        "rc:institutional:read", "rc:institutional:write",
        "rc:checklist:read", "rc:checklist:write",
        "rc:search:global",
    ],
    "discendente": [
        "rc:descendant:view",
    ],
}


def has_permission(role: str, permission: str) -> bool:
    perms = ROLE_PERMISSIONS.get(role, [])
    return permission in perms


# ─── Tabelle auth ─────────────────────────────────────────────────────────────

def init_auth_tables():
    conn = get_conn()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS rc_users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            role TEXT NOT NULL DEFAULT 'ricercatore',
            email TEXT,
            full_name TEXT,
            is_active INTEGER DEFAULT 1,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS rc_sessions (
            token TEXT PRIMARY KEY,
            user_id INTEGER NOT NULL,
            created_at TEXT NOT NULL,
            expires_at TEXT NOT NULL,
            ip_address TEXT,
            user_agent TEXT,
            FOREIGN KEY (user_id) REFERENCES rc_users(id)
        );

        CREATE INDEX IF NOT EXISTS idx_rc_sessions_user ON rc_sessions(user_id);
        CREATE INDEX IF NOT EXISTS idx_rc_sessions_expires ON rc_sessions(expires_at);
        CREATE INDEX IF NOT EXISTS idx_rc_users_role ON rc_users(role);
    """)
    conn.commit()
    conn.close()


# ─── Password ─────────────────────────────────────────────────────────────────

def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode("utf-8"), hashed.encode("utf-8"))
    except (ValueError, TypeError):
        return False


# ─── User management ──────────────────────────────────────────────────────────

def create_user(username: str, password: str, role: str, email: str = None,
                full_name: str = None) -> dict:
    if role not in ROLES:
        raise ValueError(f"Ruolo non valido: {role}. Ammessi: {', '.join(ROLES)}")
    conn = get_conn()
    now = datetime.now().isoformat()
    try:
        cur = conn.execute(
            """INSERT INTO rc_users (username, password_hash, role, email, full_name,
               is_active, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, 1, ?, ?)""",
            (username, hash_password(password), role, email, full_name, now, now),
        )
        uid = cur.lastrowid
        conn.commit()
        user = get_user_by_id(uid)
        conn.close()
        return user
    except Exception as e:
        conn.close()
        raise ValueError(f"Errore creazione utente: {e}")


def get_user_by_id(uid: int) -> Optional[dict]:
    conn = get_conn()
    row = conn.execute("SELECT * FROM rc_users WHERE id = ?", (uid,)).fetchone()
    conn.close()
    return dict(row) if row else None


def get_user_by_username(username: str) -> Optional[dict]:
    conn = get_conn()
    row = conn.execute("SELECT * FROM rc_users WHERE username = ?", (username,)).fetchone()
    conn.close()
    return dict(row) if row else None


def list_users() -> list:
    conn = get_conn()
    rows = conn.execute(
        "SELECT id, username, role, email, full_name, is_active, created_at FROM rc_users ORDER BY id"
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def update_user(uid: int, **fields) -> bool:
    allowed = {"role", "email", "full_name", "is_active"}
    updates = {k: v for k, v in fields.items() if k in allowed}
    if not updates:
        return False
    conn = get_conn()
    now = datetime.now().isoformat()
    updates["updated_at"] = now
    set_clause = ", ".join(f"{k} = ?" for k in updates)
    params = list(updates.values()) + [uid]
    conn.execute(f"UPDATE rc_users SET {set_clause} WHERE id = ?", params)
    conn.commit()
    conn.close()
    return True


def delete_user(uid: int) -> bool:
    conn = get_conn()
    cur = conn.execute("DELETE FROM rc_users WHERE id = ?", (uid,))
    conn.execute("DELETE FROM rc_sessions WHERE user_id = ?", (uid,))
    conn.commit()
    conn.close()
    return cur.rowcount > 0


# ─── Sessioni ─────────────────────────────────────────────────────────────────

def create_session(user_id: int, ip: str = None, ua: str = None) -> str:
    token = secrets.token_urlsafe(32)
    now = datetime.now()
    expires = now + timedelta(hours=RC_SESSION_TTL_HOURS)
    conn = get_conn()
    conn.execute(
        """INSERT INTO rc_sessions (token, user_id, created_at, expires_at, ip_address, user_agent)
           VALUES (?, ?, ?, ?, ?, ?)""",
        (token, user_id, now.isoformat(), expires.isoformat(), ip, ua),
    )
    conn.commit()
    conn.close()
    return token


def get_session(token: str) -> Optional[dict]:
    if not token:
        return None
    conn = get_conn()
    row = conn.execute(
        """SELECT s.*, u.username, u.role, u.email, u.full_name, u.is_active
           FROM rc_sessions s
           JOIN rc_users u ON s.user_id = u.id
           WHERE s.token = ? AND s.expires_at > ? AND u.is_active = 1""",
        (token, datetime.now().isoformat()),
    ).fetchone()
    conn.close()
    return dict(row) if row else None


def delete_session(token: str) -> bool:
    conn = get_conn()
    cur = conn.execute("DELETE FROM rc_sessions WHERE token = ?", (token,))
    conn.commit()
    conn.close()
    return cur.rowcount > 0


def cleanup_expired_sessions():
    conn = get_conn()
    conn.execute("DELETE FROM rc_sessions WHERE expires_at < ?", (datetime.now().isoformat(),))
    conn.commit()
    conn.close()


# ─── FastAPI dependencies ─────────────────────────────────────────────────────

def get_current_user(request: Request) -> Optional[dict]:
    token = request.cookies.get(RC_COOKIE_NAME)
    if not token:
        auth_header = request.headers.get("Authorization", "")
        if auth_header.startswith("Bearer "):
            token = auth_header[7:]
    if not token:
        return None
    session = get_session(token)
    if not session:
        return None
    return {
        "id": session["user_id"],
        "username": session["username"],
        "role": session["role"],
        "email": session["email"],
        "full_name": session["full_name"],
    }


def require_auth(request: Request) -> dict:
    user = get_current_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="Autenticazione richiesta")
    return user


def require_role(*roles: str):
    def dependency(request: Request) -> dict:
        user = require_auth(request)
        if user["role"] not in roles:
            raise HTTPException(status_code=403, detail="Permessi insufficienti")
        return user
    return dependency


def require_permission(permission: str):
    def dependency(request: Request) -> dict:
        user = require_auth(request)
        if not has_permission(user["role"], permission):
            raise HTTPException(status_code=403, detail="Permesso insufficiente")
        return user
    return dependency


# ─── Login/Logout helpers ─────────────────────────────────────────────────────

def login(username: str, password: str, ip: str = None, ua: str = None) -> Optional[dict]:
    user = get_user_by_username(username)
    if not user or not user.get("is_active"):
        return None
    if not verify_password(password, user["password_hash"]):
        return None
    token = create_session(user["id"], ip=ip, ua=ua)
    return {
        "token": token,
        "user": {
            "id": user["id"],
            "username": user["username"],
            "role": user["role"],
            "email": user.get("email"),
            "full_name": user.get("full_name"),
        },
    }


def logout(token: str) -> bool:
    return delete_session(token)


def ensure_default_admin():
    """Crea un admin di default se non esistono utenti."""
    conn = get_conn()
    count = conn.execute("SELECT COUNT(*) as c FROM rc_users").fetchone()["c"]
    conn.close()
    if count == 0:
        create_user(
            username="admin",
            password="admin",
            role="admin",
            email="admin@vocidalfronte.local",
            full_name="Amministratore",
        )
        return True
    return False

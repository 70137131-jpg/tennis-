"""Private academy accounts, scrypt passwords and revocable cookie sessions."""

import hashlib
import hmac
import secrets
import sqlite3
import threading
import time
from contextlib import contextmanager
from pathlib import Path

PASSWORD_SLOTS = threading.BoundedSemaphore(2)
SESSION_SECONDS = 8 * 3600
COOKIE = "courtside-session"


def password_hash(password, salt=None):
    if not 15 <= len(password) <= 128:
        raise ValueError("Use a passphrase of 15 to 128 characters")
    salt = salt or secrets.token_hex(16)
    with PASSWORD_SLOTS:
        digest = hashlib.scrypt(
            password.encode(), salt=bytes.fromhex(salt), n=2**17, r=8, p=1, maxmem=256 * 1024**2
        ).hex()
    return f"scrypt$131072$8$1${salt}${digest}"


def password_matches(password, encoded):
    if not 15 <= len(password) <= 128:
        return False
    parts = encoded.split("$")
    return hmac.compare_digest(password_hash(password, parts[4]), encoded)


def digest_token(token):
    return hashlib.sha256(token.encode()).hexdigest()


class Accounts:
    def __init__(self, root: Path, personal=False):
        self.personal = personal
        self.root = root.resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self.path = self.root / "accounts.sqlite3"
        with self.connection() as db:
            db.executescript("""
                PRAGMA journal_mode=WAL;
                CREATE TABLE IF NOT EXISTS academies(id TEXT PRIMARY KEY, name TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS users(id TEXT PRIMARY KEY, academy_id TEXT NOT NULL REFERENCES academies(id),
                    email TEXT NOT NULL UNIQUE, name TEXT NOT NULL, role TEXT NOT NULL CHECK(role IN ('admin','coach','player')),
                    password_hash TEXT NOT NULL, disabled INTEGER NOT NULL DEFAULT 0);
                CREATE TABLE IF NOT EXISTS auth_sessions(token_hash TEXT PRIMARY KEY, user_id TEXT NOT NULL REFERENCES users(id),
                    csrf TEXT NOT NULL, expires REAL NOT NULL);
                CREATE TABLE IF NOT EXISTS audit(id INTEGER PRIMARY KEY AUTOINCREMENT, academy_id TEXT NOT NULL,
                    actor_id TEXT NOT NULL, action TEXT NOT NULL, target_id TEXT NOT NULL, created REAL NOT NULL);
                CREATE TABLE IF NOT EXISTS google_identities(
                    sub TEXT PRIMARY KEY, user_id TEXT NOT NULL UNIQUE REFERENCES users(id));
                CREATE TABLE IF NOT EXISTS google_flows(
                    state_hash TEXT PRIMARY KEY, verifier TEXT NOT NULL, link_user_id TEXT,
                    expires REAL NOT NULL);
            """)
        self.dummy = password_hash(secrets.token_urlsafe(30))

    @contextmanager
    def connection(self):
        with sqlite3.connect(self.path, timeout=15) as db:
            db.row_factory = sqlite3.Row
            db.execute("PRAGMA foreign_keys=ON")
            yield db

    def has_users(self):
        with self.connection() as db:
            return bool(db.execute("SELECT 1 FROM users LIMIT 1").fetchone())

    def create_user(self, academy_id, email, name, role, password, academy_name=None, bootstrap=False):
        if role not in {"admin", "coach", "player"} or not name.strip() or "@" not in email:
            raise ValueError("A valid email, name and role are required")
        encoded = password_hash(password)
        uid = secrets.token_hex(16)
        with self.connection() as db:
            db.execute("BEGIN IMMEDIATE")
            if bootstrap and db.execute("SELECT 1 FROM users LIMIT 1").fetchone():
                raise ValueError("Initial setup is already complete")
            if academy_name:
                db.execute("INSERT INTO academies VALUES(?,?)", (academy_id, academy_name))
            try:
                db.execute(
                    "INSERT INTO users VALUES(?,?,?,?,?,?,0)",
                    (uid, academy_id, email.strip().casefold(), name.strip(), role, encoded),
                )
            except sqlite3.IntegrityError as exc:
                raise ValueError("This account cannot be created. Check its email and academy.") from exc
        return self.user(uid)

    def user(self, uid):
        with self.connection() as db:
            row = db.execute(
                "SELECT id,academy_id,email,name,role,disabled FROM users WHERE id=?", (uid,)
            ).fetchone()
            return dict(row) if row else None

    def login(self, email, password):
        with self.connection() as db:
            row = db.execute("SELECT * FROM users WHERE email=?", (email.strip().casefold(),)).fetchone()
        matches = password_matches(password, row["password_hash"] if row and row["password_hash"] else self.dummy)
        if not matches or not row or row["disabled"]:
            raise ValueError("Email or passphrase is incorrect")
        token, csrf = self.new_session(row["id"])
        self.audit(self.user(row["id"]), "login", row["id"])
        return token, csrf, self.user(row["id"])

    def new_session(self, user_id):
        token, csrf = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
        with self.connection() as db:
            db.execute("DELETE FROM auth_sessions WHERE expires<?", (time.time(),))
            db.execute(
                "INSERT INTO auth_sessions VALUES(?,?,?,?)",
                (digest_token(token), user_id, csrf, time.time() + SESSION_SECONDS),
            )
            # Bound sessions per user; retain the most recent five.
            db.execute(
                "DELETE FROM auth_sessions WHERE user_id=? AND token_hash NOT IN (SELECT token_hash FROM auth_sessions WHERE user_id=? ORDER BY expires DESC LIMIT 5)",
                (user_id, user_id),
            )
        return token, csrf

    def resolve(self, token):
        if not token or len(token) > 128:
            return None
        with self.connection() as db:
            row = db.execute(
                "SELECT u.id,u.academy_id,u.email,u.name,u.role,u.disabled,s.csrf,s.expires FROM auth_sessions s JOIN users u ON u.id=s.user_id WHERE s.token_hash=? AND s.expires>? AND u.disabled=0",
                (digest_token(token), time.time()),
            ).fetchone()
        return dict(row) if row else None

    def logout(self, token):
        with self.connection() as db:
            db.execute("DELETE FROM auth_sessions WHERE token_hash=?", (digest_token(token),))

    def workspaces(self, user):
        with self.connection() as db:
            rows = db.execute(
                "SELECT id,name,role FROM users WHERE academy_id=? AND disabled=0 ORDER BY name",
                (user["academy_id"],),
            ).fetchall()
        return [dict(r) for r in rows if r["id"] == user["id"] or (
            not self.personal and user["role"] in {"admin", "coach"}
        )]

    def workspace(self, user, uid):
        target = self.user(uid)
        if (
            not target
            or target["disabled"]
            or target["academy_id"] != user["academy_id"]
            or (uid != user["id"] and (self.personal or user["role"] == "player"))
        ):
            raise ValueError("Workspace not found")
        return self.root / "academies" / target["academy_id"] / "workspaces" / uid

    def disable(self, actor, uid):
        target = self.user(uid)
        if not target or target["academy_id"] != actor["academy_id"] or uid == actor["id"]:
            raise ValueError("Account cannot be disabled")
        with self.connection() as db:
            db.execute("UPDATE users SET disabled=1 WHERE id=?", (uid,))
            db.execute("DELETE FROM auth_sessions WHERE user_id=?", (uid,))
        self.audit(actor, "account_disabled", uid)

    def audit(self, actor, action, target=""):
        with self.connection() as db:
            db.execute(
                "INSERT INTO audit(academy_id,actor_id,action,target_id,created) VALUES(?,?,?,?,?)",
                (actor["academy_id"], actor["id"], action[:60], target[:80], time.time()),
            )
            db.execute("DELETE FROM audit WHERE created<?", (time.time() - 90 * 86400,))
            db.execute(
                "DELETE FROM audit WHERE id NOT IN (SELECT id FROM audit ORDER BY id DESC LIMIT 10000)"
            )

    def audit_log(self, user):
        with self.connection() as db:
            return [
                dict(r)
                for r in db.execute(
                    "SELECT actor_id,action,target_id,created FROM audit WHERE academy_id=? ORDER BY id DESC LIMIT 200",
                    (user["academy_id"],),
                )
            ]

    def create_google_flow(self, link_user_id=None):
        state, verifier = secrets.token_urlsafe(32), secrets.token_urlsafe(48)
        with self.connection() as db:
            db.execute("DELETE FROM google_flows WHERE expires<?", (time.time(),))
            db.execute("INSERT INTO google_flows VALUES(?,?,?,?)", (
                digest_token(state), verifier, link_user_id, time.time() + 300,
            ))
        return state, verifier

    def consume_google_flow(self, state):
        with self.connection() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT verifier,link_user_id,expires FROM google_flows WHERE state_hash=?", (
                digest_token(state),
            )).fetchone()
            db.execute("DELETE FROM google_flows WHERE state_hash=?", (digest_token(state),))
        return dict(row) if row and row["expires"] > time.time() else None

    def google_user(self, sub, email, name, link_user_id=None):
        if not isinstance(sub, str) or not 1 <= len(sub) <= 255:
            raise ValueError("Google identity is invalid")
        email = email.strip().casefold()
        if not 3 <= len(email) <= 120 or "@" not in email:
            raise ValueError("Google email is invalid")
        name = name.strip()[:80] or email.split("@", 1)[0]
        with self.connection() as db:
            db.execute("BEGIN IMMEDIATE")
            existing = db.execute("SELECT user_id FROM google_identities WHERE sub=?", (sub,)).fetchone()
            if existing:
                if link_user_id and existing[0] != link_user_id:
                    raise ValueError("This Google account is already linked to another user")
                uid = existing[0]
            elif link_user_id:
                owner = db.execute("SELECT id FROM users WHERE id=? AND disabled=0", (link_user_id,)).fetchone()
                if not owner:
                    raise ValueError("Sign in again before linking Google")
                other = db.execute("SELECT 1 FROM google_identities WHERE user_id=?", (link_user_id,)).fetchone()
                if other:
                    raise ValueError("This account already has a linked Google identity")
                uid = link_user_id
                db.execute("INSERT INTO google_identities VALUES(?,?)", (sub, uid))
            else:
                # Never merge identities by email: only a signed-in user can link accounts.
                if db.execute("SELECT 1 FROM users WHERE email=?", (email,)).fetchone():
                    raise ValueError("An account with this email exists. Sign in and link Google from your account menu.")
                uid = secrets.token_hex(16)
                db.execute("INSERT INTO academies VALUES(?,?)", (uid, "Personal"))
                db.execute("INSERT INTO users VALUES(?,?,?,?,?,?,0)", (
                    uid, uid, email, name, "player", "",
                ))
                db.execute("INSERT INTO google_identities VALUES(?,?)", (sub, uid))
        user = self.user(uid)
        if not user or user["disabled"]:
            raise ValueError("This account is unavailable")
        return user

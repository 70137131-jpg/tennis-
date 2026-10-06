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
    def __init__(self, root: Path):
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
        matches = password_matches(password, row["password_hash"] if row else self.dummy)
        if not matches or not row or row["disabled"]:
            raise ValueError("Email or passphrase is incorrect")
        token, csrf = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
        with self.connection() as db:
            db.execute("DELETE FROM auth_sessions WHERE expires<?", (time.time(),))
            db.execute(
                "INSERT INTO auth_sessions VALUES(?,?,?,?)",
                (digest_token(token), row["id"], csrf, time.time() + SESSION_SECONDS),
            )
            # Bound sessions per user; retain the most recent five.
            db.execute(
                "DELETE FROM auth_sessions WHERE user_id=? AND token_hash NOT IN (SELECT token_hash FROM auth_sessions WHERE user_id=? ORDER BY expires DESC LIMIT 5)",
                (row["id"], row["id"]),
            )
        self.audit(self.user(row["id"]), "login", row["id"])
        return token, csrf, self.user(row["id"])

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
        return [dict(r) for r in rows if user["role"] in {"admin", "coach"} or r["id"] == user["id"]]

    def workspace(self, user, uid):
        target = self.user(uid)
        if (
            not target
            or target["disabled"]
            or target["academy_id"] != user["academy_id"]
            or (user["role"] == "player" and uid != user["id"])
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

import hashlib
import json
import os
import sqlite3
import threading
import time
from contextlib import closing
from pathlib import Path

from cryptography.fernet import Fernet, InvalidToken, MultiFernet


class DurableStateError(RuntimeError):
    pass


def _sha256(value):
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


class DurableState:
    """Encrypted SQLite-backed state for TikTok OAuth/session recovery.

    The cookie/session ID and OAuth state values are never persisted in plaintext.
    Session payloads (including tokens) are encrypted with Fernet/MultiFernet.
    """

    def __init__(self, db_path, encryption_keys):
        path = Path(str(db_path or "")).expanduser()
        if not str(db_path or "").strip():
            raise DurableStateError("TIKTOK_STATE_DB_PATH is required")
        if not path.is_absolute():
            raise DurableStateError("TIKTOK_STATE_DB_PATH must be an absolute path")
        keys = [str(k).strip().encode("ascii") for k in (encryption_keys or []) if str(k).strip()]
        if not keys:
            raise DurableStateError("at least one encryption key is required")
        try:
            fernets = [Fernet(k) for k in keys]
        except Exception as exc:
            raise DurableStateError("invalid state encryption key") from exc
        self._fernet = MultiFernet(fernets)
        self._db_path = path
        self._lock = threading.RLock()
        path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()
        try:
            os.chmod(path, 0o600)
        except OSError:
            pass

    @classmethod
    def from_env(cls):
        raw_keys = os.environ.get("TIKTOK_STATE_ENCRYPTION_KEYS", "").strip()
        if not raw_keys:
            raw_keys = os.environ.get("TIKTOK_STATE_ENCRYPTION_KEY", "").strip()
        keys = [k.strip() for k in raw_keys.split(",") if k.strip()]
        return cls(os.environ.get("TIKTOK_STATE_DB_PATH", ""), keys)

    def _connect(self):
        con = sqlite3.connect(str(self._db_path), timeout=10, isolation_level=None)
        con.row_factory = sqlite3.Row
        con.execute("PRAGMA foreign_keys=ON")
        con.execute("PRAGMA journal_mode=WAL")
        con.execute("PRAGMA synchronous=FULL")
        con.execute("PRAGMA busy_timeout=10000")
        return con

    def _initialize(self):
        with self._lock, closing(self._connect()) as con:
            con.execute(
                """CREATE TABLE IF NOT EXISTS oauth_states(
                    state_hash TEXT PRIMARY KEY,
                    sid_hash TEXT NOT NULL,
                    sid_cipher BLOB NOT NULL,
                    next_path TEXT NOT NULL,
                    created_at INTEGER NOT NULL,
                    expires_at INTEGER NOT NULL,
                    consumed_at INTEGER
                )"""
            )
            con.execute(
                """CREATE TABLE IF NOT EXISTS sessions(
                    sid_hash TEXT PRIMARY KEY,
                    payload_cipher BLOB NOT NULL,
                    created_at INTEGER NOT NULL,
                    updated_at INTEGER NOT NULL,
                    expires_at INTEGER NOT NULL
                )"""
            )
            con.execute("CREATE INDEX IF NOT EXISTS idx_oauth_states_exp ON oauth_states(expires_at)")
            con.execute("CREATE INDEX IF NOT EXISTS idx_sessions_exp ON sessions(expires_at)")

    def _encrypt_json(self, payload):
        raw = json.dumps(payload, separators=(",", ":"), sort_keys=True, ensure_ascii=False).encode("utf-8")
        return self._fernet.encrypt(raw)

    def _decrypt_json(self, token):
        try:
            raw = self._fernet.decrypt(bytes(token))
            value = json.loads(raw.decode("utf-8"))
        except (InvalidToken, UnicodeDecodeError, json.JSONDecodeError, TypeError, ValueError) as exc:
            raise DurableStateError("encrypted state failed authentication") from exc
        if not isinstance(value, dict):
            raise DurableStateError("encrypted state payload is not an object")
        return value

    def upsert_session(self, sid, payload, now=None, ttl=86400):
        if not sid:
            raise DurableStateError("session id required")
        if not isinstance(payload, dict):
            raise DurableStateError("session payload must be an object")
        now = int(time.time() if now is None else now)
        ttl = int(ttl)
        if ttl <= 0:
            raise DurableStateError("session ttl must be positive")
        sid_hash = _sha256(sid)
        cipher = self._encrypt_json(payload)
        with self._lock, closing(self._connect()) as con:
            con.execute("BEGIN IMMEDIATE")
            existing = con.execute("SELECT created_at FROM sessions WHERE sid_hash=?", (sid_hash,)).fetchone()
            created_at = int(existing["created_at"]) if existing else now
            con.execute(
                """INSERT INTO sessions(sid_hash,payload_cipher,created_at,updated_at,expires_at)
                   VALUES(?,?,?,?,?)
                   ON CONFLICT(sid_hash) DO UPDATE SET
                     payload_cipher=excluded.payload_cipher,
                     updated_at=excluded.updated_at,
                     expires_at=excluded.expires_at""",
                (sid_hash, cipher, created_at, now, now + ttl),
            )
            con.execute("COMMIT")

    def get_session(self, sid, now=None, touch=True, ttl=86400):
        if not sid:
            return None
        now = int(time.time() if now is None else now)
        sid_hash = _sha256(sid)
        with self._lock, closing(self._connect()) as con:
            row = con.execute(
                "SELECT payload_cipher,expires_at FROM sessions WHERE sid_hash=?", (sid_hash,)
            ).fetchone()
            if not row:
                return None
            if int(row["expires_at"]) <= now:
                con.execute("DELETE FROM sessions WHERE sid_hash=?", (sid_hash,))
                return None
            payload = self._decrypt_json(row["payload_cipher"])
            if touch:
                con.execute(
                    "UPDATE sessions SET updated_at=?,expires_at=? WHERE sid_hash=?",
                    (now, now + int(ttl), sid_hash),
                )
            return payload

    def patch_session(self, sid, patch, now=None, ttl=86400):
        if not isinstance(patch, dict):
            raise DurableStateError("session patch must be an object")
        current = self.get_session(sid, now=now, touch=False, ttl=ttl)
        if current is None:
            current = {}
        current.update(patch)
        self.upsert_session(sid, current, now=now, ttl=ttl)
        return current

    def delete_session(self, sid):
        if not sid:
            return
        with self._lock, closing(self._connect()) as con:
            con.execute("DELETE FROM sessions WHERE sid_hash=?", (_sha256(sid),))

    def create_oauth_state(self, state, sid, next_path, now=None, ttl=600):
        if not state or not sid:
            raise DurableStateError("oauth state and session id required")
        now = int(time.time() if now is None else now)
        ttl = int(ttl)
        if ttl <= 0:
            raise DurableStateError("oauth state ttl must be positive")
        state_hash = _sha256(state)
        sid_hash = _sha256(sid)
        sid_cipher = self._fernet.encrypt(sid.encode("utf-8"))
        with self._lock, closing(self._connect()) as con:
            con.execute(
                """INSERT INTO oauth_states(
                    state_hash,sid_hash,sid_cipher,next_path,created_at,expires_at,consumed_at
                ) VALUES(?,?,?,?,?,?,NULL)""",
                (state_hash, sid_hash, sid_cipher, str(next_path), now, now + ttl),
            )

    def consume_oauth_state(self, state, now=None):
        if not state:
            return None
        now = int(time.time() if now is None else now)
        state_hash = _sha256(state)
        with self._lock, closing(self._connect()) as con:
            con.execute("BEGIN IMMEDIATE")
            row = con.execute(
                """SELECT sid_cipher,next_path,created_at,expires_at,consumed_at
                   FROM oauth_states WHERE state_hash=?""",
                (state_hash,),
            ).fetchone()
            if not row or row["consumed_at"] is not None or int(row["expires_at"]) <= now:
                if row and int(row["expires_at"]) <= now:
                    con.execute("DELETE FROM oauth_states WHERE state_hash=?", (state_hash,))
                con.execute("COMMIT")
                return None
            con.execute("UPDATE oauth_states SET consumed_at=? WHERE state_hash=?", (now, state_hash))
            con.execute("COMMIT")
        try:
            sid = self._fernet.decrypt(bytes(row["sid_cipher"])).decode("utf-8")
        except (InvalidToken, UnicodeDecodeError) as exc:
            raise DurableStateError("oauth state session binding failed authentication") from exc
        return {"sid": sid, "ts": int(row["created_at"]), "next_path": str(row["next_path"])}

    def cleanup(self, now=None):
        now = int(time.time() if now is None else now)
        with self._lock, closing(self._connect()) as con:
            con.execute("DELETE FROM oauth_states WHERE expires_at<=? OR consumed_at IS NOT NULL", (now,))
            con.execute("DELETE FROM sessions WHERE expires_at<=?", (now,))

    def health(self):
        with self._lock, closing(self._connect()) as con:
            con.execute("SELECT 1").fetchone()
        return {"ok": True, "backend": "sqlite", "path_configured": True}

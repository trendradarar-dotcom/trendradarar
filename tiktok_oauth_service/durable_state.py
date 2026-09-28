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


PUBLICATION_STATES = {
    "RECEIVED","VALIDATED","SAFETY_APPROVED","PUBLISH_REQUESTED",
    "UPLOAD_STARTED","UPLOADED","PROCESSING","READY","PUBLISHED",
    "FAILED","UNKNOWN",
}

_ALLOWED_PUBLICATION_TRANSITIONS = {
    "RECEIVED": {"VALIDATED","FAILED"},
    "VALIDATED": {"SAFETY_APPROVED","FAILED"},
    "SAFETY_APPROVED": {"PUBLISH_REQUESTED","FAILED"},
    "PUBLISH_REQUESTED": {"UPLOAD_STARTED","FAILED","UNKNOWN"},
    "UPLOAD_STARTED": {"UPLOADED","FAILED","UNKNOWN"},
    "UPLOADED": {"PROCESSING","FAILED","UNKNOWN"},
    "PROCESSING": {"PROCESSING","READY","PUBLISHED","FAILED","UNKNOWN"},
    "UNKNOWN": {"PROCESSING","READY","PUBLISHED","FAILED","UNKNOWN"},
    "READY": {"READY"},
    "PUBLISHED": {"PUBLISHED"},
    "FAILED": {"FAILED"},
}


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
            con.execute(
                """CREATE TABLE IF NOT EXISTS handoffs(
                    token_hash TEXT PRIMARY KEY,
                    sid_cipher BLOB NOT NULL,
                    next_path TEXT NOT NULL,
                    created_at INTEGER NOT NULL,
                    expires_at INTEGER NOT NULL,
                    consumed_at INTEGER
                )"""
            )
            con.execute(
                """CREATE TABLE IF NOT EXISTS publications(
                    idempotency_key TEXT PRIMARY KEY,
                    content_sha256 TEXT NOT NULL,
                    account_hash TEXT NOT NULL,
                    operation TEXT NOT NULL,
                    metadata_sha256 TEXT NOT NULL,
                    state TEXT NOT NULL,
                    provider_publish_id TEXT UNIQUE,
                    attempt_count INTEGER NOT NULL DEFAULT 0,
                    first_attempt_at INTEGER,
                    last_attempt_at INTEGER,
                    last_error_code TEXT,
                    created_at INTEGER NOT NULL,
                    updated_at INTEGER NOT NULL
                )"""
            )
            con.execute(
                """CREATE TABLE IF NOT EXISTS mutation_events(
                    event_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    idempotency_key TEXT NOT NULL UNIQUE,
                    account_hash TEXT NOT NULL,
                    operation TEXT NOT NULL,
                    created_at INTEGER NOT NULL,
                    FOREIGN KEY(idempotency_key) REFERENCES publications(idempotency_key)
                )"""
            )
            con.execute("CREATE INDEX IF NOT EXISTS idx_oauth_states_exp ON oauth_states(expires_at)")
            con.execute("CREATE INDEX IF NOT EXISTS idx_sessions_exp ON sessions(expires_at)")
            con.execute("CREATE INDEX IF NOT EXISTS idx_handoffs_exp ON handoffs(expires_at)")
            con.execute("CREATE INDEX IF NOT EXISTS idx_publications_provider ON publications(provider_publish_id)")
            con.execute("CREATE INDEX IF NOT EXISTS idx_publications_account ON publications(account_hash,updated_at)")
            con.execute("CREATE INDEX IF NOT EXISTS idx_mutation_events_time ON mutation_events(created_at)")
            con.execute("CREATE INDEX IF NOT EXISTS idx_mutation_events_account_time ON mutation_events(account_hash,created_at)")

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

    def create_handoff(self, token, sid, next_path, now=None, ttl=600):
        if not token or not sid:
            raise DurableStateError("handoff token and session id required")
        now = int(time.time() if now is None else now)
        ttl = int(ttl)
        if ttl <= 0:
            raise DurableStateError("handoff ttl must be positive")
        token_hash = _sha256(token)
        sid_cipher = self._fernet.encrypt(sid.encode("utf-8"))
        with self._lock, closing(self._connect()) as con:
            con.execute(
                """INSERT INTO handoffs(
                    token_hash,sid_cipher,next_path,created_at,expires_at,consumed_at
                ) VALUES(?,?,?,?,?,NULL)""",
                (token_hash, sid_cipher, str(next_path), now, now + ttl),
            )

    def consume_handoff(self, token, now=None):
        if not token:
            return None
        now = int(time.time() if now is None else now)
        token_hash = _sha256(token)
        with self._lock, closing(self._connect()) as con:
            con.execute("BEGIN IMMEDIATE")
            row = con.execute(
                """SELECT sid_cipher,next_path,created_at,expires_at,consumed_at
                   FROM handoffs WHERE token_hash=?""",
                (token_hash,),
            ).fetchone()
            if not row or row["consumed_at"] is not None or int(row["expires_at"]) <= now:
                if row and int(row["expires_at"]) <= now:
                    con.execute("DELETE FROM handoffs WHERE token_hash=?", (token_hash,))
                con.execute("COMMIT")
                return None
            con.execute("UPDATE handoffs SET consumed_at=? WHERE token_hash=?", (now, token_hash))
            con.execute("COMMIT")
        try:
            sid = self._fernet.decrypt(bytes(row["sid_cipher"])).decode("utf-8")
        except (InvalidToken, UnicodeDecodeError) as exc:
            raise DurableStateError("handoff session binding failed authentication") from exc
        return {"sid": sid, "ts": int(row["created_at"]), "next_path": str(row["next_path"])}

    def create_publication_intent(self, idempotency_key, content_sha256, account_hash, operation, metadata_sha256, now=None):
        if not all((idempotency_key, content_sha256, account_hash, operation, metadata_sha256)):
            raise DurableStateError("publication intent fields are required")
        now = int(time.time() if now is None else now)
        with self._lock, closing(self._connect()) as con:
            con.execute("BEGIN IMMEDIATE")
            row = con.execute(
                "SELECT * FROM publications WHERE idempotency_key=?",
                (idempotency_key,),
            ).fetchone()
            if row:
                con.execute("COMMIT")
                return dict(row), False
            con.execute(
                """INSERT INTO publications(
                    idempotency_key,content_sha256,account_hash,operation,metadata_sha256,
                    state,created_at,updated_at
                ) VALUES(?,?,?,?,?,?,?,?)""",
                (idempotency_key,content_sha256,account_hash,operation,metadata_sha256,"RECEIVED",now,now),
            )
            row = con.execute("SELECT * FROM publications WHERE idempotency_key=?", (idempotency_key,)).fetchone()
            con.execute("COMMIT")
            return dict(row), True

    def get_publication(self, idempotency_key):
        with self._lock, closing(self._connect()) as con:
            row = con.execute("SELECT * FROM publications WHERE idempotency_key=?", (idempotency_key,)).fetchone()
            return dict(row) if row else None

    def get_publication_by_provider_id(self, provider_publish_id):
        if not provider_publish_id:
            return None
        with self._lock, closing(self._connect()) as con:
            row = con.execute("SELECT * FROM publications WHERE provider_publish_id=?", (provider_publish_id,)).fetchone()
            return dict(row) if row else None

    def admit_publication(self, idempotency_key, max_per_hour, max_per_day, max_active_per_account, max_active_global, now=None):
        now = int(time.time() if now is None else now)
        limits = [int(max_per_hour),int(max_per_day),int(max_active_per_account),int(max_active_global)]
        if any(v <= 0 for v in limits):
            raise DurableStateError("publication hard limits must be positive")
        active_states = ("VALIDATED","SAFETY_APPROVED","PUBLISH_REQUESTED","UPLOAD_STARTED","UPLOADED","PROCESSING","UNKNOWN")
        with self._lock, closing(self._connect()) as con:
            con.execute("BEGIN IMMEDIATE")
            row = con.execute("SELECT * FROM publications WHERE idempotency_key=?", (idempotency_key,)).fetchone()
            if not row:
                con.execute("ROLLBACK")
                raise DurableStateError("publication intent not found")
            if row["state"] != "RECEIVED":
                con.execute("ROLLBACK")
                raise DurableStateError("publication intent is not awaiting admission")
            account_hash = str(row["account_hash"])
            hour_count = int(con.execute(
                "SELECT COUNT(*) FROM mutation_events WHERE account_hash=? AND created_at>?",
                (account_hash, now-3600),
            ).fetchone()[0])
            day_count = int(con.execute(
                "SELECT COUNT(*) FROM mutation_events WHERE account_hash=? AND created_at>?",
                (account_hash, now-86400),
            ).fetchone()[0])
            ph = ",".join("?" for _ in active_states)
            active_account = int(con.execute(
                f"SELECT COUNT(*) FROM publications WHERE account_hash=? AND idempotency_key<>? AND state IN ({ph})",
                (account_hash,idempotency_key,*active_states),
            ).fetchone()[0])
            active_global = int(con.execute(
                f"SELECT COUNT(*) FROM publications WHERE idempotency_key<>? AND state IN ({ph})",
                (idempotency_key,*active_states),
            ).fetchone()[0])
            reason = None
            if hour_count >= limits[0]:
                reason = "hourly_account_limit"
            elif day_count >= limits[1]:
                reason = "daily_account_limit"
            elif active_account >= limits[2]:
                reason = "active_account_limit"
            elif active_global >= limits[3]:
                reason = "active_global_limit"
            if reason:
                con.execute(
                    "UPDATE publications SET state='FAILED',last_error_code=?,updated_at=? WHERE idempotency_key=?",
                    (reason,now,idempotency_key),
                )
                con.execute("COMMIT")
                return False, reason
            con.execute(
                "INSERT INTO mutation_events(idempotency_key,account_hash,operation,created_at) VALUES(?,?,?,?)",
                (idempotency_key,account_hash,str(row["operation"]),now),
            )
            con.execute(
                "UPDATE publications SET state='VALIDATED',updated_at=? WHERE idempotency_key=?",
                (now,idempotency_key),
            )
            con.execute("COMMIT")
            return True, None

    def transition_publication(self, idempotency_key, new_state, now=None, provider_publish_id=None, error_code=None):
        if new_state not in PUBLICATION_STATES:
            raise DurableStateError("invalid publication state")
        now = int(time.time() if now is None else now)
        with self._lock, closing(self._connect()) as con:
            con.execute("BEGIN IMMEDIATE")
            row = con.execute("SELECT * FROM publications WHERE idempotency_key=?", (idempotency_key,)).fetchone()
            if not row:
                con.execute("ROLLBACK")
                raise DurableStateError("publication intent not found")
            current = str(row["state"])
            if new_state != current and new_state not in _ALLOWED_PUBLICATION_TRANSITIONS.get(current, set()):
                con.execute("ROLLBACK")
                raise DurableStateError(f"invalid publication transition {current}->{new_state}")
            provider = provider_publish_id if provider_publish_id is not None else row["provider_publish_id"]
            con.execute(
                """UPDATE publications
                   SET state=?,provider_publish_id=?,last_error_code=?,updated_at=?
                   WHERE idempotency_key=?""",
                (new_state,provider,error_code,now,idempotency_key),
            )
            updated = con.execute("SELECT * FROM publications WHERE idempotency_key=?", (idempotency_key,)).fetchone()
            con.execute("COMMIT")
            return dict(updated)

    def begin_publication_attempt(self, idempotency_key, now=None):
        now = int(time.time() if now is None else now)
        with self._lock, closing(self._connect()) as con:
            con.execute("BEGIN IMMEDIATE")
            row = con.execute("SELECT * FROM publications WHERE idempotency_key=?", (idempotency_key,)).fetchone()
            if not row:
                con.execute("ROLLBACK")
                raise DurableStateError("publication intent not found")
            count = int(row["attempt_count"]) + 1
            first = int(row["first_attempt_at"]) if row["first_attempt_at"] is not None else now
            con.execute(
                """UPDATE publications
                   SET attempt_count=?,first_attempt_at=?,last_attempt_at=?,updated_at=?
                   WHERE idempotency_key=?""",
                (count,first,now,now,idempotency_key),
            )
            updated = con.execute("SELECT * FROM publications WHERE idempotency_key=?", (idempotency_key,)).fetchone()
            con.execute("COMMIT")
            return dict(updated)

    def cleanup(self, now=None):
        now = int(time.time() if now is None else now)
        with self._lock, closing(self._connect()) as con:
            con.execute("DELETE FROM oauth_states WHERE expires_at<=? OR consumed_at IS NOT NULL", (now,))
            con.execute("DELETE FROM handoffs WHERE expires_at<=? OR consumed_at IS NOT NULL", (now,))
            con.execute("DELETE FROM sessions WHERE expires_at<=?", (now,))

    def backup_to(self, destination_path):
        destination = Path(str(destination_path or "")).expanduser()
        if not str(destination_path or "").strip():
            raise DurableStateError("backup destination is required")
        if not destination.is_absolute():
            raise DurableStateError("backup destination must be absolute")
        if destination == self._db_path:
            raise DurableStateError("backup destination must differ from live database")
        destination.parent.mkdir(parents=True, exist_ok=True)
        if destination.exists():
            raise DurableStateError("backup destination already exists")
        with self._lock, closing(self._connect()) as source:
            with closing(sqlite3.connect(str(destination), timeout=10)) as target:
                source.backup(target)
                check = target.execute("PRAGMA quick_check").fetchone()
                if not check or str(check[0]).lower() != "ok":
                    raise DurableStateError("backup integrity check failed")
        try:
            os.chmod(destination, 0o600)
        except OSError:
            pass
        digest = hashlib.sha256(destination.read_bytes()).hexdigest()
        return {"path": str(destination), "sha256": digest}

    @classmethod
    def restore_backup(cls, backup_path, target_path, encryption_keys):
        source_path = Path(str(backup_path or "")).expanduser()
        target_path = Path(str(target_path or "")).expanduser()
        if not source_path.is_absolute() or not target_path.is_absolute():
            raise DurableStateError("backup and restore paths must be absolute")
        if not source_path.exists() or not source_path.is_file():
            raise DurableStateError("backup source does not exist")
        if target_path.exists():
            raise DurableStateError("restore target already exists")
        target_path.parent.mkdir(parents=True, exist_ok=True)
        with closing(sqlite3.connect(str(source_path), timeout=10)) as source:
            check = source.execute("PRAGMA quick_check").fetchone()
            if not check or str(check[0]).lower() != "ok":
                raise DurableStateError("backup source integrity check failed")
            with closing(sqlite3.connect(str(target_path), timeout=10)) as target:
                source.backup(target)
                check2 = target.execute("PRAGMA quick_check").fetchone()
                if not check2 or str(check2[0]).lower() != "ok":
                    raise DurableStateError("restored database integrity check failed")
        try:
            os.chmod(target_path, 0o600)
        except OSError:
            pass
        return cls(str(target_path), encryption_keys)

    def health(self):
        with self._lock, closing(self._connect()) as con:
            check = con.execute("PRAGMA quick_check").fetchone()
            if not check or str(check[0]).lower() != "ok":
                raise DurableStateError("database integrity check failed")
        return {"ok": True, "backend": "sqlite", "path_configured": True}

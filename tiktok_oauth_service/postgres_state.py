import base64
import hashlib
import json
import os
import threading
import time
from contextlib import closing
from pathlib import Path
from urllib.parse import urlparse

from cryptography.fernet import Fernet, InvalidToken, MultiFernet

from durable_state import (
    DurableState,
    DurableStateError,
    PUBLICATION_STATES,
    _ALLOWED_PUBLICATION_TRANSITIONS,
    _sha256,
)

try:
    import psycopg
except ImportError:  # fail closed when PostgreSQL is selected
    psycopg = None


_BACKUP_MAGIC = b"TIKTOK_POSTGRES_BACKUP_V1\n"

_TABLE_COLUMNS = {
    "oauth_states": (
        "state_hash","sid_hash","sid_cipher","next_path","created_at","expires_at","consumed_at",
    ),
    "sessions": (
        "sid_hash","payload_cipher","created_at","updated_at","expires_at",
    ),
    "handoffs": (
        "token_hash","sid_cipher","next_path","created_at","expires_at","consumed_at",
    ),
    "publications": (
        "idempotency_key","content_sha256","account_hash","operation","metadata_sha256",
        "state","provider_publish_id","attempt_count","first_attempt_at","last_attempt_at",
        "last_error_code","created_at","updated_at",
    ),
    "mutation_events": (
        "event_id","idempotency_key","account_hash","operation","created_at",
    ),
    "audit_events": (
        "event_id","occurred_at","event_type","idempotency_key","account_hash","operation",
        "decision","state","detail_json",
    ),
    "recovery_markers": (
        "marker_key","marker_value_cipher","created_at","updated_at",
    ),
}

_BACKUP_ORDER = (
    "oauth_states","sessions","handoffs","publications",
    "mutation_events","audit_events","recovery_markers",
)

_ORDER_BY = {
    "oauth_states": "state_hash",
    "sessions": "sid_hash",
    "handoffs": "token_hash",
    "publications": "idempotency_key",
    "mutation_events": "event_id",
    "audit_events": "event_id",
    "recovery_markers": "marker_key",
}


class _HybridRow(dict):
    def __init__(self, columns, values):
        super().__init__(zip(columns, values))
        self._columns = tuple(columns)

    def __getitem__(self, key):
        if isinstance(key, int):
            key = self._columns[key]
        return super().__getitem__(key)


class _PgCursorAdapter:
    def __init__(self, cursor):
        self._cursor = cursor

    @property
    def rowcount(self):
        return int(self._cursor.rowcount or 0)

    def _wrap(self, row):
        if row is None:
            return None
        cols = [getattr(d, "name", d[0]) for d in (self._cursor.description or ())]
        return _HybridRow(cols, row)

    def fetchone(self):
        return self._wrap(self._cursor.fetchone())

    def fetchall(self):
        rows = self._cursor.fetchall()
        cols = [getattr(d, "name", d[0]) for d in (self._cursor.description or ())]
        return [_HybridRow(cols, row) for row in rows]


class _PgConnectionAdapter:
    def __init__(self, dsn):
        if psycopg is None:
            raise DurableStateError("PostgreSQL driver is unavailable")
        try:
            self._conn = psycopg.connect(
                dsn,
                autocommit=True,
                connect_timeout=5,
                application_name="trendradar-tiktok-durable-state",
            )
        except Exception as exc:
            raise DurableStateError("PostgreSQL connection failed") from exc

    @staticmethod
    def _adapt_sql(sql):
        text = str(sql)
        if text.strip().upper() == "BEGIN IMMEDIATE":
            return "BEGIN"
        return text.replace("?", "%s")

    def execute(self, sql, params=()):
        try:
            cur = self._conn.cursor()
            cur.execute(self._adapt_sql(sql), tuple(params or ()))
            return _PgCursorAdapter(cur)
        except Exception as exc:
            if psycopg is not None and isinstance(exc, psycopg.Error):
                raise DurableStateError("PostgreSQL operation failed") from exc
            raise

    def close(self):
        try:
            self._conn.close()
        except Exception:
            pass


def _validate_database_url(database_url):
    raw = str(database_url or "").strip()
    if not raw:
        raise DurableStateError("TIKTOK_POSTGRES_URL is required")
    try:
        parsed = urlparse(raw)
    except Exception as exc:
        raise DurableStateError("invalid PostgreSQL URL") from exc
    if parsed.scheme not in ("postgresql", "postgres"):
        raise DurableStateError("TIKTOK_POSTGRES_URL must use postgresql:// or postgres://")
    if not parsed.hostname or not parsed.path or parsed.path == "/":
        raise DurableStateError("TIKTOK_POSTGRES_URL is incomplete")
    return raw


class PostgresDurableState(DurableState):
    """Production PostgreSQL backend preserving DurableState semantics.

    Sensitive OAuth/session values stay Fernet/MultiFernet encrypted before
    database persistence. PostgreSQL unavailability is fatal: this class never
    falls back to SQLite.
    """

    def __init__(self, database_url, encryption_keys):
        self._database_url = _validate_database_url(database_url)
        keys = [str(k).strip().encode("ascii") for k in (encryption_keys or []) if str(k).strip()]
        if not keys:
            raise DurableStateError("at least one encryption key is required")
        try:
            fernets = [Fernet(k) for k in keys]
        except Exception as exc:
            raise DurableStateError("invalid state encryption key") from exc
        self._fernet = MultiFernet(fernets)
        self._lock = threading.RLock()
        self._initialize()

    @classmethod
    def from_env(cls):
        raw_keys = os.environ.get("TIKTOK_STATE_ENCRYPTION_KEYS", "").strip()
        if not raw_keys:
            raw_keys = os.environ.get("TIKTOK_STATE_ENCRYPTION_KEY", "").strip()
        keys = [k.strip() for k in raw_keys.split(",") if k.strip()]
        return cls(os.environ.get("TIKTOK_POSTGRES_URL", ""), keys)

    def _connect(self):
        return _PgConnectionAdapter(self._database_url)

    def _initialize(self):
        statements = [
            """CREATE TABLE IF NOT EXISTS oauth_states(
                state_hash TEXT PRIMARY KEY,
                sid_hash TEXT NOT NULL,
                sid_cipher BYTEA NOT NULL,
                next_path TEXT NOT NULL,
                created_at BIGINT NOT NULL,
                expires_at BIGINT NOT NULL,
                consumed_at BIGINT
            )""",
            """CREATE TABLE IF NOT EXISTS sessions(
                sid_hash TEXT PRIMARY KEY,
                payload_cipher BYTEA NOT NULL,
                created_at BIGINT NOT NULL,
                updated_at BIGINT NOT NULL,
                expires_at BIGINT NOT NULL
            )""",
            """CREATE TABLE IF NOT EXISTS handoffs(
                token_hash TEXT PRIMARY KEY,
                sid_cipher BYTEA NOT NULL,
                next_path TEXT NOT NULL,
                created_at BIGINT NOT NULL,
                expires_at BIGINT NOT NULL,
                consumed_at BIGINT
            )""",
            """CREATE TABLE IF NOT EXISTS publications(
                idempotency_key TEXT PRIMARY KEY,
                content_sha256 TEXT NOT NULL,
                account_hash TEXT NOT NULL,
                operation TEXT NOT NULL,
                metadata_sha256 TEXT NOT NULL,
                state TEXT NOT NULL,
                provider_publish_id TEXT UNIQUE,
                attempt_count INTEGER NOT NULL DEFAULT 0,
                first_attempt_at BIGINT,
                last_attempt_at BIGINT,
                last_error_code TEXT,
                created_at BIGINT NOT NULL,
                updated_at BIGINT NOT NULL
            )""",
            """CREATE TABLE IF NOT EXISTS mutation_events(
                event_id BIGSERIAL PRIMARY KEY,
                idempotency_key TEXT NOT NULL UNIQUE,
                account_hash TEXT NOT NULL,
                operation TEXT NOT NULL,
                created_at BIGINT NOT NULL,
                FOREIGN KEY(idempotency_key) REFERENCES publications(idempotency_key)
            )""",
            """CREATE TABLE IF NOT EXISTS audit_events(
                event_id BIGSERIAL PRIMARY KEY,
                occurred_at BIGINT NOT NULL,
                event_type TEXT NOT NULL,
                idempotency_key TEXT,
                account_hash TEXT,
                operation TEXT,
                decision TEXT,
                state TEXT,
                detail_json TEXT NOT NULL DEFAULT '{}'
            )""",
            """CREATE TABLE IF NOT EXISTS recovery_markers(
                marker_key TEXT PRIMARY KEY,
                marker_value_cipher BYTEA NOT NULL,
                created_at BIGINT NOT NULL,
                updated_at BIGINT NOT NULL
            )""",
            "CREATE INDEX IF NOT EXISTS idx_oauth_states_exp ON oauth_states(expires_at)",
            "CREATE INDEX IF NOT EXISTS idx_sessions_exp ON sessions(expires_at)",
            "CREATE INDEX IF NOT EXISTS idx_handoffs_exp ON handoffs(expires_at)",
            "CREATE INDEX IF NOT EXISTS idx_publications_provider ON publications(provider_publish_id)",
            "CREATE INDEX IF NOT EXISTS idx_publications_account ON publications(account_hash,updated_at)",
            "CREATE INDEX IF NOT EXISTS idx_mutation_events_time ON mutation_events(created_at)",
            "CREATE INDEX IF NOT EXISTS idx_mutation_events_account_time ON mutation_events(account_hash,created_at)",
            "CREATE INDEX IF NOT EXISTS idx_audit_events_time ON audit_events(occurred_at)",
            "CREATE INDEX IF NOT EXISTS idx_audit_events_idem ON audit_events(idempotency_key,occurred_at)",
        ]
        with self._lock, closing(self._connect()) as con:
            con.execute("BEGIN")
            try:
                for statement in statements:
                    con.execute(statement)
                con.execute("COMMIT")
            except Exception:
                try:
                    con.execute("ROLLBACK")
                except Exception:
                    pass
                raise

    def consume_oauth_state(self, state, expected_sid, now=None):
        if not state or not expected_sid:
            return None
        now = int(time.time() if now is None else now)
        state_hash = _sha256(state)
        expected_sid_hash = _sha256(expected_sid)
        with self._lock, closing(self._connect()) as con:
            con.execute("BEGIN")
            try:
                row = con.execute(
                    """SELECT sid_hash,sid_cipher,next_path,created_at,expires_at,consumed_at
                       FROM oauth_states WHERE state_hash=? FOR UPDATE""",
                    (state_hash,),
                ).fetchone()
                if not row or row["consumed_at"] is not None or int(row["expires_at"]) <= now:
                    if row and int(row["expires_at"]) <= now:
                        con.execute("DELETE FROM oauth_states WHERE state_hash=?", (state_hash,))
                    con.execute("COMMIT")
                    return None
                if str(row["sid_hash"]) != expected_sid_hash:
                    con.execute("ROLLBACK")
                    return None
                con.execute("UPDATE oauth_states SET consumed_at=? WHERE state_hash=?", (now, state_hash))
                con.execute("COMMIT")
            except Exception:
                try:
                    con.execute("ROLLBACK")
                except Exception:
                    pass
                raise
        try:
            sid = self._fernet.decrypt(bytes(row["sid_cipher"])).decode("utf-8")
        except (InvalidToken, UnicodeDecodeError) as exc:
            raise DurableStateError("oauth state session binding failed authentication") from exc
        if sid != expected_sid:
            raise DurableStateError("oauth state browser binding failed authentication")
        return {"sid": sid, "ts": int(row["created_at"]), "next_path": str(row["next_path"])}

    def consume_handoff(self, token, now=None):
        if not token:
            return None
        now = int(time.time() if now is None else now)
        token_hash = _sha256(token)
        with self._lock, closing(self._connect()) as con:
            con.execute("BEGIN")
            try:
                row = con.execute(
                    """SELECT sid_cipher,next_path,created_at,expires_at,consumed_at
                       FROM handoffs WHERE token_hash=? FOR UPDATE""",
                    (token_hash,),
                ).fetchone()
                if not row or row["consumed_at"] is not None or int(row["expires_at"]) <= now:
                    if row and int(row["expires_at"]) <= now:
                        con.execute("DELETE FROM handoffs WHERE token_hash=?", (token_hash,))
                    con.execute("COMMIT")
                    return None
                con.execute("UPDATE handoffs SET consumed_at=? WHERE token_hash=?", (now, token_hash))
                con.execute("COMMIT")
            except Exception:
                try:
                    con.execute("ROLLBACK")
                except Exception:
                    pass
                raise
        try:
            sid = self._fernet.decrypt(bytes(row["sid_cipher"])).decode("utf-8")
        except (InvalidToken, UnicodeDecodeError) as exc:
            raise DurableStateError("handoff session binding failed authentication") from exc
        return {"sid": sid, "ts": int(row["created_at"]), "next_path": str(row["next_path"])}

    def create_publication_intent(
        self,
        idempotency_key,
        content_sha256,
        account_hash,
        operation,
        metadata_sha256,
        now=None,
    ):
        if not all((idempotency_key, content_sha256, account_hash, operation, metadata_sha256)):
            raise DurableStateError("publication intent fields are required")
        now = int(time.time() if now is None else now)
        with self._lock, closing(self._connect()) as con:
            con.execute("BEGIN")
            try:
                row = con.execute(
                    """INSERT INTO publications(
                        idempotency_key,content_sha256,account_hash,operation,metadata_sha256,
                        state,created_at,updated_at
                    ) VALUES(?,?,?,?,?,?,?,?)
                    ON CONFLICT(idempotency_key) DO NOTHING
                    RETURNING *""",
                    (
                        idempotency_key,content_sha256,account_hash,operation,metadata_sha256,
                        "RECEIVED",now,now,
                    ),
                ).fetchone()
                if row:
                    con.execute(
                        """INSERT INTO audit_events(
                            occurred_at,event_type,idempotency_key,account_hash,operation,decision,state,detail_json
                        ) VALUES(?,?,?,?,?,?,?,?)""",
                        (
                            now,"PUBLICATION_INTENT_CREATED",idempotency_key,account_hash,
                            operation,"ADMIT_PENDING","RECEIVED","{}",
                        ),
                    )
                    con.execute("COMMIT")
                    return dict(row), True
                existing = con.execute(
                    "SELECT * FROM publications WHERE idempotency_key=?",
                    (idempotency_key,),
                ).fetchone()
                con.execute("COMMIT")
                if not existing:
                    raise DurableStateError("publication idempotency lookup failed")
                return dict(existing), False
            except Exception:
                try:
                    con.execute("ROLLBACK")
                except Exception:
                    pass
                raise

    def admit_publication(
        self,
        idempotency_key,
        max_per_hour,
        max_per_day,
        max_active_per_account,
        max_active_global,
        max_global_per_hour=None,
        max_global_per_day=None,
        now=None,
    ):
        now = int(time.time() if now is None else now)
        limits = [
            int(max_per_hour),int(max_per_day),int(max_active_per_account),int(max_active_global)
        ]
        global_hour = int(max_global_per_hour) if max_global_per_hour is not None else None
        global_day = int(max_global_per_day) if max_global_per_day is not None else None
        if (
            any(v <= 0 for v in limits)
            or (global_hour is not None and global_hour <= 0)
            or (global_day is not None and global_day <= 0)
        ):
            raise DurableStateError("publication hard limits must be positive")
        active_states = (
            "VALIDATED","SAFETY_APPROVED","PUBLISH_REQUESTED",
            "UPLOAD_STARTED","UPLOADED","PROCESSING","UNKNOWN",
        )
        with self._lock, closing(self._connect()) as con:
            con.execute("BEGIN")
            try:
                # Conservative global admission lock prevents cross-instance races in
                # account/global counters and active-operation blast-radius limits.
                con.execute("SELECT pg_advisory_xact_lock(hashtext('trendradar:tiktok:publication-admission'))")
                row = con.execute(
                    "SELECT * FROM publications WHERE idempotency_key=? FOR UPDATE",
                    (idempotency_key,),
                ).fetchone()
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
                global_hour_count = int(con.execute(
                    "SELECT COUNT(*) FROM mutation_events WHERE created_at>?",
                    (now-3600,),
                ).fetchone()[0])
                global_day_count = int(con.execute(
                    "SELECT COUNT(*) FROM mutation_events WHERE created_at>?",
                    (now-86400,),
                ).fetchone()[0])
                ph = ",".join("?" for _ in active_states)
                active_account = int(con.execute(
                    f"""SELECT COUNT(*) FROM publications
                        WHERE account_hash=? AND idempotency_key<>? AND state IN ({ph})""",
                    (account_hash,idempotency_key,*active_states),
                ).fetchone()[0])
                active_global = int(con.execute(
                    f"""SELECT COUNT(*) FROM publications
                        WHERE idempotency_key<>? AND state IN ({ph})""",
                    (idempotency_key,*active_states),
                ).fetchone()[0])
                reason = None
                if hour_count >= limits[0]:
                    reason = "hourly_account_limit"
                elif day_count >= limits[1]:
                    reason = "daily_account_limit"
                elif global_hour is not None and global_hour_count >= global_hour:
                    reason = "hourly_global_limit"
                elif global_day is not None and global_day_count >= global_day:
                    reason = "daily_global_limit"
                elif active_account >= limits[2]:
                    reason = "active_account_limit"
                elif active_global >= limits[3]:
                    reason = "active_global_limit"
                if reason:
                    con.execute(
                        """UPDATE publications
                           SET state='FAILED',last_error_code=?,updated_at=?
                           WHERE idempotency_key=?""",
                        (reason,now,idempotency_key),
                    )
                    con.execute(
                        """INSERT INTO audit_events(
                            occurred_at,event_type,idempotency_key,account_hash,operation,decision,state,detail_json
                        ) VALUES(?,?,?,?,?,?,?,?)""",
                        (
                            now,"PUBLICATION_ADMISSION",idempotency_key,account_hash,
                            str(row["operation"]),"BLOCK","FAILED",
                            json.dumps({"reason":reason},separators=(",",":"),sort_keys=True),
                        ),
                    )
                    con.execute("COMMIT")
                    return False, reason
                con.execute(
                    """INSERT INTO mutation_events(
                        idempotency_key,account_hash,operation,created_at
                    ) VALUES(?,?,?,?)""",
                    (idempotency_key,account_hash,str(row["operation"]),now),
                )
                con.execute(
                    "UPDATE publications SET state='VALIDATED',updated_at=? WHERE idempotency_key=?",
                    (now,idempotency_key),
                )
                con.execute(
                    """INSERT INTO audit_events(
                        occurred_at,event_type,idempotency_key,account_hash,operation,decision,state,detail_json
                    ) VALUES(?,?,?,?,?,?,?,?)""",
                    (
                        now,"PUBLICATION_ADMISSION",idempotency_key,account_hash,
                        str(row["operation"]),"ALLOW","VALIDATED","{}",
                    ),
                )
                con.execute("COMMIT")
                return True, None
            except Exception:
                try:
                    con.execute("ROLLBACK")
                except Exception:
                    pass
                raise

    def transition_publication(
        self,
        idempotency_key,
        new_state,
        now=None,
        provider_publish_id=None,
        error_code=None,
    ):
        if new_state not in PUBLICATION_STATES:
            raise DurableStateError("invalid publication state")
        now = int(time.time() if now is None else now)
        with self._lock, closing(self._connect()) as con:
            con.execute("BEGIN")
            try:
                row = con.execute(
                    "SELECT * FROM publications WHERE idempotency_key=? FOR UPDATE",
                    (idempotency_key,),
                ).fetchone()
                if not row:
                    con.execute("ROLLBACK")
                    raise DurableStateError("publication intent not found")
                current = str(row["state"])
                if (
                    new_state != current
                    and new_state not in _ALLOWED_PUBLICATION_TRANSITIONS.get(current, set())
                ):
                    con.execute("ROLLBACK")
                    raise DurableStateError(
                        f"invalid publication transition {current}->{new_state}"
                    )
                provider = (
                    provider_publish_id
                    if provider_publish_id is not None
                    else row["provider_publish_id"]
                )
                con.execute(
                    """UPDATE publications
                       SET state=?,provider_publish_id=?,last_error_code=?,updated_at=?
                       WHERE idempotency_key=?""",
                    (new_state,provider,error_code,now,idempotency_key),
                )
                con.execute(
                    """INSERT INTO audit_events(
                        occurred_at,event_type,idempotency_key,account_hash,operation,decision,state,detail_json
                    ) VALUES(?,?,?,?,?,?,?,?)""",
                    (
                        now,"PUBLICATION_STATE",idempotency_key,str(row["account_hash"]),
                        str(row["operation"]),"TRANSITION",new_state,
                        json.dumps(
                            {"from":current,"error_code":error_code},
                            separators=(",",":"),sort_keys=True,
                        ),
                    ),
                )
                updated = con.execute(
                    "SELECT * FROM publications WHERE idempotency_key=?",
                    (idempotency_key,),
                ).fetchone()
                con.execute("COMMIT")
                return dict(updated)
            except Exception:
                try:
                    con.execute("ROLLBACK")
                except Exception:
                    pass
                raise

    def begin_publication_attempt(self, idempotency_key, now=None):
        now = int(time.time() if now is None else now)
        with self._lock, closing(self._connect()) as con:
            con.execute("BEGIN")
            try:
                row = con.execute(
                    "SELECT * FROM publications WHERE idempotency_key=? FOR UPDATE",
                    (idempotency_key,),
                ).fetchone()
                if not row:
                    con.execute("ROLLBACK")
                    raise DurableStateError("publication intent not found")
                count = int(row["attempt_count"]) + 1
                first = (
                    int(row["first_attempt_at"])
                    if row["first_attempt_at"] is not None
                    else now
                )
                con.execute(
                    """UPDATE publications
                       SET attempt_count=?,first_attempt_at=?,last_attempt_at=?,updated_at=?
                       WHERE idempotency_key=?""",
                    (count,first,now,now,idempotency_key),
                )
                updated = con.execute(
                    "SELECT * FROM publications WHERE idempotency_key=?",
                    (idempotency_key,),
                ).fetchone()
                con.execute("COMMIT")
                return dict(updated)
            except Exception:
                try:
                    con.execute("ROLLBACK")
                except Exception:
                    pass
                raise

    def record_audit_event(
        self,
        event_type,
        occurred_at=None,
        idempotency_key=None,
        account_hash=None,
        operation=None,
        decision=None,
        state=None,
        detail=None,
    ):
        occurred_at = int(time.time() if occurred_at is None else occurred_at)
        safe_detail = detail if isinstance(detail, dict) else {}
        encoded = json.dumps(
            safe_detail,separators=(",",":"),sort_keys=True,ensure_ascii=False
        )
        forbidden = ("access_token","refresh_token","client_secret","authorization_code")
        lowered = encoded.lower()
        if any(name in lowered for name in forbidden):
            raise DurableStateError("sensitive audit detail rejected")
        with self._lock, closing(self._connect()) as con:
            row = con.execute(
                """INSERT INTO audit_events(
                    occurred_at,event_type,idempotency_key,account_hash,operation,decision,state,detail_json
                ) VALUES(?,?,?,?,?,?,?,?)
                RETURNING event_id""",
                (
                    occurred_at,str(event_type),idempotency_key,account_hash,
                    operation,decision,state,encoded,
                ),
            ).fetchone()
            return int(row["event_id"])

    @staticmethod
    def _encode_backup_value(value):
        if isinstance(value, memoryview):
            value = bytes(value)
        if isinstance(value, (bytes, bytearray)):
            return {"__bytes_b64__": base64.b64encode(bytes(value)).decode("ascii")}
        return value

    @staticmethod
    def _decode_backup_value(value):
        if (
            isinstance(value, dict)
            and set(value) == {"__bytes_b64__"}
            and isinstance(value["__bytes_b64__"], str)
        ):
            try:
                return base64.b64decode(value["__bytes_b64__"], validate=True)
            except Exception as exc:
                raise DurableStateError("invalid binary value in PostgreSQL backup") from exc
        return value

    def backup_to(self, destination_path):
        destination = Path(str(destination_path or "")).expanduser()
        if not str(destination_path or "").strip():
            raise DurableStateError("backup destination is required")
        if not destination.is_absolute():
            raise DurableStateError("backup destination must be absolute")
        destination.parent.mkdir(parents=True, exist_ok=True)
        if destination.exists():
            raise DurableStateError("backup destination already exists")

        snapshot = {
            "format": "trendradar-tiktok-postgresql-backup",
            "version": 1,
            "created_at": int(time.time()),
            "tables": {},
        }
        with self._lock, closing(self._connect()) as con:
            con.execute("BEGIN")
            try:
                con.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY")
                for table in _BACKUP_ORDER:
                    cols = _TABLE_COLUMNS[table]
                    rows = con.execute(
                        f"SELECT {','.join(cols)} FROM {table} ORDER BY {_ORDER_BY[table]}"
                    ).fetchall()
                    snapshot["tables"][table] = [
                        {
                            col: self._encode_backup_value(row[col])
                            for col in cols
                        }
                        for row in rows
                    ]
                con.execute("COMMIT")
            except Exception:
                try:
                    con.execute("ROLLBACK")
                except Exception:
                    pass
                raise

        raw = json.dumps(
            snapshot,separators=(",",":"),sort_keys=True,ensure_ascii=False
        ).encode("utf-8")
        encrypted = self._fernet.encrypt(raw)
        destination.write_bytes(_BACKUP_MAGIC + encrypted)
        try:
            os.chmod(destination, 0o600)
        except OSError:
            pass
        digest = hashlib.sha256(destination.read_bytes()).hexdigest()
        return {
            "path": str(destination),
            "sha256": digest,
            "backend": "postgresql",
            "format_version": 1,
        }

    @classmethod
    def restore_backup(cls, backup_path, target_database_url, encryption_keys):
        source_path = Path(str(backup_path or "")).expanduser()
        if not source_path.is_absolute():
            raise DurableStateError("backup path must be absolute")
        if not source_path.exists() or not source_path.is_file():
            raise DurableStateError("backup source does not exist")
        target_database_url = _validate_database_url(target_database_url)

        keys = [str(k).strip().encode("ascii") for k in (encryption_keys or []) if str(k).strip()]
        if not keys:
            raise DurableStateError("at least one encryption key is required")
        try:
            fernet = MultiFernet([Fernet(k) for k in keys])
        except Exception as exc:
            raise DurableStateError("invalid state encryption key") from exc

        raw = source_path.read_bytes()
        if not raw.startswith(_BACKUP_MAGIC):
            raise DurableStateError("invalid PostgreSQL backup format")
        try:
            plain = fernet.decrypt(raw[len(_BACKUP_MAGIC):])
            payload = json.loads(plain.decode("utf-8"))
        except (InvalidToken,UnicodeDecodeError,json.JSONDecodeError) as exc:
            raise DurableStateError("PostgreSQL backup failed authentication") from exc
        if (
            not isinstance(payload, dict)
            or payload.get("format") != "trendradar-tiktok-postgresql-backup"
            or payload.get("version") != 1
            or not isinstance(payload.get("tables"), dict)
        ):
            raise DurableStateError("invalid PostgreSQL backup payload")

        restored = cls(target_database_url, encryption_keys)
        with restored._lock, closing(restored._connect()) as con:
            con.execute("BEGIN")
            try:
                for table in _BACKUP_ORDER:
                    count = int(con.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])
                    if count:
                        raise DurableStateError("restore target is not empty")

                for table in _BACKUP_ORDER:
                    rows = payload["tables"].get(table)
                    if not isinstance(rows, list):
                        raise DurableStateError("PostgreSQL backup table set is incomplete")
                    cols = _TABLE_COLUMNS[table]
                    for item in rows:
                        if not isinstance(item, dict) or set(item) != set(cols):
                            raise DurableStateError("PostgreSQL backup row schema mismatch")
                        values = [
                            restored._decode_backup_value(item[col])
                            for col in cols
                        ]
                        placeholders = ",".join("?" for _ in cols)
                        con.execute(
                            f"INSERT INTO {table} ({','.join(cols)}) VALUES({placeholders})",
                            values,
                        )

                for table in ("mutation_events","audit_events"):
                    maximum = int(con.execute(
                        f"SELECT COALESCE(MAX(event_id),0) FROM {table}"
                    ).fetchone()[0])
                    if maximum > 0:
                        con.execute(
                            f"""SELECT setval(
                                pg_get_serial_sequence('{table}','event_id'),
                                ?, true
                            )""",
                            (maximum,),
                        )
                    else:
                        con.execute(
                            f"""SELECT setval(
                                pg_get_serial_sequence('{table}','event_id'),
                                1, false
                            )"""
                        )
                con.execute("COMMIT")
            except Exception:
                try:
                    con.execute("ROLLBACK")
                except Exception:
                    pass
                raise
        return restored

    def health(self):
        with self._lock, closing(self._connect()) as con:
            row = con.execute("SELECT 1 AS ok").fetchone()
            if not row or int(row["ok"]) != 1:
                raise DurableStateError("PostgreSQL health check failed")
            for table in ("sessions","publications","audit_events","recovery_markers"):
                exists = con.execute("SELECT to_regclass(?) AS relation", (table,)).fetchone()
                if not exists or not exists["relation"]:
                    raise DurableStateError("PostgreSQL schema is incomplete")
        return {
            "ok": True,
            "backend": "postgresql",
            "database_configured": True,
            "fallback": False,
        }

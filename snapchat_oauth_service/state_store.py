import hashlib
import os
import sqlite3
import threading
import time
from contextlib import contextmanager
from typing import Any, Dict, Iterable, Optional

import psycopg
from psycopg.rows import dict_row


class StateStoreError(RuntimeError):
    pass


class DurableStateStore:
    """Durable OAuth and publication state.

    PostgreSQL is required for production acceptance. SQLite is supported only
    for isolated tests/development and is never reported as production-durable.
    """

    ACTIVE_STATES = (
        "RECEIVED",
        "VALIDATED",
        "MEDIA_CREATING",
        "MEDIA_UPLOADING",
        "SUBMITTING",
    )

    def __init__(self, url: Optional[str] = None):
        self.url = (url or os.getenv("SNAPCHAT_DATABASE_URL") or os.getenv("DATABASE_URL") or "").strip()
        self._sqlite_lock = threading.RLock()
        if not self.url:
            raise StateStoreError("database_url_not_configured")
        self.is_postgres = self.url.startswith("postgresql://") or self.url.startswith("postgres://")
        self.is_sqlite = self.url.startswith("sqlite:///")
        if not (self.is_postgres or self.is_sqlite):
            raise StateStoreError("unsupported_database_url")

    @property
    def production_durable(self) -> bool:
        return self.is_postgres

    @contextmanager
    def _connect(self):
        if self.is_postgres:
            conn = psycopg.connect(self.url, row_factory=dict_row, connect_timeout=10)
        else:
            path = self.url[len("sqlite:///"):]
            conn = sqlite3.connect(path, timeout=30)
            conn.row_factory = sqlite3.Row
        try:
            yield conn
        finally:
            conn.close()

    def _sql(self, query: str) -> str:
        return query.replace("?", "%s") if self.is_postgres else query

    def _dict(self, row) -> Optional[Dict[str, Any]]:
        if row is None:
            return None
        return dict(row)

    def init_schema(self) -> None:
        statements = [
            """
            CREATE TABLE IF NOT EXISTS snapchat_oauth_intents (
                intent_hash TEXT PRIMARY KEY,
                created_at BIGINT NOT NULL,
                expires_at BIGINT NOT NULL,
                consumed_at BIGINT
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS snapchat_oauth_states (
                state_hash TEXT PRIMARY KEY,
                browser_hash TEXT NOT NULL,
                created_at BIGINT NOT NULL,
                expires_at BIGINT NOT NULL,
                consumed_at BIGINT
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS snapchat_oauth_tokens (
                id INTEGER PRIMARY KEY,
                access_cipher TEXT,
                refresh_cipher TEXT,
                expires_at BIGINT,
                scope TEXT,
                profile_id TEXT,
                username TEXT,
                connected INTEGER NOT NULL DEFAULT 0,
                updated_at BIGINT NOT NULL
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS snapchat_publications (
                profile_id TEXT NOT NULL,
                publication_id TEXT NOT NULL,
                state TEXT NOT NULL,
                attempt_count INTEGER NOT NULL,
                description TEXT,
                description_hash TEXT,
                media_sha256 TEXT,
                media_duration REAL,
                media_width INTEGER,
                media_height INTEGER,
                remote_media_id TEXT,
                remote_spotlight_id TEXT,
                correlation_id TEXT,
                created_at BIGINT NOT NULL,
                updated_at BIGINT NOT NULL,
                submit_started_at BIGINT,
                final_at BIGINT,
                last_error TEXT,
                PRIMARY KEY (profile_id, publication_id)
            )
            """,
            """
            CREATE INDEX IF NOT EXISTS idx_snapchat_publications_state_created
            ON snapchat_publications (profile_id, state, created_at)
            """,
            """
            CREATE INDEX IF NOT EXISTS idx_snapchat_publications_remote_spotlight
            ON snapchat_publications (remote_spotlight_id)
            """,
        ]
        lock = self._sqlite_lock if self.is_sqlite else _NullLock()
        with lock:
            with self._connect() as conn:
                cur = conn.cursor()
                for statement in statements:
                    cur.execute(statement)
                conn.commit()

    def ping(self) -> bool:
        self.init_schema()
        with self._connect() as conn:
            cur = conn.cursor()
            cur.execute("SELECT 1")
            return cur.fetchone() is not None

    def _cleanup_ephemeral(self, cur, now: int) -> None:
        cur.execute(self._sql("DELETE FROM snapchat_oauth_intents WHERE expires_at < ? OR consumed_at IS NOT NULL"), (now - 60,))
        cur.execute(self._sql("DELETE FROM snapchat_oauth_states WHERE expires_at < ? OR consumed_at IS NOT NULL"), (now - 60,))

    def create_oauth_intent(self, intent_hash: str, ttl_seconds: int) -> None:
        now = int(time.time())
        self.init_schema()
        with self._connect() as conn:
            cur = conn.cursor()
            self._cleanup_ephemeral(cur, now)
            cur.execute(
                self._sql(
                    "INSERT INTO snapchat_oauth_intents(intent_hash,created_at,expires_at,consumed_at) VALUES (?,?,?,NULL)"
                ),
                (intent_hash, now, now + ttl_seconds),
            )
            conn.commit()

    def consume_oauth_intent(self, intent_hash: str) -> bool:
        now = int(time.time())
        self.init_schema()
        with self._connect() as conn:
            cur = conn.cursor()
            cur.execute(
                self._sql(
                    "UPDATE snapchat_oauth_intents SET consumed_at=? WHERE intent_hash=? AND consumed_at IS NULL AND expires_at>=?"
                ),
                (now, intent_hash, now),
            )
            ok = cur.rowcount == 1
            conn.commit()
            return ok

    def create_oauth_state(self, state_hash: str, browser_hash: str, ttl_seconds: int) -> None:
        now = int(time.time())
        self.init_schema()
        with self._connect() as conn:
            cur = conn.cursor()
            self._cleanup_ephemeral(cur, now)
            cur.execute(
                self._sql(
                    "INSERT INTO snapchat_oauth_states(state_hash,browser_hash,created_at,expires_at,consumed_at) VALUES (?,?,?,?,NULL)"
                ),
                (state_hash, browser_hash, now, now + ttl_seconds),
            )
            conn.commit()

    def consume_oauth_state(self, state_hash: str, browser_hash: str) -> bool:
        now = int(time.time())
        self.init_schema()
        with self._connect() as conn:
            cur = conn.cursor()
            cur.execute(
                self._sql(
                    "UPDATE snapchat_oauth_states SET consumed_at=? WHERE state_hash=? AND browser_hash=? AND consumed_at IS NULL AND expires_at>=?"
                ),
                (now, state_hash, browser_hash, now),
            )
            ok = cur.rowcount == 1
            conn.commit()
            return ok

    def save_tokens(
        self,
        access_cipher: str,
        refresh_cipher: str,
        expires_at: int,
        scope: str,
        profile_id: str,
        username: str,
    ) -> None:
        now = int(time.time())
        self.init_schema()
        with self._connect() as conn:
            cur = conn.cursor()
            cur.execute(
                self._sql(
                    """
                    INSERT INTO snapchat_oauth_tokens
                    (id,access_cipher,refresh_cipher,expires_at,scope,profile_id,username,connected,updated_at)
                    VALUES (1,?,?,?,?,?,?,1,?)
                    ON CONFLICT(id) DO UPDATE SET
                      access_cipher=excluded.access_cipher,
                      refresh_cipher=excluded.refresh_cipher,
                      expires_at=excluded.expires_at,
                      scope=excluded.scope,
                      profile_id=excluded.profile_id,
                      username=excluded.username,
                      connected=1,
                      updated_at=excluded.updated_at
                    """
                ),
                (access_cipher, refresh_cipher, expires_at, scope, profile_id, username, now),
            )
            conn.commit()

    def load_tokens(self) -> Optional[Dict[str, Any]]:
        self.init_schema()
        with self._connect() as conn:
            cur = conn.cursor()
            cur.execute("SELECT * FROM snapchat_oauth_tokens WHERE id=1")
            return self._dict(cur.fetchone())

    def clear_tokens(self) -> None:
        now = int(time.time())
        self.init_schema()
        with self._connect() as conn:
            cur = conn.cursor()
            cur.execute(
                self._sql(
                    """
                    INSERT INTO snapchat_oauth_tokens
                    (id,access_cipher,refresh_cipher,expires_at,scope,profile_id,username,connected,updated_at)
                    VALUES (1,NULL,NULL,NULL,NULL,NULL,NULL,0,?)
                    ON CONFLICT(id) DO UPDATE SET
                      access_cipher=NULL,
                      refresh_cipher=NULL,
                      expires_at=NULL,
                      scope=NULL,
                      profile_id=NULL,
                      username=NULL,
                      connected=0,
                      updated_at=excluded.updated_at
                    """
                ),
                (now,),
            )
            conn.commit()

    def token_status(self) -> Dict[str, Any]:
        row = self.load_tokens()
        return {
            "persisted": bool(row),
            "connected": bool(row and int(row.get("connected") or 0) == 1),
            "refresh_credential_present": bool(row and row.get("refresh_cipher")),
            "access_credential_present": bool(row and row.get("access_cipher")),
            "expires_at": row.get("expires_at") if row else None,
            "scope": row.get("scope") if row else None,
            "profile_id": row.get("profile_id") if row else None,
            "username": row.get("username") if row else None,
        }

    def _advisory_key(self, profile_id: str) -> int:
        raw = hashlib.sha256(profile_id.encode("utf-8")).digest()[:8]
        value = int.from_bytes(raw, "big", signed=False)
        if value >= 2**63:
            value -= 2**64
        return value

    def _lock_publication_admission(self, cur, profile_id: str) -> None:
        if self.is_postgres:
            cur.execute("SELECT pg_advisory_xact_lock(%s)", (self._advisory_key(profile_id),))

    def begin_publication(
        self,
        *,
        profile_id: str,
        publication_id: str,
        correlation_id: str,
        description: str,
        media_sha256: str,
        duration: float,
        width: int,
        height: int,
        max_hour: int,
        max_day: int,
        max_concurrent: int,
        max_attempts: int,
        retry_horizon_seconds: int,
    ) -> Dict[str, Any]:
        now = int(time.time())
        description_hash = hashlib.sha256(description.encode("utf-8")).hexdigest()
        self.init_schema()
        lock = self._sqlite_lock if self.is_sqlite else _NullLock()
        with lock:
            with self._connect() as conn:
                cur = conn.cursor()
                self._lock_publication_admission(cur, profile_id)
                cur.execute(
                    self._sql("SELECT * FROM snapchat_publications WHERE profile_id=? AND publication_id=?"),
                    (profile_id, publication_id),
                )
                existing = self._dict(cur.fetchone())
                if existing:
                    state = existing["state"]
                    attempts = int(existing.get("attempt_count") or 0)
                    age = now - int(existing.get("created_at") or now)
                    if (
                        state == "FAILED_PRE_SUBMIT"
                        and not existing.get("remote_spotlight_id")
                        and attempts < max_attempts
                        and age <= retry_horizon_seconds
                    ):
                        cur.execute(
                            self._sql(
                                """
                                UPDATE snapchat_publications
                                SET state='RECEIVED', attempt_count=attempt_count+1,
                                    correlation_id=?, description=?, description_hash=?,
                                    media_sha256=?, media_duration=?, media_width=?, media_height=?,
                                    updated_at=?, last_error=NULL
                                WHERE profile_id=? AND publication_id=?
                                """
                            ),
                            (
                                correlation_id,
                                description,
                                description_hash,
                                media_sha256,
                                duration,
                                width,
                                height,
                                now,
                                profile_id,
                                publication_id,
                            ),
                        )
                        conn.commit()
                        cur.execute(
                            self._sql("SELECT * FROM snapchat_publications WHERE profile_id=? AND publication_id=?"),
                            (profile_id, publication_id),
                        )
                        return {"created": False, "retry_admitted": True, "row": self._dict(cur.fetchone())}
                    conn.commit()
                    return {"created": False, "retry_admitted": False, "row": existing}

                cur.execute(
                    self._sql(
                        "SELECT COUNT(*) AS c FROM snapchat_publications "
                        "WHERE profile_id=? AND state IN (?,?,?,?,?)"
                    ),
                    (profile_id, *self.ACTIVE_STATES),
                )
                active_row = self._dict(cur.fetchone()) or {"c": 0}
                if int(active_row["c"]) >= max_concurrent:
                    raise StateStoreError("maximum_concurrent_publications_reached")

                cur.execute(
                    self._sql(
                        "SELECT COUNT(*) AS c FROM snapchat_publications WHERE profile_id=? AND created_at>=?"
                    ),
                    (profile_id, now - 3600),
                )
                hour_row = self._dict(cur.fetchone()) or {"c": 0}
                if int(hour_row["c"]) >= max_hour:
                    raise StateStoreError("maximum_hourly_publications_reached")

                cur.execute(
                    self._sql(
                        "SELECT COUNT(*) AS c FROM snapchat_publications WHERE profile_id=? AND created_at>=?"
                    ),
                    (profile_id, now - 86400),
                )
                day_row = self._dict(cur.fetchone()) or {"c": 0}
                if int(day_row["c"]) >= max_day:
                    raise StateStoreError("maximum_daily_publications_reached")

                cur.execute(
                    self._sql(
                        """
                        INSERT INTO snapchat_publications
                        (profile_id,publication_id,state,attempt_count,description,description_hash,
                         media_sha256,media_duration,media_width,media_height,correlation_id,
                         created_at,updated_at)
                        VALUES (?,?, 'RECEIVED',1,?,?,?,?,?,?,?,?,?)
                        """
                    ),
                    (
                        profile_id,
                        publication_id,
                        description,
                        description_hash,
                        media_sha256,
                        duration,
                        width,
                        height,
                        correlation_id,
                        now,
                        now,
                    ),
                )
                conn.commit()
                cur.execute(
                    self._sql("SELECT * FROM snapchat_publications WHERE profile_id=? AND publication_id=?"),
                    (profile_id, publication_id),
                )
                return {"created": True, "retry_admitted": False, "row": self._dict(cur.fetchone())}

    def transition(
        self,
        *,
        profile_id: str,
        publication_id: str,
        allowed_from: Iterable[str],
        new_state: str,
        remote_media_id: Optional[str] = None,
        remote_spotlight_id: Optional[str] = None,
        last_error: Optional[str] = None,
        mark_submit_started: bool = False,
        mark_final: bool = False,
    ) -> Dict[str, Any]:
        now = int(time.time())
        allowed = tuple(allowed_from)
        if not allowed:
            raise StateStoreError("transition_requires_allowed_from")

        self.init_schema()
        lock = self._sqlite_lock if self.is_sqlite else _NullLock()
        with lock:
            with self._connect() as conn:
                cur = conn.cursor()
                if self.is_postgres:
                    cur.execute(
                        self._sql(
                            "SELECT * FROM snapchat_publications "
                            "WHERE profile_id=? AND publication_id=? FOR UPDATE"
                        ),
                        (profile_id, publication_id),
                    )
                else:
                    cur.execute(
                        self._sql(
                            "SELECT * FROM snapchat_publications "
                            "WHERE profile_id=? AND publication_id=?"
                        ),
                        (profile_id, publication_id),
                    )
                current = self._dict(cur.fetchone())
                if not current or current["state"] not in allowed:
                    conn.rollback()
                    raise StateStoreError("invalid_publication_state_transition")

                current_state = current["state"]
                cur.execute(
                    self._sql(
                        """
                        UPDATE snapchat_publications
                        SET state=?,
                            updated_at=?,
                            remote_media_id=COALESCE(?, remote_media_id),
                            remote_spotlight_id=COALESCE(?, remote_spotlight_id),
                            last_error=COALESCE(?, last_error),
                            submit_started_at=CASE WHEN ?=1 THEN ? ELSE submit_started_at END,
                            final_at=CASE WHEN ?=1 THEN ? ELSE final_at END
                        WHERE profile_id=? AND publication_id=? AND state=?
                        """
                    ),
                    (
                        new_state,
                        now,
                        remote_media_id,
                        remote_spotlight_id,
                        last_error[:500] if last_error is not None else None,
                        1 if mark_submit_started else 0,
                        now,
                        1 if mark_final else 0,
                        now,
                        profile_id,
                        publication_id,
                        current_state,
                    ),
                )
                if cur.rowcount != 1:
                    conn.rollback()
                    raise StateStoreError("concurrent_publication_state_change")
                conn.commit()

        row = self.get_publication(profile_id, publication_id)
        if not row:
            raise StateStoreError("publication_missing_after_transition")
        return row

    def get_publication(self, profile_id: str, publication_id: str) -> Optional[Dict[str, Any]]:
        self.init_schema()
        with self._connect() as conn:
            cur = conn.cursor()
            cur.execute(
                self._sql("SELECT * FROM snapchat_publications WHERE profile_id=? AND publication_id=?"),
                (profile_id, publication_id),
            )
            return self._dict(cur.fetchone())

    def publication_counts(self, profile_id: str) -> Dict[str, int]:
        now = int(time.time())
        self.init_schema()
        with self._connect() as conn:
            cur = conn.cursor()
            cur.execute(
                self._sql("SELECT COUNT(*) AS c FROM snapchat_publications WHERE profile_id=? AND created_at>=?"),
                (profile_id, now - 3600),
            )
            hour = int((self._dict(cur.fetchone()) or {"c": 0})["c"])
            cur.execute(
                self._sql("SELECT COUNT(*) AS c FROM snapchat_publications WHERE profile_id=? AND created_at>=?"),
                (profile_id, now - 86400),
            )
            day = int((self._dict(cur.fetchone()) or {"c": 0})["c"])
            return {"last_hour": hour, "last_day": day}


class _NullLock:
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

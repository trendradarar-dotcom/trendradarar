import os
import tempfile
import unittest
from unittest import mock
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import urlsplit, urlunsplit

from cryptography.fernet import Fernet

from durable_state import DurableState, DurableStateError
from postgres_state import PostgresDurableState

try:
    import psycopg
    from psycopg import sql
except ImportError:
    psycopg = None
    sql = None


class PostgresDurableStateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.dsn = os.environ.get("TIKTOK_TEST_POSTGRES_URL", "").strip()
        if not cls.dsn:
            raise unittest.SkipTest("TIKTOK_TEST_POSTGRES_URL not configured")
        if psycopg is None:
            raise unittest.SkipTest("psycopg not installed")
        cls.key = Fernet.generate_key().decode()
        cls.restore_db = "tiktok_restore_test"
        parts = urlsplit(cls.dsn)
        cls.admin_dsn = urlunsplit((
            parts.scheme, parts.netloc, "/postgres", parts.query, parts.fragment
        ))
        cls.restore_dsn = urlunsplit((
            parts.scheme, parts.netloc, "/" + cls.restore_db, parts.query, parts.fragment
        ))

    @classmethod
    def tearDownClass(cls):
        if not getattr(cls, "admin_dsn", None) or psycopg is None:
            return
        try:
            with psycopg.connect(cls.admin_dsn, autocommit=True) as con:
                con.execute(
                    sql.SQL("DROP DATABASE IF EXISTS {} WITH (FORCE)").format(
                        sql.Identifier(cls.restore_db)
                    )
                )
        except Exception:
            pass

    def setUp(self):
        self.store = PostgresDurableState(self.dsn, [self.key])
        self._truncate(self.dsn)

    def _truncate(self, dsn):
        with psycopg.connect(dsn, autocommit=True) as con:
            con.execute(
                """TRUNCATE TABLE
                   mutation_events,audit_events,recovery_markers,
                   oauth_states,handoffs,sessions,publications
                   RESTART IDENTITY CASCADE"""
            )

    def _fresh_restore_database(self):
        with psycopg.connect(self.admin_dsn, autocommit=True) as con:
            con.execute(
                sql.SQL("DROP DATABASE IF EXISTS {} WITH (FORCE)").format(
                    sql.Identifier(self.restore_db)
                )
            )
            con.execute(
                sql.SQL("CREATE DATABASE {}").format(sql.Identifier(self.restore_db))
            )

    def _create_published(self, store, idem="idem-pub", provider="provider-pub", now=100):
        store.create_publication_intent(
            idem,"a"*64,"acct","DIRECT_POST","b"*64,now=now
        )
        ok, reason = store.admit_publication(idem,20,100,5,10,40,200,now=now+1)
        self.assertTrue(ok)
        self.assertIsNone(reason)
        store.transition_publication(idem,"SAFETY_APPROVED",now=now+2)
        store.begin_publication_attempt(idem,now=now+3)
        store.transition_publication(idem,"PUBLISH_REQUESTED",now=now+4)
        store.transition_publication(
            idem,"UPLOAD_STARTED",now=now+5,provider_publish_id=provider
        )
        store.transition_publication(idem,"UPLOADED",now=now+6)
        store.transition_publication(idem,"PROCESSING",now=now+7)
        store.transition_publication(idem,"PUBLISHED",now=now+8)

    def test_production_factory_selects_postgresql(self):
        env = {
            "TIKTOK_STATE_BACKEND": "postgresql",
            "TIKTOK_RUNTIME_MODE": "production",
            "TIKTOK_POSTGRES_URL": self.dsn,
            "TIKTOK_STATE_ENCRYPTION_KEY": self.key,
        }
        with mock.patch.dict(os.environ, env, clear=False):
            selected = DurableState.from_env()
        health = selected.health()
        self.assertEqual(health["backend"], "postgresql")
        self.assertFalse(health["fallback"])

    def test_health_reports_postgresql_without_fallback(self):
        health = self.store.health()
        self.assertTrue(health["ok"])
        self.assertEqual(health["backend"], "postgresql")
        self.assertFalse(health["fallback"])

    def test_session_ciphertext_and_restart_persistence(self):
        self.store.upsert_session(
            "sid-secret",
            {"access_token":"token-secret","refresh_token":"refresh-secret"},
            now=1000,
            ttl=100,
        )
        with psycopg.connect(self.dsn, autocommit=True) as con:
            raw = con.execute(
                "SELECT payload_cipher FROM sessions"
            ).fetchone()[0]
        self.assertNotIn(b"token-secret", bytes(raw))
        reopened = PostgresDurableState(self.dsn, [self.key])
        got = reopened.get_session("sid-secret", now=1001, touch=False)
        self.assertEqual(got["access_token"], "token-secret")

    def test_oauth_state_browser_binding_and_replay(self):
        self.store.create_oauth_state(
            "state-secret","sid-A","/share",now=2000,ttl=60
        )
        self.assertIsNone(
            self.store.consume_oauth_state("state-secret","sid-B",now=2001)
        )
        ok = self.store.consume_oauth_state("state-secret","sid-A",now=2002)
        self.assertEqual(ok["sid"], "sid-A")
        self.assertIsNone(
            self.store.consume_oauth_state("state-secret","sid-A",now=2003)
        )

    def test_handoff_is_one_time(self):
        self.store.create_handoff("handoff","sid","/share",now=3000,ttl=60)
        self.assertEqual(
            self.store.consume_handoff("handoff",now=3001)["sid"], "sid"
        )
        self.assertIsNone(self.store.consume_handoff("handoff",now=3002))

    def test_concurrent_idempotency_creates_exactly_one_intent(self):
        stores = [PostgresDurableState(self.dsn,[self.key]) for _ in range(6)]
        def worker(store):
            _, created = store.create_publication_intent(
                "idem-concurrent","c"*64,"acct-concurrent","DIRECT_POST","d"*64,now=4000
            )
            return created
        with ThreadPoolExecutor(max_workers=6) as pool:
            results = list(pool.map(worker, stores))
        self.assertEqual(sum(bool(x) for x in results), 1)
        rec = self.store.get_publication("idem-concurrent")
        self.assertEqual(rec["state"], "RECEIVED")

    def test_concurrent_admission_respects_active_account_limit(self):
        self.store.create_publication_intent(
            "idem-a","e"*64,"acct-limit","DIRECT_POST","f"*64,now=5000
        )
        self.store.create_publication_intent(
            "idem-b","1"*64,"acct-limit","DIRECT_POST","2"*64,now=5000
        )
        a = PostgresDurableState(self.dsn,[self.key])
        b = PostgresDurableState(self.dsn,[self.key])
        def admit(args):
            store, idem = args
            return idem, store.admit_publication(
                idem,20,100,1,10,40,200,now=5001
            )
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = dict(pool.map(admit, [(a,"idem-a"),(b,"idem-b")]))
        allowed = [idem for idem,(ok,_) in results.items() if ok]
        blocked = [idem for idem,(ok,_) in results.items() if not ok]
        self.assertEqual(len(allowed), 1)
        self.assertEqual(len(blocked), 1)
        self.assertEqual(results[blocked[0]][1], "active_account_limit")

    def test_provider_publish_id_is_unique(self):
        for idx in (1,2):
            idem=f"idem-provider-{idx}"
            self.store.create_publication_intent(
                idem,str(idx)*64,f"acct-{idx}","DIRECT_POST",str(idx+2)*64,now=6000+idx
            )
            ok,_=self.store.admit_publication(idem,20,100,5,10,40,200,now=6010+idx)
            self.assertTrue(ok)
            self.store.transition_publication(idem,"SAFETY_APPROVED",now=6020+idx)
            self.store.begin_publication_attempt(idem,now=6030+idx)
            self.store.transition_publication(idem,"PUBLISH_REQUESTED",now=6040+idx)
        self.store.transition_publication(
            "idem-provider-1","UPLOAD_STARTED",now=6050,provider_publish_id="same-provider"
        )
        with self.assertRaises(DurableStateError):
            self.store.transition_publication(
                "idem-provider-2","UPLOAD_STARTED",now=6051,provider_publish_id="same-provider"
            )

    def test_unknown_state_survives_reopen_and_blocks_restart(self):
        idem="idem-unknown"
        self.store.create_publication_intent(
            idem,"3"*64,"acct-u","DIRECT_POST","4"*64,now=7000
        )
        ok,_=self.store.admit_publication(idem,20,100,5,10,40,200,now=7001)
        self.assertTrue(ok)
        self.store.transition_publication(idem,"SAFETY_APPROVED",now=7002)
        self.store.begin_publication_attempt(idem,now=7003)
        self.store.transition_publication(idem,"PUBLISH_REQUESTED",now=7004)
        self.store.transition_publication(
            idem,"UPLOAD_STARTED",now=7005,provider_publish_id="provider-u"
        )
        self.store.transition_publication(idem,"UNKNOWN",now=7006,error_code="timeout")
        reopened=PostgresDurableState(self.dsn,[self.key])
        rec=reopened.get_publication(idem)
        self.assertEqual(rec["state"],"UNKNOWN")
        _,created=reopened.create_publication_intent(
            idem,"3"*64,"acct-u","DIRECT_POST","4"*64,now=7007
        )
        self.assertFalse(created)
        with self.assertRaises(DurableStateError):
            reopened.transition_publication(idem,"UPLOAD_STARTED",now=7008)

    def test_unavailable_postgres_fails_closed_without_sqlite_fallback(self):
        unreachable = "postgresql://postgres:postgres@127.0.0.1:1/unreachable"
        with self.assertRaises(DurableStateError):
            PostgresDurableState(unreachable,[self.key])

    def test_concurrent_terminal_transition_is_atomic(self):
        idem="idem-terminal-race"
        self.store.create_publication_intent(
            idem,"5"*64,"acct-race","DIRECT_POST","6"*64,now=7500
        )
        ok,_=self.store.admit_publication(idem,20,100,5,10,40,200,now=7501)
        self.assertTrue(ok)
        self.store.transition_publication(idem,"SAFETY_APPROVED",now=7502)
        self.store.begin_publication_attempt(idem,now=7503)
        self.store.transition_publication(idem,"PUBLISH_REQUESTED",now=7504)
        self.store.transition_publication(
            idem,"UPLOAD_STARTED",now=7505,provider_publish_id="provider-race"
        )
        self.store.transition_publication(idem,"UPLOADED",now=7506)
        self.store.transition_publication(idem,"PROCESSING",now=7507)

        stores=[PostgresDurableState(self.dsn,[self.key]) for _ in range(2)]
        def terminal(args):
            store,state=args
            try:
                store.transition_publication(idem,state,now=7510)
                return state,"ok"
            except DurableStateError:
                return state,"blocked"
        with ThreadPoolExecutor(max_workers=2) as pool:
            outcomes=dict(pool.map(terminal,[(stores[0],"PUBLISHED"),(stores[1],"FAILED")]))
        self.assertEqual(sorted(outcomes.values()),["blocked","ok"])
        final=self.store.get_publication(idem)["state"]
        self.assertIn(final,("PUBLISHED","FAILED"))

    def test_encrypted_logical_backup_restore_preserves_duplicate_barrier(self):
        self._create_published(self.store)
        self.store.set_recovery_marker("qualification","marker-secret",now=8000)
        with tempfile.TemporaryDirectory() as td:
            backup=os.path.join(td,"postgres.backup")
            info=self.store.backup_to(backup)
            self.assertEqual(len(info["sha256"]),64)
            with open(backup,"rb") as handle:
                raw=handle.read()
            self.assertNotIn(b"marker-secret",raw)
            self.assertNotIn(b"provider-pub",raw)

            self._fresh_restore_database()
            restored=PostgresDurableState.restore_backup(
                backup,self.restore_dsn,[self.key]
            )
            self.assertEqual(
                restored.get_recovery_marker("qualification")["value"],
                "marker-secret",
            )
            rec=restored.get_publication("idem-pub")
            self.assertEqual(rec["state"],"PUBLISHED")
            self.assertEqual(rec["provider_publish_id"],"provider-pub")
            audit=restored.list_audit_events("idem-pub",limit=100)
            self.assertGreaterEqual(len(audit),2)
            same,created=restored.create_publication_intent(
                "idem-pub","a"*64,"acct","DIRECT_POST","b"*64,now=9000
            )
            self.assertFalse(created)
            self.assertEqual(same["state"],"PUBLISHED")


if __name__ == "__main__":
    unittest.main()

import os
import sqlite3
import tempfile
import unittest
from contextlib import closing

from cryptography.fernet import Fernet

from durable_state import DurableState, DurableStateError


class DurableStateTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = os.path.join(self.tmp.name, "tiktok-state.sqlite3")
        self.key = Fernet.generate_key().decode()
        self.store = DurableState(self.db, [self.key])

    def tearDown(self):
        self.tmp.cleanup()

    def test_session_survives_reopen_and_plaintext_tokens_not_in_db(self):
        self.store.upsert_session("sid-secret", {
            "csrf": "csrf-secret",
            "access_token": "ACCESS-TOKEN-PLAINTEXT",
            "refresh_token": "REFRESH-TOKEN-PLAINTEXT",
            "open_id": "creator-1",
        }, now=1000, ttl=100)
        reopened = DurableState(self.db, [self.key])
        got = reopened.get_session("sid-secret", now=1001, touch=False)
        self.assertEqual(got["access_token"], "ACCESS-TOKEN-PLAINTEXT")
        with open(self.db, "rb") as f:
            raw = f.read()
        self.assertNotIn(b"ACCESS-TOKEN-PLAINTEXT", raw)
        self.assertNotIn(b"REFRESH-TOKEN-PLAINTEXT", raw)
        self.assertNotIn(b"sid-secret", raw)

    def test_oauth_state_is_one_time_and_not_plaintext(self):
        self.store.create_oauth_state("oauth-state-secret", "sid-secret", "/share", now=2000, ttl=60)
        with open(self.db, "rb") as f:
            raw = f.read()
        self.assertNotIn(b"oauth-state-secret", raw)
        first = self.store.consume_oauth_state("oauth-state-secret", now=2001)
        self.assertEqual(first["sid"], "sid-secret")
        self.assertIsNone(self.store.consume_oauth_state("oauth-state-secret", now=2002))

    def test_handoff_is_one_time_and_not_plaintext(self):
        self.store.create_handoff("handoff-secret", "sid-secret", "/share", now=3000, ttl=60)
        with open(self.db, "rb") as f:
            raw = f.read()
        self.assertNotIn(b"handoff-secret", raw)
        self.assertNotIn(b"sid-secret", raw)
        first = self.store.consume_handoff("handoff-secret", now=3001)
        self.assertEqual(first["sid"], "sid-secret")
        self.assertIsNone(self.store.consume_handoff("handoff-secret", now=3002))

    def test_expired_state_and_session_fail_closed(self):
        self.store.upsert_session("sid", {"access_token": "x"}, now=10, ttl=2)
        self.store.create_oauth_state("state", "sid", "/share", now=10, ttl=2)
        self.assertIsNone(self.store.get_session("sid", now=12, touch=False))
        self.assertIsNone(self.store.consume_oauth_state("state", now=12))

    def test_key_rotation_can_read_old_ciphertext(self):
        self.store.upsert_session("sid", {"access_token": "old"}, now=1, ttl=100)
        new_key = Fernet.generate_key().decode()
        rotated = DurableState(self.db, [new_key, self.key])
        self.assertEqual(rotated.get_session("sid", now=2, touch=False)["access_token"], "old")
        rotated.patch_session("sid", {"access_token": "new"}, now=3, ttl=100)
        only_new = DurableState(self.db, [new_key])
        self.assertEqual(only_new.get_session("sid", now=4, touch=False)["access_token"], "new")

    def test_publication_idempotency_is_persistent(self):
        rec, created = self.store.create_publication_intent(
            "idem-1","a"*64,"acct-hash","DIRECT_POST","b"*64,now=4000
        )
        self.assertTrue(created)
        self.assertEqual(rec["state"], "RECEIVED")
        same, created2 = self.store.create_publication_intent(
            "idem-1","a"*64,"acct-hash","DIRECT_POST","b"*64,now=4001
        )
        self.assertFalse(created2)
        self.assertEqual(same["idempotency_key"], "idem-1")
        reopened = DurableState(self.db, [self.key])
        self.assertEqual(reopened.get_publication("idem-1")["state"], "RECEIVED")

    def test_publication_state_machine_rejects_invalid_transition(self):
        self.store.create_publication_intent(
            "idem-2","c"*64,"acct-hash","DIRECT_POST","d"*64,now=5000
        )
        self.store.transition_publication("idem-2","VALIDATED",now=5001)
        self.store.transition_publication("idem-2","SAFETY_APPROVED",now=5002)
        self.store.transition_publication("idem-2","PUBLISH_REQUESTED",now=5003)
        self.store.transition_publication("idem-2","UPLOAD_STARTED",now=5004,provider_publish_id="pub-1")
        self.store.transition_publication("idem-2","UPLOADED",now=5005)
        self.store.transition_publication("idem-2","PROCESSING",now=5006)
        self.store.transition_publication("idem-2","PUBLISHED",now=5007)
        self.assertEqual(self.store.get_publication_by_provider_id("pub-1")["state"], "PUBLISHED")
        with self.assertRaises(DurableStateError):
            self.store.transition_publication("idem-2","UPLOAD_STARTED",now=5008)

    def test_publication_attempt_counter_is_durable(self):
        self.store.create_publication_intent(
            "idem-3","e"*64,"acct-hash","DRAFT_UPLOAD","f"*64,now=6000
        )
        first = self.store.begin_publication_attempt("idem-3",now=6001)
        second = self.store.begin_publication_attempt("idem-3",now=6002)
        self.assertEqual(first["attempt_count"], 1)
        self.assertEqual(second["attempt_count"], 2)
        reopened = DurableState(self.db, [self.key])
        self.assertEqual(reopened.get_publication("idem-3")["attempt_count"], 2)

    def test_hard_limit_blocks_second_active_mutation(self):
        self.store.create_publication_intent(
            "idem-a","1"*64,"acct","DIRECT_POST","2"*64,now=7000
        )
        ok, reason = self.store.admit_publication("idem-a",6,24,1,2,now=7001)
        self.assertTrue(ok); self.assertIsNone(reason)
        self.store.create_publication_intent(
            "idem-b","3"*64,"acct","DIRECT_POST","4"*64,now=7002
        )
        ok2, reason2 = self.store.admit_publication("idem-b",6,24,1,2,now=7003)
        self.assertFalse(ok2)
        self.assertEqual(reason2, "active_account_limit")
        self.assertEqual(self.store.get_publication("idem-b")["state"], "FAILED")

    def test_hourly_hard_limit_persists_after_terminal_success(self):
        self.store.create_publication_intent(
            "idem-c","5"*64,"acct2","DIRECT_POST","6"*64,now=8000
        )
        ok, _ = self.store.admit_publication("idem-c",1,24,2,4,now=8001)
        self.assertTrue(ok)
        self.store.transition_publication("idem-c","SAFETY_APPROVED",now=8002)
        self.store.transition_publication("idem-c","PUBLISH_REQUESTED",now=8003)
        self.store.transition_publication("idem-c","UPLOAD_STARTED",now=8004,provider_publish_id="pub-c")
        self.store.transition_publication("idem-c","UPLOADED",now=8005)
        self.store.transition_publication("idem-c","PROCESSING",now=8006)
        self.store.transition_publication("idem-c","PUBLISHED",now=8007)
        self.store.create_publication_intent(
            "idem-d","7"*64,"acct2","DIRECT_POST","8"*64,now=8008
        )
        ok2, reason2 = self.store.admit_publication("idem-d",1,24,2,4,now=8009)
        self.assertFalse(ok2)
        self.assertEqual(reason2, "hourly_account_limit")

    def test_global_hourly_limit_bounds_multi_account_blast_radius(self):
        for idx, account in enumerate(("acct-a","acct-b"), start=1):
            idem=f"global-{idx}"
            self.store.create_publication_intent(
                idem,str(idx)*64,account,"DIRECT_POST","9"*64,now=9000+idx
            )
            ok, reason = self.store.admit_publication(
                idem,6,24,2,4,1,48,now=9010+idx
            )
            if idx == 1:
                self.assertTrue(ok); self.assertIsNone(reason)
                self.store.transition_publication(idem,"FAILED",now=9020+idx,error_code="test_terminal")
            else:
                self.assertFalse(ok)
                self.assertEqual(reason,"hourly_global_limit")

    def test_audit_trail_records_admission_and_state_without_secrets(self):
        self.store.create_publication_intent(
            "audit-1","a"*64,"acct","DIRECT_POST","b"*64,now=10000
        )
        ok, _ = self.store.admit_publication("audit-1",6,24,2,4,12,48,now=10001)
        self.assertTrue(ok)
        self.store.transition_publication("audit-1","SAFETY_APPROVED",now=10002)
        events = self.store.list_audit_events("audit-1")
        types = [e["event_type"] for e in events]
        self.assertIn("PUBLICATION_INTENT_CREATED",types)
        self.assertIn("PUBLICATION_ADMISSION",types)
        self.assertIn("PUBLICATION_STATE",types)
        joined = "\n".join(str(e) for e in events).lower()
        self.assertNotIn("access_token",joined)
        self.assertNotIn("refresh_token",joined)
        self.assertNotIn("client_secret",joined)

    def test_audit_detail_rejects_secret_field_names(self):
        with self.assertRaises(DurableStateError):
            self.store.record_audit_event(
                "BAD","BLOCK",detail={"access_token":"must-not-log"}
            )

    def test_tamper_fails_closed(self):
        self.store.upsert_session("sid", {"access_token": "x"}, now=1, ttl=100)
        with closing(sqlite3.connect(self.db)) as con:
            row = con.execute("SELECT sid_hash,payload_cipher FROM sessions").fetchone()
            damaged = bytearray(row[1]); damaged[-1] ^= 1
            con.execute("UPDATE sessions SET payload_cipher=? WHERE sid_hash=?", (bytes(damaged), row[0]))
            con.commit()
        with self.assertRaises(DurableStateError):
            self.store.get_session("sid", now=2, touch=False)


if __name__ == "__main__":
    unittest.main()

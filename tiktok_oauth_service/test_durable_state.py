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

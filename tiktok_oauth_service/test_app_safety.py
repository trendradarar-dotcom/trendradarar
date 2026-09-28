import os
import tempfile
import unittest

from cryptography.fernet import Fernet

import app


class SafetyGateTests(unittest.TestCase):
    def setUp(self):
        self.old = dict(os.environ)
        self.old_api_form_post = app.api_form_post
        app._STORE = None
        app._STORE_ERROR = ""

    def tearDown(self):
        app.api_form_post = self.old_api_form_post
        app._STORE = None
        app._STORE_ERROR = ""
        os.environ.clear()
        os.environ.update(self.old)

    def _configure_store(self):
        self.tmp = tempfile.TemporaryDirectory()
        os.environ["TIKTOK_STATE_DB_PATH"] = os.path.join(self.tmp.name, "state.sqlite3")
        os.environ["TIKTOK_STATE_ENCRYPTION_KEY"] = Fernet.generate_key().decode()
        app._STORE = None
        return app.state_store()

    def _handler(self, path):
        h = app.Handler.__new__(app.Handler)
        h.path = path
        h.js = lambda status, payload, headers=None: (status, payload)
        return h

    def test_mutations_fail_closed_by_default(self):
        os.environ.pop("TIKTOK_MUTATIONS_ENABLED", None)
        os.environ.pop("TIKTOK_KILL_SWITCH", None)
        self.assertFalse(app.mutations_allowed())
        h = self._handler("/api/post")
        status, payload = h.do_POST()
        self.assertEqual(status, 423)
        self.assertEqual(payload["error"], "tiktok_mutations_disabled")

    def test_kill_switch_overrides_explicit_enable(self):
        os.environ["TIKTOK_MUTATIONS_ENABLED"] = "true"
        os.environ["TIKTOK_KILL_SWITCH"] = "true"
        self.assertFalse(app.mutations_allowed())
        h = self._handler("/api/upload-draft")
        status, payload = h.do_POST()
        self.assertEqual(status, 423)
        self.assertTrue(payload["kill_switch_active"])

    def test_explicit_enable_routes_when_kill_switch_is_off(self):
        os.environ["TIKTOK_MUTATIONS_ENABLED"] = "true"
        os.environ["TIKTOK_KILL_SWITCH"] = "false"
        self.assertTrue(app.mutations_allowed())
        h = self._handler("/api/post")
        h.post_video = lambda p: ("routed", p.path)
        self.assertEqual(h.do_POST(), ("routed", "/api/post"))

    def test_missing_required_scope_fails_closed(self):
        sess = {"access_token":"a","refresh_token":"r","open_id":"creator","scope":"video.upload","expires_at":9999999999}
        updated, error = app.require_session_scope("sid", sess, "video.publish")
        self.assertIsNone(updated)
        self.assertEqual(error, "missing_scope")

    def test_expired_access_token_refreshes_and_rotates_refresh_token(self):
        store = self._configure_store()
        now = int(app.time.time())
        sess = {
            "access_token":"old-a",
            "refresh_token":"old-r",
            "open_id":"creator",
            "scope":"video.publish,video.upload",
            "expires_at":now-1,
            "refresh_expires_at":now+3600,
        }
        store.upsert_session("sid", sess, now=now, ttl=app.SESSION_TTL)
        app.api_form_post = lambda url, fields, timeout=20: (200, {
            "access_token":"new-a",
            "refresh_token":"new-r",
            "open_id":"creator",
            "scope":"video.publish,video.upload",
            "expires_in":86400,
            "refresh_expires_in":31536000,
        })
        updated, error = app.require_session_scope("sid", sess, "video.publish")
        self.assertIsNone(error)
        self.assertEqual(updated["access_token"], "new-a")
        self.assertEqual(updated["refresh_token"], "new-r")
        persisted = store.get_session("sid", touch=False)
        self.assertEqual(persisted["access_token"], "new-a")
        self.tmp.cleanup()

    def test_refresh_account_mismatch_fails_closed(self):
        self._configure_store()
        now = int(app.time.time())
        sess = {
            "access_token":"old-a",
            "refresh_token":"old-r",
            "open_id":"creator-a",
            "scope":"video.publish",
            "expires_at":now-1,
            "refresh_expires_at":now+3600,
        }
        app.api_form_post = lambda url, fields, timeout=20: (200, {
            "access_token":"new-a",
            "refresh_token":"new-r",
            "open_id":"creator-b",
            "scope":"video.publish",
            "expires_in":86400,
            "refresh_expires_in":31536000,
        })
        updated, error = app.require_session_scope("sid", sess, "video.publish")
        self.assertIsNone(updated)
        self.assertEqual(error, "refresh_account_mismatch")
        self.tmp.cleanup()

    def test_disconnect_revokes_then_removes_local_session(self):
        store = self._configure_store()
        now = int(app.time.time())
        sess = {
            "csrf":"csrf",
            "access_token":"token",
            "refresh_token":"refresh",
            "open_id":"creator",
            "scope":"video.publish",
            "expires_at":now+3600,
        }
        store.upsert_session("sid", sess, now=now, ttl=app.SESSION_TTL)
        app.api_form_post = lambda url, fields, timeout=20: (200,{})
        h = app.Handler.__new__(app.Handler)
        h.headers = {"X-CSRF-Token":"csrf"}
        h.get_session = lambda: ("sid", sess)
        h.js = lambda status, payload, headers=None: (status,payload)
        status, payload = h.disconnect_tiktok()
        self.assertEqual(status, 200)
        self.assertTrue(payload["remote_revoke_confirmed"])
        self.assertIsNone(store.get_session("sid", touch=False))
        self.tmp.cleanup()

    def test_retry_policy_is_zero_automatic_retries(self):
        self.assertEqual(app.MAX_AUTOMATED_RETRIES, 0)
        self.assertEqual(app.MAX_RETRY_HORIZON_SECONDS, 0)

    def test_hard_limit_defaults_are_positive_and_conservative(self):
        for name in (
            "TIKTOK_MAX_MUTATIONS_PER_HOUR",
            "TIKTOK_MAX_MUTATIONS_PER_DAY",
            "TIKTOK_MAX_ACTIVE_MUTATIONS_PER_ACCOUNT",
            "TIKTOK_MAX_ACTIVE_MUTATIONS_GLOBAL",
        ):
            os.environ.pop(name, None)
        limits = app.publication_limits()
        self.assertEqual(limits["per_hour"], 6)
        self.assertEqual(limits["per_day"], 24)
        self.assertEqual(limits["active_per_account"], 1)
        self.assertEqual(limits["active_global"], 2)


if __name__ == "__main__":
    unittest.main()

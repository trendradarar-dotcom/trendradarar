import os
import unittest

import app


class SafetyGateTests(unittest.TestCase):
    def setUp(self):
        self.old = dict(os.environ)

    def tearDown(self):
        os.environ.clear()
        os.environ.update(self.old)

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

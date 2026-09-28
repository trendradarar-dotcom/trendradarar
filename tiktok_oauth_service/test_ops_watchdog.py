import hashlib
import hmac
import importlib.util
import json
import unittest
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "tools" / "tiktok_ops_watchdog.py"
spec = importlib.util.spec_from_file_location("tiktok_ops_watchdog", SCRIPT)
watchdog = importlib.util.module_from_spec(spec)
spec.loader.exec_module(watchdog)


class _Response:
    def __init__(self, status, payload=b"{}"):
        self.status = status
        self._payload = payload

    def read(self):
        return self._payload

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


class OpsWatchdogTests(unittest.TestCase):
    def test_healthy_ops_health_sends_no_alert(self):
        payload = json.dumps({
            "ok": True,
            "durable_state_ready": True,
            "attention_required": False,
            "unknown_count": 0,
            "stale_nonterminal_count": 0,
            "active_count": 0,
            "kill_switch_active": True,
            "mutations_allowed": False,
        }).encode()
        with mock.patch.object(
            watchdog.urllib.request,
            "urlopen",
            return_value=_Response(200, payload),
        ):
            result = watchdog.fetch_health("https://example.invalid/ops/health")
        self.assertTrue(result["reachable"])
        self.assertFalse(result["attention_required"])

    def test_unknown_health_requires_attention(self):
        payload = json.dumps({
            "ok": False,
            "durable_state_ready": True,
            "attention_required": True,
            "unknown_count": 1,
            "stale_nonterminal_count": 0,
            "kill_switch_active": True,
            "mutations_allowed": False,
        }).encode()
        with mock.patch.object(
            watchdog.urllib.request,
            "urlopen",
            return_value=_Response(503, payload),
        ):
            result = watchdog.fetch_health("https://example.invalid/ops/health")
        self.assertTrue(result["attention_required"])
        alert = watchdog.build_alert(result, now=12345)
        self.assertEqual(alert["occurred_at"], 12345)
        self.assertEqual(alert["health"]["unknown_count"], 1)
        serialized = json.dumps(alert)
        self.assertNotIn("access_token", serialized)
        self.assertNotIn("refresh_token", serialized)
        self.assertNotIn("client_secret", serialized)

    def test_alert_is_hmac_signed(self):
        captured = {}

        def fake_urlopen(req, timeout=15):
            captured["body"] = req.data
            captured["signature"] = req.headers.get("X-trendradar-signature")
            return _Response(204, b"")

        alert = {
            "schema": "trendradar.tiktok.ops_alert.v1",
            "occurred_at": 123,
            "attention_required": True,
        }
        secret = "test-secret"
        with mock.patch.object(watchdog.urllib.request, "urlopen", side_effect=fake_urlopen):
            status = watchdog.send_alert(
                "https://alerts.example.invalid/tiktok",
                secret,
                alert,
            )
        self.assertEqual(status, 204)
        expected = "sha256=" + hmac.new(
            secret.encode(),
            captured["body"],
            hashlib.sha256,
        ).hexdigest()
        self.assertEqual(captured["signature"], expected)

    def test_non_https_external_urls_rejected(self):
        with self.assertRaises(watchdog.WatchdogError):
            watchdog.send_alert(
                "http://example.com/insecure",
                "secret",
                {"attention_required": True},
            )


if __name__ == "__main__":
    unittest.main()

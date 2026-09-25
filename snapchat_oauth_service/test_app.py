import os
import unittest
from unittest.mock import patch

from app import app


class DirectBridgeTests(unittest.TestCase):
    def setUp(self):
        self.client = app.test_client()

    def test_health_defaults_closed(self):
        with patch.dict(os.environ, {}, clear=True):
            response = self.client.get("/health")
            self.assertEqual(response.status_code, 200)
            body = response.get_json()
            self.assertTrue(body["ok"])
            self.assertFalse(body["config"]["direct_api_enabled"])
            self.assertFalse(body["config"]["publication_enabled"])
            self.assertTrue(body["config"]["kill_switch"])
            self.assertTrue(body["config"]["emergency_read_only"])

    def test_auth_start_is_blocked_when_direct_api_disabled(self):
        with patch.dict(os.environ, {
            "SNAPCHAT_DIRECT_API_ENABLED": "false",
        }, clear=True):
            response = self.client.get("/auth/start")
            self.assertEqual(response.status_code, 503)
            body = response.get_json()
            self.assertEqual(body["error"], "direct_api_disabled")
            self.assertEqual(body["external_side_effect"], "BLOCKED")

    def test_publish_is_blocked_when_direct_api_disabled(self):
        with patch.dict(os.environ, {
            "SNAPCHAT_DIRECT_API_ENABLED": "false",
        }, clear=True):
            response = self.client.post("/spotlight/publish")
            self.assertEqual(response.status_code, 503)
            body = response.get_json()
            self.assertEqual(body["error"], "direct_api_disabled")
            self.assertEqual(body["external_side_effect"], "BLOCKED")


if __name__ == "__main__":
    unittest.main()

import os
import unittest
from unittest.mock import patch

from app import app


def valid_body():
    return {
        "publication_id": "snap-sa-trend-001-20260925T120000Z",
        "market": "SA",
        "market_label": "السعودية",
        "language": "ar",
        "headline": "هذا ما يصعد الآن في السعودية",
        "description": "ترند سعودي مختار ومراجع",
        "media_url": "https://example.com/video.mp4",
        "duration_seconds": 35,
        "width": 1080,
        "height": 1920,
        "originality_passed": True,
        "rights_passed": True,
        "human_origin_passed": True,
        "content_origin_type": "human_source_ai_assisted",
        "visual_template_id": "snap-country-board-v1",
        "trend_id": "trend-001",
        "saudi_filter_passed": True,
        "global_selected": False,
    }


class AppTests(unittest.TestCase):
    def setUp(self):
        self.client = app.test_client()

    def test_health_is_read_only_and_fail_closed(self):
        with patch.dict(os.environ, {
            "SNAPCHAT_PUBLISH_PROVIDER": "disabled",
            "SNAPCHAT_PUBLICATION_ENABLED": "false",
            "SNAPCHAT_KILL_SWITCH": "true",
            "SNAPCHAT_EMERGENCY_READ_ONLY": "true",
        }, clear=True):
            response = self.client.get("/health")
            self.assertEqual(response.status_code, 200)
            body = response.get_json()
            self.assertTrue(body["ok"])
            self.assertEqual(body["external_publication_side_effect"], "NONE")
            self.assertEqual(body["readiness"]["provider"], "disabled")
            self.assertTrue(body["readiness"]["kill_switch"])
            self.assertTrue(body["readiness"]["emergency_read_only"])

    def test_owner_endpoint_rejects_missing_key(self):
        with patch.dict(os.environ, {
            "SNAPCHAT_PUBLISH_PROVIDER": "disabled",
            "SNAPCHAT_OWNER_KEY": "unit-test-key",
        }, clear=True):
            response = self.client.get("/admin/control-state")
            self.assertEqual(response.status_code, 401)

    def test_local_validation_passes_without_provider_and_never_publishes(self):
        with patch.dict(os.environ, {
            "SNAPCHAT_PUBLISH_PROVIDER": "disabled",
            "SNAPCHAT_OWNER_KEY": "unit-test-key",
            "SNAPCHAT_PUBLICATION_ENABLED": "false",
            "SNAPCHAT_KILL_SWITCH": "true",
            "SNAPCHAT_EMERGENCY_READ_ONLY": "true",
        }, clear=True):
            response = self.client.post(
                "/spotlight/validate",
                json=valid_body(),
                headers={"X-Owner-Key": "unit-test-key"},
            )
            self.assertEqual(response.status_code, 200)
            body = response.get_json()
            self.assertEqual(body["local_validation"], "PASS")
            self.assertEqual(body["provider_validation"], "BLOCKED_PROVIDER_NOT_SELECTED")
            self.assertEqual(body["external_publication_side_effect"], "NONE")

    def test_publish_is_blocked_with_disabled_provider(self):
        with patch.dict(os.environ, {
            "SNAPCHAT_PUBLISH_PROVIDER": "disabled",
            "SNAPCHAT_OWNER_KEY": "unit-test-key",
            "SNAPCHAT_PUBLICATION_ENABLED": "true",
            "SNAPCHAT_KILL_SWITCH": "false",
            "SNAPCHAT_EMERGENCY_READ_ONLY": "false",
        }, clear=True):
            response = self.client.post(
                "/spotlight/publish",
                json=valid_body(),
                headers={"X-Owner-Key": "unit-test-key"},
            )
            self.assertEqual(response.status_code, 403)
            body = response.get_json()
            self.assertEqual(body["error"], "provider_not_selected")
            self.assertEqual(body["external_publication_side_effect"], "BLOCKED")

    def test_response_has_correlation_and_security_headers(self):
        with patch.dict(os.environ, {
            "SNAPCHAT_PUBLISH_PROVIDER": "disabled",
        }, clear=True):
            response = self.client.get(
                "/health",
                headers={"X-Correlation-ID": "corr-20260925-0001"},
            )
            self.assertEqual(response.headers["X-Correlation-ID"], "corr-20260925-0001")
            self.assertEqual(response.headers["Cache-Control"], "no-store")
            self.assertEqual(response.headers["X-Content-Type-Options"], "nosniff")

    def test_oversized_json_request_is_rejected(self):
        with patch.dict(os.environ, {
            "SNAPCHAT_PUBLISH_PROVIDER": "disabled",
            "SNAPCHAT_OWNER_KEY": "unit-test-key",
        }, clear=True):
            body = valid_body()
            body["headline"] = "x" * (70 * 1024)
            response = self.client.post(
                "/spotlight/validate",
                json=body,
                headers={"X-Owner-Key": "unit-test-key"},
            )
            self.assertEqual(response.status_code, 413)


if __name__ == "__main__":
    unittest.main()

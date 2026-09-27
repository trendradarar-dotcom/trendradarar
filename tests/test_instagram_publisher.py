import importlib
import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(__file__))
SERVICE_DIR = os.path.join(ROOT, "instagram_oauth_service")
if SERVICE_DIR not in sys.path:
    sys.path.insert(0, SERVICE_DIR)

from publisher_runtime import IntentValidationError, PublisherRuntime


def valid_intent(**overrides):
    payload = {
        "publication_id": "pub-001",
        "content_asset_id": "asset-001",
        "video_uri": "https://media.trendradar.com.co/reels/a.mp4",
        "asset_sha256": "a" * 64,
        "caption": "Trend Radar test",
        "hashtags": ["trendradar"],
        "market": "SA",
        "language": "ar",
        "rights_status": "PASS",
        "policy_status": "PASS",
        "legal_status": "PASS",
        "commercial_status": "NOT_COMMERCIAL",
        "scheduled_time": None,
        "idempotency_key": "idem-001",
        "correlation_id": "corr-001",
        "is_ai_generated": True,
        "media": {
            "mime_type": "video/mp4",
            "size_bytes": 1024,
            "duration_seconds": 12,
            "width": 1080,
            "height": 1920,
            "fps": 30,
            "video_codec": "h264",
            "audio_codec": "aac",
        },
    }
    payload.update(overrides)
    return payload


class MemoryPublisher(PublisherRuntime):
    def __init__(self, **kwargs):
        super().__init__(
            db_connect=lambda: None,
            load_token_record=lambda: None,
            graph=lambda *a, **k: (500, {}),
            **kwargs,
        )
        self.jobs = {}
        self.events = []

    def _get_job(self, key):
        item = self.jobs.get(key)
        return dict(item) if item else None

    def _insert_job(self, intent, status):
        self.jobs[intent["idempotency_key"]] = {
            **intent,
            "account_key": self.expected_username,
            "status": status,
            "container_id": None,
            "media_id": None,
            "provider_status": None,
            "attempt_count": 0,
            "last_error_code": None,
        }

    def _transition(self, key, status, **kwargs):
        self.jobs[key]["status"] = status
        for field in ("container_id", "media_id", "provider_status"):
            if kwargs.get(field) is not None:
                self.jobs[key][field] = kwargs[field]
        if kwargs.get("error_code") is not None:
            self.jobs[key]["last_error_code"] = kwargs["error_code"]
        if kwargs.get("increment_attempt"):
            self.jobs[key]["attempt_count"] += 1

    def _event(self, key, event_type, detail=None):
        self.events.append((key, event_type, detail or {}))


class PublisherContractTests(unittest.TestCase):
    def make_runtime(self, public=False):
        return MemoryPublisher(
            expected_username="trendradarar",
            publish_secret="secret",
            public_publish_authorized=public,
            media_host_allowlist=["media.trendradar.com.co"],
            allowed_markets=["SA"],
            allowed_languages=["ar"],
            max_daily_publications=10,
            max_inflight=1,
            circuit_failure_threshold=3,
        )

    def test_m2m_authentication_is_fail_closed(self):
        runtime = self.make_runtime()
        self.assertFalse(runtime.authorize(""))
        self.assertFalse(runtime.authorize("wrong"))
        self.assertTrue(runtime.authorize("secret"))

    def test_contract_accepts_governed_ar_sa_intent(self):
        runtime = self.make_runtime()
        intent = runtime.validate_intent(valid_intent())
        self.assertEqual(intent["rights_status"], "PASS")
        self.assertEqual(intent["commercial_status"], "NOT_COMMERCIAL")
        self.assertEqual(intent["market"], "SA")
        self.assertEqual(intent["language"], "ar")

    def test_contract_rejects_unknown_rights(self):
        runtime = self.make_runtime()
        with self.assertRaises(IntentValidationError):
            runtime.validate_intent(valid_intent(rights_status="UNKNOWN"))

    def test_contract_rejects_commercial_content(self):
        runtime = self.make_runtime()
        with self.assertRaises(IntentValidationError):
            runtime.validate_intent(valid_intent(commercial_status="SPONSORED"))

    def test_contract_rejects_untrusted_media_host(self):
        runtime = self.make_runtime()
        with self.assertRaises(IntentValidationError):
            runtime.validate_intent(
                valid_intent(video_uri="https://example.com/reel.mp4")
            )

    def test_contract_rejects_backend_non_spool_path(self):
        runtime = MemoryPublisher(
            expected_username="trendradarar",
            publish_secret="secret",
            public_publish_authorized=False,
            media_host_allowlist=["trendradar-instagram-oauth.onrender.com"],
            allowed_markets=["SA"],
            allowed_languages=["ar"],
        )
        with self.assertRaises(IntentValidationError):
            runtime.validate_intent(
                valid_intent(
                    video_uri="https://trendradar-instagram-oauth.onrender.com/anything/a.mp4"
                )
            )

    def test_media_asset_probe_is_fail_closed(self):
        runtime = MemoryPublisher(
            expected_username="trendradarar",
            publish_secret="secret",
            public_publish_authorized=False,
            media_host_allowlist=["media.trendradar.com.co"],
            allowed_markets=["SA"],
            allowed_languages=["ar"],
            media_asset_probe=lambda *_: (False, "MEDIA_ASSET_NOT_ADMITTED"),
        )
        with self.assertRaises(IntentValidationError):
            runtime.validate_intent(valid_intent())


    def test_contract_rejects_ephemeral_review_media(self):
        runtime = MemoryPublisher(
            expected_username="trendradarar",
            publish_secret="secret",
            public_publish_authorized=False,
            media_host_allowlist=["trendradar-instagram-oauth.onrender.com"],
            allowed_markets=["SA"],
            allowed_languages=["ar"],
        )
        with self.assertRaises(IntentValidationError):
            runtime.validate_intent(
                valid_intent(
                    video_uri="https://trendradar-instagram-oauth.onrender.com/media/x.mp4"
                )
            )

    def test_public_disabled_creates_hold_without_provider_call(self):
        runtime = self.make_runtime(public=False)
        status, result = runtime.start(valid_intent())
        self.assertEqual(status, 202)
        self.assertEqual(result["status"], "HOLD_PUBLIC_DISABLED")
        self.assertFalse(result["public_publish_authorized"])

    def test_duplicate_is_idempotent(self):
        runtime = self.make_runtime(public=False)
        first_status, first = runtime.start(valid_intent())
        second_status, second = runtime.start(valid_intent())
        self.assertEqual(first_status, 202)
        self.assertEqual(second_status, 200)
        self.assertTrue(second["replayed"])
        self.assertEqual(first["publication_id"], second["publication_id"])

    def test_same_key_different_contract_conflicts(self):
        runtime = self.make_runtime(public=False)
        runtime.start(valid_intent())
        changed = valid_intent(caption="different")
        status, result = runtime.start(changed)
        self.assertEqual(status, 409)
        self.assertEqual(result["error"], "IDEMPOTENCY_CONFLICT")


class FlaskBoundaryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        os.environ["SESSION_SECRET"] = "test-session-secret"
        os.environ["INSTAGRAM_EXPECTED_USERNAME"] = "trendradarar"
        os.environ["INSTAGRAM_PUBLIC_PUBLISH_AUTHORIZED"] = "false"
        if "app" in sys.modules:
            del sys.modules["app"]
        cls.module = importlib.import_module("app")
        cls.client = cls.module.app.test_client()

    def test_fresh_browser_cannot_open_share(self):
        response = self.client.get("/share")
        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.get_json()["error"], "OWNER_SESSION_REQUIRED")

    def test_fresh_browser_cannot_submit_reel(self):
        response = self.client.post("/api/reel", data={"consent": "true"})
        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.get_json()["error"], "OWNER_SESSION_REQUIRED")

    def test_machine_media_upload_requires_m2m_secret(self):
        response = self.client.post("/internal/publish/media")
        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.get_json()["error"], "UNAUTHORIZED")

    def test_mp4_signature_preflight(self):
        fake = b"\x00\x00\x00\x18ftypisom" + b"x" * 20 + b"avc1" + b"x" * 20 + b"mp4a"
        ok, error = self.module._mp4_signature_preflight(fake, "aac")
        self.assertTrue(ok)
        self.assertIsNone(error)

    def test_mp4_signature_rejects_non_mp4(self):
        ok, error = self.module._mp4_signature_preflight(b"not-an-mp4-container", "")
        self.assertFalse(ok)
        self.assertEqual(error, "MEDIA_CONTAINER_NOT_MP4")

    def test_machine_publish_requires_m2m_secret(self):
        response = self.client.post("/internal/publish/reel", json=valid_intent())
        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.get_json()["error"], "UNAUTHORIZED")

    def test_deauthorize_rejects_unsigned_request(self):
        response = self.client.post("/deauthorize")
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.get_json()["error"], "INVALID_SIGNED_REQUEST")

    def test_health_keeps_public_publish_closed(self):
        response = self.client.get("/health")
        self.assertEqual(response.status_code, 200)
        body = response.get_json()
        self.assertFalse(body["public_publish_authorized"])
        self.assertFalse(body["browser_public_publish_enabled"])


if __name__ == "__main__":
    unittest.main()

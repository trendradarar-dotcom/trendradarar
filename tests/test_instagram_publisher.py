import importlib
import os
import sys
import unittest
from contextlib import contextmanager

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
        "commercial_status": "EDITORIAL_ORIGINAL",
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
            "video_bitrate_bps": 8_000_000,
            "audio_sample_rate_hz": 48_000,
            "audio_bitrate_bps": 128_000,
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
            expected_professional_user_id="17841428134382903",
            **kwargs,
        )
        self.jobs = {}
        self.events = []

    def _get_job(self, key):
        item = self.jobs.get(key)
        return dict(item) if item else None

    def _get_job_by_content_identity(self, content_asset_id, asset_sha256):
        for item in self.jobs.values():
            if item.get("account_key") == self.expected_username and (
                item.get("content_asset_id") == content_asset_id
                or item.get("asset_sha256") == asset_sha256
            ):
                return dict(item)
        return None

    def _insert_job(self, intent, status):
        if intent["idempotency_key"] in self.jobs:
            return False
        if self._get_job_by_content_identity(intent["content_asset_id"], intent["asset_sha256"]):
            return False
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
        return True

    @contextmanager
    def _advisory_lock(self, name):
        yield

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

    def _unresolved_ambiguity_exists(self, exclude_key=None):
        return any(
            k != exclude_key and v.get("status") in {
                "UNKNOWN", "PUBLISHED_UNVERIFIED", "PUBLISH_REQUESTED"
            }
            for k, v in self.jobs.items()
        )


class PublisherContractTests(unittest.TestCase):
    def make_runtime(self, public=False, enabled=False):
        return MemoryPublisher(
            expected_username="trendradarar",
            publish_secret="secret",
            public_publish_authorized=public,
            publish_enabled=enabled,
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
        self.assertEqual(intent["commercial_status"], "EDITORIAL_ORIGINAL")
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
            publish_enabled=False,
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
            publish_enabled=False,
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
            publish_enabled=False,
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

    def test_kill_switch_blocks_even_when_owner_authorizes_public_publish(self):
        runtime = self.make_runtime(public=True, enabled=False)
        status, result = runtime.start(valid_intent())
        self.assertEqual(status, 202)
        self.assertEqual(result["status"], "HOLD_KILL_SWITCH")
        self.assertTrue(result["public_publish_authorized"])
        self.assertFalse(result["publish_enabled"])

    def test_editorial_original_is_the_only_phase_one_commercial_class(self):
        runtime = self.make_runtime()
        self.assertEqual(
            runtime.validate_intent(valid_intent())["commercial_status"],
            "EDITORIAL_ORIGINAL",
        )
        for blocked in (
            "OWN_PRODUCT",
            "SPONSORED",
            "AFFILIATE",
            "PAID_PARTNERSHIP",
            "UNKNOWN_COMMERCIAL",
            "NOT_COMMERCIAL",
        ):
            with self.subTest(blocked=blocked):
                with self.assertRaises(IntentValidationError):
                    runtime.validate_intent(valid_intent(commercial_status=blocked))

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

    def test_same_content_with_new_idempotency_key_is_blocked(self):
        runtime = self.make_runtime(public=False)
        runtime.start(valid_intent())
        changed = valid_intent(
            publication_id="pub-002",
            idempotency_key="idem-002",
            correlation_id="corr-002",
        )
        status, result = runtime.start(changed)
        self.assertEqual(status, 409)
        self.assertEqual(result["error"], "CONTENT_ALREADY_BOUND_TO_PUBLICATION")

    def test_same_bytes_with_new_content_asset_id_is_blocked(self):
        runtime = self.make_runtime(public=False)
        runtime.start(valid_intent())
        changed = valid_intent(
            publication_id="pub-003",
            content_asset_id="asset-003",
            idempotency_key="idem-003",
            correlation_id="corr-003",
        )
        status, result = runtime.start(changed)
        self.assertEqual(status, 409)
        self.assertEqual(result["error"], "CONTENT_ALREADY_BOUND_TO_PUBLICATION")

    def test_meta_reel_media_limits_fail_closed(self):
        runtime = self.make_runtime()
        for overrides in (
            {"media": {**valid_intent()["media"], "duration_seconds": 2}},
            {"media": {**valid_intent()["media"], "fps": 22}},
            {"media": {**valid_intent()["media"], "width": 1921}},
            {"media": {**valid_intent()["media"], "video_bitrate_bps": 25_000_001}},
            {"media": {**valid_intent()["media"], "audio_sample_rate_hz": 44_100}},
            {"media": {**valid_intent()["media"], "audio_bitrate_bps": 128_001}},
        ):
            with self.subTest(overrides=overrides):
                with self.assertRaises(IntentValidationError):
                    runtime.validate_intent(valid_intent(**overrides))

    def test_publish_requested_after_restart_becomes_unknown_without_retry(self):
        runtime = self.make_runtime(public=True, enabled=True)
        intent = runtime.validate_intent(valid_intent())
        runtime._insert_job(intent, "PUBLISH_REQUESTED")
        status, result = runtime.reconcile(intent["idempotency_key"])
        self.assertEqual(status, 409)
        self.assertEqual(result["status"], "UNKNOWN")
        self.assertEqual(result["last_error_code"], "PUBLISH_OUTCOME_AMBIGUOUS_AFTER_RESTART")

    def test_unknown_content_cannot_be_republished_with_new_key(self):
        runtime = self.make_runtime(public=False)
        intent = runtime.validate_intent(valid_intent())
        runtime._insert_job(intent, "UNKNOWN")
        changed = valid_intent(
            publication_id="pub-unknown-2",
            idempotency_key="idem-unknown-2",
            correlation_id="corr-unknown-2",
        )
        status, result = runtime.start(changed)
        self.assertEqual(status, 409)
        self.assertEqual(result["error"], "CONTENT_ALREADY_BOUND_TO_PUBLICATION")

    def test_unresolved_unknown_blocks_new_publication(self):
        runtime = self.make_runtime(public=True, enabled=True)
        old = runtime.validate_intent(valid_intent())
        runtime._insert_job(old, "UNKNOWN")
        changed = valid_intent(
            publication_id="pub-next",
            content_asset_id="asset-next",
            asset_sha256="b" * 64,
            idempotency_key="idem-next",
            correlation_id="corr-next",
        )
        status, result = runtime.start(changed)
        self.assertEqual(status, 503)
        self.assertEqual(result["status"], "HOLD_CIRCUIT_OPEN")
        self.assertEqual(result["last_error_code"], "UNRESOLVED_PUBLICATION_AMBIGUITY")

    def test_exact_professional_user_id_is_required(self):
        runtime = PublisherRuntime(
            db_connect=lambda: None,
            load_token_record=lambda: {
                "username": "trendradarar",
                "account_type": "BUSINESS",
                "user_id": "wrong-id",
                "granted_permissions": [
                    "instagram_business_basic",
                    "instagram_business_content_publish",
                ],
                "access_token": "token",
            },
            graph=lambda *a, **k: (200, {
                "username": "trendradarar",
                "account_type": "BUSINESS",
                "user_id": "wrong-id",
            }),
            expected_username="trendradarar",
            expected_professional_user_id="17841428134382903",
            publish_secret="secret",
            public_publish_authorized=False,
            publish_enabled=False,
            media_host_allowlist=["media.trendradar.com.co"],
            allowed_markets=["SA"],
            allowed_languages=["ar"],
        )
        _, error = runtime._credential_gate()
        self.assertEqual(error, "PROFESSIONAL_USER_ID_MISMATCH")


class FlaskBoundaryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        os.environ["SESSION_SECRET"] = "test-session-secret"
        os.environ["INSTAGRAM_EXPECTED_USERNAME"] = "trendradarar"
        os.environ["INSTAGRAM_EXPECTED_PROFESSIONAL_USER_ID"] = "17841428134382903"
        os.environ["INSTAGRAM_PUBLIC_PUBLISH_AUTHORIZED"] = "false"
        if "app" in sys.modules:
            del sys.modules["app"]
        cls.module = importlib.import_module("app")
        cls.client = cls.module.app.test_client()

    def setUp(self):
        self.module.TOKEN_STORE.clear()
        with self.client.session_transaction() as sess:
            sess.clear()

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

    def test_disconnect_get_is_not_a_mutating_route(self):
        response = self.client.get("/disconnect")
        self.assertEqual(response.status_code, 405)

    def test_disconnect_post_requires_owner_session(self):
        response = self.client.post("/disconnect")
        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.get_json()["error"], "OWNER_SESSION_REQUIRED")

    def test_deauthorize_rejects_unsigned_request(self):
        response = self.client.post("/deauthorize")
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.get_json()["error"], "INVALID_SIGNED_REQUEST")

    def test_public_oauth_state_is_one_time(self):
        issued = set()
        original_store = self.module._store_public_oauth_nonce
        original_consume = self.module._consume_public_oauth_nonce
        try:
            self.module._store_public_oauth_nonce = lambda nonce, ttl_seconds=900: (issued.add(nonce) or True)
            self.module._consume_public_oauth_nonce = lambda nonce: (issued.remove(nonce) is None) if nonce in issued else False
            state = self.module._make_public_oauth_state()
            self.assertTrue(state)
            self.assertIsNotNone(self.module._verify_public_oauth_state(state))
            self.assertIsNone(self.module._verify_public_oauth_state(state))
        finally:
            self.module._store_public_oauth_nonce = original_store
            self.module._consume_public_oauth_nonce = original_consume

    def test_browser_review_flow_cannot_mutate_when_no_publish(self):
        with self.client.session_transaction() as sess:
            sess["instagram_owner_verified"] = True
            sess["sid"] = "owner-test"
        self.module.TOKEN_STORE["owner-test"] = {
            "username": "trendradarar",
            "user_id": "17841428134382903",
            "account_type": "BUSINESS",
        }
        response = self.client.post("/api/reel", data={"consent": "true"})
        self.assertEqual(response.status_code, 423)
        self.assertEqual(response.get_json()["error"], "INSTAGRAM_MUTATIONS_DISABLED")

    def test_health_keeps_public_publish_closed(self):
        response = self.client.get("/health")
        self.assertEqual(response.status_code, 200)
        body = response.get_json()
        self.assertFalse(body["public_publish_authorized"])
        self.assertFalse(body["instagram_publish_enabled"])
        self.assertFalse(body["browser_public_publish_enabled"])
        self.assertTrue(body["exact_account_binding_configured"])


if __name__ == "__main__":
    unittest.main()

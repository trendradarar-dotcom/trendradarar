import os
import sys
import threading
import unittest
from concurrent.futures import ThreadPoolExecutor

import psycopg

ROOT = os.path.dirname(os.path.dirname(__file__))
SERVICE_DIR = os.path.join(ROOT, "instagram_oauth_service")
if SERVICE_DIR not in sys.path:
    sys.path.insert(0, SERVICE_DIR)

from publisher_runtime import PublisherRuntime


DSN = os.getenv("INSTAGRAM_TEST_DATABASE_URL", "").strip()


def valid_intent(**overrides):
    payload = {
        "publication_id": "pg-pub-001",
        "content_asset_id": "pg-asset-001",
        "video_uri": "https://media.trendradar.com.co/reels/a.mp4",
        "asset_sha256": "a" * 64,
        "caption": "Trend Radar PostgreSQL integration",
        "hashtags": ["trendradar"],
        "market": "SA",
        "language": "ar",
        "rights_status": "PASS",
        "policy_status": "PASS",
        "legal_status": "PASS",
        "commercial_status": "EDITORIAL_ORIGINAL",
        "scheduled_time": None,
        "idempotency_key": "pg-idem-001",
        "correlation_id": "pg-corr-001",
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


class GraphStub:
    def __init__(self):
        self.lock = threading.Lock()
        self.media_create_calls = 0
        self.publish_calls = 0

    def __call__(self, method, path, token, *, params=None, data=None):
        if method == "GET" and path == "me":
            return 200, {
                "id": "app-scoped",
                "user_id": "17841428134382903",
                "username": "trendradarar",
                "account_type": "BUSINESS",
            }
        if method == "GET" and path.endswith("/content_publishing_limit"):
            return 200, {"data": [{"quota_usage": 0}]}
        if method == "POST" and path.endswith("/media_publish"):
            with self.lock:
                self.publish_calls += 1
                n = self.publish_calls
            return 200, {"id": f"media-{n}"}
        if method == "POST" and path.endswith("/media"):
            with self.lock:
                self.media_create_calls += 1
                n = self.media_create_calls
            return 200, {"id": f"container-{n}"}
        if method == "GET" and path.startswith("media-"):
            return 200, {
                "id": path,
                "media_type": "VIDEO",
                "media_product_type": "REELS",
                "permalink": "https://instagram.example/reel",
                "timestamp": "2026-09-28T00:00:00+0000",
            }
        if method == "GET" and path.startswith("container-"):
            return 200, {"status_code": "FINISHED", "status": "FINISHED"}
        return 500, {"error": "unexpected graph call"}


@unittest.skipUnless(DSN, "INSTAGRAM_TEST_DATABASE_URL is required")
class PostgresIntegrationTests(unittest.TestCase):
    def connect(self):
        return psycopg.connect(DSN, connect_timeout=10)

    def setUp(self):
        with self.connect() as conn:
            with conn.cursor() as cur:
                cur.execute("DROP TABLE IF EXISTS instagram_publication_events")
                cur.execute("DROP TABLE IF EXISTS instagram_publication_jobs")
            conn.commit()
        self.graph = GraphStub()
        self.runtime = self.make_runtime(public=True, enabled=True)
        self.runtime._ensure_tables()

    def make_runtime(self, *, public=True, enabled=True, max_daily=10):
        return PublisherRuntime(
            db_connect=self.connect,
            load_token_record=lambda: {
                "username": "trendradarar",
                "account_type": "BUSINESS",
                "user_id": "17841428134382903",
                "granted_permissions": [
                    "instagram_business_basic",
                    "instagram_business_content_publish",
                ],
                "access_token": "test-token",
            },
            graph=self.graph,
            expected_username="trendradarar",
            expected_professional_user_id="17841428134382903",
            publish_secret="test-secret",
            public_publish_authorized=public,
            publish_enabled=enabled,
            media_host_allowlist=["media.trendradar.com.co"],
            allowed_markets=["SA"],
            allowed_languages=["ar"],
            max_daily_publications=max_daily,
            max_inflight=2,
            circuit_failure_threshold=3,
            max_unpublished_queue=10,
            max_api_mutations_per_minute=10,
            max_provider_mutations_per_job=2,
        )

    def test_concurrent_duplicate_reservation_is_db_safe(self):
        runtime = self.make_runtime(public=False, enabled=False)
        first = valid_intent()
        second = valid_intent(
            publication_id="pg-pub-002",
            idempotency_key="pg-idem-002",
            correlation_id="pg-corr-002",
        )

        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(runtime.start, (first, second)))

        codes = sorted(code for code, _ in results)
        self.assertEqual(codes, [202, 409])
        with self.connect() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT COUNT(*) FROM instagram_publication_jobs")
                self.assertEqual(cur.fetchone()[0], 1)

    def test_daily_blast_radius_is_atomic_across_workers(self):
        runtime = self.make_runtime(public=True, enabled=True, max_daily=1)
        first = runtime.validate_intent(valid_intent())
        second = runtime.validate_intent(
            valid_intent(
                publication_id="pg-pub-002",
                content_asset_id="pg-asset-002",
                asset_sha256="b" * 64,
                idempotency_key="pg-idem-002",
                correlation_id="pg-corr-002",
            )
        )
        runtime._insert_job(first, "NEW")
        runtime._transition(first["idempotency_key"], "READY", container_id="container-a")
        runtime._insert_job(second, "NEW")
        runtime._transition(second["idempotency_key"], "READY", container_id="container-b")

        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(
                pool.map(
                    runtime.reconcile,
                    (first["idempotency_key"], second["idempotency_key"]),
                )
            )

        self.assertEqual(self.graph.publish_calls, 1)
        statuses = {body["status"] for _, body in results}
        self.assertIn("VERIFIED", statuses)
        self.assertIn("HOLD_BLAST_RADIUS", statuses)

    def test_new_state_resumes_safely_after_restart(self):
        runtime = self.make_runtime(public=True, enabled=True)
        intent = runtime.validate_intent(valid_intent())
        runtime._insert_job(intent, "NEW")

        status, body = runtime.reconcile(intent["idempotency_key"])

        self.assertEqual(status, 202)
        self.assertEqual(body["status"], "CONTAINER_CREATED")
        self.assertEqual(self.graph.media_create_calls, 1)

    def test_container_create_requested_never_retries_after_restart(self):
        runtime = self.make_runtime(public=True, enabled=True)
        intent = runtime.validate_intent(valid_intent())
        runtime._insert_job(intent, "NEW")
        runtime._transition(
            intent["idempotency_key"],
            "CONTAINER_CREATE_REQUESTED",
            provider_status="REQUESTED",
            increment_attempt=True,
        )

        status, body = runtime.reconcile(intent["idempotency_key"])

        self.assertEqual(status, 409)
        self.assertEqual(body["status"], "UNKNOWN")
        self.assertEqual(
            body["last_error_code"],
            "CREATE_CONTAINER_OUTCOME_AMBIGUOUS_AFTER_RESTART",
        )
        self.assertEqual(self.graph.media_create_calls, 0)

    def test_state_and_audit_event_rollback_atomically(self):
        runtime = self.make_runtime(public=True, enabled=True)
        intent = runtime.validate_intent(valid_intent())
        runtime._insert_job(intent, "NEW")

        with self.connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    ALTER TABLE instagram_publication_events
                    ADD CONSTRAINT reject_state_transition_for_test
                    CHECK (event_type <> 'STATE_TRANSITION')
                    """
                )
            conn.commit()

        with self.assertRaises(Exception):
            runtime._transition(
                intent["idempotency_key"],
                "PROCESSING",
                provider_status="IN_PROGRESS",
            )

        with self.connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT status FROM instagram_publication_jobs WHERE idempotency_key = %s",
                    (intent["idempotency_key"],),
                )
                self.assertEqual(cur.fetchone()[0], "NEW")
                cur.execute(
                    "SELECT COUNT(*) FROM instagram_publication_events "
                    "WHERE idempotency_key = %s AND event_type = 'STATE_TRANSITION'",
                    (intent["idempotency_key"],),
                )
                self.assertEqual(cur.fetchone()[0], 0)


if __name__ == "__main__":
    unittest.main()

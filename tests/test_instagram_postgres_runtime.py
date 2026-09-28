import os
import sys
import threading
import time
import unittest
from concurrent.futures import ThreadPoolExecutor

import psycopg

ROOT = os.path.dirname(os.path.dirname(__file__))
SERVICE_DIR = os.path.join(ROOT, "instagram_oauth_service")
if SERVICE_DIR not in sys.path:
    sys.path.insert(0, SERVICE_DIR)

from publisher_runtime import PublisherRuntime


DSN = os.getenv("INSTAGRAM_TEST_DATABASE_URL", "").strip()


def valid_payload(index=1, *, content_asset_id=None, asset_sha256=None):
    return {
        "publication_id": f"pg-pub-{index}",
        "content_asset_id": content_asset_id or f"pg-asset-{index}",
        "video_uri": f"https://media.trendradar.com.co/reels/{index}.mp4",
        "asset_sha256": asset_sha256 or (f"{index:x}"[-1] * 64),
        "caption": f"Postgres concurrency test {index}",
        "hashtags": ["trendradar"],
        "market": "SA",
        "language": "ar",
        "rights_status": "PASS",
        "policy_status": "PASS",
        "legal_status": "PASS",
        "commercial_status": "EDITORIAL_ORIGINAL",
        "scheduled_time": None,
        "idempotency_key": f"pg-idem-{index}",
        "correlation_id": f"pg-corr-{index}",
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


@unittest.skipUnless(DSN, "INSTAGRAM_TEST_DATABASE_URL is required")
class PostgresRuntimeTests(unittest.TestCase):
    def db_connect(self):
        return psycopg.connect(DSN, connect_timeout=5)

    def token_record(self):
        return {
            "username": "trendradarar",
            "account_type": "BUSINESS",
            "user_id": "17841428134382903",
            "granted_permissions": [
                "instagram_business_basic",
                "instagram_business_content_publish",
            ],
            "access_token": "test-token",
        }

    def make_runtime(self, *, graph=None, max_daily=10):
        return PublisherRuntime(
            db_connect=self.db_connect,
            load_token_record=self.token_record,
            graph=graph or (lambda *a, **k: (500, {})),
            expected_username="trendradarar",
            expected_professional_user_id="17841428134382903",
            publish_secret="test-secret",
            public_publish_authorized=True,
            publish_enabled=True,
            media_host_allowlist=["media.trendradar.com.co"],
            allowed_markets=["SA"],
            allowed_languages=["ar"],
            max_daily_publications=max_daily,
            max_inflight=10,
            circuit_failure_threshold=10,
            max_unpublished_queue=20,
            max_api_mutations_per_minute=50,
            max_provider_mutations_per_job=3,
        )

    def setUp(self):
        runtime = self.make_runtime()
        runtime._ensure_tables()
        with self.db_connect() as conn:
            with conn.cursor() as cur:
                cur.execute("DROP TRIGGER IF EXISTS reject_ready_event ON instagram_publication_events")
                cur.execute("DROP FUNCTION IF EXISTS reject_ready_event()")
                cur.execute("DELETE FROM instagram_publication_events")
                cur.execute("DELETE FROM instagram_publication_jobs")
            conn.commit()

    def tearDown(self):
        with self.db_connect() as conn:
            with conn.cursor() as cur:
                cur.execute("DROP TRIGGER IF EXISTS reject_ready_event ON instagram_publication_events")
                cur.execute("DROP FUNCTION IF EXISTS reject_ready_event()")
            conn.commit()

    def test_concurrent_duplicate_reservation_allows_exactly_one_job(self):
        shared_asset = "pg-shared-asset"
        shared_hash = "a" * 64

        def reserve(index):
            runtime = self.make_runtime()
            intent = runtime.validate_intent(
                valid_payload(
                    index,
                    content_asset_id=shared_asset,
                    asset_sha256=shared_hash,
                )
            )
            return runtime._insert_job(intent, "NEW")

        with ThreadPoolExecutor(max_workers=8) as pool:
            results = list(pool.map(reserve, range(1, 9)))

        self.assertEqual(sum(bool(x) for x in results), 1)
        with self.db_connect() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT COUNT(*) FROM instagram_publication_jobs")
                self.assertEqual(cur.fetchone()[0], 1)
                cur.execute(
                    "SELECT COUNT(*) FROM instagram_publication_events "
                    "WHERE event_type = 'JOB_CREATED'"
                )
                self.assertEqual(cur.fetchone()[0], 1)

    def test_state_and_audit_event_rollback_atomically(self):
        runtime = self.make_runtime()
        intent = runtime.validate_intent(valid_payload(20))
        self.assertTrue(runtime._insert_job(intent, "NEW"))

        with self.db_connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    CREATE FUNCTION reject_ready_event() RETURNS trigger
                    LANGUAGE plpgsql AS $$
                    BEGIN
                        RAISE EXCEPTION 'injected audit failure';
                    END;
                    $$
                    """
                )
                cur.execute(
                    """
                    CREATE TRIGGER reject_ready_event
                    BEFORE INSERT ON instagram_publication_events
                    FOR EACH ROW
                    WHEN (
                        NEW.event_type = 'STATE_TRANSITION'
                        AND NEW.safe_detail->>'status' = 'READY'
                    )
                    EXECUTE FUNCTION reject_ready_event()
                    """
                )
            conn.commit()

        with self.assertRaises(psycopg.Error):
            runtime._transition(intent["idempotency_key"], "READY")

        with self.db_connect() as conn:
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

    def test_advisory_lock_serializes_independent_workers(self):
        runtime_a = self.make_runtime()
        runtime_b = self.make_runtime()
        holder_entered = threading.Event()
        release_holder = threading.Event()
        waiter_entered = threading.Event()

        def holder():
            with runtime_a._advisory_lock("instagram-multi-worker-test"):
                holder_entered.set()
                release_holder.wait(5)

        def waiter():
            holder_entered.wait(5)
            with runtime_b._advisory_lock("instagram-multi-worker-test"):
                waiter_entered.set()

        with ThreadPoolExecutor(max_workers=2) as pool:
            first = pool.submit(holder)
            second = pool.submit(waiter)
            self.assertTrue(holder_entered.wait(2))
            self.assertFalse(waiter_entered.wait(0.35))
            release_holder.set()
            self.assertTrue(waiter_entered.wait(2))
            first.result(timeout=3)
            second.result(timeout=3)

    def test_daily_blast_radius_holds_second_concurrent_publish(self):
        publish_lock = threading.Lock()
        publish_calls = []

        def graph(method, path, token, **kwargs):
            if method == "GET" and path == "me":
                return 200, {
                    "username": "trendradarar",
                    "account_type": "BUSINESS",
                    "user_id": "17841428134382903",
                }
            if method == "POST" and path == "17841428134382903/media_publish":
                with publish_lock:
                    publish_calls.append(kwargs["data"]["creation_id"])
                    media_id = f"media-{len(publish_calls)}"
                time.sleep(0.15)
                return 200, {"id": media_id}
            if method == "GET" and path.startswith("media-"):
                return 200, {
                    "id": path,
                    "media_type": "VIDEO",
                    "media_product_type": "REELS",
                }
            raise AssertionError((method, path, kwargs))

        runtime = self.make_runtime(graph=graph, max_daily=1)
        keys = []
        for index in (31, 32):
            intent = runtime.validate_intent(valid_payload(index))
            self.assertTrue(runtime._insert_job(intent, "NEW"))
            runtime._transition(
                intent["idempotency_key"],
                "READY",
                container_id=f"container-{index}",
                provider_status="FINISHED",
            )
            keys.append(intent["idempotency_key"])

        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(runtime.reconcile, keys))

        codes = sorted(code for code, _ in results)
        statuses = sorted(result["status"] for _, result in results)
        self.assertEqual(codes, [200, 429])
        self.assertEqual(
            statuses,
            ["HOLD_BLAST_RADIUS", "VERIFIED"],
        )
        self.assertEqual(len(publish_calls), 1)


if __name__ == "__main__":
    unittest.main()

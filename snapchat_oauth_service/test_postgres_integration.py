import os
import threading
import unittest
import uuid

import psycopg

from state_store import DurableStateStore, StateStoreError


POSTGRES_URL = os.getenv("SNAPCHAT_TEST_POSTGRES_URL", "")


@unittest.skipUnless(POSTGRES_URL.startswith("postgres"), "PostgreSQL integration URL not configured")
class PostgreSQLDurableStateIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.store = DurableStateStore(POSTGRES_URL)
        self.assertTrue(self.store.production_durable)
        self.store.init_schema()
        with psycopg.connect(POSTGRES_URL) as conn:
            with conn.cursor() as cur:
                cur.execute("TRUNCATE TABLE snapchat_publications, snapchat_oauth_tokens, snapchat_oauth_states, snapchat_oauth_intents")
            conn.commit()

    def test_token_and_oauth_state_survive_fresh_store_instance(self):
        intent = "intent-" + uuid.uuid4().hex
        state = "state-" + uuid.uuid4().hex
        browser = "browser-" + uuid.uuid4().hex

        self.store.create_oauth_intent(intent, 300)
        self.assertTrue(self.store.consume_oauth_intent(intent))
        self.assertFalse(self.store.consume_oauth_intent(intent))

        self.store.create_oauth_state(state, browser, 300)
        self.assertTrue(self.store.consume_oauth_state(state, browser))
        self.assertFalse(self.store.consume_oauth_state(state, browser))

        self.store.save_tokens(
            access_cipher="encrypted-access",
            refresh_cipher="encrypted-refresh",
            expires_at=4102444800,
            scope="snapchat-profile-api",
            profile_id="profile-postgres-1",
            username="trendradarar",
        )

        fresh = DurableStateStore(POSTGRES_URL)
        status = fresh.token_status()
        self.assertTrue(status["connected"])
        self.assertTrue(status["access_credential_present"])
        self.assertTrue(status["refresh_credential_present"])
        self.assertEqual(status["profile_id"], "profile-postgres-1")
        self.assertEqual(status["username"], "trendradarar")

    def test_unknown_state_survives_restart_and_blocks_blind_retry(self):
        profile_id = "profile-postgres-unknown"
        publication_id = "publication-postgres-unknown-0001"
        admission = self.store.begin_publication(
            profile_id=profile_id,
            publication_id=publication_id,
            correlation_id="corr-postgres-unknown-0001",
            description="unknown-state-test",
            media_sha256="a" * 64,
            duration=35.0,
            width=1080,
            height=1920,
            max_hour=10,
            max_day=20,
            max_concurrent=1,
            max_attempts=2,
            retry_horizon_seconds=1800,
        )
        self.assertTrue(admission["created"])

        self.store.transition(
            profile_id=profile_id,
            publication_id=publication_id,
            allowed_from=("RECEIVED",),
            new_state="VALIDATED",
        )
        self.store.transition(
            profile_id=profile_id,
            publication_id=publication_id,
            allowed_from=("VALIDATED",),
            new_state="MEDIA_CREATING",
        )
        self.store.transition(
            profile_id=profile_id,
            publication_id=publication_id,
            allowed_from=("MEDIA_CREATING",),
            new_state="MEDIA_UPLOADING",
        )
        self.store.transition(
            profile_id=profile_id,
            publication_id=publication_id,
            allowed_from=("MEDIA_UPLOADING",),
            new_state="SUBMITTING",
            mark_submit_started=True,
        )
        self.store.transition(
            profile_id=profile_id,
            publication_id=publication_id,
            allowed_from=("SUBMITTING",),
            new_state="UNKNOWN",
            last_error="simulated_timeout",
        )

        fresh = DurableStateStore(POSTGRES_URL)
        row = fresh.get_publication(profile_id, publication_id)
        self.assertEqual(row["state"], "UNKNOWN")

        duplicate = fresh.begin_publication(
            profile_id=profile_id,
            publication_id=publication_id,
            correlation_id="corr-postgres-unknown-0002",
            description="unknown-state-test",
            media_sha256="a" * 64,
            duration=35.0,
            width=1080,
            height=1920,
            max_hour=10,
            max_day=20,
            max_concurrent=1,
            max_attempts=2,
            retry_horizon_seconds=1800,
        )
        self.assertFalse(duplicate["created"])
        self.assertFalse(duplicate["retry_admitted"])
        self.assertEqual(duplicate["row"]["state"], "UNKNOWN")

    def test_postgres_advisory_lock_enforces_single_concurrent_admission(self):
        profile_id = "profile-postgres-concurrent"
        barrier = threading.Barrier(2)
        outcomes = []
        outcome_lock = threading.Lock()

        def attempt(suffix):
            local = DurableStateStore(POSTGRES_URL)
            publication_id = f"publication-postgres-concurrent-{suffix}"
            barrier.wait(timeout=10)
            try:
                result = local.begin_publication(
                    profile_id=profile_id,
                    publication_id=publication_id,
                    correlation_id=f"corr-postgres-concurrent-{suffix}",
                    description="concurrency-test",
                    media_sha256=suffix * 64,
                    duration=35.0,
                    width=1080,
                    height=1920,
                    max_hour=10,
                    max_day=20,
                    max_concurrent=1,
                    max_attempts=2,
                    retry_horizon_seconds=1800,
                )
                outcome = ("admitted", result["row"]["publication_id"])
            except StateStoreError as exc:
                outcome = ("blocked", str(exc))
            with outcome_lock:
                outcomes.append(outcome)

        threads = [
            threading.Thread(target=attempt, args=("1",), daemon=True),
            threading.Thread(target=attempt, args=("2",), daemon=True),
        ]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=15)
            self.assertFalse(thread.is_alive(), "concurrency test thread did not finish")

        self.assertEqual(len(outcomes), 2)
        admitted = [value for kind, value in outcomes if kind == "admitted"]
        blocked = [value for kind, value in outcomes if kind == "blocked"]
        self.assertEqual(len(admitted), 1)
        self.assertEqual(blocked, ["maximum_concurrent_publications_reached"])

    def test_hourly_hard_limit_persists_across_store_instances(self):
        profile_id = "profile-postgres-hourly"
        self.store.begin_publication(
            profile_id=profile_id,
            publication_id="publication-postgres-hourly-0001",
            correlation_id="corr-postgres-hourly-0001",
            description="first",
            media_sha256="1" * 64,
            duration=35.0,
            width=1080,
            height=1920,
            max_hour=1,
            max_day=10,
            max_concurrent=10,
            max_attempts=2,
            retry_horizon_seconds=1800,
        )

        fresh = DurableStateStore(POSTGRES_URL)
        with self.assertRaises(StateStoreError) as ctx:
            fresh.begin_publication(
                profile_id=profile_id,
                publication_id="publication-postgres-hourly-0002",
                correlation_id="corr-postgres-hourly-0002",
                description="second",
                media_sha256="2" * 64,
                duration=35.0,
                width=1080,
                height=1920,
                max_hour=1,
                max_day=10,
                max_concurrent=10,
                max_attempts=2,
                retry_horizon_seconds=1800,
            )
        self.assertEqual(str(ctx.exception), "maximum_hourly_publications_reached")


if __name__ == "__main__":
    unittest.main()

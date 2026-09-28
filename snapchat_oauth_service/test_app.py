import io
import os
import tempfile
import unittest
from urllib.parse import parse_qs, urlparse
from unittest.mock import patch

from cryptography.fernet import Fernet

import app as app_module
from state_store import DurableStateStore, StateStoreError

app = app_module.app


class DirectBridgeRemediationTests(unittest.TestCase):
    def setUp(self):
        self.client = app.test_client()
        with app_module._token_lock:
            app_module._runtime_tokens.clear()

    def _env(self, db_url, **overrides):
        env = {
            "SNAPCHAT_DIRECT_API_ENABLED": "true",
            "SNAPCHAT_PUBLICATION_ENABLED": "false",
            "SNAPCHAT_KILL_SWITCH": "true",
            "SNAPCHAT_EMERGENCY_READ_ONLY": "true",
            "SNAPCHAT_TARGET_ACCOUNT_VERIFIED": "false",
            "SNAPCHAT_DURABLE_RECONCILIATION_READY": "false",
            "SNAPCHAT_ALERTING_READY": "false",
            "SNAPCHAT_PRODUCTION_ASSURANCE_READY": "false",
            "SNAPCHAT_HARD_LIMITS_VERIFIED": "false",
            "SNAPCHAT_CLIENT_ID": "client-id",
            "SNAPCHAT_CLIENT_SECRET": "client-secret",
            "SNAPCHAT_REDIRECT_URI": "https://example.test/auth/callback",
            "SNAPCHAT_STATE_SECRET": "state-secret-for-tests",
            "SNAPCHAT_TOKEN_ENCRYPTION_KEY": Fernet.generate_key().decode("ascii"),
            "SNAPCHAT_PUBLIC_PROFILE_ID": "3f5d8925-0da7-4da6-9b87-d8aa326026a0",
            "SNAPCHAT_EXPECTED_USERNAME": "trendradarar",
            "SNAPCHAT_OWNER_KEY": "owner-key",
            "SNAPCHAT_DATABASE_URL": db_url,
        }
        env.update(overrides)
        return env

    def _sqlite_url(self):
        handle = tempfile.NamedTemporaryFile(prefix="snap-state-", suffix=".sqlite3", delete=False)
        handle.close()
        self.addCleanup(lambda: os.path.exists(handle.name) and os.remove(handle.name))
        return "sqlite:///" + handle.name

    def _begin_oauth(self, env):
        with patch.dict(os.environ, env, clear=True):
            response = self.client.post("/admin/oauth-intent", headers={"X-Owner-Key": "owner-key"})
            self.assertEqual(response.status_code, 200)
            start_url = response.get_json()["start_url"]
            intent = parse_qs(urlparse(start_url).query)["intent"][0]
            start = self.client.get("/auth/start", query_string={"intent": intent}, follow_redirects=False)
            self.assertEqual(start.status_code, 302)
            location = start.headers["Location"]
            state = parse_qs(urlparse(location).query)["state"][0]
            return state

    def test_health_defaults_fail_closed_and_sqlite_is_not_production_durable(self):
        db_url = self._sqlite_url()
        env = self._env(db_url)
        with patch.dict(os.environ, env, clear=True):
            response = self.client.get("/health")
            self.assertEqual(response.status_code, 200)
            body = response.get_json()
            self.assertTrue(body["ok"])
            self.assertFalse(body["config"]["publication_enabled"])
            self.assertTrue(body["config"]["kill_switch"])
            self.assertTrue(body["config"]["emergency_read_only"])
            self.assertTrue(body["config"]["durable_store_ready"])
            self.assertFalse(body["config"]["durable_store_production"])
            self.assertIn("production_requires_postgresql_state_store", body["publication_gate_errors"])

    def test_oauth_intent_requires_owner_authorization(self):
        db_url = self._sqlite_url()
        env = self._env(db_url)
        with patch.dict(os.environ, env, clear=True):
            response = self.client.post("/admin/oauth-intent")
            self.assertEqual(response.status_code, 401)

    def test_auth_start_rejects_missing_or_reused_intent(self):
        db_url = self._sqlite_url()
        env = self._env(db_url)
        with patch.dict(os.environ, env, clear=True):
            missing = self.client.get("/auth/start")
            self.assertEqual(missing.status_code, 403)

            intent_response = self.client.post("/admin/oauth-intent", headers={"X-Owner-Key": "owner-key"})
            intent = parse_qs(urlparse(intent_response.get_json()["start_url"]).query)["intent"][0]
            first = self.client.get("/auth/start", query_string={"intent": intent}, follow_redirects=False)
            self.assertEqual(first.status_code, 302)
            second = self.client.get("/auth/start", query_string={"intent": intent}, follow_redirects=False)
            self.assertEqual(second.status_code, 403)

    def test_oauth_state_is_one_time_browser_bound_and_tokens_persist(self):
        db_url = self._sqlite_url()
        env = self._env(db_url)
        with patch.dict(os.environ, env, clear=True):
            state = self._begin_oauth(env)
            fake_payload = {
                "access_token": "access-token",
                "refresh_token": "refresh-token",
                "expires_in": 3600,
                "scope": "snapchat-profile-api",
            }
            with patch.object(app_module, "_exchange_code", return_value=fake_payload),                  patch.object(
                     app_module,
                     "_fetch_exact_public_profile",
                     return_value={
                         "id": env["SNAPCHAT_PUBLIC_PROFILE_ID"],
                         "username": "trendradarar",
                         "display_name": "Trend Radar",
                     },
                 ),                  patch.object(app_module, "_verify_authorized_profile_access", return_value=None):
                callback = self.client.get("/auth/callback", query_string={"code": "one-time-code", "state": state})
                self.assertEqual(callback.status_code, 200)
                body = callback.get_json()
                self.assertEqual(body["exact_profile_binding"], "PASS")
                self.assertTrue(body["refresh_credential_persisted"])

                replay = self.client.get("/auth/callback", query_string={"code": "one-time-code", "state": state})
                self.assertEqual(replay.status_code, 400)

            fresh_store = DurableStateStore(db_url)
            status = fresh_store.token_status()
            self.assertTrue(status["connected"])
            self.assertTrue(status["refresh_present"])
            self.assertEqual(status["profile_id"], env["SNAPCHAT_PUBLIC_PROFILE_ID"])
            self.assertEqual(status["username"], "trendradarar")

    def test_oauth_binding_failure_does_not_persist_tokens(self):
        db_url = self._sqlite_url()
        env = self._env(db_url)
        with patch.dict(os.environ, env, clear=True):
            state = self._begin_oauth(env)
            fake_payload = {
                "access_token": "access-token",
                "refresh_token": "refresh-token",
                "expires_in": 3600,
                "scope": "snapchat-profile-api",
            }
            with patch.object(app_module, "_exchange_code", return_value=fake_payload),                  patch.object(app_module, "_fetch_exact_public_profile", side_effect=RuntimeError("public_profile_username_mismatch")):
                callback = self.client.get("/auth/callback", query_string={"code": "code", "state": state})
                self.assertEqual(callback.status_code, 502)

            status = DurableStateStore(db_url).token_status()
            self.assertFalse(status["connected"])
            self.assertFalse(status["refresh_present"])

    def test_disconnect_invalidates_persisted_tokens(self):
        db_url = self._sqlite_url()
        env = self._env(db_url)
        with patch.dict(os.environ, env, clear=True):
            app_module._store_tokens(
                {
                    "access_token": "access-token",
                    "refresh_token": "refresh-token",
                    "expires_in": 3600,
                    "scope": "snapchat-profile-api",
                },
                env["SNAPCHAT_PUBLIC_PROFILE_ID"],
                "trendradarar",
            )
            before = app_module._store().token_status()
            self.assertTrue(before["connected"])

            response = self.client.post("/admin/disconnect", headers={"X-Owner-Key": "owner-key"})
            self.assertEqual(response.status_code, 200)
            after = DurableStateStore(db_url).token_status()
            self.assertFalse(after["connected"])
            self.assertFalse(after["refresh_present"])

    def test_direct_publication_gate_requires_all_assurance_controls(self):
        db_url = self._sqlite_url()
        env = self._env(
            db_url,
            SNAPCHAT_PUBLICATION_ENABLED="true",
            SNAPCHAT_KILL_SWITCH="false",
            SNAPCHAT_EMERGENCY_READ_ONLY="false",
        )
        with patch.dict(os.environ, env, clear=True):
            errors = app_module._production_gate_errors()
            self.assertIn("target_account_not_verified", errors)
            self.assertIn("durable_reconciliation_not_ready", errors)
            self.assertIn("alerting_not_ready", errors)
            self.assertIn("production_assurance_not_ready", errors)
            self.assertIn("hard_limits_not_verified", errors)
            self.assertIn("production_requires_postgresql_state_store", errors)
            self.assertIn("durable_oauth_connection_not_ready", errors)

    def test_publish_duplicate_is_blocked_after_first_remote_submit(self):
        db_url = self._sqlite_url()
        env = self._env(db_url)
        publication_id = "snap-sa-trend-001-20260928T010000Z"
        form = {
            "publication_id": publication_id,
            "description": "اختبار آمن",
            "locale": "ar_SA",
        }

        with patch.dict(os.environ, env, clear=True),              patch.object(app_module, "_publication_control_gate", return_value=None),              patch.object(app_module, "_access_token", return_value="access"),              patch.object(
                 app_module,
                 "_fetch_exact_public_profile",
                 return_value={"id": env["SNAPCHAT_PUBLIC_PROFILE_ID"], "username": "trendradarar", "display_name": "Trend Radar"},
             ),              patch.object(app_module, "_verify_authorized_profile_access", return_value=None),              patch.object(app_module, "probe_video", return_value={"width": 1080, "height": 1920, "duration_seconds": 35.0, "codec": "h264"}),              patch.object(app_module, "_create_media", return_value={"media_id": "media-1", "add_path": "/add", "finalize_path": "/final"}),              patch.object(app_module, "_upload_encrypted_media", return_value={"request_status": "SUCCESS"}),              patch.object(app_module, "_post_spotlight", return_value={"request_status": "SUCCESS", "spotlight_id": "spotlight_12345678"}) as post_mock:

            first = self.client.post(
                "/spotlight/publish",
                data={**form, "video": (io.BytesIO(b"not-a-real-video-but-probe-is-mocked"), "video.mp4", "video/mp4")},
                headers={"X-Owner-Key": "owner-key"},
                content_type="multipart/form-data",
            )
            self.assertEqual(first.status_code, 201)

            second = self.client.post(
                "/spotlight/publish",
                data={**form, "video": (io.BytesIO(b"same-video"), "video.mp4", "video/mp4")},
                headers={"X-Owner-Key": "owner-key"},
                content_type="multipart/form-data",
            )
            self.assertEqual(second.status_code, 409)
            self.assertEqual(second.get_json()["error"], "duplicate_or_unreconciled_publication")
            self.assertEqual(post_mock.call_count, 1)

            row = DurableStateStore(db_url).get_publication(env["SNAPCHAT_PUBLIC_PROFILE_ID"], publication_id)
            self.assertEqual(row["state"], "SUBMITTED")
            self.assertEqual(row["remote_spotlight_id"], "spotlight_12345678")

    def test_timeout_after_submit_becomes_unknown_and_never_blind_retries(self):
        db_url = self._sqlite_url()
        env = self._env(db_url)
        publication_id = "snap-sa-trend-002-20260928T010000Z"
        form = {
            "publication_id": publication_id,
            "description": "اختبار حالة غير معروفة",
            "locale": "ar_SA",
        }

        with patch.dict(os.environ, env, clear=True),              patch.object(app_module, "_publication_control_gate", return_value=None),              patch.object(app_module, "_access_token", return_value="access"),              patch.object(
                 app_module,
                 "_fetch_exact_public_profile",
                 return_value={"id": env["SNAPCHAT_PUBLIC_PROFILE_ID"], "username": "trendradarar", "display_name": "Trend Radar"},
             ),              patch.object(app_module, "_verify_authorized_profile_access", return_value=None),              patch.object(app_module, "probe_video", return_value={"width": 1080, "height": 1920, "duration_seconds": 35.0, "codec": "h264"}),              patch.object(app_module, "_create_media", return_value={"media_id": "media-2", "add_path": "/add", "finalize_path": "/final"}),              patch.object(app_module, "_upload_encrypted_media", return_value={"request_status": "SUCCESS"}),              patch.object(app_module, "_post_spotlight", side_effect=requests.Timeout("timeout")) as post_mock:

            first = self.client.post(
                "/spotlight/publish",
                data={**form, "video": (io.BytesIO(b"video-a"), "video.mp4", "video/mp4")},
                headers={"X-Owner-Key": "owner-key"},
                content_type="multipart/form-data",
            )
            self.assertEqual(first.status_code, 502)
            self.assertEqual(first.get_json()["external_publication_side_effect"], "UNKNOWN_REQUIRES_RECONCILIATION")

            second = self.client.post(
                "/spotlight/publish",
                data={**form, "video": (io.BytesIO(b"video-b"), "video.mp4", "video/mp4")},
                headers={"X-Owner-Key": "owner-key"},
                content_type="multipart/form-data",
            )
            self.assertEqual(second.status_code, 409)
            self.assertEqual(post_mock.call_count, 1)

            row = DurableStateStore(db_url).get_publication(env["SNAPCHAT_PUBLIC_PROFILE_ID"], publication_id)
            self.assertEqual(row["state"], "UNKNOWN")

    def test_real_media_metadata_gate_is_used_by_validation_endpoint(self):
        db_url = self._sqlite_url()
        env = self._env(db_url)
        with patch.dict(os.environ, env, clear=True),              patch.object(app_module, "probe_video", return_value={"width": 1080, "height": 1920, "duration_seconds": 20.0, "codec": "h264"}):
            response = self.client.post(
                "/spotlight/validate",
                data={
                    "publication_id": "snap-sa-trend-003-20260928T010000Z",
                    "description": "اختبار",
                    "locale": "ar_SA",
                    "video": (io.BytesIO(b"video"), "video.mp4", "video/mp4"),
                },
                headers={"X-Owner-Key": "owner-key"},
                content_type="multipart/form-data",
            )
            self.assertEqual(response.status_code, 400)
            self.assertIn("duration_below_internal_30_second_floor", response.get_json()["errors"])


class StateStoreRecoveryTests(unittest.TestCase):
    def _store(self):
        handle = tempfile.NamedTemporaryFile(prefix="snap-state-recovery-", suffix=".sqlite3", delete=False)
        handle.close()
        self.addCleanup(lambda: os.path.exists(handle.name) and os.remove(handle.name))
        url = "sqlite:///" + handle.name
        return url, DurableStateStore(url)

    def test_publication_state_survives_new_process_store_instance(self):
        url, store = self._store()
        store.init_schema()
        profile_id = "profile-1"
        publication_id = "publication-12345678"
        admission = store.begin_publication(
            profile_id=profile_id,
            publication_id=publication_id,
            correlation_id="corr-12345678",
            description="desc",
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
        store.transition(
            profile_id=profile_id,
            publication_id=publication_id,
            allowed_from=("RECEIVED",),
            new_state="SUBMITTING",
            mark_submit_started=True,
        )

        fresh = DurableStateStore(url)
        row = fresh.get_publication(profile_id, publication_id)
        self.assertEqual(row["state"], "SUBMITTING")

        duplicate = fresh.begin_publication(
            profile_id=profile_id,
            publication_id=publication_id,
            correlation_id="corr-87654321",
            description="desc",
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
        self.assertEqual(duplicate["row"]["state"], "SUBMITTING")

    def test_concurrent_blast_radius_gate_blocks_second_active_publication(self):
        _, store = self._store()
        store.begin_publication(
            profile_id="profile-1",
            publication_id="publication-11111111",
            correlation_id="corr-11111111",
            description="one",
            media_sha256="1" * 64,
            duration=35.0,
            width=1080,
            height=1920,
            max_hour=10,
            max_day=20,
            max_concurrent=1,
            max_attempts=2,
            retry_horizon_seconds=1800,
        )
        with self.assertRaises(StateStoreError) as ctx:
            store.begin_publication(
                profile_id="profile-1",
                publication_id="publication-22222222",
                correlation_id="corr-22222222",
                description="two",
                media_sha256="2" * 64,
                duration=35.0,
                width=1080,
                height=1920,
                max_hour=10,
                max_day=20,
                max_concurrent=1,
                max_attempts=2,
                retry_horizon_seconds=1800,
            )
        self.assertEqual(str(ctx.exception), "maximum_concurrent_publications_reached")


if __name__ == "__main__":
    unittest.main()

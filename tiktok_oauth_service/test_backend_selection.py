import os
import tempfile
import unittest
from unittest import mock

from cryptography.fernet import Fernet

from durable_state import DurableState, DurableStateError


class BackendSelectionTests(unittest.TestCase):
    def test_development_defaults_to_sqlite(self):
        with tempfile.TemporaryDirectory() as td:
            env = {
                "TIKTOK_STATE_BACKEND": "sqlite",
                "TIKTOK_RUNTIME_MODE": "development",
                "TIKTOK_STATE_DB_PATH": os.path.join(td, "state.sqlite3"),
                "TIKTOK_STATE_ENCRYPTION_KEY": Fernet.generate_key().decode(),
            }
            with mock.patch.dict(os.environ, env, clear=False):
                store = DurableState.from_env()
                self.assertEqual(store.health()["backend"], "sqlite")

    def test_production_refuses_sqlite_without_fallback(self):
        env = {
            "TIKTOK_STATE_BACKEND": "sqlite",
            "TIKTOK_RUNTIME_MODE": "production",
            "TIKTOK_STATE_DB_PATH": "/tmp/should-not-open.sqlite3",
            "TIKTOK_STATE_ENCRYPTION_KEY": Fernet.generate_key().decode(),
        }
        with mock.patch.dict(os.environ, env, clear=False):
            with self.assertRaises(DurableStateError):
                DurableState.from_env()

    def test_production_postgres_requires_database_url(self):
        env = {
            "TIKTOK_STATE_BACKEND": "postgresql",
            "TIKTOK_RUNTIME_MODE": "production",
            "TIKTOK_POSTGRES_URL": "",
            "TIKTOK_STATE_ENCRYPTION_KEY": Fernet.generate_key().decode(),
        }
        with mock.patch.dict(os.environ, env, clear=False):
            with self.assertRaises(DurableStateError):
                DurableState.from_env()

    def test_missing_backend_fails_closed(self):
        env = {
            "TIKTOK_STATE_BACKEND": "",
            "TIKTOK_RUNTIME_MODE": "test",
            "TIKTOK_STATE_ENCRYPTION_KEY": Fernet.generate_key().decode(),
        }
        with mock.patch.dict(os.environ, env, clear=False):
            with self.assertRaises(DurableStateError):
                DurableState.from_env()

    def test_missing_runtime_mode_fails_closed(self):
        with tempfile.TemporaryDirectory() as td:
            env = {
                "TIKTOK_STATE_BACKEND": "sqlite",
                "TIKTOK_RUNTIME_MODE": "",
                "TIKTOK_STATE_DB_PATH": os.path.join(td, "state.sqlite3"),
                "TIKTOK_STATE_ENCRYPTION_KEY": Fernet.generate_key().decode(),
            }
            with mock.patch.dict(os.environ, env, clear=False):
                with self.assertRaises(DurableStateError):
                    DurableState.from_env()

    def test_invalid_postgres_url_fails_closed(self):
        env = {
            "TIKTOK_STATE_BACKEND": "postgresql",
            "TIKTOK_RUNTIME_MODE": "production",
            "TIKTOK_POSTGRES_URL": "sqlite:///not-postgres",
            "TIKTOK_STATE_ENCRYPTION_KEY": Fernet.generate_key().decode(),
        }
        with mock.patch.dict(os.environ, env, clear=False):
            with self.assertRaises(DurableStateError):
                DurableState.from_env()

    def test_unknown_backend_fails_closed(self):
        env = {
            "TIKTOK_STATE_BACKEND": "memory",
            "TIKTOK_RUNTIME_MODE": "development",
            "TIKTOK_STATE_ENCRYPTION_KEY": Fernet.generate_key().decode(),
        }
        with mock.patch.dict(os.environ, env, clear=False):
            with self.assertRaises(DurableStateError):
                DurableState.from_env()


if __name__ == "__main__":
    unittest.main()

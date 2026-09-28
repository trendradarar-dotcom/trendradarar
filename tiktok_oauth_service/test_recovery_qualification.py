import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from cryptography.fernet import Fernet


class RecoveryQualificationToolTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(__file__).resolve().parents[1]
        self.script = self.root / "tools" / "tiktok_recovery_qualification.py"
        self.env = dict(os.environ)
        self.env["TIKTOK_STATE_DB_PATH"] = str(Path(self.tmp.name) / "state.sqlite3")
        self.env["TIKTOK_STATE_ENCRYPTION_KEY"] = Fernet.generate_key().decode()

    def tearDown(self):
        self.tmp.cleanup()

    def run_tool(self, *args):
        cp = subprocess.run(
            [sys.executable, str(self.script), *args],
            cwd=str(self.root),
            env=self.env,
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(cp.returncode, 0, cp.stderr + cp.stdout)
        return json.loads(cp.stdout.strip())

    def test_marker_restart_backup_restore_round_trip(self):
        written = self.run_tool("write-marker")
        marker_sha = written["marker_sha256"]
        self.assertTrue(marker_sha)

        # New process simulates restart/reopen of the state backend.
        verified = self.run_tool("verify-marker", "--expected-sha256", marker_sha)
        self.assertTrue(verified["ok"])

        backup = str(Path(self.tmp.name) / "off-runtime-backup.sqlite3")
        backed = self.run_tool("backup", "--destination", backup)
        self.assertEqual(backed["marker_sha256"], marker_sha)
        self.assertTrue(Path(backup).is_file())

        target = str(Path(self.tmp.name) / "isolated-restore.sqlite3")
        restored = self.run_tool(
            "restore-verify",
            "--backup", backup,
            "--target", target,
            "--expected-sha256", marker_sha,
        )
        self.assertEqual(restored["marker_sha256"], marker_sha)
        self.assertTrue(Path(target).is_file())

        cleaned = self.run_tool("cleanup-marker")
        self.assertTrue(cleaned["deleted"])


if __name__ == "__main__":
    unittest.main()

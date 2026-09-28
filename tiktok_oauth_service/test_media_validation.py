import base64
import unittest
from pathlib import Path

from media_validation import MediaValidationError, validate_mp4


class MediaValidationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        raw = Path("demo_video.b64").read_text(encoding="utf-8").strip()
        cls.demo = base64.b64decode(raw)

    def test_verified_demo_passes_strict_validator(self):
        info = validate_mp4(self.demo, 100 * 1024 * 1024, max_duration_sec=60)
        self.assertEqual(info["container"], "mp4")
        self.assertEqual(info["codec"], "h264")
        self.assertGreaterEqual(info["width"], 240)
        self.assertGreaterEqual(info["height"], 240)
        self.assertGreater(info["duration_sec"], 0)

    def test_truncated_media_fails_closed(self):
        with self.assertRaises(MediaValidationError):
            validate_mp4(self.demo[:64], 100 * 1024 * 1024, max_duration_sec=60)

    def test_non_mp4_fails_closed(self):
        with self.assertRaises(MediaValidationError):
            validate_mp4(b"not-an-mp4-payload", 100 * 1024 * 1024)

    def test_oversize_policy_fails_before_publish(self):
        with self.assertRaises(MediaValidationError):
            validate_mp4(self.demo, len(self.demo) - 1)


if __name__ == "__main__":
    unittest.main()

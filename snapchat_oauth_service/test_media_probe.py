import os
import subprocess
import tempfile
import unittest

import imageio_ffmpeg

from media_probe import MediaProbeError, probe_video, validate_spotlight_media


class MediaProbeIntegrationTests(unittest.TestCase):
    def test_corrupt_mp4_is_rejected_by_real_probe(self):
        with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as handle:
            handle.write(b"not-a-valid-mp4")
            path = handle.name
        self.addCleanup(lambda: os.path.exists(path) and os.remove(path))

        with self.assertRaises(MediaProbeError):
            probe_video(path)

    def test_real_generated_mp4_metadata_is_measured(self):
        ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
        with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as handle:
            path = handle.name
        self.addCleanup(lambda: os.path.exists(path) and os.remove(path))

        subprocess.run(
            [
                ffmpeg,
                "-y",
                "-f",
                "lavfi",
                "-i",
                "color=c=black:s=540x960:d=1",
                "-an",
                "-c:v",
                "libx264",
                "-pix_fmt",
                "yuv420p",
                "-t",
                "1",
                path,
            ],
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=30,
        )

        meta = probe_video(path)
        self.assertEqual(meta["width"], 540)
        self.assertEqual(meta["height"], 960)
        self.assertGreater(meta["duration_seconds"], 0)
        self.assertLess(meta["duration_seconds"], 2)
        errors = validate_spotlight_media(meta)
        self.assertIn("duration_below_internal_30_second_floor", errors)


if __name__ == "__main__":
    unittest.main()

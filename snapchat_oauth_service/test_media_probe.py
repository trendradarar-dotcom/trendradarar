import os
import subprocess
import tempfile
import unittest

import imageio_ffmpeg

from media_probe import MediaProbeError, probe_video, validate_spotlight_media


class MediaProbeIntegrationTests(unittest.TestCase):
    def _temp_mp4_path(self):
        handle = tempfile.NamedTemporaryFile(suffix=".mp4", delete=False)
        path = handle.name
        handle.close()
        self.addCleanup(lambda: os.path.exists(path) and os.remove(path))
        return path

    def _generate_valid_mp4(self, duration=4):
        ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
        path = self._temp_mp4_path()
        subprocess.run(
            [
                ffmpeg,
                "-y",
                "-f",
                "lavfi",
                "-i",
                f"testsrc2=size=270x480:rate=24:duration={duration}",
                "-an",
                "-c:v",
                "libx264",
                "-pix_fmt",
                "yuv420p",
                "-preset",
                "ultrafast",
                "-crf",
                "18",
                "-movflags",
                "+faststart",
                path,
            ],
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=30,
        )
        return path

    def _copy_with_late_payload_corruption(self, source):
        target = self._temp_mp4_path()
        with open(source, "rb") as handle:
            data = bytearray(handle.read())
        marker = data.find(b"mdat")
        self.assertGreater(marker, 0, "generated MP4 does not contain mdat")
        payload_start = marker + 4
        payload_len = len(data) - payload_start
        self.assertGreater(payload_len, 4096)

        start = payload_start + int(payload_len * 0.70)
        end = min(len(data) - 16, start + max(4096, payload_len // 5))
        self.assertGreater(end, start)

        pattern = bytes(((index * 73) + 19) % 256 for index in range(end - start))
        data[start:end] = pattern
        with open(target, "wb") as handle:
            handle.write(data)
        return target

    def _copy_with_late_truncation(self, source):
        target = self._temp_mp4_path()
        with open(source, "rb") as handle:
            data = handle.read()
        marker = data.find(b"mdat")
        self.assertGreater(marker, 0, "generated MP4 does not contain mdat")
        payload_start = marker + 4
        cutoff = payload_start + int((len(data) - payload_start) * 0.70)
        self.assertGreater(cutoff, payload_start)
        with open(target, "wb") as handle:
            handle.write(data[:cutoff])
        return target

    def test_corrupt_mp4_is_rejected_by_real_probe(self):
        path = self._temp_mp4_path()
        with open(path, "wb") as handle:
            handle.write(b"not-a-valid-mp4")

        with self.assertRaises(MediaProbeError):
            probe_video(path)

    def test_real_generated_mp4_metadata_is_measured(self):
        ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
        path = self._temp_mp4_path()

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

    def test_late_stream_corruption_after_valid_start_is_rejected(self):
        valid = self._generate_valid_mp4(duration=4)
        corrupt = self._copy_with_late_payload_corruption(valid)

        # Prove the container still starts normally: metadata and an early frame
        # are readable before the deliberately corrupted later payload.
        reader = imageio_ffmpeg.read_frames(corrupt, pix_fmt="rgb24")
        try:
            meta = next(reader)
            self.assertEqual(tuple(meta["size"]), (270, 480))
            first_frame = next(reader)
            self.assertGreater(len(first_frame), 0)
        finally:
            reader.close()

        with self.assertRaises(MediaProbeError):
            probe_video(corrupt)

    def test_late_truncation_after_valid_container_metadata_is_rejected(self):
        valid = self._generate_valid_mp4(duration=4)
        truncated = self._copy_with_late_truncation(valid)

        reader = imageio_ffmpeg.read_frames(truncated, pix_fmt="rgb24")
        try:
            meta = next(reader)
            self.assertEqual(tuple(meta["size"]), (270, 480))
        finally:
            reader.close()

        with self.assertRaises(MediaProbeError):
            probe_video(truncated)


if __name__ == "__main__":
    unittest.main()

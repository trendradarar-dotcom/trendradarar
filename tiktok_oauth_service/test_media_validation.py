import base64
import struct
import unittest
from pathlib import Path

from media_validation import MediaValidationError, validate_mp4


def box(kind, payload):
    return struct.pack(">I4s", 8 + len(payload), kind) + payload


def synthetic_structural_h264_mp4():
    ftyp = box(b"ftyp", b"isom" + struct.pack(">I", 0x200) + b"isomavc1")
    mvhd_payload = bytearray(20)
    mvhd_payload[0] = 0
    mvhd_payload[12:16] = struct.pack(">I", 1000)
    mvhd_payload[16:20] = struct.pack(">I", 3000)
    mvhd = box(b"mvhd", bytes(mvhd_payload))

    tkhd_payload = bytearray(92)
    tkhd_payload[0] = 0
    tkhd_payload[-8:-4] = struct.pack(">I", 720 << 16)
    tkhd_payload[-4:] = struct.pack(">I", 1280 << 16)
    tkhd = box(b"tkhd", bytes(tkhd_payload))

    avc1_entry = struct.pack(">I4s", 16, b"avc1") + b"\x00" * 8
    stsd_payload = b"\x00\x00\x00\x00" + struct.pack(">I", 1) + avc1_entry
    stsd = box(b"stsd", stsd_payload)
    stbl = box(b"stbl", stsd)
    minf = box(b"minf", stbl)
    mdia = box(b"mdia", minf)
    trak = box(b"trak", tkhd + mdia)
    moov = box(b"moov", mvhd + trak)
    mdat = box(b"mdat", b"\x00" * 64)
    return ftyp + moov + mdat


class MediaValidationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        raw = Path("demo_video.b64").read_text(encoding="utf-8").strip()
        cls.legacy_demo = base64.b64decode(raw)
        cls.structural_sample = synthetic_structural_h264_mp4()

    def test_structurally_valid_h264_sample_passes_policy_parser(self):
        info = validate_mp4(
            self.structural_sample,
            100 * 1024 * 1024,
            max_duration_sec=60,
        )
        self.assertEqual(info["container"], "mp4")
        self.assertEqual(info["codec"], "h264")
        self.assertEqual(info["width"], 720)
        self.assertEqual(info["height"], 1280)
        self.assertAlmostEqual(info["duration_sec"], 3.0)

    def test_legacy_private_demo_is_rejected_if_structurally_truncated(self):
        with self.assertRaises(MediaValidationError):
            validate_mp4(self.legacy_demo, 100 * 1024 * 1024, max_duration_sec=60)

    def test_truncated_media_fails_closed(self):
        with self.assertRaises(MediaValidationError):
            validate_mp4(self.structural_sample[:64], 100 * 1024 * 1024, max_duration_sec=60)

    def test_non_mp4_fails_closed(self):
        with self.assertRaises(MediaValidationError):
            validate_mp4(b"not-an-mp4-payload", 100 * 1024 * 1024)

    def test_oversize_policy_fails_before_publish(self):
        with self.assertRaises(MediaValidationError):
            validate_mp4(self.structural_sample, len(self.structural_sample) - 1)


if __name__ == "__main__":
    unittest.main()

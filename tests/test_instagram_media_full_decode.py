import io
import os
import sys
import unittest

import av


ROOT = os.path.dirname(os.path.dirname(__file__))
SERVICE_DIR = os.path.join(ROOT, "instagram_oauth_service")
if SERVICE_DIR not in sys.path:
    sys.path.insert(0, SERVICE_DIR)

os.environ.setdefault("SESSION_SECRET", "r5-media-test-session")
os.environ.setdefault("INSTAGRAM_EXPECTED_USERNAME", "trendradarar")
os.environ.setdefault(
    "INSTAGRAM_EXPECTED_PROFESSIONAL_USER_ID",
    "17841428134382903",
)
os.environ.setdefault("INSTAGRAM_PUBLIC_PUBLISH_AUTHORIZED", "false")
os.environ.setdefault("INSTAGRAM_PUBLISH_ENABLED", "false")

import app as service_app


def build_valid_mp4():
    buffer = io.BytesIO()
    with av.open(buffer, mode="w", format="mp4") as output:
        video = output.add_stream("libx264", rate=30)
        video.width = 320
        video.height = 240
        video.pix_fmt = "yuv420p"
        video.bit_rate = 500_000

        audio = output.add_stream("aac", rate=48_000)
        audio.layout = "stereo"
        audio.bit_rate = 96_000

        audio_pts = 0
        for index in range(120):
            frame = av.VideoFrame(320, 240, "yuv420p")
            for plane_index, plane in enumerate(frame.planes):
                value = 16 + (index % 200) if plane_index == 0 else 128
                plane.update(bytes([value]) * plane.buffer_size)
            frame.pts = index
            for packet in video.encode(frame):
                output.mux(packet)

            # 1,600 samples per 30fps video frame = exactly 48,000 samples/s.
            remaining = 1_600
            while remaining:
                sample_count = min(1_024, remaining)
                audio_frame = av.AudioFrame(
                    format="fltp",
                    layout="stereo",
                    samples=sample_count,
                )
                audio_frame.sample_rate = 48_000
                audio_frame.pts = audio_pts
                audio_pts += sample_count
                remaining -= sample_count
                for plane in audio_frame.planes:
                    plane.update(b"\x00" * plane.buffer_size)
                for packet in audio.encode(audio_frame):
                    output.mux(packet)

        for packet in video.encode():
            output.mux(packet)
        for packet in audio.encode():
            output.mux(packet)

    return buffer.getvalue()


def packet_locations(blob, stream_kind):
    locations = []
    with av.open(io.BytesIO(blob), mode="r") as container:
        stream = (
            container.streams.video[0]
            if stream_kind == "video"
            else container.streams.audio[0]
        )
        for packet in container.demux(stream):
            if packet.size and packet.pos is not None and packet.pos >= 0:
                locations.append((int(packet.pos), int(packet.size), packet.pts))
    return locations


def corrupt_packet_length_prefix(blob, stream_kind, packet_index):
    locations = packet_locations(blob, stream_kind)
    position, size, pts = locations[packet_index]
    mutable = bytearray(blob)
    corrupt_bytes = min(4, size)
    mutable[position : position + corrupt_bytes] = b"\xff" * corrupt_bytes
    return bytes(mutable), {
        "packet_count": len(locations),
        "packet_index": packet_index,
        "position": position,
        "size": size,
        "pts": pts,
    }


def demux_only_succeeds(blob):
    try:
        packet_count = 0
        with av.open(io.BytesIO(blob), mode="r") as container:
            for packet in container.demux():
                if packet.size:
                    packet_count += 1
        return packet_count > 0
    except Exception:
        return False


def decode_until_error(blob, stream_kind):
    frame_count = 0
    try:
        with av.open(io.BytesIO(blob), mode="r") as container:
            iterator = (
                container.decode(video=0)
                if stream_kind == "video"
                else container.decode(audio=0)
            )
            for _frame in iterator:
                frame_count += 1
    except Exception:
        return False, frame_count
    return True, frame_count


class FullDecodeMediaPreflightTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.valid = build_valid_mp4()

    def test_valid_h264_aac_decodes_completely(self):
        verified, error = service_app._inspect_media_blob(self.valid)
        self.assertIsNone(error)
        self.assertIsNotNone(verified)
        self.assertEqual(verified["video_codec"], "h264")
        self.assertEqual(verified["audio_codec"], "aac")
        self.assertEqual(verified["decoded_video_frames"], 120)
        self.assertGreater(verified["decoded_audio_frames"], 0)

    def test_early_video_corruption_is_rejected(self):
        corrupted, _ = corrupt_packet_length_prefix(self.valid, "video", 0)
        verified, error = service_app._inspect_media_blob(corrupted)
        self.assertIsNone(verified)
        self.assertEqual(error, "MEDIA_VIDEO_DECODE_FAILED")

    def test_late_video_corruption_after_valid_frames_is_rejected(self):
        locations = packet_locations(self.valid, "video")
        corrupted, evidence = corrupt_packet_length_prefix(
            self.valid, "video", len(locations) // 2
        )

        # This proves the MP4 remains structurally demuxable: the old R4
        # packet-only preflight class would not detect this corruption.
        self.assertTrue(demux_only_succeeds(corrupted))

        decoded_ok, decoded_frames = decode_until_error(corrupted, "video")
        self.assertFalse(decoded_ok)
        self.assertGreater(decoded_frames, 30)
        self.assertGreater(evidence["packet_index"], 0)

        verified, error = service_app._inspect_media_blob(corrupted)
        self.assertIsNone(verified)
        self.assertEqual(error, "MEDIA_VIDEO_DECODE_FAILED")

    def test_near_end_video_corruption_is_rejected(self):
        locations = packet_locations(self.valid, "video")
        corrupted, _ = corrupt_packet_length_prefix(
            self.valid, "video", len(locations) - 10
        )
        self.assertTrue(demux_only_succeeds(corrupted))

        decoded_ok, decoded_frames = decode_until_error(corrupted, "video")
        self.assertFalse(decoded_ok)
        self.assertGreater(decoded_frames, 90)

        verified, error = service_app._inspect_media_blob(corrupted)
        self.assertIsNone(verified)
        self.assertEqual(error, "MEDIA_VIDEO_DECODE_FAILED")

    def test_late_audio_corruption_is_rejected_while_video_remains_valid(self):
        locations = packet_locations(self.valid, "audio")
        corrupted, _ = corrupt_packet_length_prefix(
            self.valid, "audio", len(locations) // 2
        )
        self.assertTrue(demux_only_succeeds(corrupted))

        video_ok, video_frames = decode_until_error(corrupted, "video")
        self.assertTrue(video_ok)
        self.assertEqual(video_frames, 120)

        audio_ok, audio_frames = decode_until_error(corrupted, "audio")
        self.assertFalse(audio_ok)
        self.assertGreater(audio_frames, 30)

        verified, error = service_app._inspect_media_blob(corrupted)
        self.assertIsNone(verified)
        self.assertEqual(error, "MEDIA_AUDIO_DECODE_FAILED")

    def test_truncated_tail_is_rejected(self):
        # Remove enough of the MP4 tail to cut required terminal structure.
        # A 128-byte cut can remove only dispensable padding for this fixture;
        # 256 bytes deterministically produces a truncated media tail.
        truncated = self.valid[:-256]
        verified, error = service_app._inspect_media_blob(truncated)
        self.assertIsNone(verified)
        self.assertIsNotNone(error)


if __name__ == "__main__":
    unittest.main()

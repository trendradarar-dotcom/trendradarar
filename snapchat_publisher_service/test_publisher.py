import os
import unittest
from unittest.mock import patch

from publisher import (
    AyrshareSpotlightPublisher,
    EnvelopeValidationError,
    PublicationGateClosed,
    SpotlightEnvelope,
    build_ayrshare_payload,
    validate_envelope,
)


def base_payload():
    return {
        "market": "SA",
        "language": "ar",
        "headline": "هذا ما يصعد الآن في السعودية",
        "description": "ترند سعودي مختار ومراجع",
        "media_url": "https://example.com/video.mp4",
        "duration_seconds": 35,
        "width": 1080,
        "height": 1920,
        "originality_passed": True,
        "rights_passed": True,
        "trend_id": "trend-001",
        "saudi_filter_passed": True,
        "global_selected": False,
    }


class PublisherTests(unittest.TestCase):
    def test_saudi_market_passes_when_all_gates_pass(self):
        env = SpotlightEnvelope.from_dict(base_payload())
        self.assertEqual(validate_envelope(env), [])

    def test_saudi_filter_is_mandatory(self):
        data = base_payload()
        data["saudi_filter_passed"] = False
        errors = validate_envelope(SpotlightEnvelope.from_dict(data))
        self.assertIn("saudi_filter_required", errors)

    def test_global_lane_requires_explicit_selection(self):
        data = base_payload()
        data["market"] = "GLOBAL_SELECTED"
        data["saudi_filter_passed"] = None
        data["global_selected"] = False
        errors = validate_envelope(SpotlightEnvelope.from_dict(data))
        self.assertIn("global_selection_required", errors)

    def test_non_arab_market_is_blocked(self):
        data = base_payload()
        data["market"] = "US"
        errors = validate_envelope(SpotlightEnvelope.from_dict(data))
        self.assertIn("unsupported_market", errors)

    def test_under_30_seconds_is_blocked(self):
        data = base_payload()
        data["duration_seconds"] = 29.9
        errors = validate_envelope(SpotlightEnvelope.from_dict(data))
        self.assertIn("duration_below_internal_30_second_floor", errors)

    def test_payload_targets_snapchat_spotlight(self):
        env = SpotlightEnvelope.from_dict(base_payload())
        payload = build_ayrshare_payload(env)
        self.assertEqual(payload["platforms"], ["snapchat"])
        self.assertEqual(payload["mediaUrls"], ["https://example.com/video.mp4"])
        self.assertEqual(payload["snapChatOptions"], {"spotlight": True})

    def test_schedule_normalizes_to_utc(self):
        env = SpotlightEnvelope.from_dict(base_payload())
        payload = build_ayrshare_payload(env, "2026-09-26T12:30:00+03:00")
        self.assertEqual(payload["scheduleDate"], "2026-09-26T09:30:00Z")

    def test_publication_gate_defaults_closed(self):
        env = SpotlightEnvelope.from_dict(base_payload())
        publisher = AyrshareSpotlightPublisher(api_key="test-key")
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaises(PublicationGateClosed):
                publisher.publish(env)

    def test_missing_rights_gate_is_blocked(self):
        data = base_payload()
        data["rights_passed"] = False
        with self.assertRaises(EnvelopeValidationError):
            build_ayrshare_payload(SpotlightEnvelope.from_dict(data))


if __name__ == "__main__":
    unittest.main()

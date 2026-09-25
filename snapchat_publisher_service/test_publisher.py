import os
import unittest
from unittest.mock import Mock, patch

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
        "publication_id": "snap-sa-trend-001-20260925T120000Z",
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
        "human_origin_passed": True,
        "visual_template_id": "snap-country-board-v1",
        "trend_id": "trend-001",
        "saudi_filter_passed": True,
        "global_selected": False,
    }


class FakeResponse:
    def __init__(self, status_code=200, payload=None):
        self.status_code = status_code
        self._payload = payload or {}
        self.text = str(self._payload)

    def json(self):
        return self._payload


class PublisherTests(unittest.TestCase):
    def test_saudi_market_passes_when_all_gates_pass(self):
        env = SpotlightEnvelope.from_dict(base_payload())
        self.assertEqual(validate_envelope(env), [])

    def test_saudi_filter_is_mandatory(self):
        data = base_payload()
        data["saudi_filter_passed"] = False
        errors = validate_envelope(SpotlightEnvelope.from_dict(data))
        self.assertIn("saudi_filter_required", errors)

    def test_string_false_does_not_pass_boolean_gate(self):
        data = base_payload()
        data["saudi_filter_passed"] = "false"
        errors = validate_envelope(SpotlightEnvelope.from_dict(data))
        self.assertIn("saudi_filter_required", errors)

    def test_human_origin_gate_is_mandatory(self):
        data = base_payload()
        data["human_origin_passed"] = False
        errors = validate_envelope(SpotlightEnvelope.from_dict(data))
        self.assertIn("snapchat_human_origin_gate_failed", errors)

    def test_visual_template_is_mandatory(self):
        data = base_payload()
        data["visual_template_id"] = ""
        errors = validate_envelope(SpotlightEnvelope.from_dict(data))
        self.assertIn("visual_template_id_required", errors)

    def test_global_lane_requires_explicit_selection(self):
        data = base_payload()
        data["market"] = "GLOBAL_SELECTED"
        data["saudi_filter_passed"] = False
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

    def test_payload_targets_snapchat_spotlight_and_idempotency(self):
        env = SpotlightEnvelope.from_dict(base_payload())
        payload = build_ayrshare_payload(env)
        self.assertEqual(payload["platforms"], ["snapchat"])
        self.assertEqual(payload["mediaUrls"], ["https://example.com/video.mp4"])
        self.assertEqual(payload["snapChatOptions"], {"spotlight": True})
        self.assertTrue(payload["idempotencyKey"].startswith("trendradar-snap-"))

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

    def test_provider_validation_uses_no_side_effect_endpoint(self):
        session = Mock()
        session.post.return_value = FakeResponse(200, {"status": "success", "message": "ok"})
        env = SpotlightEnvelope.from_dict(base_payload())
        publisher = AyrshareSpotlightPublisher(api_key="test-key", session=session)
        result = publisher.validate_provider(env)
        self.assertTrue(result["ok"])
        called_url = session.post.call_args.args[0]
        self.assertTrue(called_url.endswith("/validate/post"))

    def test_status_reconciliation_reads_provider_post(self):
        session = Mock()
        session.get.return_value = FakeResponse(200, {"status": "success", "id": "abc"})
        publisher = AyrshareSpotlightPublisher(api_key="test-key", session=session)
        result = publisher.get_post_status("abc")
        self.assertEqual(result["id"], "abc")
        self.assertTrue(session.get.call_args.args[0].endswith("/post/abc"))


if __name__ == "__main__":
    unittest.main()

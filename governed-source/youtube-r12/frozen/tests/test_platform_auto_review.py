from __future__ import annotations

from trend_hunter.platform_auto_review import PlatformPolicyAutoReviewService
from trend_hunter.platform_policy import platform_policy_rules


def _raw(platform: str, status: str, confidence: float):
    return {
        "review_complete": True,
        "reviewed_modalities": ["text", "image", "audio", "video"],
        "rules": [
            {
                "rule_id": rule["rule_id"],
                "status": status,
                "confidence": confidence,
                "reason": "test",
            }
            for rule in platform_policy_rules(platform)
        ],
    }


def test_high_confidence_complete_pass():
    decision, findings, reason = PlatformPolicyAutoReviewService._normalize_provider_result(
        rules=platform_policy_rules("youtube"),
        raw=_raw("youtube", "PASS", 0.99),
    )
    assert decision == "PASS"
    assert findings
    assert all(x["status"] == "PASS" for x in findings)


def test_low_confidence_pass_becomes_hold():
    decision, findings, reason = PlatformPolicyAutoReviewService._normalize_provider_result(
        rules=platform_policy_rules("youtube"),
        raw=_raw("youtube", "PASS", 0.60),
    )
    assert decision == "HOLD"


def test_high_confidence_block():
    decision, findings, reason = PlatformPolicyAutoReviewService._normalize_provider_result(
        rules=platform_policy_rules("tiktok"),
        raw=_raw("tiktok", "BLOCK", 0.99),
    )
    assert decision == "BLOCK"


def test_incomplete_review_holds():
    raw = _raw("instagram", "PASS", 0.99)
    raw["review_complete"] = False
    decision, findings, reason = PlatformPolicyAutoReviewService._normalize_provider_result(
        rules=platform_policy_rules("instagram"),
        raw=raw,
    )
    assert decision == "HOLD"
    assert findings == []


def test_missing_rule_holds():
    raw = _raw("snapchat", "PASS", 0.99)
    raw["rules"] = raw["rules"][:-1]
    decision, findings, reason = PlatformPolicyAutoReviewService._normalize_provider_result(
        rules=platform_policy_rules("snapchat"),
        raw=raw,
    )
    assert decision == "HOLD"
    assert findings == []
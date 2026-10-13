from types import SimpleNamespace

import pytest

from trend_hunter.ledger import LedgerError
from trend_hunter.platform_compliance_bridge import (
    PlatformComplianceBridge,
)
from trend_hunter.saudi_legal import (
    SAUDI_ANTI_CYBERCRIME_POLICY,
)


class FakeLedger:
    def __init__(self, review_present=True):
        self.review_present = review_present

        self.review = {
            "id": "saudi-review-1",
            "state_type": "EVIDENCE",
            "payload": {
                "creative_state_id": "creative-1",
                "review_scope": "legal",
                "verification_status": "HUMAN_REVIEWED",
                "finding_key": (
                    SAUDI_ANTI_CYBERCRIME_POLICY["policy_key"]
                ),
                "jurisdiction": "SA",
                "status": "PASS",
                "fixture": False,
                "automated_legal_clearance": False,
            },
        }

    def get_state(self, state_id):
        if state_id == "creative-1":
            return {
                "id": "creative-1",
                "state_type": "CREATIVE_ARTIFACT",
                "payload": {"title": "Saudi candidate"},
            }

        if state_id == "saudi-review-1":
            return self.review

        raise LedgerError(
            f"unknown fake state: {state_id}"
        )

    def get_latest_state_by_natural_key(
        self,
        kind,
        natural_key,
    ):
        assert kind == "EVIDENCE"
        assert natural_key == (
            "saudi-cybercrime-review:creative-1"
        )

        if self.review_present:
            return self.review

        return None


class FakePlatformReview:
    def __init__(self):
        self.called = False

    def review(self, **kwargs):
        self.called = True

        return SimpleNamespace(
            decision="PASS",
            platform_findings=[
                {
                    "finding": "PLATFORM-AUTO",
                    "status": "PASS",
                    "reason": "governed automated platform review",
                    "evidence_state_ids": [
                        "platform-evidence-1"
                    ],
                }
            ],
            reason="platform pass",
        )


class CaptureCompliance:
    def assess(self, *args, **kwargs):
        return {"args": args, **kwargs}


def build_bridge(review_present=True):
    platform = FakePlatformReview()

    bridge = PlatformComplianceBridge(
        FakeLedger(review_present),
        CaptureCompliance(),
        platform,
    )

    bridge.enforce_governed_saudi_review = True

    return bridge, platform


def test_saudi_uses_governed_human_review_not_client_input():
    bridge, platform = build_bridge(True)

    result = bridge.assess(
        creative_state_id="creative-1",
        eligibility_state_id="eligibility-1",
        target={
            "platform": "youtube",
            "jurisdiction": "SA",
        },
        legal_findings=[
            {
                "finding": "CLIENT-BYPASS",
                "status": "PASS",
            }
        ],
        coverage_state="SUFFICIENT",
        gate_decision="PASS",
        strict_c1=False,
    )

    assert platform.called is True
    assert result["strict_c1"] is True

    findings = result["legal_findings"]

    assert len(findings) == 1
    assert findings[0]["finding"] == (
        SAUDI_ANTI_CYBERCRIME_POLICY["policy_key"]
    )
    assert findings[0]["status"] == "PASS"
    assert findings[0]["evidence_state_ids"] == [
        "saudi-review-1"
    ]
    assert findings[0]["finding"] != "CLIENT-BYPASS"


def test_saudi_missing_human_review_fails_closed():
    bridge, platform = build_bridge(False)

    with pytest.raises(
        LedgerError,
        match="Saudi human legal review is required",
    ):
        bridge.assess(
            creative_state_id="creative-1",
            eligibility_state_id="eligibility-1",
            target={
                "platform": "youtube",
                "jurisdiction": "SA",
            },
            legal_findings=[],
            coverage_state="SUFFICIENT",
            gate_decision="PASS",
            strict_c1=False,
        )

    # Platform automation occurs first, as required.
    assert platform.called is True


def test_non_sa_keeps_existing_legal_behavior():
    bridge, platform = build_bridge(False)

    supplied = [
        {
            "finding": "NON-SA-LEGAL",
            "status": "PASS",
        }
    ]

    result = bridge.assess(
        creative_state_id="creative-1",
        eligibility_state_id="eligibility-1",
        target={
            "platform": "youtube",
            "jurisdiction": "US",
        },
        legal_findings=supplied,
        coverage_state="SUFFICIENT",
        gate_decision="PASS",
        strict_c1=False,
    )

    assert platform.called is True
    assert result["legal_findings"] == supplied
    assert result["strict_c1"] is False

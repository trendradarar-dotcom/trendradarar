from __future__ import annotations

import json
from types import SimpleNamespace

from trend_hunter.platform_compliance_bridge import PlatformComplianceBridge


class FakeLedger:
    def get_state(self, state_id):
        return {
            "state_id": state_id,
            "state_type": "CREATIVE_ARTIFACT",
            "payload_json": json.dumps(
                {
                    "title": "Morning coffee",
                    "caption": "A simple coffee routine",
                    "target": {"platform": "youtube", "jurisdiction": "SA"},
                }
            ),
        }


class FakeCompliance:
    def __init__(self):
        self.kwargs = None

    def assess(self, creative_state_id, eligibility_state_id, **kwargs):
        self.kwargs = kwargs
        return SimpleNamespace(state_id="compliance-1")


class FakeReviewer:
    def __init__(self, decision, findings):
        self.decision = decision
        self.findings = findings
        self.seen = None

    def review(self, **kwargs):
        self.seen = kwargs
        return SimpleNamespace(
            decision=self.decision,
            platform_findings=self.findings,
            evidence_state_ids=[],
            analyzer="fake",
            reason="automated review reason",
        )


def _bridge(decision, findings):
    compliance = FakeCompliance()
    reviewer = FakeReviewer(decision, findings)
    bridge = PlatformComplianceBridge(FakeLedger(), compliance, reviewer)
    return bridge, compliance, reviewer


def test_pass_uses_automated_platform_findings_not_client_data():
    bridge, compliance, reviewer = _bridge(
        "PASS",
        [{"rule_id": "YT-1", "status": "PASS", "reason": "ok", "evidence_state_ids": ["ev-1"]}],
    )
    result = bridge.assess(
        creative_state_id="creative-1",
        eligibility_state_id="elig-1",
        target={"platform": "youtube", "jurisdiction": "SA"},
        legal_findings=[{"rule_id": "SA-1", "status": "PASS"}],
        coverage_state="SUFFICIENT",
        gate_decision="PASS",
        strict_c1=False,
    )
    assert result.state_id == "compliance-1"
    assert reviewer.seen["platform"] == "youtube"
    assert compliance.kwargs["platform_findings"][0]["rule_id"] == "YT-1"
    assert compliance.kwargs["gate_decision"] == "PASS"


def test_hold_is_internal_human_review_and_unresolved_not_platform_manual_review():
    bridge, compliance, _ = _bridge(
        "HOLD",
        [{"rule_id": "YT-1", "status": "HOLD", "reason": "missing video", "evidence_state_ids": []}],
    )
    bridge.assess(
        creative_state_id="creative-1",
        eligibility_state_id="elig-1",
        target={"platform": "youtube", "jurisdiction": "SA"},
        legal_findings=[],
        coverage_state="SUFFICIENT",
        gate_decision="PASS",
        strict_c1=False,
    )
    finding = compliance.kwargs["platform_findings"][0]
    assert finding["status"] == "UNRESOLVED"
    assert finding["provider_status"] == "HOLD"
    assert compliance.kwargs["gate_decision"] == "HUMAN_REVIEW"
    assert compliance.kwargs["coverage_state"] == "PARTIAL"


def test_block_forces_block_gate():
    bridge, compliance, _ = _bridge(
        "BLOCK",
        [{"rule_id": "TT-1", "status": "BLOCK", "reason": "violation", "evidence_state_ids": ["ev-2"]}],
    )
    bridge.assess(
        creative_state_id="creative-1",
        eligibility_state_id="elig-1",
        target={"platform": "tiktok", "jurisdiction": "SA"},
        legal_findings=[],
        coverage_state="SUFFICIENT",
        gate_decision="PASS",
        strict_c1=False,
    )
    assert compliance.kwargs["gate_decision"] == "BLOCK"


def test_target_platform_is_required():
    bridge, _, _ = _bridge("PASS", [])
    try:
        bridge.assess(
            creative_state_id="creative-1",
            eligibility_state_id="elig-1",
            target={"jurisdiction": "SA"},
            legal_findings=[],
            coverage_state="SUFFICIENT",
            gate_decision="PASS",
            strict_c1=False,
        )
    except Exception as exc:
        assert "target.platform" in str(exc)
    else:
        raise AssertionError("missing target.platform must fail closed")
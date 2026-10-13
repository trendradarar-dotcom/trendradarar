from types import SimpleNamespace

import pytest

from trend_hunter.ledger import LedgerError
from trend_hunter.saudi_publication_orchestrator import (
    SaudiPublicationAuthorizationOrchestrator,
)


class FakeLedger:
    def __init__(self, recommendation="RECOMMEND_PUBLISH"):
        self.states = {
            "creative-1": {
                "state_type": "CREATIVE_ARTIFACT",
                "payload": {
                    "target": {
                        "platform": "youtube",
                        "language": "ar",
                        "region": "SA",
                    }
                },
            },
            "rec-1": {
                "state_type": "PUBLICATION_RECOMMENDATION",
                "payload": {"recommendation": recommendation},
            },
        }

    def get_state(self, state_id):
        return self.states[state_id]


class FakeSaudi:
    def __init__(self, status="PASS"):
        self.status = status
        self.review_calls = []

    def review(self, creative_state_id, **kwargs):
        self.review_calls.append((creative_state_id, kwargs))
        return SimpleNamespace(state_id="legal-1")

    def compliance_finding(self, review_state_id):
        assert review_state_id == "legal-1"
        return {
            "finding": "SAUDI_ANTI_CYBERCRIME_CONTENT",
            "status": self.status,
            "reason": "governed specialist review",
            "evidence_state_ids": ["legal-1"],
        }


class FakeBridge:
    def __init__(self):
        self.calls = []

    def assess(self, **kwargs):
        self.calls.append(kwargs)
        return SimpleNamespace(state_id="comp-1")


class FakeRecommendation:
    def recommend(self, creative_state_id, eligibility_state_id, compliance_state_id):
        assert creative_state_id == "creative-1"
        assert eligibility_state_id == "elig-1"
        assert compliance_state_id == "comp-1"
        return SimpleNamespace(state_id="rec-1")


class FakeOperations:
    def __init__(self):
        self.calls = []

    def record_human_authorization(self, *args, **kwargs):
        self.calls.append((args, kwargs))
        return SimpleNamespace(state_id="auth-1")


def build(recommendation="RECOMMEND_PUBLISH", legal_status="PASS"):
    ledger = FakeLedger(recommendation)
    saudi = FakeSaudi(legal_status)
    bridge = FakeBridge()
    rec = FakeRecommendation()
    ops = FakeOperations()
    svc = SaudiPublicationAuthorizationOrchestrator(
        ledger, saudi, bridge, rec, ops
    )
    return svc, saudi, bridge, ops


def test_single_human_action_creates_distinct_legal_and_exact_authorization_records():
    svc, saudi, bridge, ops = build()

    result = svc.approve_and_authorize(
        creative_state_id="creative-1",
        eligibility_state_id="elig-1",
        reviewer="ali-ahmad",
        authorizer="ali-ahmad",
        determinations=[{"rule_id": "x", "status": "PASS", "reason": "checked"}],
        source_checked_at="2026-09-16",
        execution_configuration_state_id="cfg-1",
        channel_binding_state_id="channel-1",
        media_descriptor_state_id="media-1",
        auth_context={"subject": "ali-ahmad"},
    )

    assert result.legal_review_state_id == "legal-1"
    assert result.compliance_state_id == "comp-1"
    assert result.recommendation_state_id == "rec-1"
    assert result.authorization_state_id == "auth-1"
    assert result.disposition == "AUTHORIZED_FOR_EXACT_PUBLICATION_BUNDLE"

    assert len(saudi.review_calls) == 1
    assert len(bridge.calls) == 1
    assert bridge.calls[0]["legal_findings"][0]["evidence_state_ids"] == ["legal-1"]
    assert bridge.calls[0]["strict_c1"] is True
    assert bridge.calls[0]["gate_decision"] == "PASS"

    assert len(ops.calls) == 1
    args, kwargs = ops.calls[0]
    assert args[:3] == ("rec-1", "ali-ahmad", "AUTHORIZED")
    assert kwargs["execution_configuration_state_id"] == "cfg-1"
    assert kwargs["channel_binding_state_id"] == "channel-1"
    assert kwargs["media_descriptor_state_id"] == "media-1"
    assert kwargs["require_exact_channel"] is True
    assert kwargs["require_exact_media"] is True


def test_hold_or_nonpublish_recommendation_never_creates_publication_authorization():
    svc, _, bridge, ops = build(
        recommendation="RECOMMEND_HOLD", legal_status="UNRESOLVED"
    )

    result = svc.approve_and_authorize(
        creative_state_id="creative-1",
        eligibility_state_id="elig-1",
        reviewer="ali-ahmad",
        authorizer="ali-ahmad",
        determinations=[
            {"rule_id": "x", "status": "UNRESOLVED", "reason": "needs review"}
        ],
        source_checked_at="2026-09-16",
    )

    assert result.authorization_state_id is None
    assert result.disposition == "RECOMMEND_HOLD"
    assert bridge.calls[0]["gate_decision"] == "HUMAN_REVIEW"
    assert ops.calls == []


def test_single_action_refuses_split_human_attribution():
    svc, _, _, ops = build()

    with pytest.raises(LedgerError, match="different humans"):
        svc.approve_and_authorize(
            creative_state_id="creative-1",
            eligibility_state_id="elig-1",
            reviewer="legal-reviewer",
            authorizer="publisher-owner",
            determinations=[{"rule_id": "x", "status": "PASS", "reason": "checked"}],
            source_checked_at="2026-09-16",
            execution_configuration_state_id="cfg-1",
            channel_binding_state_id="channel-1",
            media_descriptor_state_id="media-1",
        )

    assert ops.calls == []


def test_publish_path_requires_exact_final_bundle_before_authorization():
    svc, _, _, ops = build()

    with pytest.raises(LedgerError, match="exact execution configuration"):
        svc.approve_and_authorize(
            creative_state_id="creative-1",
            eligibility_state_id="elig-1",
            reviewer="ali-ahmad",
            authorizer="ali-ahmad",
            determinations=[{"rule_id": "x", "status": "PASS", "reason": "checked"}],
            source_checked_at="2026-09-16",
        )

    assert ops.calls == []
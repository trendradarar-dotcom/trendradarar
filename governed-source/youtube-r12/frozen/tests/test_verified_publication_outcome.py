import pytest
from trend_hunter.db import init_db
from trend_hunter.ledger import GovernanceLedger, LedgerError
from trend_hunter.publication_outcome import PublicationOutcomeService


@pytest.fixture
def service(tmp_path):
    db = str(tmp_path / "outcome.sqlite")
    init_db(db)
    return PublicationOutcomeService(GovernanceLedger(db))


def attempt(s, **overrides):
    args = dict(command_id="cmd-1", idempotency_key="idem-1",
                creative_state_id="creative-1", authorization_state_id="auth-1",
                platform="youtube", target="channel-1", content_version="v1",
                status="OUTCOME_UNKNOWN", evidence={"source": "local-attempt"})
    args.update(overrides)
    return s.record_attempt(**args)


def test_attempt_persists_and_recovers_without_replay(service):
    sid = attempt(service)
    reopened = PublicationOutcomeService(GovernanceLedger(service.ledger.db_path))
    result = reopened.inspect("cmd-1")
    assert result["state_id"] == sid
    assert result["reconciliation_required"] is True
    assert result["automatic_resend_allowed"] is False
    assert result["verified"] is False


def test_identical_retry_is_idempotent(service):
    assert attempt(service) == attempt(service)


def test_conflicting_idempotency_is_rejected(service):
    attempt(service)
    with pytest.raises(LedgerError, match="Conflicting"):
        attempt(service, content_version="v2")


@pytest.mark.parametrize("status", ["VERIFIED", "PUBLISHED", "SUCCESS"])
def test_attempt_cannot_claim_publication(service, status):
    with pytest.raises(LedgerError):
        attempt(service, status=status)


@pytest.mark.parametrize("evidence", [
    {"synthetic_only": True},
    {"wrapper": {"state_type": "PUBLISHER_TEST_COMMAND"}},
    {"wrapper": [{"fixture": True}]},
])
def test_rewrapped_synthetic_provenance_is_rejected(service, evidence):
    with pytest.raises(LedgerError):
        attempt(service, evidence=evidence)


def test_provider_id_without_independent_verifier_is_not_proof(service):
    sid = attempt(service)
    with pytest.raises(LedgerError, match="verifier not authorized"):
        service.verify(attempt_state_id=sid, evidence={
            "platform": "youtube", "target": "channel-1",
            "creative_state_id": "creative-1", "content_version": "v1",
            "external_post_id": "video-1", "source_ref": "untrusted-claim"})


def test_mismatched_provider_evidence_is_rejected(service):
    sid = attempt(service)
    with pytest.raises(LedgerError, match="mismatch"):
        service.verify(attempt_state_id=sid, evidence={
            "platform": "instagram", "target": "channel-1",
            "creative_state_id": "creative-1", "content_version": "v1",
            "external_post_id": "post", "source_ref": "claim"})


def test_synthetic_attempt_is_not_allowed_to_become_verified(service):
    sid = attempt(service)
    with pytest.raises(LedgerError):
        service.verify(attempt_state_id=sid, evidence={
            "platform": "youtube", "target": "channel-1",
            "creative_state_id": "creative-1", "content_version": "v1",
            "external_post_id": "post", "source_ref": "PUBLISHER_TEST_COMMAND"})


def test_failed_and_received_attempts_remain_recordable(service):
    for status in ("SENT", "RECEIVED", "FAILED_FINAL", "HELD"):
        sid = attempt(service, command_id="cmd-"+status,
                      idempotency_key="key-"+status, status=status)
        assert service.ledger.get_state(sid)["payload"]["verified"] is False

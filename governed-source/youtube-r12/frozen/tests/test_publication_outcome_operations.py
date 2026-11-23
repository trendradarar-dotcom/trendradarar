import inspect
import pytest
from trend_hunter.db import init_db
from trend_hunter.ledger import GovernanceLedger, LedgerError
from trend_hunter.operations import OperationsService
from trend_hunter.publication_outcome import PublicationOutcomeService


@pytest.fixture
def services(tmp_path):
    path = str(tmp_path / "ops.sqlite")
    init_db(path)
    ledger = GovernanceLedger(path)
    return OperationsService(ledger), PublicationOutcomeService(ledger)


def test_existing_publication_signature_retained(services):
    ops, _ = services
    sig = inspect.signature(ops.record_publication_execution)
    assert "external_result_ref" in sig.parameters
    assert sig.parameters["verified_outcome_state_id"].default is None


def test_synthetic_attempt_cannot_be_passed_as_verified_outcome(services):
    ops, outcomes = services
    sid = outcomes.record_attempt(
        command_id="cmd", idempotency_key="idem", creative_state_id="creative",
        authorization_state_id="auth", platform="youtube", target="channel",
        content_version="v1", status="RECEIVED", evidence={"attempt": True})
    with pytest.raises(LedgerError, match="Independently verified"):
        ops.record_publication_execution(
            "creative", "auth", external_result_ref="video",
            verified_outcome_state_id=sid)


def test_missing_verified_outcome_fails_without_side_effect(services):
    ops, _ = services
    with pytest.raises(LedgerError):
        ops.record_publication_execution(
            "creative", "auth", external_result_ref="video",
            verified_outcome_state_id="missing")

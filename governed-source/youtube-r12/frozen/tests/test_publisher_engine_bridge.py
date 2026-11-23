"""Isolated publisher bridge regression checks; no network access."""
import pytest
from trend_hunter.db import init_db
from trend_hunter.ledger import GovernanceLedger
from trend_hunter.publisher_contract import ContractError
from trend_hunter.publisher_bridge import PublisherEngineBridge, assert_test_runtime
from trend_hunter.publisher_dispatch import PublisherCommandJournal


@pytest.fixture
def journal(tmp_path, monkeypatch):
    monkeypatch.setenv("TREND_HUNTER_PUBLISHER_BRIDGE_TEST_ONLY", "1")
    path = str(tmp_path / "bridge.sqlite")
    init_db(path)
    return PublisherCommandJournal(GovernanceLedger(path))


def test_disabled_without_explicit_opt_in(monkeypatch):
    monkeypatch.delenv("TREND_HUNTER_PUBLISHER_BRIDGE_TEST_ONLY", raising=False)
    with pytest.raises(ContractError):
        assert_test_runtime()


def test_missing_authorization_fails_before_command_creation(journal):
    bridge = PublisherEngineBridge(journal.ledger)
    with pytest.raises(Exception):
        bridge.create(creative_state_id="missing", authorization_state_id="missing",
                      channel_binding_state_id="missing", platform="youtube",
                      target="synthetic", command_id="cmd", idempotency_key="idem")
    with pytest.raises(ContractError):
        journal._latest("cmd")


def test_durable_reopen_duplicate_and_conflicting_content(journal):
    sid, payload = journal.create("cmd", "key", "youtube", "synthetic", {"version": 1})
    reopened = PublisherCommandJournal(GovernanceLedger(journal.ledger.db_path))
    sid2, _ = reopened.create("cmd", "key", "youtube", "synthetic", {"version": 1})
    assert sid2 == sid
    with pytest.raises(ContractError):
        reopened.create("cmd", "key", "youtube", "synthetic", {"version": 2})
    assert reopened.inspect_recovery("cmd")["state"] == "CREATED"


def test_unknown_outcome_never_redispatches(journal):
    bridge = PublisherEngineBridge(journal.ledger)
    sid, _ = journal.create("unknown", "unknown-key", "youtube", "synthetic", {"version": 1})
    sid, _ = bridge.authorize_test("unknown", sid)
    sid, _ = bridge.dispatch("unknown", sid)
    sid, _ = journal.advance("unknown", sid, "OUTCOME_UNKNOWN", "simulated-disconnect")
    reopened = PublisherCommandJournal(GovernanceLedger(journal.ledger.db_path))
    assert reopened.inspect_recovery("unknown")["replay_blocked"]
    with pytest.raises(ContractError):
        reopened.dispatch_to_synthetic("unknown", sid, "forbidden-retry")
    sid, _ = bridge.reconcile("unknown", sid, "RECONCILIATION_REQUIRED", "manual-evidence-pending")
    assert reopened.inspect_recovery("unknown")["replay_blocked"]


def test_reconciliation_cannot_create_dispatch(journal):
    bridge = PublisherEngineBridge(journal.ledger)
    sid, _ = journal.create("recon", "recon-key", "youtube", "synthetic", {"version": 1})
    with pytest.raises(ContractError):
        bridge.reconcile("recon", sid, "DISPATCHED", "forbidden")


def test_synthetic_command_does_not_claim_real_publication(journal):
    sid, payload = journal.create("local", "local-key", "instagram", "synthetic", {"version": 1})
    assert payload["synthetic_only"] is True
    assert payload["state"] == "CREATED"
    assert journal.inspect_recovery("local")["synthetic_only"] is True

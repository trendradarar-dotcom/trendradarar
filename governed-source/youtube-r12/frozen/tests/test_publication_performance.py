import pytest

@pytest.fixture(autouse=True)
def _isolated_runtime(monkeypatch):
    monkeypatch.setenv('TREND_HUNTER_PERFORMANCE_TEST_ONLY', '1')
from trend_hunter.db import init_db
from trend_hunter.ledger import GovernanceLedger, LedgerError
from trend_hunter.publication_performance import PublicationPerformanceService

@pytest.fixture
def env(tmp_path):
    db=str(tmp_path/"performance.sqlite")
    init_db(db)
    ledger=GovernanceLedger(db)
    proof=ledger.record_domain("VERIFIED_PUBLICATION_OUTCOME","Test Evidence",{
        "verification_status":"INDEPENDENTLY_VERIFIED","platform":"youtube",
        "channel_ref":"channel","external_post_id":"post","creative_state_id":"creative",
        "content_version":"v1","synthetic_only":True},natural_key="isolated-proof")
    service=PublicationPerformanceService(ledger,isolated_test_verifier=lambda state: state["state_type"]=="VERIFIED_PUBLICATION_OUTCOME")
    args=dict(publication_state_id=proof.state_id,platform="youtube",channel_ref="channel",
              external_post_id="post",creative_state_id="creative",content_version="v1",
              source_ref="local-test-evidence",source_digest="sha256:local",
              observed_at="2026-11-23T12:00:00Z",window_start="2026-11-22T00:00:00Z",
              window_end="2026-11-23T00:00:00Z",
              metrics=[{"name":"views","unit":"views","definition":"platform views","platform":"youtube","value":10}],
              idempotency_key="key",isolated_test=True)
    return ledger,service,args

def test_isolated_record_and_durable_idempotency(env):
    ledger,service,args=env
    sid=service.record(**args)
    reopened=PublicationPerformanceService(GovernanceLedger(ledger.db_path),
        isolated_test_verifier=lambda _:True)
    assert reopened.record(**args)==sid
    assert reopened.inspect("key")["production_eligible"] is False

def test_conflict_after_reopen(env):
    ledger,service,args=env
    service.record(**args)
    other=PublicationPerformanceService(GovernanceLedger(ledger.db_path),isolated_test_verifier=lambda _:True)
    with pytest.raises(LedgerError,match="Conflicting"):
        other.record(**{**args,"source_digest":"changed"})

@pytest.mark.parametrize("change",[
    {"platform":"instagram"},{"content_version":"v2"},{"channel_ref":"other"},
    {"creative_state_id":"other"},{"external_post_id":"other"},
    {"window_end":"2026-11-21T00:00:00Z"},
    {"observed_at":"2026-11-20T00:00:00Z"},
    {"metrics":[{"name":"views","unit":"views","definition":"views","platform":"tiktok","value":1}]},
    {"metrics":[{"name":"views","unit":"","definition":"views","platform":"youtube","value":1}]},
    {"metrics":[{"name":"views","unit":"views","definition":"views","platform":"youtube","value":-1}]},
])
def test_invalid_bindings_rejected(env,change):
    _,service,args=env
    with pytest.raises(LedgerError):
        service.record(**{**args,**change})

def test_unresolved_without_invented_values(env):
    _,service,args=env
    sid=service.record(**{**args,"status":"OUTCOME_UNKNOWN","metrics":[]})
    assert service.inspect("key")["reconciliation_required"] is True
    assert service.ledger.get_state(sid)["payload"]["metrics"]==[]

def test_unresolved_cannot_claim_metrics(env):
    _,service,args=env
    with pytest.raises(LedgerError):
        service.record(**{**args,"status":"OUTCOME_UNKNOWN"})

def test_production_without_verifier_fails_closed(env):
    ledger,_,args=env
    service=PublicationPerformanceService(ledger)
    with pytest.raises(LedgerError,match="HOLD"):
        service.record(**{**args,"isolated_test":False})

def test_execution_alone_rejected(env):
    ledger,service,args=env
    attempt=ledger.record_domain("PUBLICATION_EXECUTION","Test",{},natural_key="attempt")
    with pytest.raises(LedgerError,match="Independently verified"):
        service.record(**{**args,"publication_state_id":attempt.state_id})

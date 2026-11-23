import pytest
from trend_hunter.db import init_db, connect
from trend_hunter.ledger import GovernanceLedger, LedgerError
from trend_hunter.publication_performance import PublicationPerformanceService

def test_isolation_from_trends_learning_economics_and_synthetic_rewrap(tmp_path):
    db=str(tmp_path/"isolation.sqlite")
    init_db(db)
    ledger=GovernanceLedger(db)
    proof=ledger.record_domain("VERIFIED_PUBLICATION_OUTCOME","Isolated Test",{
        "verification_status":"INDEPENDENTLY_VERIFIED","platform":"youtube",
        "channel_ref":"channel","external_post_id":"post",
        "creative_state_id":"creative","content_version":"v1",
        "synthetic_only":True,"provenance":{"state_type":"PUBLISHER_TEST_COMMAND"}},
        natural_key="test-proof")
    service=PublicationPerformanceService(ledger,isolated_test_verifier=lambda _:True)
    args=dict(publication_state_id=proof.state_id,platform="youtube",channel_ref="channel",
        external_post_id="post",creative_state_id="creative",content_version="v1",
        source_ref="isolated-evidence",source_digest="sha256:test",
        observed_at="2026-11-23T12:00:00Z",window_start="2026-11-22T00:00:00Z",
        window_end="2026-11-23T00:00:00Z",
        metrics=[{"name":"views","unit":"views","definition":"YouTube views","platform":"youtube","value":5}],
        idempotency_key="isolation",isolated_test=True)
    sid=service.record(**args)
    assert ledger.get_state(sid)["payload"]["production_eligible"] is False
    with connect(db) as conn:
        rows=conn.execute("SELECT stage,COUNT(*) FROM domain_record GROUP BY stage").fetchall()
    kinds={row["stage"] for row in rows}
    assert "PUBLICATION_PERFORMANCE_MEASUREMENT" in kinds
    assert not kinds.intersection({"TREND_MEASUREMENT","PERFORMANCE_OBSERVATION",
        "REVENUE_OBSERVATION","REALIZED_ECONOMIC_OUTCOME","LEARNING_UPDATE_PROPOSAL"})
    with pytest.raises(LedgerError):
        service.record(**{**args,"isolated_test":False})
    with pytest.raises(LedgerError):
        service.record(**{**args,"source_ref":"PUBLISHER_TEST_COMMAND","isolated_test":False})

def test_untrusted_rewrapped_proof_cannot_enter_production(tmp_path):
    db=str(tmp_path/"negative.sqlite")
    init_db(db)
    ledger=GovernanceLedger(db)
    state=ledger.record_domain("PUBLISHER_TEST_COMMAND","Test",{
        "wrapped":{"state_type":"VERIFIED_PUBLICATION_OUTCOME"}},natural_key="wrapped")
    service=PublicationPerformanceService(ledger,isolated_test_verifier=lambda _:True)
    with pytest.raises(LedgerError):
        service.record(publication_state_id=state.state_id,platform="youtube",
            channel_ref="channel",external_post_id="post",creative_state_id="creative",
            content_version="v1",source_ref="provider",source_digest="hash",
            observed_at="2026-11-23T12:00:00Z",window_start="2026-11-22T00:00:00Z",
            window_end="2026-11-23T00:00:00Z",metrics=[],
            idempotency_key="reject",status="OUTCOME_UNKNOWN",isolated_test=True)

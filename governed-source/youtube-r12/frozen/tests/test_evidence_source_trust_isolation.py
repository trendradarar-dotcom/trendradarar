import hashlib
import pytest
from trend_hunter.db import init_db, connect
from trend_hunter.ledger import GovernanceLedger, LedgerError
from trend_hunter.evidence_source_trust import EvidenceSourceTrustService

def test_no_test_runtime_authority(tmp_path):
    db=str(tmp_path/"runtime.sqlite")
    init_db(db)
    service=EvidenceSourceTrustService(GovernanceLedger(db))
    raw=b"test"
    with pytest.raises(LedgerError,match="Explicit isolated"):
        service.record(evidence_id="test",declared_source="PUBLISHER_TEST_REWRAPPED",
            platform="youtube",channel_ref="channel",post_id="post",
            creative_state_id="creative",content_version="v1",access_scope="read",
            raw_response=raw,claimed_sha256=hashlib.sha256(raw).hexdigest(),
            acquired_at="2026-11-23T10:00:00Z",valid_from="2026-11-23T09:00:00Z",
            valid_until="2026-11-23T11:00:00Z",isolated_test=True)

def test_wrapped_synthetic_lineage_never_production_and_no_downstream(tmp_path,monkeypatch):
    monkeypatch.setenv("TREND_HUNTER_EVIDENCE_TEST_ONLY","1")
    db=str(tmp_path/"isolation.sqlite")
    init_db(db)
    ledger=GovernanceLedger(db)
    synthetic=ledger.record_domain("PUBLISHER_TEST_COMMAND","Fixture",
        {"synthetic_only":True,"platform":"youtube","channel_ref":"channel",
         "post_id":"post","creative_state_id":"creative","content_version":"v1"},
        natural_key="synthetic")
    wrapped=ledger.record_domain("WRAPPED_PROVIDER_EVIDENCE","Fixture",
        {"platform":"youtube","channel_ref":"channel","post_id":"post",
         "creative_state_id":"creative","content_version":"v1"},
        natural_key="wrapped",upstream_states=[(synthetic.state_id,"WRAPPED")])
    raw=b"fixture"
    args=dict(evidence_id="e1",declared_source="provider",platform="youtube",
        channel_ref="channel",post_id="post",creative_state_id="creative",
        content_version="v1",access_scope="read",raw_response=raw,
        claimed_sha256=hashlib.sha256(raw).hexdigest(),
        acquired_at="2026-11-23T10:00:00Z",valid_from="2026-11-23T09:00:00Z",
        valid_until="2026-11-23T11:00:00Z",related_state_id=wrapped.state_id)
    service=EvidenceSourceTrustService(ledger)
    with pytest.raises(LedgerError,match="Synthetic lineage"):
        service.record(**args)
    state=service.record(**{**args,"isolated_test":True})
    assert state["payload"]["production_eligible"] is False
    with connect(db) as conn:
        stages={r["stage"] for r in conn.execute("SELECT stage FROM domain_record")}
    assert not stages.intersection({"PUBLICATION_PERFORMANCE_MEASUREMENT","TREND_MEASUREMENT",
        "REALIZED_ECONOMIC_OUTCOME","PERFORMANCE_OBSERVATION","LEARNING_UPDATE_PROPOSAL"})

def test_claim_reconciliation_does_not_write_downstream(tmp_path):
    db = str(tmp_path / "reconciliation.sqlite")
    init_db(db)
    ledger = GovernanceLedger(db)
    with connect(db) as conn:
        before = {row["stage"] for row in conn.execute("SELECT stage FROM domain_record")}
    # No claim can be reconciled without a durable original claim.
    with pytest.raises(LedgerError, match="not found"):
        ledger.reconcile_evidence_claim(
            claim_key="missing", decision="KEEP_HOLD",
            reason="no claim", reviewer_ref="reviewer")
    with pytest.raises(LedgerError, match="cannot approve"):
        ledger.reconcile_evidence_claim(
            claim_key="missing", decision="APPROVE_PRODUCTION",
            reason="invalid", reviewer_ref="reviewer")
    with connect(db) as conn:
        after = {row["stage"] for row in conn.execute("SELECT stage FROM domain_record")}
    assert before == after

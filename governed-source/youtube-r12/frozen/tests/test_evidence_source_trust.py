import hashlib
import pytest
from trend_hunter.db import init_db
from trend_hunter.ledger import GovernanceLedger, LedgerError
from trend_hunter.evidence_source_trust import EvidenceSourceTrustService

@pytest.fixture(autouse=True)
def runtime(monkeypatch):
    monkeypatch.setenv("TREND_HUNTER_EVIDENCE_TEST_ONLY", "1")

@pytest.fixture
def case(tmp_path):
    db=str(tmp_path/"evidence.sqlite")
    init_db(db)
    ledger=GovernanceLedger(db)
    raw=b'{"status":"pending","source":"fixture"}'
    args=dict(evidence_id="e1",declared_source="local-fixture",platform="youtube",
              channel_ref="channel",post_id="post",creative_state_id="creative",
              content_version="v1",access_scope="declared-read-only",
              raw_response=raw,claimed_sha256=hashlib.sha256(raw).hexdigest(),
              acquired_at="2026-11-23T10:00:00Z",
              valid_from="2026-11-23T09:00:00Z",
              valid_until="2026-11-23T11:00:00Z",isolated_test=True)
    return ledger,args

def test_unknown_evidence_durable_and_reopened(case):
    ledger,args=case
    s=EvidenceSourceTrustService(ledger)
    first=s.record(**args)
    reopened=EvidenceSourceTrustService(GovernanceLedger(ledger.db_path))
    assert reopened.record(**args)["id"]==first["id"]
    info=reopened.inspect("e1")
    assert info["reconciliation_required"] is True
    assert info["production_eligible"] is False
    assert info["automatic_replay_allowed"] is False
    path=ledger.resolve_storage_ref(first["payload"]["raw_storage_ref"])
    assert path.read_bytes()==args["raw_response"]

@pytest.mark.parametrize("changed",[
    {"channel_ref":"different"},{"platform":"tiktok"},{"post_id":"different"},
    {"content_version":"v2"},{"declared_source":"different"},
    {"state":"EVIDENCE_CONFLICT"},{"raw_response":b"other"},
])
def test_reopen_conflict(case,changed):
    ledger,args=case
    EvidenceSourceTrustService(ledger).record(**args)
    updated={**args,**changed}
    if "raw_response" in changed:
        updated["claimed_sha256"]=hashlib.sha256(changed["raw_response"]).hexdigest()
    with pytest.raises(LedgerError,match="Conflicting"):
        EvidenceSourceTrustService(GovernanceLedger(ledger.db_path)).record(**updated)

@pytest.mark.parametrize("changed",[
    {"claimed_sha256":"0"*64},{"valid_until":"2026-11-23T08:00:00Z"},
    {"platform":"unknown"},{"state":"VERIFIED"},{"raw_response":b""},
])
def test_invalid_evidence_rejected(case,changed):
    ledger,args=case
    with pytest.raises(LedgerError):
        EvidenceSourceTrustService(ledger).record(**{**args,**changed})

def test_no_production_promotion(case):
    ledger,args=case
    service=EvidenceSourceTrustService(ledger)
    service.record(**args)
    with pytest.raises(LedgerError,match="HOLD"):
        service.verify_production("e1")

def test_relationship_mismatch(case):
    ledger,args=case
    parent=ledger.record_domain("PUBLISHER_TEST_COMMAND","Test",
        {"platform":"instagram","channel_ref":"channel","post_id":"post",
         "creative_state_id":"creative","content_version":"v1"},natural_key="parent")
    with pytest.raises(LedgerError,match="relationship mismatch"):
        EvidenceSourceTrustService(ledger).record(**{**args,"related_state_id":parent.state_id})

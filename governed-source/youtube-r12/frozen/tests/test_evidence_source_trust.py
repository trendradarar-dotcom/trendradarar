import hashlib
import pytest
from trend_hunter.db import init_db, connect
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

def _independent_claim(db, args, start, queue):
    start.wait(10)
    try:
        state = EvidenceSourceTrustService(GovernanceLedger(db)).record(**args)
        queue.put(("ok", state["id"]))
    except Exception as exc:
        queue.put(("error", str(exc)))


def test_two_independent_processes_same_identity(case):
    import multiprocessing as mp
    ledger, args = case
    ctx = mp.get_context("spawn")
    start, queue = ctx.Event(), ctx.Queue()
    workers = [ctx.Process(target=_independent_claim,
                           args=(ledger.db_path, {**args, "isolated_test": False},
                                 start, queue)) for _ in range(2)]
    for worker in workers:
        worker.start()
    start.set()
    outcomes = [queue.get(timeout=20) for _ in workers]
    for worker in workers:
        worker.join(timeout=20)
        assert worker.exitcode == 0
    assert all(x[0] in {"ok", "error"} for x in outcomes)
    with connect(ledger.db_path) as conn:
        assert conn.execute(
            "SELECT count(*) FROM artifact_state s JOIN artifact_identity i ON i.id=s.identity_id "
            "WHERE i.kind='EVIDENCE_SOURCE_TRUST' AND i.natural_key='evidence-source:e1'"
        ).fetchone()[0] <= 1
    # A pending claim must be manually reconciled; no automatic retry.
    if any(x[0] == "error" for x in outcomes):
        assert all("Interrupted evidence claim" in x[1] for x in outcomes if x[0] == "error")


@pytest.mark.parametrize("point", ["after_claim", "after_raw", "before_commit"])
def test_interruption_persists_claim_without_false_success(case, point):
    ledger, args = case
    service = EvidenceSourceTrustService(ledger)
    payload = dict(evidence_id=args["evidence_id"], declared_source=args["declared_source"],
        source_authenticated=False, access_authorized=False,
        platform=args["platform"], channel_ref=args["channel_ref"], post_id=args["post_id"],
        creative_state_id=args["creative_state_id"], content_version=args["content_version"],
        access_scope=args["access_scope"], claimed_sha256=args["claimed_sha256"],
        acquired_at=args["acquired_at"], valid_from=args["valid_from"],
        valid_until=args["valid_until"], state="SOURCE_UNVERIFIED",
        related_state_id=None, synthetic_only=True, production_eligible=False,
        automatic_replay_allowed=False, independent_verification="NOT_AVAILABLE",
        raw_storage_ref=ledger._object_ref("sha256", args["claimed_sha256"]))
    with pytest.raises(LedgerError, match="Simulated"):
        ledger.record_evidence_claim_atomic(
            claim_key="e1", payload=payload, raw_bytes=args["raw_response"],
            failpoint=point)
    reopened = GovernanceLedger(ledger.db_path)
    with connect(reopened.db_path) as conn:
        claim = conn.execute(
            "SELECT metadata_json FROM artifact_identity "
            "WHERE kind='EVIDENCE_SOURCE_ATOMIC_CLAIM' AND natural_key='evidence-source:e1'"
        ).fetchone()
        assert claim is not None
        assert conn.execute(
            "SELECT count(*) FROM artifact_state s JOIN artifact_identity i ON i.id=s.identity_id "
            "WHERE i.kind='EVIDENCE_SOURCE_TRUST' AND i.natural_key='evidence-source:e1'"
        ).fetchone()[0] == 0
    with pytest.raises(LedgerError, match="Interrupted"):
        reopened.record_evidence_claim_atomic(
            claim_key="e1", payload=payload, raw_bytes=args["raw_response"])
    decision = reopened.reconcile_evidence_claim(
        claim_key="e1", decision="KEEP_HOLD", reason="interrupted write",
        reviewer_ref="local-reviewer")
    assert decision["production_eligible"] is False
    assert decision["automatic_replay_allowed"] is False


def test_conflict_audit_is_durable(case):
    ledger, args = case
    EvidenceSourceTrustService(ledger).record(**args)
    with pytest.raises(LedgerError, match="Conflicting"):
        EvidenceSourceTrustService(GovernanceLedger(ledger.db_path)).record(
            **{**args, "post_id": "different"})
    with connect(ledger.db_path) as conn:
        assert conn.execute(
            "SELECT count(*) FROM artifact_identity WHERE kind='EVIDENCE_SOURCE_CONFLICT'"
        ).fetchone()[0] == 1

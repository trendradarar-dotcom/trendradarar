from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest
from tests._governance_template import isolated_governance_ledger

from trend_hunter.db import init_db, connect
from trend_hunter.ledger import GovernanceLedger, LedgerError
from trend_hunter.bootstrap import bootstrap_governance
from trend_hunter.pipeline import SyntheticPilotRunner


@pytest.fixture()
def ledger(tmp_path: Path):
    return isolated_governance_ledger(tmp_path, 'ledger')


def test_identity_state_are_distinct_and_versioned(ledger: GovernanceLedger):
    iid = ledger.get_or_create_identity("TEST", "A")
    s1 = ledger.create_state(iid, "TEST_STATE", {"x": 1})
    s2 = ledger.create_state(iid, "TEST_STATE", {"x": 2}, supersedes_state_id=s1.state_id)
    assert s1.identity_id == s2.identity_id
    assert s1.state_id != s2.state_id
    assert s1.version == 1 and s2.version == 2


def test_append_only_trigger(ledger: GovernanceLedger):
    iid = ledger.get_or_create_identity("TEST", "B")
    s = ledger.create_state(iid, "TEST_STATE", {"x": 1})
    with connect(ledger.db_path) as conn:
        with pytest.raises(sqlite3.DatabaseError):
            conn.execute("UPDATE artifact_state SET status='X' WHERE id=?", (s.state_id,))


def test_raw_and_canonical_hash_are_separate(ledger: GovernanceLedger):
    iid = ledger.get_or_create_identity("TEST", "C")
    s = ledger.create_state(iid, "TEST_STATE", {"a": 1, "b": 2}, raw_bytes=b'{"b":2, "a":1}\n')
    st = ledger.get_state(s.state_id)
    assert st["raw_hash"] != st["canonical_hash"]
    assert ledger.integrity_check()["ok"]


def test_delegation_cannot_exceed_scope_or_cycle(ledger: GovernanceLedger):
    root = ledger.add_authority_grant("PROCESS", "root", {"domain": "H", "scope": ["A","B"]}, can_delegate=True, root_basis_state_id=None, effective_from="2026-08-10T00:00:00+00:00")
    child = ledger.add_authority_grant("PROCESS", "child", {"domain": "H", "scope": ["A"]}, can_delegate=True, root_basis_state_id=None, effective_from="2026-08-10T00:00:00+00:00")
    ledger.add_delegation(root, child, {"domain": "H", "scope": ["A"]}, effective_from="2026-08-10T00:00:00+00:00")
    with pytest.raises(LedgerError):
        ledger.add_delegation(child, root, {"domain": "H", "scope": ["A"]}, effective_from="2026-08-10T00:00:00+00:00")
    wider = ledger.add_authority_grant("PROCESS", "wider", {"domain": "H", "scope": ["A","B","C"]}, can_delegate=False, root_basis_state_id=None, effective_from="2026-08-10T00:00:00+00:00")
    with pytest.raises(LedgerError):
        ledger.add_delegation(child, wider, {"domain": "H", "scope": ["A","B"]}, effective_from="2026-08-10T00:00:00+00:00")


def test_adjudication_pins_exact_consumed_hashes_and_current_view(ledger: GovernanceLedger):
    src_i = ledger.get_or_create_identity("SOURCE", "src")
    src = ledger.create_state(src_i, "SOURCE_RECORD", {"x": 1})
    norm_id, norm = ledger.create_normalization(src.state_id, {"x": 1, "normalized": True})
    mid = ledger.create_methodology("TEST_METH", 1, {"frozen": True})
    corpus = ledger.create_audit_corpus(mid, [src.state_id, norm.state_id], {"surface":"test"})
    target = ledger.create_target("test:authority", "AUTHORITY_ACTUALITY")
    d1 = ledger.create_adjudication(target, mid, corpus, "UNRESOLVED", {}, [(src.state_id,"SOURCE"),(norm.state_id,"NORMALIZED")])
    with connect(ledger.db_path) as conn:
        rows = conn.execute("SELECT * FROM adjudication_consumed_artifact WHERE adjudication_id=?", (d1,)).fetchall()
        assert len(rows) == 2
        cv = conn.execute("SELECT * FROM current_view_projection WHERE projection_key=?", (f"adjudication:{target}",)).fetchone()
        assert cv["current_adjudication_id"] == d1


def test_synthetic_demo_stops_before_human_authorization(ledger: GovernanceLedger):
    result = SyntheticPilotRunner(ledger).run()
    assert result.stopped_at == "HUMAN_FINAL_AUTHORIZATION"
    assert "PUBLICATION_RECOMMENDATION" in result.records
    creative = ledger.get_state(result.records["CREATIVE_ARTIFACT"][0])
    assert creative["payload"]["target"] == {"language": "ar", "region": "SA", "platform": "youtube"}
    assert "HUMAN_AUTHORIZATION" not in result.records
    assert "MONETIZATION_ACTIVATION" not in result.records
    assert ledger.integrity_check()["ok"]


def test_u1_envelope_has_exact_contract_reference_pins(ledger: GovernanceLedger):
    from trend_hunter.db import connect
    with connect(ledger.db_path) as conn:
        parent=conn.execute("SELECT id FROM governance_contract_version WHERE contract_key='U1_EFFECTIVE_ENVELOPE' AND version=1").fetchone()
        refs=conn.execute("SELECT * FROM governance_contract_reference WHERE parent_contract_version_id=?",(parent['id'],)).fetchall()
        assert {r['reference_role'] for r in refs} == {
            'PURPOSE_ANCHOR','MANDATORY_CLASS_K_GAP','CLASS_SATISFACTION','ADMISSIBILITY_PREDICATE',
            'SUFFICIENCY_PREDICATE','COVERAGE_FORMULA','ROUTING_COMBINATION_RULE'
        }
        assert all(r['exact_raw_hash'] for r in refs)


def test_target_key_cannot_be_reused_for_different_semantics(ledger: GovernanceLedger):
    target=ledger.create_target('same-key','AUTHORITY_ACTUALITY',semantic_scope={'region':'SA'},time_basis={'t':'T1'})
    assert target
    with pytest.raises(LedgerError):
        ledger.create_target('same-key','AUTHORITY_ACTUALITY',semantic_scope={'region':'US'},time_basis={'t':'T1'})


def test_adjudication_can_pin_normalization_correspondence_and_entitlement(ledger: GovernanceLedger):
    from trend_hunter.db import connect
    src_i=ledger.get_or_create_identity('SOURCE','ent-src')
    src=ledger.create_state(src_i,'SOURCE_RECORD',{'assertion':'H was approved'})
    nid,norm=ledger.create_normalization(src.state_id,{'assertion':'H was approved','normalized':True})
    mid=ledger.create_methodology('ENT_METH',1,{'frozen':True})
    cid=ledger.create_correspondence(src.state_id,norm.state_id,'SEMANTIC_CORRESPONDENCE',methodology_version_id=mid)
    target=ledger.create_target('ent-target','GOVERNING_ADOPTION',semantic_scope={'H':'Cross-Market-Gap'})
    eid,ent=ledger.create_evidentiary_entitlement(src.state_id,target,entitlement_state='ENTITLED',proposition_strength='ASSERTION_OF_PRIOR_APPROVAL',methodology_version_id=mid,basis={'limited':True})
    corpus=ledger.create_audit_corpus(mid,[src.state_id,norm.state_id,ledger.normalization_assertion_artifact_state(nid),ledger.correspondence_judgment_artifact_state(cid),ent.state_id],{'surface':'test'})
    adj=ledger.create_adjudication(target,mid,corpus,'UNRESOLVED',{},[(src.state_id,'SOURCE')],consumed_normalization_assertion_ids=[nid],consumed_correspondence_judgment_ids=[cid],consumed_entitlement_ids=[eid])
    with connect(ledger.db_path) as conn:
        roles={r['consumption_role'] for r in conn.execute('SELECT consumption_role FROM adjudication_consumed_artifact WHERE adjudication_id=?',(adj,))}
    assert {'SOURCE','NORMALIZATION_ASSERTION','CORRESPONDENCE_JUDGMENT','EVIDENTIARY_ENTITLEMENT'} <= roles
    assert ledger.integrity_check()['ok']


def test_connect_context_manager_closes_connection(tmp_path: Path):
    import sqlite3
    from trend_hunter.db import connect, init_db

    db = tmp_path / "close.db"
    init_db(str(db))
    with connect(str(db)) as conn:
        assert conn.execute("SELECT 1").fetchone()[0] == 1
    with pytest.raises(sqlite3.ProgrammingError, match="closed database"):
        conn.execute("SELECT 1")

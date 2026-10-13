from __future__ import annotations

import pytest

from tests._governance_template import isolated_governance_ledger
from trend_hunter.ledger import GovernanceLedger, LedgerError
from trend_hunter.scale_policy import LearningScaleStopService, RepeatabilityPolicy


def base(tmp_path):
    l = isolated_governance_ledger(tmp_path, 'scale')
    subject = l.get_or_create_identity("OPPORTUNITY_SUBJECT", "subject:scale")
    channel = l.record_domain("LIVE_CHANNEL_BINDING", "Operationalization Channel Binding", {"platform":"youtube","language":"ar","region":"SA","channel_ref":"c1","status":"ACTIVE"}, natural_key="channel:youtube:c1", subject_identity_id=subject, record_state="ACTIVE")
    cfg = l.record_domain("MONETIZATION_CONFIGURATION", "MCAA", {"mechanism":"AD_REVENUE","provider":"adsense","account_ref":"acct-A","offer_or_product_ref":None,"campaign_ref":None,"tracked_destination":None}, natural_key="mon:1", subject_identity_id=subject, record_state="READY_FOR_ACTIVATION")
    act = l.record_domain("MONETIZATION_ACTIVATION", "MCAA", {"monetization_configuration_state_id":cfg.state_id,"activation_state":"ACTIVE"}, natural_key="act:1", subject_identity_id=subject, record_state="ACTIVE", upstream_states=[(cfg.state_id,"ACTIVATES_CONFIGURATION")])
    return l, subject, channel, cfg, act


def outcome(l, subject, channel, act, key, profit, currency="SAR", *, synthetic=False, performance=None):
    ev = l.record_domain("EVIDENCE", "Economic Evidence Authority", {"synthetic":synthetic,"amount":abs(profit)+10,"currency":currency}, natural_key=f"ev:{key}", subject_identity_id=subject, record_state="VERIFIED")
    pub = l.record_domain("PUBLICATION_EXECUTION", "Execution / Publication Records", {"channel_binding_state_id":channel.state_id,"monetization_activation_state_id":act.state_id,"performance":performance or {}}, natural_key=f"pub:{key}", subject_identity_id=subject, record_state="EXECUTED")
    return l.record_domain("REALIZED_ECONOMIC_OUTCOME", "Economic Outcome & Learning Authority", {
        "publication_state_id":pub.state_id,
        "profit":{"amount":profit,"currency":currency},
        "profit_verification":{"status":"SYSTEM_EVIDENCE_BOUND","evidence_status":"SYSTEM_EVIDENCE_BOUND","evidence_state_ids":[ev.state_id]},
        "evaluation_blockers":[],
    }, natural_key=f"out:{key}", subject_identity_id=subject, record_state="REALIZED", upstream_states=[(pub.state_id,"OUTCOME_OF"),(ev.state_id,"ECONOMIC_EVIDENCE")])


def decision(l, ids, n=2):
    return l.get_state(LearningScaleStopService(l).decide(ids, policy=RepeatabilityPolicy(n)).state_id)["payload"]


def test_policy_cannot_scale_on_single_outcome_by_configuration(tmp_path):
    l, subject, ch, cfg, act = base(tmp_path); a = outcome(l,subject,ch,act,"a",10)
    with pytest.raises(LedgerError, match="single"):
        LearningScaleStopService(l).decide([a.state_id], policy=RepeatabilityPolicy(1))
    assert decision(l,[a.state_id],2)["decision"] == "CONTINUE"


def test_two_verified_profitable_same_route_can_scale_when_policy_min_is_two(tmp_path):
    l, subject, ch, cfg, act = base(tmp_path)
    a=outcome(l,subject,ch,act,"a",10); b=outcome(l,subject,ch,act,"b",5)
    p=decision(l,[a.state_id,b.state_id],2)
    assert p["decision"] == "SCALE" and p["sample_size"] == 2


def test_viral_video_does_not_override_repeatability(tmp_path):
    l, subject, ch, cfg, act = base(tmp_path)
    a=outcome(l,subject,ch,act,"viral",100,performance={"views":100_000_000})
    assert decision(l,[a.state_id],2)["decision"] == "CONTINUE"


def test_one_profit_followed_by_loss_never_scales(tmp_path):
    l, subject, ch, cfg, act = base(tmp_path)
    a=outcome(l,subject,ch,act,"a",10); b=outcome(l,subject,ch,act,"b",-20)
    assert decision(l,[a.state_id,b.state_id],2)["decision"] == "STOP"


def test_mixed_currency_pauses(tmp_path):
    l, subject, ch, cfg, act = base(tmp_path)
    a=outcome(l,subject,ch,act,"a",10,"SAR"); b=outcome(l,subject,ch,act,"b",10,"USD")
    p=decision(l,[a.state_id,b.state_id],2)
    assert p["decision"] == "PAUSE" and "NON_COMPARABLE_CURRENCIES" in p["blockers"]


def test_synthetic_economic_evidence_pauses(tmp_path):
    l, subject, ch, cfg, act = base(tmp_path)
    a=outcome(l,subject,ch,act,"a",10); b=outcome(l,subject,ch,act,"b",10,synthetic=True)
    p=decision(l,[a.state_id,b.state_id],2)
    assert p["decision"] == "PAUSE" and "SYNTHETIC_ECONOMIC_EVIDENCE" in p["blockers"]


def test_mixed_channels_pause(tmp_path):
    l, subject, ch, cfg, act = base(tmp_path)
    ch2=l.record_domain("LIVE_CHANNEL_BINDING","Operationalization Channel Binding",{"platform":"youtube","language":"ar","region":"SA","channel_ref":"c2","status":"ACTIVE"},natural_key="channel:youtube:c2",subject_identity_id=subject,record_state="ACTIVE")
    a=outcome(l,subject,ch,act,"a",10); b=outcome(l,subject,ch2,act,"b",10)
    p=decision(l,[a.state_id,b.state_id],2)
    assert p["decision"] == "PAUSE" and "MIXED_CHANNELS" in p["blockers"]


def test_mixed_monetization_paths_pause(tmp_path):
    l, subject, ch, cfg, act = base(tmp_path)
    cfg2=l.record_domain("MONETIZATION_CONFIGURATION","MCAA",{"mechanism":"AFFILIATE","provider":"p2","account_ref":"acct-B","offer_or_product_ref":"o","campaign_ref":None,"tracked_destination":None},natural_key="mon:2",subject_identity_id=subject,record_state="READY_FOR_ACTIVATION")
    act2=l.record_domain("MONETIZATION_ACTIVATION","MCAA",{"monetization_configuration_state_id":cfg2.state_id,"activation_state":"ACTIVE"},natural_key="act:2",subject_identity_id=subject,record_state="ACTIVE")
    a=outcome(l,subject,ch,act,"a",10); b=outcome(l,subject,ch,act2,"b",10)
    p=decision(l,[a.state_id,b.state_id],2)
    assert p["decision"] == "PAUSE" and "MIXED_MONETIZATION_PATHS" in p["blockers"]



def test_same_provider_but_different_monetization_account_pauses(tmp_path):
    l, subject, ch, cfg, act = base(tmp_path)
    cfg2=l.record_domain("MONETIZATION_CONFIGURATION","MCAA",{"mechanism":"AD_REVENUE","provider":"adsense","account_ref":"acct-B","offer_or_product_ref":None,"campaign_ref":None,"tracked_destination":None},natural_key="mon:account-b",subject_identity_id=subject,record_state="READY_FOR_ACTIVATION")
    act2=l.record_domain("MONETIZATION_ACTIVATION","MCAA",{"monetization_configuration_state_id":cfg2.state_id,"activation_state":"ACTIVE"},natural_key="act:account-b",subject_identity_id=subject,record_state="ACTIVE")
    a=outcome(l,subject,ch,act,"a",10); b=outcome(l,subject,ch,act2,"b",10)
    p=decision(l,[a.state_id,b.state_id],2)
    assert p["decision"] == "PAUSE" and "MIXED_MONETIZATION_PATHS" in p["blockers"]

def test_stale_outcome_pauses(tmp_path):
    l, subject, ch, cfg, act = base(tmp_path)
    a=outcome(l,subject,ch,act,"a",10); b=outcome(l,subject,ch,act,"b",10)
    l.create_state(a.identity_id,"REALIZED_ECONOMIC_OUTCOME",{**l.get_state(a.state_id)["payload"],"correction":True},supersedes_state_id=a.state_id)
    p=decision(l,[a.state_id,b.state_id],2)
    assert p["decision"] == "PAUSE" and "STALE_OR_SUPERSEDED_OUTCOME" in p["blockers"]


def test_missing_exact_economic_evidence_pauses(tmp_path):
    l, subject, ch, cfg, act = base(tmp_path)
    a=outcome(l,subject,ch,act,"a",10); b=outcome(l,subject,ch,act,"b",10)
    bp = dict(l.get_state(b.state_id)["payload"])
    bp["profit_verification"] = {"status":"SYSTEM_EVIDENCE_BOUND","evidence_status":"SYSTEM_EVIDENCE_BOUND","evidence_state_ids":[]}
    b2 = l.create_state(b.identity_id, "REALIZED_ECONOMIC_OUTCOME", bp, supersedes_state_id=b.state_id)
    p=decision(l,[a.state_id,b2.state_id],2)
    assert p["decision"] == "PAUSE" and "NO_EXACT_ECONOMIC_EVIDENCE" in p["blockers"]


def test_superseded_economic_evidence_pauses(tmp_path):
    l, subject, ch, cfg, act = base(tmp_path)
    a=outcome(l,subject,ch,act,"a",10); b=outcome(l,subject,ch,act,"b",10)
    evid = l.get_state(b.state_id)["payload"]["profit_verification"]["evidence_state_ids"][0]
    ev = l.get_state(evid)
    l.create_state(ev["identity_id"], "EVIDENCE", {**ev["payload"], "corrected": True}, supersedes_state_id=evid)
    p=decision(l,[a.state_id,b.state_id],2)
    assert p["decision"] == "PAUSE" and "STALE_OR_WRONG_TYPE_ECONOMIC_EVIDENCE" in p["blockers"]

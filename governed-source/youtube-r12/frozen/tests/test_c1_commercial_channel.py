from __future__ import annotations

import pytest

from trend_hunter.commercial_channel import CommercialChannelService
from trend_hunter.ledger import GovernanceLedger, LedgerError
from tests._governance_template import isolated_governance_ledger
from trend_hunter.monetization import MonetizationService


def make_ledger(tmp_path):
    ledger = isolated_governance_ledger(tmp_path, 'commercial')
    ledger._test_subject_identity = ledger.get_or_create_identity("OPPORTUNITY_SUBJECT", "subject:1")
    return ledger


def opportunity(ledger):
    return ledger.record_domain(
        "OPPORTUNITY", "Opportunity Authority", {"title": "real candidate"},
        natural_key="opp:1", subject_identity_id=ledger._test_subject_identity, record_state="CANDIDATE"
    )


def current_channel(ledger, *, platform="youtube", language="ar", region="SA"):
    return ledger.record_domain(
        "LIVE_CHANNEL_BINDING", "Operationalization Channel Binding",
        {"platform": platform, "language": language, "region": region, "channel_ref": "owned-1", "status": "ACTIVE"},
        natural_key="channel:youtube:owned-1", record_state="ACTIVE"
    )


def independent_basis(ledger):
    return ledger.record_domain(
        "SOURCE_RECORD", "Source Adapter Authority",
        {"connector": "youtube", "external_id": "channel-audit-1", "synthetic": False},
        natural_key="source:channel-audit-1", record_state="OBSERVED"
    )


def suitability(ledger, channel_state_id, *, platform="youtube", language="ar", region="SA", suitable=True, synthetic=False, record_state="VERIFIED", review_scope="COMMERCIAL_CHANNEL_SUITABILITY", basis_state_ids=None):
    if basis_state_ids is None:
        basis_state_ids = [independent_basis(ledger).state_id]
    return ledger.record_domain(
        "EVIDENCE", "Commercial Channel Evidence Authority", {
            "review_scope": review_scope,
            "channel_state_id": channel_state_id,
            "platform": platform, "language": language, "region": region,
            "suitable": suitable, "verification_status": "VERIFIED",
            "synthetic": synthetic, "basis_state_ids": basis_state_ids,
        },
        natural_key="channel-suitability:1", subject_identity_id=ledger._test_subject_identity, record_state=record_state,
        upstream_states=[(channel_state_id, "EVIDENCE_FOR_EXACT_CHANNEL")],
    )


def path(provider="adsense", account_ref=None):
    return {"mechanism": "AD_REVENUE", "provider": provider, "account_ref": account_ref, "offer_or_product_ref": None, "campaign_ref": None, "tracked_destination": None}


def test_reuse_existing_requires_exact_current_channel_and_independent_evidence(tmp_path):
    ledger = make_ledger(tmp_path); opp = opportunity(ledger); ch = current_channel(ledger); ev = suitability(ledger, ch.state_id)
    out = CommercialChannelService(ledger).evaluate(
        opportunity_state_id=opp.state_id, decision="REUSE_EXISTING", platform="youtube", language="ar", region="SA",
        monetization_path=path(), existing_channel_state_id=ch.state_id, suitability_evidence_state_id=ev.state_id,
    )
    assert ledger.get_state(out.state_id)["payload"]["decision"] == "REUSE_EXISTING"


@pytest.mark.parametrize("field,value", [("platform", "tiktok"), ("language", "en"), ("region", "US")])
def test_reuse_existing_rejects_target_mismatch(tmp_path, field, value):
    ledger = make_ledger(tmp_path); opp = opportunity(ledger); ch = current_channel(ledger); ev = suitability(ledger, ch.state_id)
    kwargs = {"platform": "youtube", "language": "ar", "region": "SA"}; kwargs[field] = value
    with pytest.raises(LedgerError):
        CommercialChannelService(ledger).evaluate(
            opportunity_state_id=opp.state_id, decision="REUSE_EXISTING", monetization_path=path(),
            existing_channel_state_id=ch.state_id, suitability_evidence_state_id=ev.state_id, **kwargs,
        )


def test_reuse_existing_rejects_stale_channel(tmp_path):
    ledger = make_ledger(tmp_path); opp = opportunity(ledger); ch = current_channel(ledger); ev = suitability(ledger, ch.state_id)
    ledger.record_domain("LIVE_CHANNEL_BINDING", "Operationalization Channel Binding", {"platform": "youtube", "language": "ar", "region": "SA", "channel_ref": "owned-1", "status": "ACTIVE", "changed": True}, natural_key="channel:youtube:owned-1", record_state="ACTIVE")
    with pytest.raises(LedgerError, match="stale/superseded"):
        CommercialChannelService(ledger).evaluate(
            opportunity_state_id=opp.state_id, decision="REUSE_EXISTING", platform="youtube", language="ar", region="SA",
            monetization_path=path(), existing_channel_state_id=ch.state_id, suitability_evidence_state_id=ev.state_id,
        )


def test_reuse_existing_rejects_stale_evidence(tmp_path):
    ledger = make_ledger(tmp_path); opp = opportunity(ledger); ch = current_channel(ledger); ev = suitability(ledger, ch.state_id)
    ledger.create_state(ev.identity_id, "EVIDENCE", {**ledger.get_state(ev.state_id)["payload"], "suitable": False}, supersedes_state_id=ev.state_id)
    with pytest.raises(LedgerError, match="stale/superseded"):
        CommercialChannelService(ledger).evaluate(
            opportunity_state_id=opp.state_id, decision="REUSE_EXISTING", platform="youtube", language="ar", region="SA",
            monetization_path=path(), existing_channel_state_id=ch.state_id, suitability_evidence_state_id=ev.state_id,
        )


@pytest.mark.parametrize("mutator", [
    lambda kw: kw.update(synthetic=True),
    lambda kw: kw.update(record_state="AVAILABLE"),
    lambda kw: kw.update(review_scope="GENERIC"),
    lambda kw: kw.update(suitable=False),
])
def test_reuse_existing_rejects_unqualified_suitability_evidence(tmp_path, mutator):
    ledger = make_ledger(tmp_path); opp = opportunity(ledger); ch = current_channel(ledger)
    kw = {}; mutator(kw); ev = suitability(ledger, ch.state_id, **kw)
    with pytest.raises(LedgerError):
        CommercialChannelService(ledger).evaluate(
            opportunity_state_id=opp.state_id, decision="REUSE_EXISTING", platform="youtube", language="ar", region="SA",
            monetization_path=path(), existing_channel_state_id=ch.state_id, suitability_evidence_state_id=ev.state_id,
        )



def test_reuse_existing_rejects_evidence_without_independent_basis(tmp_path):
    ledger = make_ledger(tmp_path); opp = opportunity(ledger); ch = current_channel(ledger)
    ev = suitability(ledger, ch.state_id, basis_state_ids=[])
    with pytest.raises(LedgerError, match="independent governed basis"):
        CommercialChannelService(ledger).evaluate(
            opportunity_state_id=opp.state_id, decision="REUSE_EXISTING", platform="youtube", language="ar", region="SA",
            monetization_path=path(), existing_channel_state_id=ch.state_id, suitability_evidence_state_id=ev.state_id,
        )

def test_create_new_and_hold_cannot_smuggle_reuse_proof(tmp_path):
    ledger = make_ledger(tmp_path); opp = opportunity(ledger); ch = current_channel(ledger); ev = suitability(ledger, ch.state_id)
    svc = CommercialChannelService(ledger)
    for decision in ("CREATE_NEW", "HOLD"):
        with pytest.raises(LedgerError):
            svc.evaluate(
                opportunity_state_id=opp.state_id, decision=decision, platform="youtube", language="ar", region="SA",
                monetization_path=path(), existing_channel_state_id=ch.state_id, suitability_evidence_state_id=ev.state_id,
            )


def test_monetization_path_is_exactly_bound_and_substitution_rejected(tmp_path):
    ledger = make_ledger(tmp_path); opp = opportunity(ledger); ch = current_channel(ledger); ev = suitability(ledger, ch.state_id)
    svc = CommercialChannelService(ledger)
    decision = svc.evaluate(
        opportunity_state_id=opp.state_id, decision="REUSE_EXISTING", platform="youtube", language="ar", region="SA",
        monetization_path=path("adsense"), existing_channel_state_id=ch.state_id, suitability_evidence_state_id=ev.state_id,
    )
    # MonetizationService requires a PRIORITY_DECISION; create one explicitly for the same subject.
    pr = ledger.record_domain("PRIORITY_DECISION", "Priority Authority", {"decision": "ALLOCATE"}, natural_key="priority:1", subject_identity_id=ledger._test_subject_identity, record_state="ALLOCATED")
    mon = MonetizationService(ledger).configure(
        pr.state_id, mechanism="AD_REVENUE", provider="adsense", account_ref=None, offer_or_product_ref=None,
        campaign_ref=None, tracked_destination=None, attribution={}, payout_terms={}, currency="SAR",
    )
    svc.assert_monetization_configuration_matches(decision.state_id, mon.state_id)

    with pytest.raises(LedgerError, match="differs from the current evaluated"):
        MonetizationService(ledger).configure(
            pr.state_id, mechanism="AD_REVENUE", provider="other-provider", account_ref=None, offer_or_product_ref=None,
            campaign_ref=None, tracked_destination=None, attribution={}, payout_terms={}, currency="SAR",
        )



def test_monetization_account_substitution_is_rejected(tmp_path):
    ledger = make_ledger(tmp_path); opp = opportunity(ledger); ch = current_channel(ledger); ev = suitability(ledger, ch.state_id)
    svc = CommercialChannelService(ledger)
    d = svc.evaluate(opportunity_state_id=opp.state_id, decision="REUSE_EXISTING", platform="youtube", language="ar", region="SA", monetization_path=path("adsense", "acct-A"), existing_channel_state_id=ch.state_id, suitability_evidence_state_id=ev.state_id)
    pr = ledger.record_domain("PRIORITY_DECISION", "Priority Authority", {"decision": "ALLOCATE"}, natural_key="priority:account-sub", subject_identity_id=ledger._test_subject_identity, record_state="ALLOCATED")
    with pytest.raises(LedgerError, match="differs from the current evaluated"):
        MonetizationService(ledger).configure(pr.state_id, mechanism="AD_REVENUE", provider="adsense", account_ref="acct-B", offer_or_product_ref=None, campaign_ref=None, tracked_destination=None, attribution={}, payout_terms={}, currency="SAR")


def test_monetization_service_automatically_enforces_current_channel_decision(tmp_path):
    ledger = make_ledger(tmp_path); opp = opportunity(ledger); ch = current_channel(ledger); ev = suitability(ledger, ch.state_id)
    svc = CommercialChannelService(ledger)
    d = svc.evaluate(opportunity_state_id=opp.state_id, decision="REUSE_EXISTING", platform="youtube", language="ar", region="SA", monetization_path=path("adsense", "acct-A"), existing_channel_state_id=ch.state_id, suitability_evidence_state_id=ev.state_id)
    pr = ledger.record_domain("PRIORITY_DECISION", "Priority Authority", {"decision": "ALLOCATE"}, natural_key="priority:auto-enforce", subject_identity_id=ledger._test_subject_identity, record_state="ALLOCATED")
    good = MonetizationService(ledger).configure(pr.state_id, mechanism="AD_REVENUE", provider="adsense", account_ref="acct-A", offer_or_product_ref=None, campaign_ref=None, tracked_destination=None, attribution={}, payout_terms={}, currency="SAR")
    assert ledger.get_state(good.state_id)["payload"]["commercial_channel_decision_state_id"] == d.state_id
    with pytest.raises(LedgerError, match="differs from the current evaluated"):
        MonetizationService(ledger).configure(pr.state_id, mechanism="AD_REVENUE", provider="adsense", account_ref="acct-B", offer_or_product_ref=None, campaign_ref=None, tracked_destination=None, attribution={}, payout_terms={}, currency="SAR")

def test_missing_or_empty_monetization_path_fails_closed(tmp_path):
    ledger = make_ledger(tmp_path); opp = opportunity(ledger)
    for p in ({}, {"provider": "x"}, {"mechanism": ""}):
        with pytest.raises(LedgerError):
            CommercialChannelService(ledger).evaluate(
                opportunity_state_id=opp.state_id, decision="CREATE_NEW", platform="youtube", language="ar", region="SA", monetization_path=p,
            )


def test_newer_subject_channel_decision_cannot_be_bypassed_by_older_decision(tmp_path):
    ledger = make_ledger(tmp_path); opp = opportunity(ledger); ch = current_channel(ledger); ev = suitability(ledger, ch.state_id)
    svc = CommercialChannelService(ledger)
    old = svc.evaluate(
        opportunity_state_id=opp.state_id, decision="REUSE_EXISTING", platform="youtube", language="ar", region="SA",
        monetization_path=path("adsense", "acct-A"), existing_channel_state_id=ch.state_id, suitability_evidence_state_id=ev.state_id,
    )
    newer = svc.evaluate(
        opportunity_state_id=opp.state_id, decision="CREATE_NEW", platform="youtube", language="ar", region="SA",
        monetization_path=path("adsense", "acct-B"),
    )
    pr = ledger.record_domain("PRIORITY_DECISION", "Priority Authority", {"decision": "ALLOCATE"}, natural_key="priority:newer-channel-decision", subject_identity_id=ledger._test_subject_identity, record_state="ALLOCATED")
    with pytest.raises(LedgerError, match="differs from the current evaluated"):
        MonetizationService(ledger).configure(
            pr.state_id, mechanism="AD_REVENUE", provider="adsense", account_ref="acct-A", offer_or_product_ref=None,
            campaign_ref=None, tracked_destination=None, attribution={}, payout_terms={}, currency="SAR",
        )
    mon = MonetizationService(ledger).configure(
        pr.state_id, mechanism="AD_REVENUE", provider="adsense", account_ref="acct-B", offer_or_product_ref=None,
        campaign_ref=None, tracked_destination=None, attribution={}, payout_terms={}, currency="SAR",
    )
    mp = ledger.get_state(mon.state_id)["payload"]
    assert mp["commercial_channel_decision_state_id"] == newer.state_id
    assert mp["commercial_channel_decision_state_id"] != old.state_id

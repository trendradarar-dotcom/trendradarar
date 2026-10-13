from pathlib import Path
import pytest
from tests._governance_template import isolated_governance_ledger

from trend_hunter.db import connect
from trend_hunter.ledger import GovernanceLedger, LedgerError
from trend_hunter.pipeline import SyntheticPilotRunner
from trend_hunter.operations import OperationsService


def setup(tmp_path: Path):
    l=isolated_governance_ledger(tmp_path, 'operations')
    r=SyntheticPilotRunner(l).run(); return l,r


def economic_evidence(l: GovernanceLedger, publication_state_id: str, *, role: str, amount: float, currency: str, key: str):
    ops=OperationsService(l)
    source_name=f'governed-finance-provider-{key}'
    binding=ops.bind_economic_evidence_source(
        connector='finance_provider_fixture',
        source_name=source_name,
        allowed_roles=[role],
        allowed_currencies=[currency],
    )
    source=l.record_domain(
        'SOURCE_RECORD','Source Adapter Authority',
        {'source_name':source_name,'connector':'finance_provider_fixture','external_id':f'src-{key}','payload':{'fixture':False,'kind':'settled_transaction'}},
        natural_key=f'econ-source-{key}',record_state='OBSERVED'
    )
    return l.record_domain(
        'EVIDENCE','Evidence Authority',
        {
            'source_state_id':source.state_id,
            'economic_source_binding_state_id':binding.state_id,
            'publication_state_id':publication_state_id,
            'economic_role':role,
            'amount':amount,
            'currency':currency,
            'verification_status':'EXTERNAL_SOURCE_BOUND',
            'fixture':False,
        },
        natural_key=f'econ-evidence-{key}',record_state='VERIFIED',
        upstream_states=[
            (source.state_id,'ECONOMIC_EVIDENCE_SOURCE'),
            (binding.state_id,'ECONOMIC_EVIDENCE_SOURCE_AUTHORITY'),
        ],
    )


def test_activation_requires_governing_gates(tmp_path: Path):
    l,r=setup(tmp_path); ops=OperationsService(l)
    mon=r.records['MONETIZATION_CONFIGURATION'][0]
    with pytest.raises(LedgerError):
        ops.activate_monetization(mon, dependency_state_ids=[])


def test_human_auth_then_activation_and_execution(tmp_path: Path):
    l,r=setup(tmp_path); ops=OperationsService(l)
    rec=r.records['PUBLICATION_RECOMMENDATION'][0]
    auth=ops.record_human_authorization(rec,'test-human','AUTHORIZED')
    mon=r.records['MONETIZATION_CONFIGURATION'][0]
    deps=[auth.state_id, r.records['COMPLIANCE_ASSESSMENT'][0], r.records['ELIGIBILITY_ASSESSMENT'][0], r.records['CREATIVE_ARTIFACT'][0]]
    act=ops.activate_monetization(mon, dependency_state_ids=deps, provider_result_ref='fixture-activation')
    pub=ops.record_publication_execution(r.records['CREATIVE_ARTIFACT'][0],auth.state_id,channel='fixture',external_result_ref='fixture-post',monetization_activation_state_id=act.state_id)
    revenue_evidence=economic_evidence(l,pub.state_id,role='REVENUE',amount=5,currency='SAR',key='revenue-1')
    cost_evidence=economic_evidence(l,pub.state_id,role='COST',amount=2,currency='SAR',key='cost-1')
    out=ops.record_economic_outcome(pub.state_id,performance={'views':10},revenue={'amount':5,'currency':'SAR'},costs=[{'amount':2,'currency':'SAR'}],attribution={'basis':'fixture'},evidence_state_ids=[revenue_evidence.state_id,cost_evidence.state_id])
    payload=l.get_state(out['outcome'].state_id)['payload']
    assert payload['profit']['amount'] == 3
    assert payload['profit_verification']['status'] == 'SYSTEM_EVIDENCE_BOUND'
    assert payload['profit_verification']['audited_profit'] is False
    assert payload['profit_verification']['statutory_profit'] is False



def test_activation_fails_closed_when_reconciliation_policy_missing(tmp_path: Path, monkeypatch):
    l,r=setup(tmp_path); ops=OperationsService(l)
    rec=r.records['PUBLICATION_RECOMMENDATION'][0]
    auth=ops.record_human_authorization(rec,'test-human','AUTHORIZED')
    mon=r.records['MONETIZATION_CONFIGURATION'][0]
    deps=[auth.state_id, r.records['COMPLIANCE_ASSESSMENT'][0], r.records['ELIGIBILITY_ASSESSMENT'][0], r.records['CREATIVE_ARTIFACT'][0]]
    original=l.get_dependency_policy
    def fail_policy(key, version=1):
        if key == 'UPSTREAM_REQUIRES_RECONCILIATION':
            raise LedgerError('missing governed reconciliation policy')
        return original(key, version)
    monkeypatch.setattr(l, 'get_dependency_policy', fail_policy)
    with pytest.raises(LedgerError, match='missing governed reconciliation policy'):
        ops.activate_monetization(mon, dependency_state_ids=deps, provider_result_ref='fixture-activation')

def test_activation_requires_exact_creative_binding_and_matching_authorization(tmp_path: Path):
    l,r=setup(tmp_path); ops=OperationsService(l)
    rec=r.records['PUBLICATION_RECOMMENDATION'][0]
    auth=ops.record_human_authorization(rec,'test-human','AUTHORIZED')
    mon=r.records['MONETIZATION_CONFIGURATION'][0]
    deps=[auth.state_id, r.records['COMPLIANCE_ASSESSMENT'][0], r.records['ELIGIBILITY_ASSESSMENT'][0]]
    with pytest.raises(LedgerError):
        ops.activate_monetization(mon,dependency_state_ids=deps)


def test_material_commercial_commitment_can_require_commercial_authorization(tmp_path: Path):
    from trend_hunter.monetization import MonetizationService
    l,r=setup(tmp_path); ops=OperationsService(l)
    # Reconfigure from the selected priority with an explicit commercial-authorization requirement.
    mon=MonetizationService(l).configure(r.records['PRIORITY_DECISION'][0],mechanism='paid_affiliate',provider='p',account_ref='a',offer_or_product_ref='o',campaign_ref='c',tracked_destination='https://example.invalid/x',attribution={},payout_terms={'currency':'SAR'},currency='SAR',requires_commercial_authorization=True)
    # Existing creative is bound to another monetization configuration, so even with commercial auth this one cannot activate.
    commercial=ops.record_commercial_authorization(mon.state_id,'owner','AUTHORIZED')
    rec=r.records['PUBLICATION_RECOMMENDATION'][0]
    auth=ops.record_human_authorization(rec,'owner','AUTHORIZED')
    deps=[commercial.state_id,auth.state_id,r.records['COMPLIANCE_ASSESSMENT'][0],r.records['ELIGIBILITY_ASSESSMENT'][0],r.records['CREATIVE_ARTIFACT'][0]]
    with pytest.raises(LedgerError):
        ops.activate_monetization(mon.state_id,dependency_state_ids=deps)


def test_economic_outcome_blocks_mixed_currency_false_profit(tmp_path: Path):
    l,r=setup(tmp_path); ops=OperationsService(l)
    rec=r.records['PUBLICATION_RECOMMENDATION'][0]
    auth=ops.record_human_authorization(rec,'test-human','AUTHORIZED')
    mon=r.records['MONETIZATION_CONFIGURATION'][0]
    deps=[auth.state_id, r.records['COMPLIANCE_ASSESSMENT'][0], r.records['ELIGIBILITY_ASSESSMENT'][0], r.records['CREATIVE_ARTIFACT'][0]]
    act=ops.activate_monetization(mon, dependency_state_ids=deps, provider_result_ref='fixture-activation')
    pub=ops.record_publication_execution(r.records['CREATIVE_ARTIFACT'][0],auth.state_id,channel='fixture',external_result_ref='fixture-post-mixed',monetization_activation_state_id=act.state_id)
    revenue_evidence=economic_evidence(l,pub.state_id,role='REVENUE',amount=100,currency='SAR',key='mixed-revenue')
    cost_sar=economic_evidence(l,pub.state_id,role='COST',amount=20,currency='SAR',key='mixed-cost-sar')
    cost_usd=economic_evidence(l,pub.state_id,role='COST',amount=10,currency='USD',key='mixed-cost-usd')
    out=ops.record_economic_outcome(pub.state_id,performance={'views':10},revenue={'amount':100,'currency':'SAR'},costs=[{'amount':20,'currency':'SAR'},{'amount':10,'currency':'USD'}],attribution={'basis':'test'},evidence_state_ids=[revenue_evidence.state_id,cost_sar.state_id,cost_usd.state_id])
    payload=l.get_state(out['outcome'].state_id)['payload']
    assert payload['profit'] is None
    assert 'MIXED_COST_CURRENCIES' in payload['evaluation_blockers']
    with connect(l.db_path) as conn:
        assert conn.execute("SELECT record_state FROM domain_record WHERE artifact_state_id=?", (out['outcome'].state_id,)).fetchone()['record_state'] == 'NOT_EVALUABLE'


def test_economic_outcome_without_evidence_or_with_synthetic_evidence_cannot_be_verified_profit(tmp_path: Path):
    l,r=setup(tmp_path); ops=OperationsService(l)
    rec=r.records['PUBLICATION_RECOMMENDATION'][0]
    auth=ops.record_human_authorization(rec,'test-human','AUTHORIZED')
    mon=r.records['MONETIZATION_CONFIGURATION'][0]
    deps=[auth.state_id, r.records['COMPLIANCE_ASSESSMENT'][0], r.records['ELIGIBILITY_ASSESSMENT'][0], r.records['CREATIVE_ARTIFACT'][0]]
    act=ops.activate_monetization(mon, dependency_state_ids=deps, provider_result_ref='fixture-activation')
    pub=ops.record_publication_execution(r.records['CREATIVE_ARTIFACT'][0],auth.state_id,channel='fixture',external_result_ref='fixture-post-evidence',monetization_activation_state_id=act.state_id)
    no_evidence=ops.record_economic_outcome(pub.state_id,performance={'views':10},revenue={'amount':5,'currency':'SAR'},costs=[{'amount':2,'currency':'SAR'}],attribution={'basis':'test'})
    p1=l.get_state(no_evidence['outcome'].state_id)['payload']
    assert p1['profit'] is None
    assert p1['profit_verification']['evidence_status'] == 'INSUFFICIENT_NO_EVIDENCE'
    synthetic_sid=r.records['EVIDENCE'][0]
    synthetic=ops.record_economic_outcome(pub.state_id,performance={'views':10},revenue={'amount':5,'currency':'SAR'},costs=[{'amount':2,'currency':'SAR'}],attribution={'basis':'test'},evidence_state_ids=[synthetic_sid])
    p2=l.get_state(synthetic['outcome'].state_id)['payload']
    assert p2['profit'] is None
    assert p2['profit_verification']['evidence_status'] == 'SYNTHETIC_CONTAMINATION'


def test_arbitrary_source_record_cannot_forge_verified_profit(tmp_path: Path):
    l,r=setup(tmp_path); ops=OperationsService(l)
    rec=r.records['PUBLICATION_RECOMMENDATION'][0]
    auth=ops.record_human_authorization(rec,'test-human','AUTHORIZED')
    mon=r.records['MONETIZATION_CONFIGURATION'][0]
    deps=[auth.state_id, r.records['COMPLIANCE_ASSESSMENT'][0], r.records['ELIGIBILITY_ASSESSMENT'][0], r.records['CREATIVE_ARTIFACT'][0]]
    act=ops.activate_monetization(mon, dependency_state_ids=deps, provider_result_ref='fixture-activation')
    pub=ops.record_publication_execution(r.records['CREATIVE_ARTIFACT'][0],auth.state_id,channel='fixture',external_result_ref='fixture-post-forged',monetization_activation_state_id=act.state_id)
    fake=l.record_domain('SOURCE_RECORD','Source Adapter Authority',{'source_name':'weather','connector':'manual_api','external_id':'x','payload':{'fixture':False,'temperature':42}},natural_key='fake-economic-proof',record_state='OBSERVED')
    out=ops.record_economic_outcome(pub.state_id,performance={'views':1},revenue={'amount':100,'currency':'SAR'},costs=[{'amount':1,'currency':'SAR'}],attribution={'basis':'claim'},evidence_state_ids=[fake.state_id])
    payload=l.get_state(out['outcome'].state_id)['payload']
    assert payload['profit'] is None
    assert payload['profit_verification']['status'] == 'NOT_VERIFIED'
    assert 'INSUFFICIENT_UNTYPED_EVIDENCE' in payload['evaluation_blockers']


def test_economic_evidence_must_match_exact_publication_amount_and_currency(tmp_path: Path):
    l,r=setup(tmp_path); ops=OperationsService(l)
    rec=r.records['PUBLICATION_RECOMMENDATION'][0]
    auth=ops.record_human_authorization(rec,'test-human','AUTHORIZED')
    mon=r.records['MONETIZATION_CONFIGURATION'][0]
    deps=[auth.state_id, r.records['COMPLIANCE_ASSESSMENT'][0], r.records['ELIGIBILITY_ASSESSMENT'][0], r.records['CREATIVE_ARTIFACT'][0]]
    act=ops.activate_monetization(mon, dependency_state_ids=deps, provider_result_ref='fixture-activation')
    pub=ops.record_publication_execution(r.records['CREATIVE_ARTIFACT'][0],auth.state_id,channel='fixture',external_result_ref='fixture-post-mismatch',monetization_activation_state_id=act.state_id)
    bad_revenue=economic_evidence(l,pub.state_id,role='REVENUE',amount=999,currency='SAR',key='bad-revenue')
    good_cost=economic_evidence(l,pub.state_id,role='COST',amount=2,currency='SAR',key='good-cost')
    out=ops.record_economic_outcome(pub.state_id,performance={'views':1},revenue={'amount':5,'currency':'SAR'},costs=[{'amount':2,'currency':'SAR'}],attribution={'basis':'claim'},evidence_state_ids=[bad_revenue.state_id,good_cost.state_id])
    payload=l.get_state(out['outcome'].state_id)['payload']
    assert payload['profit'] is None
    assert 'REVENUE_EVIDENCE_MISMATCH' in payload['evaluation_blockers']


def test_nonmanual_source_without_governed_economic_binding_cannot_verify_profit(tmp_path: Path):
    l,r=setup(tmp_path); ops=OperationsService(l)
    rec=r.records['PUBLICATION_RECOMMENDATION'][0]
    auth=ops.record_human_authorization(rec,'test-human','AUTHORIZED')
    mon=r.records['MONETIZATION_CONFIGURATION'][0]
    deps=[auth.state_id, r.records['COMPLIANCE_ASSESSMENT'][0], r.records['ELIGIBILITY_ASSESSMENT'][0], r.records['CREATIVE_ARTIFACT'][0]]
    act=ops.activate_monetization(mon, dependency_state_ids=deps, provider_result_ref='fixture-activation')
    pub=ops.record_publication_execution(r.records['CREATIVE_ARTIFACT'][0],auth.state_id,channel='fixture',external_result_ref='fixture-post-unbound-source',monetization_activation_state_id=act.state_id)
    source=l.record_domain('SOURCE_RECORD','Source Adapter Authority',{'source_name':'looks-financial','connector':'bank_api','external_id':'x','payload':{'fixture':False}},natural_key='unbound-bank-source',record_state='OBSERVED')
    evidence=l.record_domain(
        'EVIDENCE','Evidence Authority',
        {'source_state_id':source.state_id,'publication_state_id':pub.state_id,'economic_role':'REVENUE','amount':5,'currency':'SAR','verification_status':'EXTERNAL_SOURCE_BOUND','fixture':False},
        natural_key='unbound-bank-evidence',record_state='VERIFIED',
        upstream_states=[(source.state_id,'ECONOMIC_EVIDENCE_SOURCE')],
    )
    out=ops.record_economic_outcome(pub.state_id,performance={'views':1},revenue={'amount':5,'currency':'SAR'},costs=[],attribution={'basis':'test'},evidence_state_ids=[evidence.state_id])
    payload=l.get_state(out['outcome'].state_id)['payload']
    assert payload['profit'] is None
    assert 'INSUFFICIENT_EVIDENCE_CONTRACT' in payload['evaluation_blockers']


def test_economic_binding_is_exact_to_connector_source_role_and_currency(tmp_path: Path):
    l,r=setup(tmp_path); ops=OperationsService(l)
    rec=r.records['PUBLICATION_RECOMMENDATION'][0]
    auth=ops.record_human_authorization(rec,'test-human','AUTHORIZED')
    mon=r.records['MONETIZATION_CONFIGURATION'][0]
    deps=[auth.state_id, r.records['COMPLIANCE_ASSESSMENT'][0], r.records['ELIGIBILITY_ASSESSMENT'][0], r.records['CREATIVE_ARTIFACT'][0]]
    act=ops.activate_monetization(mon, dependency_state_ids=deps, provider_result_ref='fixture-activation')
    pub=ops.record_publication_execution(r.records['CREATIVE_ARTIFACT'][0],auth.state_id,channel='fixture',external_result_ref='fixture-post-binding-scope',monetization_activation_state_id=act.state_id)
    binding=ops.bind_economic_evidence_source(connector='bank_api',source_name='acct-a',allowed_roles=['REVENUE'],allowed_currencies=['SAR'])
    source=l.record_domain('SOURCE_RECORD','Source Adapter Authority',{'source_name':'acct-b','connector':'bank_api','external_id':'x','payload':{'fixture':False}},natural_key='wrong-source-name',record_state='OBSERVED')
    evidence=l.record_domain(
        'EVIDENCE','Evidence Authority',
        {'source_state_id':source.state_id,'economic_source_binding_state_id':binding.state_id,'publication_state_id':pub.state_id,'economic_role':'REVENUE','amount':5,'currency':'SAR','verification_status':'EXTERNAL_SOURCE_BOUND','fixture':False},
        natural_key='wrong-source-name-evidence',record_state='VERIFIED',
        upstream_states=[(source.state_id,'ECONOMIC_EVIDENCE_SOURCE'),(binding.state_id,'ECONOMIC_EVIDENCE_SOURCE_AUTHORITY')],
    )
    out=ops.record_economic_outcome(pub.state_id,performance={'views':1},revenue={'amount':5,'currency':'SAR'},costs=[],attribution={'basis':'test'},evidence_state_ids=[evidence.state_id])
    payload=l.get_state(out['outcome'].state_id)['payload']
    assert payload['profit'] is None
    assert 'INSUFFICIENT_SOURCE_AUTHORITY' in payload['evaluation_blockers']


def test_stale_or_revoked_economic_source_binding_fails_closed(tmp_path: Path):
    l,r=setup(tmp_path); ops=OperationsService(l)
    rec=r.records['PUBLICATION_RECOMMENDATION'][0]
    auth=ops.record_human_authorization(rec,'test-human','AUTHORIZED')
    mon=r.records['MONETIZATION_CONFIGURATION'][0]
    deps=[auth.state_id, r.records['COMPLIANCE_ASSESSMENT'][0], r.records['ELIGIBILITY_ASSESSMENT'][0], r.records['CREATIVE_ARTIFACT'][0]]
    act=ops.activate_monetization(mon, dependency_state_ids=deps, provider_result_ref='fixture-activation')
    pub=ops.record_publication_execution(r.records['CREATIVE_ARTIFACT'][0],auth.state_id,channel='fixture',external_result_ref='fixture-post-stale-binding',monetization_activation_state_id=act.state_id)
    binding=ops.bind_economic_evidence_source(connector='bank_api',source_name='acct-a',allowed_roles=['REVENUE'],allowed_currencies=['SAR'])
    source=l.record_domain('SOURCE_RECORD','Source Adapter Authority',{'source_name':'acct-a','connector':'bank_api','external_id':'x','payload':{'fixture':False}},natural_key='stale-binding-source',record_state='OBSERVED')
    evidence=l.record_domain(
        'EVIDENCE','Evidence Authority',
        {'source_state_id':source.state_id,'economic_source_binding_state_id':binding.state_id,'publication_state_id':pub.state_id,'economic_role':'REVENUE','amount':5,'currency':'SAR','verification_status':'EXTERNAL_SOURCE_BOUND','fixture':False},
        natural_key='stale-binding-evidence',record_state='VERIFIED',
        upstream_states=[(source.state_id,'ECONOMIC_EVIDENCE_SOURCE'),(binding.state_id,'ECONOMIC_EVIDENCE_SOURCE_AUTHORITY')],
    )
    ops.bind_economic_evidence_source(connector='bank_api',source_name='acct-a',allowed_roles=['REVENUE'],allowed_currencies=['SAR'],status='REVOKED')
    out=ops.record_economic_outcome(pub.state_id,performance={'views':1},revenue={'amount':5,'currency':'SAR'},costs=[],attribution={'basis':'test'},evidence_state_ids=[evidence.state_id])
    payload=l.get_state(out['outcome'].state_id)['payload']
    assert payload['profit'] is None
    assert 'INSUFFICIENT_SOURCE_AUTHORITY' in payload['evaluation_blockers']


def test_manual_or_synthetic_connector_cannot_receive_economic_authority(tmp_path: Path):
    l,r=setup(tmp_path); ops=OperationsService(l)
    for connector in ('manual','manual_api','manual_json','synthetic'):
        with pytest.raises(LedgerError, match='cannot be granted economic evidence authority'):
            ops.bind_economic_evidence_source(connector=connector,source_name='x',allowed_roles=['REVENUE'],allowed_currencies=['SAR'])


def test_stale_or_nonverified_economic_evidence_cannot_verify_profit(tmp_path: Path):
    l,r=setup(tmp_path); ops=OperationsService(l)
    rec=r.records['PUBLICATION_RECOMMENDATION'][0]
    auth=ops.record_human_authorization(rec,'test-human','AUTHORIZED')
    mon=r.records['MONETIZATION_CONFIGURATION'][0]
    deps=[auth.state_id, r.records['COMPLIANCE_ASSESSMENT'][0], r.records['ELIGIBILITY_ASSESSMENT'][0], r.records['CREATIVE_ARTIFACT'][0]]
    act=ops.activate_monetization(mon, dependency_state_ids=deps, provider_result_ref='fixture-activation')
    pub=ops.record_publication_execution(r.records['CREATIVE_ARTIFACT'][0],auth.state_id,channel='fixture',external_result_ref='fixture-post-stale-evidence',monetization_activation_state_id=act.state_id)
    binding=ops.bind_economic_evidence_source(connector='bank_api',source_name='acct-a',allowed_roles=['REVENUE'],allowed_currencies=['SAR'])
    source=l.record_domain('SOURCE_RECORD','Source Adapter Authority',{'source_name':'acct-a','connector':'bank_api','external_id':'x','payload':{'fixture':False}},natural_key='stale-evidence-source',record_state='OBSERVED')
    evidence=l.record_domain(
        'EVIDENCE','Evidence Authority',
        {'source_state_id':source.state_id,'economic_source_binding_state_id':binding.state_id,'publication_state_id':pub.state_id,'economic_role':'REVENUE','amount':5,'currency':'SAR','verification_status':'EXTERNAL_SOURCE_BOUND','fixture':False},
        natural_key='stale-evidence',record_state='VERIFIED',
        upstream_states=[(source.state_id,'ECONOMIC_EVIDENCE_SOURCE'),(binding.state_id,'ECONOMIC_EVIDENCE_SOURCE_AUTHORITY')],
    )
    # Same evidence identity gets a later state; the old state must no longer authorize economics.
    l.record_domain(
        'EVIDENCE','Evidence Authority',
        {'source_state_id':source.state_id,'economic_source_binding_state_id':binding.state_id,'publication_state_id':pub.state_id,'economic_role':'REVENUE','amount':0,'currency':'SAR','verification_status':'RETRACTED','fixture':False},
        natural_key='stale-evidence',record_state='RETRACTED',
        upstream_states=[(source.state_id,'ECONOMIC_EVIDENCE_SOURCE'),(binding.state_id,'ECONOMIC_EVIDENCE_SOURCE_AUTHORITY')],
    )
    out=ops.record_economic_outcome(pub.state_id,performance={'views':1},revenue={'amount':5,'currency':'SAR'},costs=[],attribution={'basis':'test'},evidence_state_ids=[evidence.state_id])
    payload=l.get_state(out['outcome'].state_id)['payload']
    assert payload['profit'] is None
    assert 'INSUFFICIENT_STALE_EVIDENCE' in payload['evaluation_blockers']


def test_stale_source_record_cannot_support_current_economic_evidence(tmp_path: Path):
    l,r=setup(tmp_path); ops=OperationsService(l)
    rec=r.records['PUBLICATION_RECOMMENDATION'][0]
    auth=ops.record_human_authorization(rec,'test-human','AUTHORIZED')
    mon=r.records['MONETIZATION_CONFIGURATION'][0]
    deps=[auth.state_id, r.records['COMPLIANCE_ASSESSMENT'][0], r.records['ELIGIBILITY_ASSESSMENT'][0], r.records['CREATIVE_ARTIFACT'][0]]
    act=ops.activate_monetization(mon, dependency_state_ids=deps, provider_result_ref='fixture-activation')
    pub=ops.record_publication_execution(r.records['CREATIVE_ARTIFACT'][0],auth.state_id,channel='fixture',external_result_ref='fixture-post-stale-source',monetization_activation_state_id=act.state_id)
    binding=ops.bind_economic_evidence_source(connector='bank_api',source_name='acct-a',allowed_roles=['REVENUE'],allowed_currencies=['SAR'])
    source=l.record_domain('SOURCE_RECORD','Source Adapter Authority',{'source_name':'acct-a','connector':'bank_api','external_id':'txn-1','payload':{'fixture':False,'status':'settled'}},natural_key='correctable-source',record_state='OBSERVED')
    evidence=l.record_domain(
        'EVIDENCE','Evidence Authority',
        {'source_state_id':source.state_id,'economic_source_binding_state_id':binding.state_id,'publication_state_id':pub.state_id,'economic_role':'REVENUE','amount':5,'currency':'SAR','verification_status':'EXTERNAL_SOURCE_BOUND','fixture':False},
        natural_key='evidence-from-stale-source',record_state='VERIFIED',
        upstream_states=[(source.state_id,'ECONOMIC_EVIDENCE_SOURCE'),(binding.state_id,'ECONOMIC_EVIDENCE_SOURCE_AUTHORITY')],
    )
    l.record_domain('SOURCE_RECORD','Source Adapter Authority',{'source_name':'acct-a','connector':'bank_api','external_id':'txn-1','payload':{'fixture':False,'status':'reversed'}},natural_key='correctable-source',record_state='OBSERVED')
    out=ops.record_economic_outcome(pub.state_id,performance={'views':1},revenue={'amount':5,'currency':'SAR'},costs=[],attribution={'basis':'test'},evidence_state_ids=[evidence.state_id])
    payload=l.get_state(out['outcome'].state_id)['payload']
    assert payload['profit'] is None
    assert 'INSUFFICIENT_EVIDENCE_SOURCE' in payload['evaluation_blockers']

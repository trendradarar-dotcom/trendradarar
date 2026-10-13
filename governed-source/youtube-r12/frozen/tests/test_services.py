from pathlib import Path
import pytest
from tests._governance_template import isolated_governance_ledger

from trend_hunter.ledger import GovernanceLedger, LedgerError
from trend_hunter.story import StoryService
from trend_hunter.measurement import TrendMeasurementService
from trend_hunter.saturation import SaturationCharacterizationService
from trend_hunter.opportunity import OpportunityService
from trend_hunter.eligibility import EligibilityService
from trend_hunter.execution import ExecutionService
from trend_hunter.economics import EconomicExpectationService
from trend_hunter.prioritization import PrioritizationService
from trend_hunter.monetization import MonetizationService
from trend_hunter.creative import CreativeService, ManualCreativeProvider
from trend_hunter.compliance import ComplianceService
from trend_hunter.recommendation import PublicationRecommendationService


def base(tmp_path: Path):
    l=isolated_governance_ledger(tmp_path, 'services')
    src=l.record_domain('SOURCE_RECORD','Source Adapter Authority',{'payload':{'title':'Alpha','language':'en','region':'US','platform':'manual'}},natural_key='src1',record_state='OBSERVED')
    signal=l.record_domain('SIGNAL','Signal Authority',{'metrics':[{'metric':'count','value':10,'unit':'count'}]},natural_key='sig1',record_state='OBSERVED',upstream_states=[(src.state_id,'SIGNAL_FROM_SOURCE')])
    story=StoryService(l).bind_story('story1',[src.state_id],basis='test',human_reviewed=True)
    trend=TrendMeasurementService(l).measure(story.state_id,[signal.state_id],scope={'language':'en','region':'US','platform':'manual'},window={'from':'t1','to':'t2'})
    sat=SaturationCharacterizationService(l).content_supply_occupancy(trend.state_id,eligible_supply_value=2,baseline_value=10,baseline_contract={'id':'b1','selection_basis':'PRECOMMITTED_EXACT'},coverage='SUFFICIENT',uncertainty={})
    opp=OpportunityService(l).create_candidate('opp1',story_state_id=story.state_id,role_bound_scope={'language':'en','region':'US','platform':'manual'},thesis='test',factor_state_ids=[trend.state_id,sat.state_id],factor_assertions={'x':True})
    return l,opp


def test_execution_siblings_share_exact_config(tmp_path: Path):
    l,opp=base(tmp_path)
    elig=EligibilityService(l).assess(opp.state_id,target={'jurisdiction':'US'},political_risk_determination='NON_POLITICAL')
    ex=ExecutionService(l)
    cfg=ex.define_configuration(opp.state_id,elig.state_id,platform='manual',channel='c',content_form='text',production_route='manual',actionable_from=None,actionable_to=None,required_resources={},capital_assumption={'amount':0,'currency':'USD'},operational_mode='MANUAL')
    econ=EconomicExpectationService(l).estimate(cfg.state_id,mechanism='affiliate',horizon='7d',scenarios=[{'expected_revenue':{'amount':10,'currency':'USD'},'incremental_cost':{'amount':2,'currency':'USD'}}],coverage='SUFFICIENT',uncertainty={})
    feas=ex.assess_feasibility(cfg.state_id,constraints={},outcome='FEASIBLE',rationale={})
    p=PrioritizationService(l).decide(econ.state_id,feas.state_id,policy_key='p',policy_version=1,decision='SELECT',rationale={})
    assert l.get_state(p.state_id)['payload']['execution_configuration_state_id']==cfg.state_id


def test_creative_requires_eligible_and_compliance_no_laundering(tmp_path: Path):
    l,opp=base(tmp_path)
    bad=EligibilityService(l).assess(opp.state_id,target={'jurisdiction':'US'},political_risk_determination='POLITICAL_OPPOSITION')
    with pytest.raises(LedgerError):
        CreativeService(l).create(bad.state_id,None,target={'jurisdiction':'US'},brief={},provider=ManualCreativeProvider({'text':'x'}))


def test_full_prepublication_service_chain(tmp_path: Path):
    l,opp=base(tmp_path)
    elig=EligibilityService(l).assess(opp.state_id,target={'jurisdiction':'US'},political_risk_determination='NON_POLITICAL')
    ex=ExecutionService(l)
    cfg=ex.define_configuration(opp.state_id,elig.state_id,platform='manual',channel='c',content_form='text',production_route='manual',actionable_from=None,actionable_to=None,required_resources={},capital_assumption={'amount':0,'currency':'USD'},operational_mode='MANUAL')
    econ=EconomicExpectationService(l).estimate(cfg.state_id,mechanism='affiliate',horizon='7d',scenarios=[{'expected_revenue':{'amount':10,'currency':'USD'},'incremental_cost':{'amount':2,'currency':'USD'}}],coverage='SUFFICIENT',uncertainty={})
    feas=ex.assess_feasibility(cfg.state_id,constraints={},outcome='FEASIBLE',rationale={})
    pri=PrioritizationService(l).decide(econ.state_id,feas.state_id,policy_key='p',policy_version=1,decision='SELECT',rationale={})
    mon=MonetizationService(l).configure(pri.state_id,mechanism='affiliate',provider='x',account_ref='a',offer_or_product_ref='o',campaign_ref='c',tracked_destination='https://example.invalid',attribution={},payout_terms={'amount':1,'currency':'USD'},currency='USD')
    creative=CreativeService(l).create(elig.state_id,mon.state_id,target={'jurisdiction':'US'},brief={'goal':'test'},provider=ManualCreativeProvider({'text':'hello'}))
    comp=ComplianceService(l).assess(creative.state_id,elig.state_id,target={'jurisdiction':'US'},legal_findings=[],platform_findings=[],coverage_state='SUFFICIENT',gate_decision='PASS')
    rec=PublicationRecommendationService(l).recommend(creative.state_id,elig.state_id,comp.state_id)
    assert l.get_state(rec.state_id)['payload']['recommendation']=='RECOMMEND_PUBLISH'


def test_execution_configuration_requires_prior_eligible_state(tmp_path: Path):
    l,opp=base(tmp_path)
    bad=EligibilityService(l).assess(opp.state_id,target={'jurisdiction':'US'},political_risk_determination='STATE_SENSITIVE')
    ex=ExecutionService(l)
    with pytest.raises(LedgerError):
        ex.define_configuration(opp.state_id,bad.state_id,platform='manual',channel='c',content_form='text',production_route='manual',actionable_from=None,actionable_to=None,required_resources={},capital_assumption={'amount':0,'currency':'USD'},operational_mode='MANUAL')


def test_rsupply_rejects_hidden_competition_semantics_nested(tmp_path: Path):
    l,opp=base(tmp_path)
    # base() already proves a clean baseline works; now create a fresh trend from its upstream graph.
    from trend_hunter.db import connect
    with connect(l.db_path) as conn:
        trend=conn.execute("SELECT artifact_state_id FROM domain_record WHERE stage='TREND_MEASUREMENT' ORDER BY rowid DESC LIMIT 1").fetchone()['artifact_state_id']
    with pytest.raises(LedgerError):
        SaturationCharacterizationService(l).content_supply_occupancy(trend,eligible_supply_value=2,baseline_value=10,baseline_contract={'id':'bad','selection_basis':'PRECOMMITTED_EXACT','nested':{'competitive_arena':'x'}},coverage='SUFFICIENT',uncertainty={})

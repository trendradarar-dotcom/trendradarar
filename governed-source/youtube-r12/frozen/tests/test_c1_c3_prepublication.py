from pathlib import Path
import pytest

from tests._governance_template import isolated_governance_ledger
from trend_hunter.ledger import GovernanceLedger, LedgerError
from trend_hunter.story import StoryService
from trend_hunter.measurement import TrendMeasurementService
from trend_hunter.saturation import SaturationCharacterizationService
from trend_hunter.opportunity import OpportunityService
from trend_hunter.eligibility import EligibilityService
from trend_hunter.creative import CreativeService, ManualCreativeProvider
from trend_hunter.compliance import ComplianceService
from trend_hunter.recommendation import PublicationRecommendationService
from trend_hunter.operations import OperationsService
from trend_hunter.c1_policy import C1_MARKET_LANGUAGES, C1_UI_LANGUAGE


def make_chain(tmp_path: Path, *, natural: str = 'one', language: str = 'en', region: str = 'US'):
    ledger = isolated_governance_ledger(tmp_path, natural)
    target = {'language': language, 'region': region, 'platform': 'youtube'}
    src = ledger.record_domain(
        'SOURCE_RECORD', 'Source Adapter Authority',
        {'connector': 'google_trends_export', 'payload': {'title': f'Alpha-{natural}', 'language': language, 'region': region, 'fixture': False}},
        natural_key=f'src-{natural}', record_state='OBSERVED'
    )
    signal = ledger.record_domain(
        'SIGNAL', 'Signal Authority',
        {'metrics': [{'metric':'search_interest_lower_bound','value':10000,'unit':'count'}]},
        natural_key=f'sig-{natural}', record_state='OBSERVED', upstream_states=[(src.state_id,'SIGNAL_FROM_SOURCE')]
    )
    story = StoryService(ledger).bind_story(f'story-{natural}', [src.state_id], basis='c1-test', human_reviewed=True)
    trend = TrendMeasurementService(ledger).measure(story.state_id,[signal.state_id],scope=target,window={'from':'t1','to':'t2'})
    sat = SaturationCharacterizationService(ledger).content_supply_occupancy(
        trend.state_id, eligible_supply_value=2, baseline_value=10,
        baseline_contract={'id':f'b-{natural}','selection_basis':'PRECOMMITTED_EXACT'}, coverage='SUFFICIENT', uncertainty={}
    )
    opp = OpportunityService(ledger).create_candidate(
        f'opp-{natural}', story_state_id=story.state_id, role_bound_scope=target,
        thesis='c1-test', factor_state_ids=[trend.state_id,sat.state_id], factor_assertions={'live': True}
    )
    elig = EligibilityService(ledger).assess(opp.state_id,target=target,political_risk_determination='NON_POLITICAL')
    creative = CreativeService(ledger).create(
        elig.state_id, None, target=target, brief={'goal':'test','language':language},
        provider=ManualCreativeProvider({'text':f'content-{natural}','language':language})
    )
    return ledger, target, opp, elig, creative


def review_evidence(ledger: GovernanceLedger, creative_state_id: str, *, dimension: str, key: str):
    return ledger.record_domain(
        'EVIDENCE','Evidence Authority',
        {
            'creative_state_id': creative_state_id,
            'review_scope': dimension,
            'verification_status': 'HUMAN_REVIEWED',
            'finding_key': key,
            'fixture': False,
        },
        natural_key=f'c1-review-evidence:{dimension}:{creative_state_id}:{key}',
        subject_identity_id=ledger.subject_identity_for_state(creative_state_id),
        record_state='VERIFIED',
    )


def strict_pass_compliance(ledger, target, elig, creative):
    le = review_evidence(ledger,creative.state_id,dimension='legal',key='legal-screen')
    pe = review_evidence(ledger,creative.state_id,dimension='platform',key='youtube-policy-screen')
    return ComplianceService(ledger).assess(
        creative.state_id,elig.state_id,target=target,
        legal_findings=[{'finding':'legal-screen','status':'PASS','evidence_state_ids':[le.state_id]}],
        platform_findings=[{'finding':'youtube-policy-screen','status':'PASS','evidence_state_ids':[pe.state_id]}],
        coverage_state='SUFFICIENT',gate_decision='PASS',strict_c1=True,
    )


def test_c1_language_policy_is_global_while_ui_is_arabic():
    assert C1_UI_LANGUAGE == 'ar'
    assert C1_MARKET_LANGUAGES == {'ar','en','fr','fa','es'}


@pytest.mark.parametrize('language,region', [('ar','SA'),('en','US'),('fr','FR'),('fa','IR'),('es','ES')])
def test_c1_strict_compliance_accepts_each_governed_market_language(tmp_path: Path, language: str, region: str):
    l,target,opp,elig,creative=make_chain(tmp_path,natural=f'{language}-{region}',language=language,region=region)
    comp=strict_pass_compliance(l,target,elig,creative)
    assert l.get_state(comp.state_id)['payload']['gate_decision']=='PASS'
    assert l.get_state(comp.state_id)['payload']['c1_strict_review'] is True


def test_c1_strict_compliance_rejects_unapproved_market_language(tmp_path: Path):
    l,target,opp,elig,creative=make_chain(tmp_path,natural='de',language='de',region='DE')
    le=review_evidence(l,creative.state_id,dimension='legal',key='l')
    pe=review_evidence(l,creative.state_id,dimension='platform',key='p')
    with pytest.raises(LedgerError, match='ar/en/fr/fa/es'):
        ComplianceService(l).assess(
            creative.state_id,elig.state_id,target=target,
            legal_findings=[{'status':'PASS','evidence_state_ids':[le.state_id]}],
            platform_findings=[{'status':'PASS','evidence_state_ids':[pe.state_id]}],
            coverage_state='SUFFICIENT',gate_decision='PASS',strict_c1=True,
        )


def test_c1_generic_or_wrong_scope_evidence_cannot_be_laundered_into_compliance(tmp_path: Path):
    l,target,opp,elig,creative=make_chain(tmp_path,natural='evidence')
    generic=l.record_domain('EVIDENCE','Evidence Authority',{'fixture':False,'verification_status':'HUMAN_REVIEWED'},natural_key='generic',record_state='VERIFIED')
    proper=review_evidence(l,creative.state_id,dimension='platform',key='p')
    with pytest.raises(LedgerError, match='exact creative|wrong specialized'):
        ComplianceService(l).assess(
            creative.state_id,elig.state_id,target=target,
            legal_findings=[{'status':'PASS','evidence_state_ids':[generic.state_id]}],
            platform_findings=[{'status':'PASS','evidence_state_ids':[proper.state_id]}],
            coverage_state='SUFFICIENT',gate_decision='PASS',strict_c1=True,
        )


def test_c1_unresolved_or_not_applicable_finding_requires_reason(tmp_path: Path):
    l,target,opp,elig,creative=make_chain(tmp_path,natural='unresolved')
    with pytest.raises(LedgerError, match='requires an explicit reason'):
        ComplianceService(l).assess(
            creative.state_id,elig.state_id,target=target,
            legal_findings=[{'status':'UNRESOLVED'}],
            platform_findings=[{'status':'NOT_APPLICABLE','reason':'not a platform-specific claim'}],
            coverage_state='PARTIAL',gate_decision='HUMAN_REVIEW',strict_c1=True,
        )


def test_recommendation_rejects_cross_content_compliance_laundering(tmp_path: Path):
    l,target,opp,elig,creative1=make_chain(tmp_path,natural='cross')
    creative2=CreativeService(l).create(
        elig.state_id,None,target=target,brief={'goal':'other'},provider=ManualCreativeProvider({'text':'other','language':'en'})
    )
    comp1=strict_pass_compliance(l,target,elig,creative1)
    with pytest.raises(LedgerError, match='exact creative'):
        PublicationRecommendationService(l).recommend(creative2.state_id,elig.state_id,comp1.state_id)


def test_authorization_cannot_override_recommend_revise(tmp_path: Path):
    l,target,opp,elig,creative=make_chain(tmp_path,natural='revise')
    le=review_evidence(l,creative.state_id,dimension='legal',key='l')
    pe=review_evidence(l,creative.state_id,dimension='platform',key='p')
    comp=ComplianceService(l).assess(
        creative.state_id,elig.state_id,target=target,
        legal_findings=[{'status':'PASS','evidence_state_ids':[le.state_id]}],
        platform_findings=[{'status':'WARNING','evidence_state_ids':[pe.state_id]}],
        coverage_state='SUFFICIENT',gate_decision='WARNING',strict_c1=True,
    )
    rec=PublicationRecommendationService(l).recommend(creative.state_id,elig.state_id,comp.state_id)
    assert l.get_state(rec.state_id)['payload']['recommendation']=='RECOMMEND_REVISE'
    with pytest.raises(LedgerError, match='RECOMMEND_PUBLISH'):
        OperationsService(l).record_human_authorization(rec.state_id,'human','AUTHORIZED')


def test_publication_rechecks_stale_compliance_after_human_authorization(tmp_path: Path):
    l,target,opp,elig,creative=make_chain(tmp_path,natural='stale')
    comp1=strict_pass_compliance(l,target,elig,creative)
    rec=PublicationRecommendationService(l).recommend(creative.state_id,elig.state_id,comp1.state_id)
    auth=OperationsService(l).record_human_authorization(rec.state_id,'human','AUTHORIZED')
    # Same compliance natural key -> new version, making the authorized review chain stale.
    le=review_evidence(l,creative.state_id,dimension='legal',key='l2')
    pe=review_evidence(l,creative.state_id,dimension='platform',key='p2')
    ComplianceService(l).assess(
        creative.state_id,elig.state_id,target=target,
        legal_findings=[{'status':'PASS','evidence_state_ids':[le.state_id]}],
        platform_findings=[{'status':'WARNING','evidence_state_ids':[pe.state_id]}],
        coverage_state='SUFFICIENT',gate_decision='WARNING',strict_c1=True,
    )
    with pytest.raises(LedgerError, match='stale/superseded'):
        OperationsService(l).record_publication_execution(
            creative.state_id,auth.state_id,channel='fixture',external_result_ref='should-not-publish'
        )


def test_authenticated_authorizer_string_must_match_governed_subject(tmp_path: Path):
    from trend_hunter.operational import OperationalBindingService
    l,target,opp,elig,creative=make_chain(tmp_path,natural='actor')
    comp=strict_pass_compliance(l,target,elig,creative)
    rec=PublicationRecommendationService(l).recommend(creative.state_id,elig.state_id,comp.state_id)
    binding=OperationalBindingService(l).register_operator('alice',roles=['publisher_authorizer'],scopes=['publication:authorize'])
    ctx={
        'authenticated':True,'subject':'alice','governed_operator_binding_state_id':binding.state_id,
        'authorized_role':'publisher_authorizer','authorized_scope':'publication:authorize','issued_at':9999999999,
    }
    with pytest.raises(LedgerError, match='must match the authenticated governed subject'):
        OperationsService(l).record_human_authorization(rec.state_id,'bob','AUTHORIZED',auth_context=ctx)


def test_c1_not_applicable_cannot_be_used_as_evidence_free_bypass(tmp_path: Path):
    l,target,opp,elig,creative=make_chain(tmp_path,natural='na-bypass')
    proper=review_evidence(l,creative.state_id,dimension='platform',key='p')
    with pytest.raises(LedgerError, match='requires typed non-synthetic evidence'):
        ComplianceService(l).assess(
            creative.state_id,elig.state_id,target=target,
            legal_findings=[{'status':'NOT_APPLICABLE','reason':'claimed not applicable'}],
            platform_findings=[{'status':'PASS','evidence_state_ids':[proper.state_id]}],
            coverage_state='SUFFICIENT',gate_decision='PASS',strict_c1=True,
        )

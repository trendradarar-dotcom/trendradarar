from pathlib import Path

from trend_hunter.bootstrap import bootstrap_governance
from trend_hunter.db import init_db
from trend_hunter.language_board import LanguageBoardPresentationAdapter, LanguageBoardService
from trend_hunter.ledger import GovernanceLedger


def _ledger(tmp_path: Path):
    db=tmp_path/'board.db'; init_db(str(db)); l=GovernanceLedger(str(db)); bootstrap_governance(l); return l


def _opp(l, key, lang, region, fixture=False):
    subject=l.get_or_create_identity('OPPORTUNITY',key)
    return l.record_domain(
        'OPPORTUNITY','Opportunity Authority',{
            'candidate_key':key,
            'role_bound_scope':{'language':lang,'region':region},
            'thesis':f'thesis-{key}',
            'factor_assertions':{'observed_title':f'title-{key}'},
            'fixture':fixture,
        },natural_key=f'candidate:{key}',subject_identity_id=subject,
        scope={'language':lang,'region':region},record_state='CANDIDATE')


def test_language_board_excludes_other_languages_and_fixtures(tmp_path):
    l=_ledger(tmp_path)
    ar1=_opp(l,'ar-sa-1','ar','SA')
    _opp(l,'ar-eg-1','ar','EG')
    _opp(l,'fr-fr-1','fr','FR')
    _opp(l,'ar-fixture','ar','SA',fixture=True)
    board=LanguageBoardService(l).build('ar')
    ids={x['opportunity_state_id'] for x in board.global_top_6}
    assert ar1.state_id in ids
    assert all(x['language_code']=='ar' for x in board.global_top_6)
    assert sum(x['governed_opportunity_count'] for x in board.priority_markets)==2
    assert len(board.global_top_6)<=6
    assert board.evidence_contract['universal_score'] is None


def test_presentation_adapter_never_becomes_truth_source(tmp_path):
    l=_ledger(tmp_path); _opp(l,'ar-sa-1','ar','SA')
    board=LanguageBoardService(l).build('ar')
    view=LanguageBoardPresentationAdapter.adapt(board,'youtube_wide')
    assert view['presentation_is_not_source_of_truth'] is True
    assert view['language_code']=='ar'

from pathlib import Path
import os
import urllib.parse

import pytest

from tests._governance_template import isolated_governance_ledger
from trend_hunter.ledger import GovernanceLedger, LedgerError
from trend_hunter.story import StoryService
from trend_hunter.measurement import TrendMeasurementService
from trend_hunter.saturation import SaturationCharacterizationService
from trend_hunter.opportunity import OpportunityService
from trend_hunter.eligibility import EligibilityService
from trend_hunter.execution import ExecutionService
from trend_hunter.creative import CreativeService, ManualCreativeProvider
from trend_hunter.compliance import ComplianceService
from trend_hunter.recommendation import PublicationRecommendationService
from trend_hunter.operations import OperationsService
from trend_hunter.operational import OperationalBindingService
from trend_hunter.c1_youtube import (
    YouTubeOAuthService, YouTubePublicationService, InMemoryRefreshTokenStore,
    WindowsDPAPIRefreshTokenStore, NoProxyHTTPTransport, OAuthTokenBundle,
    YOUTUBE_UPLOAD_SCOPE,
)


class FakeTransport:
    def __init__(self):
        self.token_response = {
            'access_token':'ACCESS','refresh_token':'REFRESH','token_type':'Bearer','expires_in':3600,
            'scope':YOUTUBE_UPLOAD_SCOPE,
        }
        self.channel_ids=['UC_EXPECTED']
        self.location='https://www.googleapis.com/upload/youtube/v3/videos?upload_id=abc'
        self.upload_response={'id':'vid-1','status':{'privacyStatus':'private'},'snippet':{'channelId':'UC_EXPECTED'}}
        self.calls=[]
    def post_form(self,url,values): self.calls.append(('post_form',url,dict(values))); return dict(self.token_response)
    def get_json(self,url,*,access_token): self.calls.append(('get_json',url,access_token)); return {'items':[{'id':x} for x in self.channel_ids]}
    def post_json_headers(self,url,payload,*,headers): self.calls.append(('post_json',url,payload,dict(headers))); return {'Location':self.location}, None
    def put_bytes(self,url,data,*,headers): self.calls.append(('put_bytes',url,len(data),dict(headers))); return dict(self.upload_response)
    def put_file_resumable(self,url,file_path,*,access_token,content_type,total_size,chunk_size=8*1024*1024):
        self.calls.append(('put_file',url,str(file_path),total_size,content_type,chunk_size)); return dict(self.upload_response)


def make_chain(tmp_path: Path, natural='one'):
    l = isolated_governance_ledger(tmp_path, natural)
    target={'language':'en','region':'US','platform':'youtube'}
    src=l.record_domain('SOURCE_RECORD','Source Adapter Authority',{'connector':'google_trends_export','payload':{'title':'Alpha','fixture':False}},natural_key=f'src-{natural}',record_state='OBSERVED')
    sig=l.record_domain('SIGNAL','Signal Authority',{'metrics':[{'metric':'search_interest_lower_bound','value':10000,'unit':'count'}]},natural_key=f'sig-{natural}',record_state='OBSERVED',upstream_states=[(src.state_id,'SIGNAL_FROM_SOURCE')])
    story=StoryService(l).bind_story(f'story-{natural}',[src.state_id],basis='c1-c4-test',human_reviewed=True)
    trend=TrendMeasurementService(l).measure(story.state_id,[sig.state_id],scope=target,window={'from':'t1','to':'t2'})
    sat=SaturationCharacterizationService(l).content_supply_occupancy(trend.state_id,eligible_supply_value=2,baseline_value=10,baseline_contract={'id':f'b-{natural}','selection_basis':'PRECOMMITTED_EXACT'},coverage='SUFFICIENT',uncertainty={})
    opp=OpportunityService(l).create_candidate(f'opp-{natural}',story_state_id=story.state_id,role_bound_scope=target,thesis='c4',factor_state_ids=[trend.state_id,sat.state_id],factor_assertions={'live':True})
    elig=EligibilityService(l).assess(opp.state_id,target=target,political_risk_determination='NON_POLITICAL')
    bindings=OperationalBindingService(l)
    acc=bindings.bind_external_account('youtube','acct-1',account_kind='CHANNEL_OWNER')
    chan=bindings.bind_channel(acc.state_id,'youtube','UC_EXPECTED',language='en',region='US')
    cfg=ExecutionService(l).define_configuration(opp.state_id,elig.state_id,platform='youtube',channel='UC_EXPECTED',content_form='video',production_route='manual-render',actionable_from=None,actionable_to=None,required_resources={},capital_assumption={},operational_mode='LOOPBACK_ONLY',live_channel_binding_state_id=chan.state_id,require_live_channel_binding=True)
    creative=CreativeService(l).create(elig.state_id,None,target=target,brief={'goal':'test'},provider=ManualCreativeProvider({'text':'hello','language':'en'}))
    def evidence(dim,key):
        return l.record_domain('EVIDENCE','Evidence Authority',{'creative_state_id':creative.state_id,'review_scope':dim,'verification_status':'HUMAN_REVIEWED','finding_key':key,'fixture':False},natural_key=f'ev-{natural}-{dim}',subject_identity_id=l.subject_identity_for_state(creative.state_id),record_state='VERIFIED')
    le,pe=evidence('legal','l'),evidence('platform','p')
    comp=ComplianceService(l).assess(creative.state_id,elig.state_id,target=target,legal_findings=[{'status':'PASS','evidence_state_ids':[le.state_id]}],platform_findings=[{'status':'PASS','evidence_state_ids':[pe.state_id]}],coverage_state='SUFFICIENT',gate_decision='PASS',strict_c1=True)
    rec=PublicationRecommendationService(l).recommend(creative.state_id,elig.state_id,comp.state_id)
    return l,opp,elig,chan,cfg,creative,rec


def make_media(tmp_path: Path, name='clip.mp4', content=b'video-bytes'):
    p=tmp_path/name; p.write_bytes(content); return p


def authorize_with_media(l,chan,cfg,creative,rec,media_desc):
    return OperationsService(l).record_human_authorization(
        rec.state_id,'human','AUTHORIZED',execution_configuration_state_id=cfg.state_id,
        channel_binding_state_id=chan.state_id,media_descriptor_state_id=media_desc.state_id,
        require_exact_channel=True,require_exact_media=True,
    )


TEST_STATE='S'*32
ALT_STATE='W'*32


def verified_grant(l,chan,transport):
    oauth=YouTubeOAuthService(l,transport=transport)
    req=oauth.prepare_authorization_request('client-1','http://127.0.0.1:8765/callback',state=TEST_STATE,code_verifier='A'*64)
    att=oauth.record_authorization_attempt(chan.state_id,req,client_id='client-1')
    tok=oauth.exchange_code(att.state_id,returned_state=TEST_STATE,code='code',code_verifier='A'*64,client_id='client-1')
    store=InMemoryRefreshTokenStore(); grant=oauth.commit_verified_grant(att.state_id,tok,channel_binding_state_id=chan.state_id,refresh_store=store,allow_ephemeral_secret_store=True)
    return oauth,grant,store,tok




def ready_publication(l,chan,cfg,creative,rec,media,transport,*,title='Title',description=''):
    pub=YouTubePublicationService(l,transport=transport)
    desc=pub.create_media_descriptor(creative.state_id,media,title=title,description=description)
    auth=authorize_with_media(l,chan,cfg,creative,rec,desc)
    oauth,grant,store,tok=verified_grant(l,chan,transport)
    attempt=pub.prepare_publication_attempt(
        operations=OperationsService(l),creative_state_id=creative.state_id,authorization_state_id=auth.state_id,
        oauth_grant_state_id=grant.state_id,oauth_token=tok,media_path=media,
    )
    return pub,desc,auth,oauth,grant,store,tok,attempt

def test_oauth_request_is_pkce_loopback_offline_and_minimal_scope():
    req=YouTubeOAuthService.prepare_authorization_request('client','http://127.0.0.1:43210/callback',state='S'*32,code_verifier='A'*64)
    q=urllib.parse.parse_qs(urllib.parse.urlparse(req.authorization_url).query)
    assert q['code_challenge_method']==['S256']
    assert q['access_type']==['offline'] and q['prompt']==['consent']
    assert q['scope']==[YOUTUBE_UPLOAD_SCOPE]
    assert req.code_verifier not in req.authorization_url


def test_oauth_rejects_non_loopback_or_secret_bearing_redirect():
    for uri in ['https://example.com/cb','http://localhost:8080/cb','http://user:pw@127.0.0.1:8080/cb']:
        with pytest.raises(LedgerError,match='loopback'):
            YouTubeOAuthService.prepare_authorization_request('client',uri,code_verifier='A'*64)


def test_oauth_attempt_persists_hashes_not_state_or_verifier(tmp_path: Path):
    l,opp,elig,chan,cfg,creative,rec=make_chain(tmp_path,'attempt')
    oauth=YouTubeOAuthService(l,transport=FakeTransport())
    req=oauth.prepare_authorization_request('client-1','http://127.0.0.1:8765/cb',state=TEST_STATE,code_verifier='A'*64)
    att=oauth.record_authorization_attempt(chan.state_id,req,client_id='client-1')
    payload=l.get_state(att.state_id)['payload']
    text=str(payload)
    assert TEST_STATE not in text and 'A'*64 not in text
    assert payload['plaintext_state_persisted'] is False and payload['plaintext_code_verifier_persisted'] is False


def test_exchange_rejects_state_pkce_and_client_mismatch(tmp_path: Path):
    l,opp,elig,chan,cfg,creative,rec=make_chain(tmp_path,'mismatch')
    oauth=YouTubeOAuthService(l,transport=FakeTransport())
    req=oauth.prepare_authorization_request('client-1','http://127.0.0.1:8765/cb',state=TEST_STATE,code_verifier='A'*64)
    att=oauth.record_authorization_attempt(chan.state_id,req,client_id='client-1')
    with pytest.raises(LedgerError,match='state mismatch'): oauth.exchange_code(att.state_id,returned_state=ALT_STATE,code='c',code_verifier='A'*64,client_id='client-1')
    with pytest.raises(LedgerError,match='PKCE'): oauth.exchange_code(att.state_id,returned_state=TEST_STATE,code='c',code_verifier='B'*64,client_id='client-1')
    with pytest.raises(LedgerError,match='client_id'): oauth.exchange_code(att.state_id,returned_state=TEST_STATE,code='c',code_verifier='A'*64,client_id='client-2')


def test_exchange_requires_refresh_token_and_exact_upload_scope(tmp_path: Path):
    l,opp,elig,chan,cfg,creative,rec=make_chain(tmp_path,'token')
    tr=FakeTransport(); oauth=YouTubeOAuthService(l,transport=tr)
    req=oauth.prepare_authorization_request('client-1','http://127.0.0.1:8765/cb',state=TEST_STATE,code_verifier='A'*64)
    att=oauth.record_authorization_attempt(chan.state_id,req,client_id='client-1')
    tr.token_response.pop('refresh_token')
    with pytest.raises(LedgerError,match='refresh token'): oauth.exchange_code(att.state_id,returned_state=TEST_STATE,code='c',code_verifier='A'*64,client_id='client-1')
    tr.token_response['refresh_token']='R'; tr.token_response['scope']='https://www.googleapis.com/auth/youtube.readonly'
    with pytest.raises(LedgerError,match='youtube.upload'): oauth.exchange_code(att.state_id,returned_state=TEST_STATE,code='c',code_verifier='A'*64,client_id='client-1')


def test_exact_channel_verification_rejects_wrong_or_ambiguous_identity(tmp_path: Path):
    l,opp,elig,chan,cfg,creative,rec=make_chain(tmp_path,'channel')
    tr=FakeTransport(); oauth=YouTubeOAuthService(l,transport=tr)
    tr.channel_ids=['UC_OTHER']
    with pytest.raises(LedgerError,match='unambiguously'): oauth.verify_exact_channel('A',chan.state_id)
    tr.channel_ids=['UC_EXPECTED','UC_OTHER']
    with pytest.raises(LedgerError,match='unambiguously'): oauth.verify_exact_channel('A',chan.state_id)
    tr.channel_ids=['UC_EXPECTED']; assert oauth.verify_exact_channel('A',chan.state_id)['verified'] is True


def test_verified_grant_persists_only_secret_reference(tmp_path: Path):
    l,opp,elig,chan,cfg,creative,rec=make_chain(tmp_path,'grant')
    tr=FakeTransport(); oauth,grant,store,tok=verified_grant(l,chan,tr)
    payload=l.get_state(grant.state_id)['payload']; text=str(payload)
    assert 'REFRESH' not in text and 'ACCESS' not in text
    assert payload['refresh_token_plaintext_persisted'] is False and payload['access_token_persisted'] is False
    assert store.get(payload['refresh_token_secret_ref'])=='REFRESH'


def test_refresh_reverifies_exact_channel_and_scope(tmp_path: Path):
    l,opp,elig,chan,cfg,creative,rec=make_chain(tmp_path,'refresh')
    tr=FakeTransport(); oauth,grant,store,tok=verified_grant(l,chan,tr)
    tr.token_response={'access_token':'NEW','token_type':'Bearer','expires_in':3600,'scope':YOUTUBE_UPLOAD_SCOPE}
    refreshed=oauth.refresh_access_token(grant.state_id,client_id='client-1',client_secret=None,refresh_store=store)
    assert refreshed.access_token=='NEW'
    tr.channel_ids=['UC_OTHER']
    with pytest.raises(LedgerError,match='unambiguously'): oauth.refresh_access_token(grant.state_id,client_id='client-1',client_secret=None,refresh_store=store)


def test_media_descriptor_binds_exact_bytes_and_does_not_persist_path(tmp_path: Path):
    l,opp,elig,chan,cfg,creative,rec=make_chain(tmp_path,'media')
    media=make_media(tmp_path)
    svc=YouTubePublicationService(l,transport=FakeTransport()); desc=svc.create_media_descriptor(creative.state_id,media,title='Title')
    payload=l.get_state(desc.state_id)['payload']
    assert str(media.resolve()) not in str(payload) and payload['local_path_persisted'] is False
    svc.assert_media_matches(desc.state_id,media,creative_state_id=creative.state_id)
    media.write_bytes(b'changed')
    with pytest.raises(LedgerError,match='changed'): svc.assert_media_matches(desc.state_id,media,creative_state_id=creative.state_id)


def test_human_authorization_requires_exact_media_when_c1_flag_enabled(tmp_path: Path):
    l,opp,elig,chan,cfg,creative,rec=make_chain(tmp_path,'authmedia')
    with pytest.raises(LedgerError,match='media descriptor'):
        OperationsService(l).record_human_authorization(rec.state_id,'human','AUTHORIZED',execution_configuration_state_id=cfg.state_id,channel_binding_state_id=chan.state_id,require_exact_channel=True,require_exact_media=True)


def test_human_authorization_rejects_media_from_other_creative(tmp_path: Path):
    l,opp,elig,chan,cfg,creative,rec=make_chain(tmp_path,'crossmedia')
    other=CreativeService(l).create(elig.state_id,None,target={'language':'en','region':'US','platform':'youtube'},brief={'goal':'other'},provider=ManualCreativeProvider({'text':'other'}))
    media=make_media(tmp_path); desc=YouTubePublicationService(l,transport=FakeTransport()).create_media_descriptor(other.state_id,media,title='Other')
    with pytest.raises(LedgerError,match='exact creative'):
        authorize_with_media(l,chan,cfg,creative,rec,desc)


def test_later_human_rejection_supersedes_prior_authorization(tmp_path: Path):
    l,opp,elig,chan,cfg,creative,rec=make_chain(tmp_path,'rejection')
    media=make_media(tmp_path); desc=YouTubePublicationService(l,transport=FakeTransport()).create_media_descriptor(creative.state_id,media,title='Title')
    auth=authorize_with_media(l,chan,cfg,creative,rec,desc)
    OperationsService(l).record_human_authorization(rec.state_id,'human','REJECTED',execution_configuration_state_id=cfg.state_id,channel_binding_state_id=chan.state_id,media_descriptor_state_id=desc.state_id,require_exact_channel=True,require_exact_media=True)
    with pytest.raises(LedgerError,match='stale/superseded'):
        OperationsService(l).record_publication_execution(creative.state_id,auth.state_id,channel_binding_state_id=chan.state_id,external_result_ref='youtube:x',require_bound_channel=True)


def test_upload_rejects_malicious_resumable_location_before_bytes_sent(tmp_path: Path):
    l,opp,elig,chan,cfg,creative,rec=make_chain(tmp_path,'evil')
    media=make_media(tmp_path); tr=FakeTransport()
    pub,desc,auth,oauth,grant,store,tok,attempt=ready_publication(l,chan,cfg,creative,rec,media,tr)
    tr.location='https://evil.example/upload'; tr.calls.clear()
    with pytest.raises(LedgerError,match='allowlist'):
        pub.upload_private(publication_attempt_state_id=attempt.state_id,oauth_token=tok,media_path=media)
    assert not any(c[0] in {'put_file','put_bytes'} for c in tr.calls)

def test_upload_requires_private_and_exact_response_channel(tmp_path: Path):
    l,opp,elig,chan,cfg,creative,rec=make_chain(tmp_path,'privacy')
    media=make_media(tmp_path); tr=FakeTransport()
    pub,desc,auth,oauth,grant,store,tok,attempt=ready_publication(l,chan,cfg,creative,rec,media,tr)
    tr.upload_response['status']['privacyStatus']='public'; tr.calls.clear()
    with pytest.raises(LedgerError,match='EMERGENCY_HUMAN_ACTION_REQUIRED'):
        pub.upload_private(publication_attempt_state_id=attempt.state_id,oauth_token=tok,media_path=media)
    # R1.1: one human authorization is strictly one-use. The second adverse
    # response needs a DISTINCT fresh human authorization, not a replay.
    tr.upload_response['status']['privacyStatus']='private'; tr.upload_response['snippet']['channelId']='UC_OTHER'
    auth2=authorize_with_media(l,chan,cfg,creative,rec,desc)
    attempt2=pub.prepare_publication_attempt(operations=OperationsService(l),creative_state_id=creative.state_id,authorization_state_id=auth2.state_id,oauth_grant_state_id=grant.state_id,oauth_token=tok,media_path=media)
    with pytest.raises(LedgerError,match='EMERGENCY_HUMAN_ACTION_REQUIRED'):
        pub.upload_private(publication_attempt_state_id=attempt2.state_id,oauth_token=tok,media_path=media)

def test_authorized_private_upload_records_provider_proof_and_execution(tmp_path: Path):
    l,opp,elig,chan,cfg,creative,rec=make_chain(tmp_path,'execute')
    tr=FakeTransport(); media=make_media(tmp_path); pub=YouTubePublicationService(l,transport=tr)
    desc=pub.create_media_descriptor(creative.state_id,media,title='Title'); auth=authorize_with_media(l,chan,cfg,creative,rec,desc)
    oauth,grant,store,tok=verified_grant(l,chan,tr)
    result=pub.execute_authorized_private_upload(operations=OperationsService(l),creative_state_id=creative.state_id,authorization_state_id=auth.state_id,oauth_grant_state_id=grant.state_id,oauth_token=tok,media_path=media)
    proof=l.get_state(result['proof'].state_id); execution=l.get_state(result['execution'].state_id)
    assert proof['payload']['privacy_status']=='private' and proof['payload']['media_sha256']==l.get_state(desc.state_id)['payload']['sha256']
    assert execution['payload']['external_result_ref']=='youtube:vid-1'


def test_authorized_upload_rejects_media_changed_after_human_approval(tmp_path: Path):
    l,opp,elig,chan,cfg,creative,rec=make_chain(tmp_path,'changed-after-auth')
    tr=FakeTransport(); media=make_media(tmp_path); pub=YouTubePublicationService(l,transport=tr)
    desc=pub.create_media_descriptor(creative.state_id,media,title='Title'); auth=authorize_with_media(l,chan,cfg,creative,rec,desc); oauth,grant,store,tok=verified_grant(l,chan,tr)
    media.write_bytes(b'changed after approval')
    with pytest.raises(LedgerError,match='changed'):
        pub.execute_authorized_private_upload(operations=OperationsService(l),creative_state_id=creative.state_id,authorization_state_id=auth.state_id,oauth_grant_state_id=grant.state_id,oauth_token=tok,media_path=media)
    assert not any(c[0] in {'put_file','put_bytes'} for c in tr.calls)


def test_stale_channel_binding_invalidates_oauth_grant(tmp_path: Path):
    l,opp,elig,chan,cfg,creative,rec=make_chain(tmp_path,'stale-channel')
    tr=FakeTransport(); oauth,grant,store,tok=verified_grant(l,chan,tr)
    # Same natural channel key creates a newer binding version.
    account_state=l.get_state(chan.state_id)['payload']['account_binding_state_id']
    OperationalBindingService(l).bind_channel(account_state,'youtube','UC_EXPECTED',language='en',region='US')
    with pytest.raises(LedgerError,match='stale/superseded'):
        oauth.refresh_access_token(grant.state_id,client_id='client-1',client_secret=None,refresh_store=store)


def test_transport_disables_environment_proxy_inheritance():
    t=NoProxyHTTPTransport()
    proxy_handlers=[h for h in t._opener.handlers if isinstance(h, __import__('urllib.request').request.ProxyHandler)]
    assert proxy_handlers==[]  # ProxyHandler({}) suppresses urllib's environment-derived proxy handler.


def test_windows_dpapi_store_fails_closed_off_windows():
    if os.name!='nt':
        with pytest.raises(LedgerError,match='only available on Windows'): WindowsDPAPIRefreshTokenStore()


def test_oauth_rejects_short_low_assurance_state_and_loopback_query_fragment():
    with pytest.raises(LedgerError, match='OAuth state'):
        YouTubeOAuthService.prepare_authorization_request('client','http://127.0.0.1:8765/cb',state='short',code_verifier='A'*64)
    for uri in ['http://127.0.0.1:8765/cb?next=x','http://127.0.0.1:8765/cb#frag']:
        with pytest.raises(LedgerError, match='loopback'):
            YouTubeOAuthService.prepare_authorization_request('client',uri,state=TEST_STATE,code_verifier='A'*64)


def test_oauth_attempt_expires_and_successful_exchange_is_one_time(tmp_path: Path):
    from datetime import datetime, timezone
    l,opp,elig,chan,cfg,creative,rec=make_chain(tmp_path,'attempt-ttl')
    tr=FakeTransport(); oauth=YouTubeOAuthService(l,transport=tr)
    req=oauth.prepare_authorization_request('client-1','http://127.0.0.1:8765/cb',state=TEST_STATE,code_verifier='A'*64)
    att=oauth.record_authorization_attempt(chan.state_id,req,client_id='client-1')
    st=l.get_state(att.state_id)
    expired_payload=dict(st['payload']); expired_payload['expires_at']='2000-01-01T00:00:00+00:00'
    expired=l.record_domain(
        'YOUTUBE_OAUTH_AUTHORIZATION_ATTEMPT','C1 YouTube OAuth Authority',expired_payload,
        natural_key=st['natural_key'],subject_identity_id=l.subject_identity_for_state(chan.state_id),record_state='AWAITING_CALLBACK',
        upstream_states=[(chan.state_id,'OAUTH_EXACT_CHANNEL_BINDING')],
    )
    with pytest.raises(LedgerError,match='expired'):
        oauth.exchange_code(expired.state_id,returned_state=TEST_STATE,code='c',code_verifier='A'*64,client_id='client-1')

    # Start a new current attempt and prove successful exchange consumes it inside governance.
    req2=oauth.prepare_authorization_request('client-1','http://127.0.0.1:8766/cb',state=ALT_STATE,code_verifier='B'*64)
    att2=oauth.record_authorization_attempt(chan.state_id,req2,client_id='client-1')
    tok=oauth.exchange_code(att2.state_id,returned_state=ALT_STATE,code='c2',code_verifier='B'*64,client_id='client-1')
    assert tok.token_receipt_state_id
    latest=l.get_state(att2.state_id)
    # The original state is immutable; a newer version of the same attempt identity records CONSUMED.
    from trend_hunter.db import connect
    with connect(l.db_path) as conn:
        row=conn.execute('SELECT id FROM artifact_state WHERE identity_id=? ORDER BY version DESC LIMIT 1',(latest['identity_id'],)).fetchone()
    assert l.get_state(row['id'])['payload']['status']=='CONSUMED'
    calls_before=len([c for c in tr.calls if c[0]=='post_form'])
    with pytest.raises(LedgerError,match='stale/superseded'):
        oauth.exchange_code(att2.state_id,returned_state=ALT_STATE,code='again',code_verifier='B'*64,client_id='client-1')
    assert len([c for c in tr.calls if c[0]=='post_form'])==calls_before


def test_forged_token_bundle_cannot_launder_exchange_receipt(tmp_path: Path):
    l,opp,elig,chan,cfg,creative,rec=make_chain(tmp_path,'forged-token')
    tr=FakeTransport(); oauth=YouTubeOAuthService(l,transport=tr)
    req=oauth.prepare_authorization_request('client-1','http://127.0.0.1:8765/cb',state=TEST_STATE,code_verifier='A'*64)
    att=oauth.record_authorization_attempt(chan.state_id,req,client_id='client-1')
    tok=oauth.exchange_code(att.state_id,returned_state=TEST_STATE,code='c',code_verifier='A'*64,client_id='client-1')
    forged=OAuthTokenBundle('FORGED_ACCESS',tok.refresh_token,tok.token_type,tok.expires_in,tok.scopes,tok.token_receipt_state_id)
    with pytest.raises(LedgerError,match='access token'):
        oauth.commit_verified_grant(att.state_id,forged,channel_binding_state_id=chan.state_id,refresh_store=InMemoryRefreshTokenStore(),allow_ephemeral_secret_store=True)


def test_ephemeral_refresh_store_is_rejected_by_default(tmp_path: Path):
    l,opp,elig,chan,cfg,creative,rec=make_chain(tmp_path,'ephemeral-store')
    tr=FakeTransport(); oauth=YouTubeOAuthService(l,transport=tr)
    req=oauth.prepare_authorization_request('client-1','http://127.0.0.1:8765/cb',state=TEST_STATE,code_verifier='A'*64)
    att=oauth.record_authorization_attempt(chan.state_id,req,client_id='client-1')
    tok=oauth.exchange_code(att.state_id,returned_state=TEST_STATE,code='c',code_verifier='A'*64,client_id='client-1')
    with pytest.raises(LedgerError,match='test-only'):
        oauth.commit_verified_grant(att.state_id,tok,channel_binding_state_id=chan.state_id,refresh_store=InMemoryRefreshTokenStore())


def test_refresh_rejects_wrong_client_and_broader_scope(tmp_path: Path):
    l,opp,elig,chan,cfg,creative,rec=make_chain(tmp_path,'refresh-contract')
    tr=FakeTransport(); oauth,grant,store,tok=verified_grant(l,chan,tr)
    with pytest.raises(LedgerError,match='client_id'):
        oauth.refresh_access_token(grant.state_id,client_id='other-client',client_secret=None,refresh_store=store)
    tr.token_response={'access_token':'NEW','token_type':'Bearer','expires_in':3600,'scope':YOUTUBE_UPLOAD_SCOPE+' https://www.googleapis.com/auth/youtube.readonly'}
    with pytest.raises(LedgerError,match='exactly'):
        oauth.refresh_access_token(grant.state_id,client_id='client-1',client_secret=None,refresh_store=store)


def test_only_latest_refresh_receipt_can_drive_publication_token(tmp_path: Path):
    l,opp,elig,chan,cfg,creative,rec=make_chain(tmp_path,'latest-refresh')
    tr=FakeTransport(); oauth,grant,store,initial=verified_grant(l,chan,tr)
    tr.token_response={'access_token':'NEW1','token_type':'Bearer','expires_in':3600,'scope':YOUTUBE_UPLOAD_SCOPE}
    one=oauth.refresh_access_token(grant.state_id,client_id='client-1',client_secret=None,refresh_store=store)
    tr.token_response={'access_token':'NEW2','token_type':'Bearer','expires_in':3600,'scope':YOUTUBE_UPLOAD_SCOPE}
    two=oauth.refresh_access_token(grant.state_id,client_id='client-1',client_secret=None,refresh_store=store)
    with pytest.raises(LedgerError,match='superseded'):
        oauth.assert_token_bound_to_grant(grant.state_id,one)
    with pytest.raises(LedgerError,match='superseded'):
        oauth.assert_token_bound_to_grant(grant.state_id,initial)
    assert oauth.assert_token_bound_to_grant(grant.state_id,two)['id']==grant.state_id


def test_publication_descriptor_binds_exact_metadata_and_streaming_upload(tmp_path: Path):
    l,opp,elig,chan,cfg,creative,rec=make_chain(tmp_path,'metadata-stream')
    tr=FakeTransport(); media=make_media(tmp_path)
    pub,desc,auth,oauth,grant,store,tok,attempt=ready_publication(l,chan,cfg,creative,rec,media,tr,title='Approved title',description='Approved description')
    payload=l.get_state(desc.state_id)['payload']
    assert payload['youtube_title']=='Approved title' and payload['intended_privacy_status']=='private'
    tr.calls.clear(); pub.upload_private(publication_attempt_state_id=attempt.state_id,oauth_token=tok,media_path=media)
    init=[c for c in tr.calls if c[0]=='post_json'][-1]
    assert init[2]['snippet']=={'title':'Approved title','description':'Approved description'}
    assert any(c[0]=='put_file' for c in tr.calls)
    assert not any(c[0]=='put_bytes' for c in tr.calls)

def test_human_authorization_binds_publication_metadata_hash(tmp_path: Path):
    l,opp,elig,chan,cfg,creative,rec=make_chain(tmp_path,'metadata-auth')
    media=make_media(tmp_path); pub=YouTubePublicationService(l,transport=FakeTransport())
    desc=pub.create_media_descriptor(creative.state_id,media,title='Reviewed title',description='Reviewed body')
    auth=authorize_with_media(l,chan,cfg,creative,rec,desc)
    ap=l.get_state(auth.state_id)['payload']; dp=l.get_state(desc.state_id)['payload']
    assert ap['publication_metadata_sha256']==dp['publication_metadata_sha256']
    assert ap['intended_privacy_status']=='private'


def test_abnormal_provider_privacy_records_emergency_incident_without_execution(tmp_path: Path):
    from trend_hunter.db import connect
    l,opp,elig,chan,cfg,creative,rec=make_chain(tmp_path,'safety-incident')
    tr=FakeTransport(); media=make_media(tmp_path)
    pub,desc,auth,oauth,grant,store,tok,attempt=ready_publication(l,chan,cfg,creative,rec,media,tr)
    tr.upload_response['status']['privacyStatus']='public'; tr.calls.clear()
    with pytest.raises(LedgerError,match='EMERGENCY_HUMAN_ACTION_REQUIRED'):
        pub.upload_private(publication_attempt_state_id=attempt.state_id,oauth_token=tok,media_path=media)
    with connect(l.db_path) as conn:
        rows=conn.execute("SELECT s.payload_json FROM domain_record d JOIN artifact_state s ON s.id=d.artifact_state_id WHERE d.stage='YOUTUBE_PUBLICATION_SAFETY_INCIDENT'").fetchall()
        pubs=conn.execute("SELECT COUNT(*) AS n FROM domain_record WHERE stage='PUBLICATION_EXECUTION'").fetchone()['n']
    assert len(rows)==1 and 'EMERGENCY_HUMAN_ACTION_REQUIRED' in rows[0]['payload_json'] and pubs==0

def test_rejected_newer_human_decision_blocks_before_youtube_side_effect(tmp_path: Path):
    l,opp,elig,chan,cfg,creative,rec=make_chain(tmp_path,'preflight-reject')
    tr=FakeTransport(); media=make_media(tmp_path); pub=YouTubePublicationService(l,transport=tr)
    desc=pub.create_media_descriptor(creative.state_id,media,title='Title'); auth=authorize_with_media(l,chan,cfg,creative,rec,desc)
    oauth,grant,store,tok=verified_grant(l,chan,tr)
    OperationsService(l).record_human_authorization(rec.state_id,'human','REJECTED',execution_configuration_state_id=cfg.state_id,channel_binding_state_id=chan.state_id,media_descriptor_state_id=desc.state_id,require_exact_channel=True,require_exact_media=True)
    tr.calls.clear()
    with pytest.raises(LedgerError,match='stale/superseded'):
        pub.execute_authorized_private_upload(operations=OperationsService(l),creative_state_id=creative.state_id,authorization_state_id=auth.state_id,oauth_grant_state_id=grant.state_id,oauth_token=tok,media_path=media)
    assert not any(c[0] in {'post_json','put_file','put_bytes'} for c in tr.calls)


def test_upload_session_rejects_non_youtube_path_and_nonstandard_port(tmp_path: Path):
    l,opp,elig,chan,cfg,creative,rec=make_chain(tmp_path,'session-boundary')
    media=make_media(tmp_path); tr=FakeTransport()
    pub,desc,auth,oauth,grant,store,tok,attempt=ready_publication(l,chan,cfg,creative,rec,media,tr)
    locations=[
        'https://www.googleapis.com/drive/v3/files?upload_id=x',
        'https://www.googleapis.com:444/upload/youtube/v3/videos?upload_id=x',
    ]
    for i,location in enumerate(locations):
        tr.location=location; tr.calls.clear()
        if i==0:
            current_attempt=attempt
        else:
            # Separate approval: a failed/ambiguous provider attempt may
            # never be replayed under its original authorization.
            auth2=authorize_with_media(l,chan,cfg,creative,rec,desc)
            current_attempt=pub.prepare_publication_attempt(operations=OperationsService(l),creative_state_id=creative.state_id,authorization_state_id=auth2.state_id,oauth_grant_state_id=grant.state_id,oauth_token=tok,media_path=media)
        with pytest.raises(LedgerError,match='upload path boundary|allowlist'):
            pub.upload_private(publication_attempt_state_id=current_attempt.state_id,oauth_token=tok,media_path=media)
        assert not any(c[0]=='put_file' for c in tr.calls)

def test_empty_video_is_rejected_before_authorization(tmp_path: Path):
    l,opp,elig,chan,cfg,creative,rec=make_chain(tmp_path,'empty-video')
    p=make_media(tmp_path,content=b'')
    with pytest.raises(LedgerError,match='must not be empty'):
        YouTubePublicationService(l,transport=FakeTransport()).create_media_descriptor(creative.state_id,p,title='Title')

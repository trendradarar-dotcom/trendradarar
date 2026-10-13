"""R1.1 narrow replay tests: isolated temp DB and fake provider only."""
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

import pytest

from tests.test_c1_c4_youtube import (
    make_chain, make_media, ready_publication, FakeTransport,
    authorize_with_media, verified_grant,
)
from trend_hunter.c1_youtube import YouTubePublicationService
from trend_hunter.ledger import GovernanceLedger, LedgerError
from trend_hunter.operations import OperationsService


def test_r11_same_authorization_cannot_prepare_twice_or_upload_twice(tmp_path):
    ledger, _, _, channel, config, creative, rec = make_chain(tmp_path, "r11-repeat")
    media = make_media(tmp_path)
    transport = FakeTransport()
    pub, desc, auth, oauth, grant, store, token, first = ready_publication(
        ledger, channel, config, creative, rec, media, transport
    )
    assert first.version == 1
    with pytest.raises(LedgerError, match="already"):
        pub.prepare_publication_attempt(
            operations=OperationsService(ledger),
            creative_state_id=creative.state_id,
            authorization_state_id=auth.state_id,
            oauth_grant_state_id=grant.state_id,
            oauth_token=token,
            media_path=media,
        )
    transport.calls.clear()
    pub.upload_private(publication_attempt_state_id=first.state_id, oauth_token=token, media_path=media)
    assert len([c for c in transport.calls if c[0] == "post_json"]) == 1
    assert len([c for c in transport.calls if c[0] == "put_file"]) == 1
    with pytest.raises(LedgerError, match="already"):
        pub.prepare_publication_attempt(
            operations=OperationsService(ledger),
            creative_state_id=creative.state_id,
            authorization_state_id=auth.state_id,
            oauth_grant_state_id=grant.state_id,
            oauth_token=token,
            media_path=media,
        )
    assert len([c for c in transport.calls if c[0] == "post_json"]) == 1


def test_r11_claim_survives_process_recreation_and_preparation_crash(tmp_path):
    ledger, _, _, channel, config, creative, rec = make_chain(tmp_path, "r11-crash")
    media = make_media(tmp_path)
    transport = FakeTransport()
    pub, desc, auth, oauth, grant, store, token, first = ready_publication(
        ledger, channel, config, creative, rec, media, transport
    )
    fresh = GovernanceLedger(ledger.db_path)
    with pytest.raises(LedgerError, match="already"):
        fresh.claim_youtube_private_authorization_once(auth.state_id)
    assert not any(c[0] in {"post_json", "put_file"} and "upload" in str(c) for c in transport.calls)


def test_r11_concurrent_same_authorization_exactly_one_claim(tmp_path):
    ledger, _, _, channel, config, creative, rec = make_chain(tmp_path, "r11-concurrent")
    media = make_media(tmp_path)
    transport = FakeTransport()
    pub = YouTubePublicationService(ledger, transport=transport)
    desc = pub.create_media_descriptor(creative.state_id, media, title="Concurrent")
    auth = authorize_with_media(ledger, channel, config, creative, rec, desc)
    oauth, grant, store, token = verified_grant(ledger, channel, transport)
    barrier = Barrier(2)
    def attempt(_):
        local = GovernanceLedger(ledger.db_path)
        publishing = YouTubePublicationService(local, transport=transport)
        barrier.wait(timeout=10)
        try:
            return publishing.prepare_publication_attempt(
                operations=OperationsService(local),
                creative_state_id=creative.state_id,
                authorization_state_id=auth.state_id,
                oauth_grant_state_id=grant.state_id,
                oauth_token=token,
                media_path=media,
            ).state_id
        except LedgerError as exc:
            return "BLOCKED:" + str(exc)
    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = list(pool.map(attempt, [0, 1]))
    assert sum(not x.startswith("BLOCKED:") for x in outcomes) == 1, outcomes
    assert sum(x.startswith("BLOCKED:") for x in outcomes) == 1, outcomes
    assert not any(c[0] in {"put_file", "put_bytes"} for c in transport.calls)


def test_r11_same_ready_attempt_concurrent_provider_effect_once(tmp_path):
    ledger, _, _, channel, config, creative, rec = make_chain(tmp_path, "r11-provider-race")
    media = make_media(tmp_path)
    transport = FakeTransport()
    pub, desc, auth, oauth, grant, store, token, first = ready_publication(
        ledger, channel, config, creative, rec, media, transport
    )
    transport.calls.clear()
    barrier = Barrier(2)
    def call_upload(_):
        local = GovernanceLedger(ledger.db_path)
        publishing = YouTubePublicationService(local, transport=transport)
        barrier.wait(timeout=10)
        try:
            publishing.upload_private(
                publication_attempt_state_id=first.state_id,
                oauth_token=token,
                media_path=media,
            )
            return "SUCCESS"
        except LedgerError as exc:
            return "BLOCKED:" + str(exc)
    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = list(pool.map(call_upload, [0, 1]))
    assert outcomes.count("SUCCESS") == 1, outcomes
    assert sum(x.startswith("BLOCKED:") for x in outcomes) == 1, outcomes
    assert sum(c[0] == "post_json" for c in transport.calls) == 1
    assert sum(c[0] == "put_file" for c in transport.calls) == 1


def test_r11_provider_claim_crash_remains_hold_without_upload(tmp_path):
    ledger, _, _, channel, config, creative, rec = make_chain(tmp_path, "r11-provider-crash")
    media = make_media(tmp_path)
    transport = FakeTransport()
    pub, desc, auth, oauth, grant, store, token, first = ready_publication(
        ledger, channel, config, creative, rec, media, transport
    )
    transport.calls.clear()
    GovernanceLedger(ledger.db_path).claim_youtube_private_provider_once(first.state_id)
    with pytest.raises(LedgerError, match="already claimed"):
        pub.upload_private(
            publication_attempt_state_id=first.state_id, oauth_token=token, media_path=media,
        )
    assert not any(c[0] in {"post_json", "put_file", "put_bytes"} for c in transport.calls)


def test_r11_legacy_attempt_consumes_authorization_without_new_claim(tmp_path):
    ledger, _, _, channel, config, creative, rec = make_chain(tmp_path, "r11-legacy")
    media = make_media(tmp_path)
    transport = FakeTransport()
    pub = YouTubePublicationService(ledger, transport=transport)
    desc = pub.create_media_descriptor(creative.state_id, media, title="Legacy")
    auth = authorize_with_media(ledger, channel, config, creative, rec, desc)
    oauth, grant, store, token = verified_grant(ledger, channel, transport)
    ledger.record_domain(
        "YOUTUBE_PUBLICATION_ATTEMPT", "Legacy test evidence",
        {"authorization_state_id": auth.state_id, "status": "AMBIGUOUS_PROVIDER_STATE"},
        natural_key="legacy-one-use-attempt",
    )
    with pytest.raises(LedgerError, match="already consumed"):
        pub.prepare_publication_attempt(
            operations=OperationsService(ledger),
            creative_state_id=creative.state_id,
            authorization_state_id=auth.state_id,
            oauth_grant_state_id=grant.state_id,
            oauth_token=token,
            media_path=media,
        )
    assert not any(c[0] == "put_file" for c in transport.calls)


def test_r11_api_replay_rejected_before_second_refresh(tmp_path, monkeypatch):
    """API preflight rejects sequential replay before OAuth refresh.
    The fake publisher represents C1's durable claim; no real provider/DPAPI.
    """
    from types import SimpleNamespace
    import trend_hunter.api as api
    from tests.test_youtube_private_entrypoint import setup_route, payload, RADAR

    client, ledger, channel, auth, grant, headers = setup_route(tmp_path, monkeypatch)
    calls = []
    token = SimpleNamespace(access_token="FAKE_ACCESS", token_receipt_state_id="FAKE_RECEIPT")

    class FakeOAuth:
        def __init__(self, _ledger):
            pass
        def refresh_access_token(self, *_args, **_kwargs):
            calls.append("refresh")
            return token

    class FakePublisher:
        def __init__(self, _ledger):
            self.ledger = _ledger
        def execute_authorized_private_upload(self, **kwargs):
            self.ledger.claim_youtube_private_authorization_once(
                kwargs["authorization_state_id"]
            )
            calls.append("fake-upload")
            return {
                "provider_result": {"channel_id": RADAR, "privacy_status": "private", "video_id": "FAKE"},
                "proof": SimpleNamespace(),
                "execution": SimpleNamespace(),
            }

    monkeypatch.setattr(api, "YouTubeOAuthService", FakeOAuth)
    monkeypatch.setattr(api, "WindowsDPAPIRefreshTokenStore", lambda: object())
    monkeypatch.setattr(api, "YouTubePublicationService", FakePublisher)
    first = client.post(
        "/api/youtube/private-upload",
        json=payload(auth.state_id, grant.state_id), headers=headers,
    )
    second = client.post(
        "/api/youtube/private-upload",
        json=payload(auth.state_id, grant.state_id), headers=headers,
    )
    assert first.status_code == 200, first.text
    assert second.status_code == 400, second.text
    assert "already" in second.json()["detail"]
    assert calls == ["refresh", "fake-upload"]

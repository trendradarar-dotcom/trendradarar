from __future__ import annotations

import os

import pytest

from trend_hunter import api
from trend_hunter.c1_youtube import EnvironmentRefreshTokenStore
from trend_hunter.ledger import LedgerError


def test_environment_store_requires_preprovisioned_secret(monkeypatch):
    monkeypatch.delenv("TREND_HUNTER_YOUTUBE_REFRESH_TOKEN", raising=False)
    with pytest.raises(LedgerError, match="unavailable"):
        EnvironmentRefreshTokenStore()


def test_environment_store_roundtrip_is_reference_bound(monkeypatch):
    monkeypatch.setenv("TREND_HUNTER_YOUTUBE_REFRESH_TOKEN", "REFRESH_SECRET")
    store = EnvironmentRefreshTokenStore()
    ref = store.put("youtube-channel", "REFRESH_SECRET")
    assert ref == "env://TREND_HUNTER_YOUTUBE_REFRESH_TOKEN"
    assert store.get(ref) == "REFRESH_SECRET"
    with pytest.raises(LedgerError, match="does not match"):
        store.get("env://OTHER")


def test_environment_store_rejects_mismatched_grant_secret(monkeypatch):
    monkeypatch.setenv("TREND_HUNTER_YOUTUBE_REFRESH_TOKEN", "EXPECTED")
    store = EnvironmentRefreshTokenStore()
    with pytest.raises(LedgerError, match="does not match"):
        store.put("youtube-channel", "DIFFERENT")


def test_linux_runtime_requires_explicit_store_selection(monkeypatch):
    monkeypatch.delenv("TREND_HUNTER_YOUTUBE_REFRESH_TOKEN_STORE", raising=False)
    monkeypatch.delenv("TREND_HUNTER_YOUTUBE_REFRESH_TOKEN", raising=False)
    if os.name != "nt":
        with pytest.raises(LedgerError, match="only available on Windows"):
            api._youtube_refresh_token_store_from_runtime()


def test_linux_render_environment_store_selection(monkeypatch):
    monkeypatch.setenv("TREND_HUNTER_YOUTUBE_REFRESH_TOKEN_STORE", "environment")
    monkeypatch.setenv("TREND_HUNTER_YOUTUBE_REFRESH_TOKEN", "ROTATABLE_SECRET")
    store = api._youtube_refresh_token_store_from_runtime()
    assert isinstance(store, EnvironmentRefreshTokenStore)
    assert store.get("env://TREND_HUNTER_YOUTUBE_REFRESH_TOKEN") == "ROTATABLE_SECRET"


def test_unsupported_store_backend_fails_closed(monkeypatch):
    monkeypatch.setenv("TREND_HUNTER_YOUTUBE_REFRESH_TOKEN_STORE", "unknown")
    with pytest.raises(LedgerError, match="Unsupported"):
        api._youtube_refresh_token_store_from_runtime()


def test_private_upload_route_uses_environment_store_when_selected(tmp_path, monkeypatch):
    from types import SimpleNamespace
    from tests.test_youtube_private_entrypoint import setup_route, payload, RADAR

    client, _, channel, auth, grant, headers = setup_route(tmp_path, monkeypatch)
    monkeypatch.setenv("TREND_HUNTER_YOUTUBE_REFRESH_TOKEN_STORE", "environment")
    monkeypatch.setenv("TREND_HUNTER_YOUTUBE_REFRESH_TOKEN", "RENDER_SECRET")

    token = SimpleNamespace(access_token="FAKE_ACCESS", token_receipt_state_id="FAKE_RECEIPT")

    class FakeOAuth:
        def __init__(self, _ledger):
            pass

        def refresh_access_token(self, grant_id, *, client_id, client_secret, refresh_store):
            assert grant_id == grant.state_id
            assert client_id == "client-test"
            assert client_secret is None
            assert isinstance(refresh_store, EnvironmentRefreshTokenStore)
            assert refresh_store.get("env://TREND_HUNTER_YOUTUBE_REFRESH_TOKEN") == "RENDER_SECRET"
            return token

    class FakePublisher:
        def __init__(self, _ledger):
            pass

        def execute_authorized_private_upload(self, **kwargs):
            return {
                "provider_result": {
                    "channel_id": RADAR,
                    "privacy_status": "private",
                    "video_id": "FAKE_RENDER_PORTABILITY",
                },
                "proof": SimpleNamespace(__dict__={}),
                "execution": SimpleNamespace(__dict__={}),
            }

    monkeypatch.setattr(api, "YouTubeOAuthService", FakeOAuth)
    monkeypatch.setattr(api, "YouTubePublicationService", FakePublisher)

    response = client.post(
        "/api/youtube/private-upload",
        json=payload(auth.state_id, grant.state_id),
        headers=headers,
    )
    assert response.status_code == 200, response.text
    assert response.json()["provider_result"]["video_id"] == "FAKE_RENDER_PORTABILITY"

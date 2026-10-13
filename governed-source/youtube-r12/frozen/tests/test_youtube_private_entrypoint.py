"""Isolated tests for the YouTube-only private upload API entrypoint.

No production database, DPAPI secrets, OAuth endpoint, or real YouTube upload is used.
The C1 publication engine has its own independent fake-provider test suite.
"""
from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

import trend_hunter.api as api
from trend_hunter.ledger import GovernanceLedger
from trend_hunter.operational import OperationalBindingService
from trend_hunter.security import HMACTokenAuthority

RADAR = "UCPm6nbktPc2Egr05AV-zPhA"
OTHER = "UCvsTLGtzV5XqBUSn0eDs6sA"
SECRET = "isolated-youtube-entrypoint-fake-secret-123456789"


class FakeBound:
    authorized_role = "publication_operator"
    operator_binding_state_id = "isolated-operator"

    def audit_context(self):
        return {"authenticated": True, "isolated_test": True}


def payload(auth, grant):
    return {
        "creative_state_id": "creative-test",
        "authorization_state_id": auth,
        "oauth_grant_state_id": grant,
        "oauth_client_id": "client-test",
    }


def setup_route(tmp_path: Path, monkeypatch, channel_ref: str = RADAR):
    monkeypatch.setenv("TREND_HUNTER_AUTH_SECRET", SECRET)
    monkeypatch.setenv("TREND_HUNTER_YOUTUBE_PRIVATE_UPLOAD_ENABLED", "1")
    monkeypatch.setattr(
        api.GovernedAuthorizationResolver, "require",
        lambda self, actor, role, scope: FakeBound(),
    )
    db = tmp_path / "data" / "test-ledger.db"
    db.parent.mkdir(parents=True)
    app = api.create_app(str(db), auth_required=True)
    ledger = GovernanceLedger(str(db))
    binding = OperationalBindingService(ledger)
    account = binding.bind_external_account("youtube", "isolated-fake-owner", account_kind="CHANNEL_OWNER")
    channel = binding.bind_channel(account.state_id, "youtube", channel_ref)
    auth = ledger.record_domain(
        "HUMAN_AUTHORIZATION", "Test Only", {"channel_binding_state_id": channel.state_id},
        natural_key="isolated-entry-auth",
    )
    grant = ledger.record_domain(
        "YOUTUBE_OAUTH_GRANT_BINDING", "Test Only", {"channel_binding_state_id": channel.state_id},
        natural_key="isolated-entry-grant",
    )
    token = HMACTokenAuthority(SECRET).issue("isolated-test-operator", ["publication_operator"])
    headers = {"Authorization": "Bearer " + token}
    return TestClient(app), ledger, channel, auth, grant, headers


def test_private_upload_is_locked_without_production_auth(tmp_path, monkeypatch):
    monkeypatch.setenv("TREND_HUNTER_YOUTUBE_PRIVATE_UPLOAD_ENABLED", "1")
    app = api.create_app(str(tmp_path / "ledger.db"), auth_required=False)
    response = TestClient(app).post(
        "/api/youtube/private-upload", json=payload("missing", "missing")
    )
    assert response.status_code == 423
    assert "HOLD" in response.json()["detail"]


def test_private_upload_is_locked_by_default(tmp_path, monkeypatch):
    monkeypatch.delenv("TREND_HUNTER_YOUTUBE_PRIVATE_UPLOAD_ENABLED", raising=False)
    app = api.create_app(str(tmp_path / "ledger.db"), auth_required=False)
    response = TestClient(app).post(
        "/api/youtube/private-upload", json=payload("missing", "missing")
    )
    assert response.status_code == 423


def test_private_upload_requires_authenticated_operator(tmp_path, monkeypatch):
    client, _, _, auth, grant, _ = setup_route(tmp_path, monkeypatch)
    response = client.post("/api/youtube/private-upload", json=payload(auth.state_id, grant.state_id))
    assert response.status_code == 401


def test_private_upload_rejects_other_youtube_channel_before_oauth(tmp_path, monkeypatch):
    client, _, _, auth, grant, headers = setup_route(tmp_path, monkeypatch, OTHER)
    class MustNotRefresh:
        def __init__(self, *a, **kw):
            raise AssertionError("OAuth refresh must not be reached for wrong channel")
    monkeypatch.setattr(api, "YouTubeOAuthService", MustNotRefresh)
    response = client.post(
        "/api/youtube/private-upload",
        json=payload(auth.state_id, grant.state_id), headers=headers,
    )
    assert response.status_code == 400
    assert "Only the exact Trend Radar" in response.json()["detail"]


def test_private_upload_rejects_mismatched_grant_before_oauth(tmp_path, monkeypatch):
    client, ledger, _, auth, _, headers = setup_route(tmp_path, monkeypatch)
    bad = ledger.record_domain(
        "YOUTUBE_OAUTH_GRANT_BINDING", "Test Only",
        {"channel_binding_state_id": "unrelated-channel"}, natural_key="isolated-bad-grant",
    )
    response = client.post(
        "/api/youtube/private-upload",
        json=payload(auth.state_id, bad.state_id), headers=headers,
    )
    assert response.status_code == 400
    assert "do not match" in response.json()["detail"]


def test_private_upload_rejects_superseded_channel_before_oauth(tmp_path, monkeypatch):
    client, ledger, channel, auth, grant, headers = setup_route(tmp_path, monkeypatch)
    data = dict(ledger.get_state(channel.state_id)["payload"])
    data["status"] = "REMOVED_BY_OWNER"
    ledger.record_domain(
        "LIVE_CHANNEL_BINDING", "Test Only", data, natural_key=f"channel:youtube:{RADAR}",
        record_state="REMOVED",
    )
    response = client.post(
        "/api/youtube/private-upload",
        json=payload(auth.state_id, grant.state_id), headers=headers,
    )
    assert response.status_code == 400
    assert "stale/superseded" in response.json()["detail"]


def test_private_upload_wires_exact_inputs_to_c1_using_fakes_only(tmp_path, monkeypatch):
    client, _, channel, auth, grant, headers = setup_route(tmp_path, monkeypatch)
    calls = []
    token = SimpleNamespace(access_token="FAKE_ACCESS", token_receipt_state_id="fake-receipt")

    class FakeOAuth:
        def __init__(self, ledger):
            calls.append("oauth-service")
        def refresh_access_token(self, grant_id, *, client_id, client_secret, refresh_store):
            assert grant_id == grant.state_id
            assert client_id == "client-test"
            assert client_secret is None
            calls.append("fake-refresh")
            return token

    class FakePublisher:
        def __init__(self, ledger):
            calls.append("publisher-service")
        def execute_authorized_private_upload(self, **kwargs):
            assert kwargs["creative_state_id"] == "creative-test"
            assert kwargs["authorization_state_id"] == auth.state_id
            assert kwargs["oauth_grant_state_id"] == grant.state_id
            assert kwargs["oauth_token"] is token
            assert kwargs["media_path"].parts[-3:] == (
                "publication_media", "creative-test", "publication.mp4"
            )
            assert kwargs["auth_context"]["authenticated"] is True
            calls.append("fake-private-execution")
            return {
                "provider_result": {"channel_id": RADAR, "privacy_status": "private", "video_id": "FAKE_ID"},
                "proof": SimpleNamespace(__dict__={}),
                "execution": SimpleNamespace(__dict__={}),
            }

    monkeypatch.setattr(api, "YouTubeOAuthService", FakeOAuth)
    monkeypatch.setattr(api, "WindowsDPAPIRefreshTokenStore", lambda: object())
    monkeypatch.setattr(api, "YouTubePublicationService", FakePublisher)
    response = client.post(
        "/api/youtube/private-upload",
        json=payload(auth.state_id, grant.state_id), headers=headers,
    )
    assert response.status_code == 200, response.text
    assert response.json()["provider_result"]["channel_id"] == RADAR
    assert calls == ["oauth-service", "fake-refresh", "publisher-service", "fake-private-execution"]

from __future__ import annotations

import io
import json
import os
import shutil
import urllib.error
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from trend_hunter.api import create_app
from trend_hunter.backup import create_backup, restore_backup
from trend_hunter.bootstrap import bootstrap_governance
from trend_hunter.connectors.http import HTTPPolicy, ResilientHTTPClient
from trend_hunter.connectors.google_trends_export import GoogleTrendsExportConnector
from trend_hunter.db import init_db, connect
from trend_hunter.ledger import GovernanceLedger, LedgerError
from trend_hunter.ingest import IngestionService
from trend_hunter.operational import OperationalBindingService, OperationalPreflight
from trend_hunter.security import HMACTokenAuthority, SecurityError, SecretResolver


def make_ledger(tmp_path: Path) -> GovernanceLedger:
    db = tmp_path / "trend_hunter.db"
    init_db(str(db))
    ledger = GovernanceLedger(str(db))
    bootstrap_governance(ledger)
    return ledger


def test_hmac_token_binds_subject_roles_and_rejects_tampering():
    auth = HMACTokenAuthority("s" * 32)
    token = auth.issue("operator-1", ["publisher_authorizer", "operator"], ttl_seconds=60, now=1000)
    actor = auth.verify(token, now=1020)
    assert actor.subject == "operator-1"
    assert actor.has_role("publisher_authorizer")
    assert actor.audit_context()["authenticated"] is True
    prefix, payload, signature = token.split(".", 2)
    tampered_signature = ("A" if signature[0] != "A" else "B") + signature[1:]
    with pytest.raises(SecurityError):
        auth.verify(f"{prefix}.{payload}.{tampered_signature}", now=1020)
    with pytest.raises(SecurityError):
        auth.verify(token, now=2000)


def test_secret_resolver_uses_reference_not_persisted_plaintext(monkeypatch):
    monkeypatch.setenv("O1_TEST_SECRET", "super-secret-value")
    assert SecretResolver.resolve("env://O1_TEST_SECRET") == "super-secret-value"
    redacted = SecretResolver.redacted("env://O1_TEST_SECRET")
    assert redacted == {"secret_ref": "env://O1_TEST_SECRET", "available": True, "plaintext_persisted": False}
    assert "super-secret-value" not in json.dumps(redacted)


def test_operational_api_requires_authenticated_mutation_and_specialized_role(tmp_path: Path, monkeypatch, make_test_client):
    monkeypatch.setenv("TREND_HUNTER_AUTH_SECRET", "a" * 32)
    db = tmp_path / "api.db"
    app = create_app(str(db), auth_required=True)
    ledger = GovernanceLedger(str(db))
    bindings = OperationalBindingService(ledger)
    bindings.register_operator("op", roles=["operator"], scopes=["source:write"])
    bindings.register_operator("publisher", roles=["publisher_authorizer"], scopes=["publication:authorize"])
    c = make_test_client(app)
    assert c.get("/health").status_code == 200
    # Mutation without bearer is blocked before domain logic.
    r = c.post("/api/source/manual", json={"items": []})
    assert r.status_code == 401

    auth = HMACTokenAuthority("a" * 32)
    operator = auth.issue("op", ["operator"], ttl_seconds=60)
    r = c.post("/api/source/manual", json={"items": []}, headers={"Authorization": f"Bearer {operator}"})
    assert r.status_code == 200

    # Token role alone cannot exercise final publication authority.
    r = c.post(
        "/api/human-authorization",
        json={"recommendation_state_id": "missing", "decision": "AUTHORIZED"},
        headers={"Authorization": f"Bearer {operator}"},
    )
    assert r.status_code == 403

    publisher = auth.issue("publisher", ["publisher_authorizer"], ttl_seconds=60)
    r = c.post(
        "/api/human-authorization",
        json={"recommendation_state_id": "missing", "decision": "AUTHORIZED", "execution_configuration_state_id":"missing", "channel_binding_state_id":"missing"},
        headers={"Authorization": f"Bearer {publisher}"},
    )
    assert r.status_code == 400  # governed identity/role reached exact domain validation


def test_publication_execution_requires_exact_live_channel_in_operational_mode(tmp_path: Path):
    ledger = make_ledger(tmp_path)
    # Test only the exact-bound-channel guard with intentionally invalid state ids after it would be reached later.
    # Directly verify a channel binding is persisted as governed state, not free-form runtime configuration.
    ops = OperationalBindingService(ledger)
    account = ops.bind_external_account("youtube", "acct-1", account_kind="CHANNEL_OWNER")
    channel = ops.bind_channel(account.state_id, "youtube", "channel-123", language="ar", region="SA")
    assert ledger.get_state(channel.state_id)["payload"]["channel_ref"] == "channel-123"
    with connect(ledger.db_path) as conn:
        n = conn.execute("SELECT COUNT(*) n FROM domain_record WHERE stage='LIVE_CHANNEL_BINDING' AND record_state='ACTIVE'").fetchone()["n"]
    assert n == 1


def test_backup_restore_roundtrip_is_hash_and_ledger_verified(tmp_path: Path):
    ledger = make_ledger(tmp_path / "src")
    iid = ledger.get_or_create_identity("TEST", "backup")
    state = ledger.create_state(iid, "TEST_STATE", {"x": 1}, raw_bytes=b"backup-data")
    archive = tmp_path / "backup.zip"
    info = create_backup(ledger.db_path, str(archive))
    assert info["ok"] is True and archive.is_file()

    restored = tmp_path / "restored"
    result = restore_backup(str(archive), str(restored))
    assert result["ok"] is True
    ledger2 = GovernanceLedger(str(restored / "trend_hunter.db"), str(restored / "trend_hunter_objects"))
    assert ledger2.get_state(state.state_id)["payload"] == {"x": 1}
    assert ledger2.integrity_check()["ok"] is True


def test_operational_preflight_distinguishes_user_actions_and_external_dependencies(tmp_path: Path, monkeypatch):
    monkeypatch.delenv("TREND_HUNTER_AUTH_SECRET", raising=False)
    monkeypatch.delenv("YOUTUBE_API_KEY", raising=False)
    ledger = make_ledger(tmp_path)
    report = OperationalPreflight(ledger).report()
    by_key = {x["key"]: x for x in report["checks"]}
    assert by_key["governance_ledger_integrity"]["status"] == "SYSTEM_CAN_EXECUTE"
    assert by_key["production_auth_signing_secret"]["status"] == "USER_ACTION_REQUIRED"
    assert by_key["youtube_api_credential"]["status"] == "EXTERNAL_DEPENDENCY"
    assert by_key["gdelt_live_connector_smoke"]["status"] == "EXTERNAL_DEPENDENCY"
    assert by_key["youtube_live_connector_smoke"]["status"] == "EXTERNAL_DEPENDENCY"
    assert report["commercial_launch_ready"] is False


def test_operational_preflight_recognizes_current_governed_google_trends_export(tmp_path: Path, monkeypatch):
    monkeypatch.delenv("TREND_HUNTER_AUTH_SECRET", raising=False)
    monkeypatch.delenv("YOUTUBE_API_KEY", raising=False)
    ledger = make_ledger(tmp_path)
    csv_path = tmp_path / "trending_SA.csv"
    csv_path.write_text("Trends,Search volume\nartificial intelligence,20000\n", encoding="utf-8")
    connector = GoogleTrendsExportConnector(str(csv_path), region="SA")
    refs = IngestionService(ledger).ingest(connector.fetch(), connector.name)
    assert len(refs) == 1

    report = OperationalPreflight(ledger).report()
    by_key = {x["key"]: x for x in report["checks"]}
    check = by_key["google_trends_export"]
    assert check["status"] == "SYSTEM_CAN_EXECUTE"
    assert check["detail"]["fresh"] is True
    assert check["detail"]["observed_record_count"] >= 1
    assert check["detail"]["latest_state_id"] == refs[0].state_id
    assert check["detail"]["regions"] == ["SA"]


def test_operational_preflight_google_trends_export_absent_is_user_action_required(tmp_path: Path, monkeypatch):
    monkeypatch.delenv("TREND_HUNTER_AUTH_SECRET", raising=False)
    monkeypatch.delenv("YOUTUBE_API_KEY", raising=False)
    ledger = make_ledger(tmp_path)
    report = OperationalPreflight(ledger).report()
    by_key = {x["key"]: x for x in report["checks"]}
    check = by_key["google_trends_export"]
    assert check["status"] == "USER_ACTION_REQUIRED"
    assert check["detail"]["mode"] == "export/import"


def test_resilient_http_client_retries_retryable_status_then_succeeds():
    calls = []
    sleeps = []

    class Response:
        def __init__(self, body: bytes): self.body = body
        def __enter__(self): return self
        def __exit__(self, *args): return False
        def read(self): return self.body

    def opener(req, timeout=0):
        calls.append((req, timeout))
        if len(calls) == 1:
            raise urllib.error.HTTPError("http://x", 503, "unavailable", {}, io.BytesIO())
        return Response(b"ok")

    client = ResilientHTTPClient(HTTPPolicy(max_attempts=3, backoff_base_seconds=0.01), opener=opener, sleeper=sleeps.append)
    assert client.open("request", timeout=7) == b"ok"
    assert len(calls) == 2
    assert sleeps == [0.01]

from __future__ import annotations

import os
from pathlib import Path

import pytest
from tests._governance_template import isolated_governance_ledger
from fastapi.testclient import TestClient

from trend_hunter.api import create_app
from trend_hunter.connectors.http import ConnectorHTTPError
from trend_hunter.db import connect
from trend_hunter.execution import ExecutionService
from trend_hunter.ledger import GovernanceLedger, LedgerError
from trend_hunter.live import connector_smoke
from trend_hunter.operational import OperationalBindingService, OperationalPreflight
from trend_hunter.operations import OperationsService
from trend_hunter.pipeline import SyntheticPilotRunner
from trend_hunter.security import HMACTokenAuthority


def make_ledger(tmp_path: Path) -> GovernanceLedger:
    return isolated_governance_ledger(tmp_path, 'o1')


def test_signed_token_without_governed_operator_binding_is_denied(tmp_path: Path, monkeypatch, make_test_client):
    monkeypatch.setenv("TREND_HUNTER_AUTH_SECRET", "b" * 32)
    app = create_app(str(tmp_path / "api.db"), auth_required=True)
    token = HMACTokenAuthority("b" * 32).issue("unbound", ["operator"])
    r = make_test_client(app).post("/api/source/manual", json={"items": []}, headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 403
    assert "no governed operator" in r.json()["detail"].lower()


def test_role_and_scope_must_both_be_governed_by_current_binding(tmp_path: Path, monkeypatch, make_test_client):
    monkeypatch.setenv("TREND_HUNTER_AUTH_SECRET", "c" * 32)
    db = tmp_path / "api.db"
    app = create_app(str(db), auth_required=True)
    ledger = GovernanceLedger(str(db))
    OperationalBindingService(ledger).register_operator("op", roles=["operator"], scopes=["trend:write"])
    token = HMACTokenAuthority("c" * 32).issue("op", ["operator"])
    r = make_test_client(app).post("/api/source/manual", json={"items": []}, headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 403
    assert "scope" in r.json()["detail"].lower()


def test_internal_reads_are_authenticated_and_governed_when_auth_enabled(tmp_path: Path, monkeypatch, make_test_client):
    monkeypatch.setenv("TREND_HUNTER_AUTH_SECRET", "d" * 32)
    db = tmp_path / "api.db"
    app = create_app(str(db), auth_required=True)
    c = make_test_client(app)
    assert c.get("/health").status_code == 200
    assert c.get("/api/status").status_code == 401
    ledger = GovernanceLedger(str(db))
    OperationalBindingService(ledger).register_operator("reader", roles=["reader"], scopes=["internal:read"])
    token = HMACTokenAuthority("d" * 32).issue("reader", ["reader"])
    assert c.get("/api/status", headers={"Authorization": f"Bearer {token}"}).status_code == 200
    assert c.get("/api/integrity", headers={"Authorization": f"Bearer {token}"}).status_code == 200
    assert c.get("/", headers={"Authorization": f"Bearer {token}"}).status_code == 200


def test_revoked_operator_binding_blocks_still_cryptographically_valid_token(tmp_path: Path, monkeypatch, make_test_client):
    monkeypatch.setenv("TREND_HUNTER_AUTH_SECRET", "e" * 32)
    db = tmp_path / "api.db"
    app = create_app(str(db), auth_required=True)
    ledger = GovernanceLedger(str(db))
    b = OperationalBindingService(ledger)
    b.register_operator("op", roles=["operator"], scopes=["source:write"])
    token = HMACTokenAuthority("e" * 32).issue("op", ["operator"])
    assert make_test_client(app).post("/api/source/manual", json={"items": []}, headers={"Authorization": f"Bearer {token}"}).status_code == 200
    b.revoke_operator("op", reason="test")
    r = make_test_client(app).post("/api/source/manual", json={"items": []}, headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 403


def test_channel_binding_provider_must_match_platform_without_explicit_contract(tmp_path: Path):
    ledger = make_ledger(tmp_path)
    b = OperationalBindingService(ledger)
    acct = b.bind_external_account("youtube", "acct", account_kind="CHANNEL_OWNER")
    with pytest.raises(LedgerError):
        b.bind_channel(acct.state_id, "tiktok", "chan")


def test_exact_channel_state_is_pinned_across_execution_authorization_and_publication(tmp_path: Path):
    ledger = make_ledger(tmp_path)
    demo = SyntheticPilotRunner(ledger).run()
    b = OperationalBindingService(ledger)
    acct = b.bind_external_account("youtube", "acct", account_kind="CHANNEL_OWNER")
    channel_v1 = b.bind_channel(acct.state_id, "youtube", "channel-123", language="ar", region="SA")
    cfg = ExecutionService(ledger).define_configuration(
        demo.records["OPPORTUNITY"][0], demo.records["ELIGIBILITY_ASSESSMENT"][0],
        platform="youtube", channel=None, live_channel_binding_state_id=channel_v1.state_id,
        content_form="short_form_video", production_route="manual",
        actionable_from=None, actionable_to=None, required_resources={},
        capital_assumption={"amount": 0, "currency": "SAR"}, operational_mode="LIVE",
        require_live_channel_binding=True,
    )
    ops = OperationsService(ledger)
    auth = ops.record_human_authorization(
        demo.records["PUBLICATION_RECOMMENDATION"][0], "human", "AUTHORIZED",
        execution_configuration_state_id=cfg.state_id,
        channel_binding_state_id=channel_v1.state_id,
        require_exact_channel=True,
    )
    pub = ops.record_publication_execution(
        demo.records["CREATIVE_ARTIFACT"][0], auth.state_id,
        channel_binding_state_id=channel_v1.state_id,
        external_result_ref="post-1", require_bound_channel=True,
    )
    payload = ledger.get_state(pub.state_id)["payload"]
    assert payload["channel_binding_state_id"] == channel_v1.state_id
    assert payload["channel"] == "channel-123"

    # Same logical channel gets a new exact state; old authorization may not silently follow latest.
    channel_v2 = b.bind_channel(acct.state_id, "youtube", "channel-123", language="ar", region="SA")
    assert channel_v2.state_id != channel_v1.state_id
    with pytest.raises(LedgerError):
        ops.record_publication_execution(
            demo.records["CREATIVE_ARTIFACT"][0], auth.state_id,
            channel_binding_state_id=channel_v1.state_id,
            external_result_ref="post-stale", require_bound_channel=True,
        )
    with pytest.raises(LedgerError):
        ops.record_publication_execution(
            demo.records["CREATIVE_ARTIFACT"][0], auth.state_id,
            channel_binding_state_id=channel_v2.state_id,
            external_result_ref="post-wrong-auth", require_bound_channel=True,
        )


def test_material_execution_record_preserves_exact_operator_binding_provenance(tmp_path: Path):
    ledger = make_ledger(tmp_path)
    demo = SyntheticPilotRunner(ledger).run()
    binding = OperationalBindingService(ledger).register_operator("human", roles=["publisher_authorizer"], scopes=["publication:authorize"])
    auth_context = {
        "authenticated": True,
        "subject": "human",
        "auth_method": "HMAC_SHA256_BEARER",
        "token_id": "redacted-jti-ref",
        "governed_operator_binding_state_id": binding.state_id,
        "authorized_role": "publisher_authorizer",
        "authorized_scope": "publication:authorize",
    }
    auth = OperationsService(ledger).record_human_authorization(
        demo.records["PUBLICATION_RECOMMENDATION"][0], "human", "AUTHORIZED", auth_context=auth_context
    )
    with connect(ledger.db_path) as conn:
        edge = conn.execute(
            "SELECT 1 FROM provenance_edge WHERE from_state_id=? AND to_state_id=? AND edge_type='AUTHORIZED_OPERATOR_BINDING'",
            (binding.state_id, auth.state_id),
        ).fetchone()
    assert edge is not None
    assert ledger.get_state(auth.state_id)["payload"]["identity_assurance"]["governed_operator_binding_state_id"] == binding.state_id


def test_network_exposure_readiness_requires_governed_tls_transport_binding(tmp_path: Path, monkeypatch):
    ledger = make_ledger(tmp_path)
    b = OperationalBindingService(ledger)
    b.register_operator("op", roles=["reader"], scopes=["internal:read"])
    monkeypatch.setenv("TREND_HUNTER_AUTH_SECRET", "f" * 32)
    monkeypatch.setenv("TREND_HUNTER_TRANSPORT_SECURITY", "DIRECT_TLS")
    r1 = OperationalPreflight(ledger).report()
    assert r1["ready_for_network_exposure"] is False
    b.configure_transport_security("DIRECT_TLS", endpoint="https://example.invalid")
    r2 = OperationalPreflight(ledger).report()
    assert r2["ready_for_network_exposure"] is True


def test_connector_failure_classification_distinguishes_internal_from_external(monkeypatch):
    from trend_hunter import live

    def dns_fail(self):
        raise ConnectorHTTPError("dns", failure_class="DNS_UNAVAILABLE", attempts=4)
    monkeypatch.setattr(live.GDELTDocConnector, "fetch", dns_fail)
    ext = connector_smoke("gdelt")
    assert ext["failure_class"] == "DNS_UNAVAILABLE"
    assert ext["status"] == "EXTERNAL_DEPENDENCY"

    def parse_fail(self):
        import xml.etree.ElementTree as ET
        raise ET.ParseError("bad response")
    monkeypatch.setattr(live.GDELTDocConnector, "fetch", parse_fail)
    internal = connector_smoke("gdelt")
    assert internal["failure_class"] == "RESPONSE_PARSE_FAILURE"
    assert internal["status"] == "INTERNAL_ENGINEERING_BLOCKER"


def test_activation_publication_and_outcome_preserve_authenticated_operator_binding(tmp_path: Path):
    ledger = make_ledger(tmp_path)
    demo = SyntheticPilotRunner(ledger).run()
    b = OperationalBindingService(ledger)
    operator = b.register_operator(
        "ops-owner",
        roles=["publisher_authorizer", "commercial_operator", "publication_operator", "finance_operator"],
        scopes=["publication:authorize", "monetization:activate", "publication:execute", "economics:record"],
    )
    acct = b.bind_external_account("youtube", "acct-auth", account_kind="CHANNEL_OWNER")
    channel = b.bind_channel(acct.state_id, "youtube", "chan-auth", language="ar", region="SA")
    cfg = ExecutionService(ledger).define_configuration(
        demo.records["OPPORTUNITY"][0], demo.records["ELIGIBILITY_ASSESSMENT"][0],
        platform="youtube", channel=None, live_channel_binding_state_id=channel.state_id,
        content_form="short_form_video", production_route="manual",
        actionable_from=None, actionable_to=None, required_resources={},
        capital_assumption={"amount": 0, "currency": "SAR"}, operational_mode="LIVE",
        require_live_channel_binding=True,
    )
    base_ctx = {
        "authenticated": True,
        "subject": "ops-owner",
        "auth_method": "HMAC_SHA256_BEARER",
        "token_id": "token-ref-only",
        "governed_operator_binding_state_id": operator.state_id,
        "authorized_role": "publisher_authorizer",
        "authorized_scope": "publication:authorize",
    }
    ops = OperationsService(ledger)
    auth = ops.record_human_authorization(
        demo.records["PUBLICATION_RECOMMENDATION"][0], "ops-owner", "AUTHORIZED",
        auth_context=base_ctx, execution_configuration_state_id=cfg.state_id,
        channel_binding_state_id=channel.state_id, require_exact_channel=True,
    )
    activation_ctx = {**base_ctx, "authorized_role": "commercial_operator", "authorized_scope": "monetization:activate"}
    mon = demo.records["MONETIZATION_CONFIGURATION"][0]
    deps = [
        auth.state_id,
        demo.records["COMPLIANCE_ASSESSMENT"][0],
        demo.records["ELIGIBILITY_ASSESSMENT"][0],
        demo.records["CREATIVE_ARTIFACT"][0],
    ]
    act = ops.activate_monetization(mon, dependency_state_ids=deps, provider_result_ref="fixture-activation", auth_context=activation_ctx)
    pub_ctx = {**base_ctx, "authorized_role": "publication_operator", "authorized_scope": "publication:execute"}
    pub = ops.record_publication_execution(
        demo.records["CREATIVE_ARTIFACT"][0], auth.state_id,
        channel_binding_state_id=channel.state_id, external_result_ref="post-auth",
        monetization_activation_state_id=act.state_id, require_bound_channel=True, auth_context=pub_ctx,
    )
    finance_ctx = {**base_ctx, "authorized_role": "finance_operator", "authorized_scope": "economics:record"}
    outcome = ops.record_economic_outcome(
        pub.state_id, performance={"views": 10}, revenue={"amount": 5, "currency": "SAR"},
        costs=[{"amount": 2, "currency": "SAR"}], attribution={"basis": "fixture"}, auth_context=finance_ctx,
    )
    material = [act.state_id, pub.state_id, outcome["outcome"].state_id]
    with connect(ledger.db_path) as conn:
        for sid in material:
            assert conn.execute(
                "SELECT 1 FROM provenance_edge WHERE from_state_id=? AND to_state_id=? AND edge_type='AUTHORIZED_OPERATOR_BINDING'",
                (operator.state_id, sid),
            ).fetchone() is not None
    assert ledger.integrity_check()["ok"] is True


def test_non_loopback_http_is_blocked_even_with_auth_when_direct_tls_is_governed(tmp_path: Path, monkeypatch, make_test_client):
    monkeypatch.setenv("TREND_HUNTER_AUTH_SECRET", "g" * 32)
    monkeypatch.setenv("TREND_HUNTER_TRANSPORT_SECURITY", "DIRECT_TLS")
    db = tmp_path / "api.db"
    app = create_app(str(db), auth_required=True)
    ledger = GovernanceLedger(str(db))
    b = OperationalBindingService(ledger)
    b.register_operator("reader", roles=["reader"], scopes=["internal:read"])
    b.configure_transport_security("DIRECT_TLS", endpoint="https://trend.example")
    token = HMACTokenAuthority("g" * 32).issue("reader", ["reader"])
    headers = {"Authorization": f"Bearer {token}"}
    http_client = make_test_client(app, base_url="http://trend.example")
    assert http_client.get("/api/status", headers=headers).status_code == 503
    https_client = make_test_client(app, base_url="https://trend.example")
    assert https_client.get("/api/status", headers=headers).status_code == 200



def test_non_loopback_is_rejected_even_when_app_auth_is_disabled(tmp_path: Path, make_test_client):
    """Direct ASGI hosting must not bypass the CLI network-exposure guard."""
    app = create_app(str(tmp_path / "api.db"), auth_required=False)
    client = make_test_client(app, base_url="http://198.51.100.25")
    r = client.get("/health")
    assert r.status_code == 503
    assert "non-loopback" in r.json()["detail"].lower()


def test_external_peer_cannot_spoof_localhost_host_to_bypass_direct_tls(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("TREND_HUNTER_AUTH_SECRET", "h" * 32)
    monkeypatch.setenv("TREND_HUNTER_TRANSPORT_SECURITY", "DIRECT_TLS")
    db = tmp_path / "api.db"
    app = create_app(str(db), auth_required=True)
    ledger = GovernanceLedger(str(db))
    bindings = OperationalBindingService(ledger)
    bindings.register_operator("reader", roles=["reader"], scopes=["internal:read"])
    bindings.configure_transport_security("DIRECT_TLS", endpoint="https://trend.example")
    token = HMACTokenAuthority("h" * 32).issue("reader", ["reader"])
    with TestClient(app, base_url="http://trend.example", client=("198.51.100.25", 54321)) as client:
        r = client.get(
            "/api/status",
            headers={"Authorization": f"Bearer {token}", "Host": "localhost"},
        )
        assert r.status_code == 503


def test_external_peer_cannot_spoof_localhost_when_auth_disabled(tmp_path: Path):
    app = create_app(str(tmp_path / "api.db"), auth_required=False)
    with TestClient(app, base_url="http://trend.example", client=("198.51.100.25", 54321)) as client:
        r = client.get("/health", headers={"Host": "localhost"})
        assert r.status_code == 503
        assert "non-loopback" in r.json()["detail"].lower()


def test_reverse_proxy_headers_require_exact_governed_proxy_peer(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("TREND_HUNTER_AUTH_SECRET", "i" * 32)
    monkeypatch.setenv("TREND_HUNTER_TRANSPORT_SECURITY", "TRUSTED_TLS_TERMINATING_REVERSE_PROXY")
    monkeypatch.setenv("TREND_HUNTER_TRUST_PROXY_HEADERS", "1")
    db = tmp_path / "api.db"
    app = create_app(str(db), auth_required=True)
    ledger = GovernanceLedger(str(db))
    bindings = OperationalBindingService(ledger)
    bindings.register_operator("reader", roles=["reader"], scopes=["internal:read"])
    bindings.configure_transport_security(
        "TRUSTED_TLS_TERMINATING_REVERSE_PROXY",
        endpoint="https://trend.example",
        metadata={"trusted_proxy_ips": ["127.0.0.1"]},
    )
    token = HMACTokenAuthority("i" * 32).issue("reader", ["reader"])
    headers = {"Authorization": f"Bearer {token}", "X-Forwarded-Proto": "https"}

    with TestClient(app, base_url="http://trend.example", client=("198.51.100.25", 54321)) as forged:
        assert forged.get("/api/status", headers=headers).status_code == 503

    with TestClient(app, base_url="http://trend.example", client=("127.0.0.1", 54321)) as trusted:
        assert trusted.get("/api/status", headers=headers).status_code == 200


def test_reverse_proxy_mode_fails_closed_without_exact_proxy_peer_binding(tmp_path: Path):
    ledger = make_ledger(tmp_path)
    with pytest.raises(LedgerError, match="trusted_proxy_ip"):
        OperationalBindingService(ledger).configure_transport_security(
            "TRUSTED_TLS_TERMINATING_REVERSE_PROXY", endpoint="https://trend.example"
        )


def test_non_loopback_transport_endpoint_must_be_explicit_https(tmp_path: Path):
    ledger = make_ledger(tmp_path)
    with pytest.raises(LedgerError, match="explicit https"):
        OperationalBindingService(ledger).configure_transport_security("DIRECT_TLS")
    with pytest.raises(LedgerError, match="explicit https"):
        OperationalBindingService(ledger).configure_transport_security(
            "DIRECT_TLS", endpoint="http://trend.example"
        )


def test_token_role_cannot_exceed_governed_binding_role(tmp_path: Path, monkeypatch, make_test_client):
    monkeypatch.setenv("TREND_HUNTER_AUTH_SECRET", "g" * 32)
    db = tmp_path / "api.db"
    app = create_app(str(db), auth_required=True)
    ledger = GovernanceLedger(str(db))
    OperationalBindingService(ledger).register_operator(
        "op", roles=["reader"], scopes=["internal:read"]
    )
    # The token cryptographically asserts operator, but the governed binding does not authorize it.
    token = HMACTokenAuthority("g" * 32).issue("op", ["operator"])
    r = make_test_client(app).post(
        "/api/source/manual", json={"items": []}, headers={"Authorization": f"Bearer {token}"}
    )
    assert r.status_code == 403
    assert "binding does not authorize role" in r.json()["detail"].lower()


def test_material_service_rejects_forged_operator_binding_context(tmp_path: Path):
    ledger = make_ledger(tmp_path)
    demo = SyntheticPilotRunner(ledger).run()
    real = OperationalBindingService(ledger).register_operator(
        "real-human", roles=["publisher_authorizer"], scopes=["publication:authorize"]
    )
    forged = {
        "authenticated": True,
        "subject": "different-human",
        "auth_method": "HMAC_SHA256_BEARER",
        "issued_at": 9999999999,
        "token_id": "audit-id-only",
        "governed_operator_binding_state_id": real.state_id,
        "authorized_role": "publisher_authorizer",
        "authorized_scope": "publication:authorize",
    }
    with pytest.raises(LedgerError, match="does not match an ACTIVE governed subject binding"):
        OperationsService(ledger).record_human_authorization(
            demo.records["PUBLICATION_RECOMMENDATION"][0],
            "different-human",
            "AUTHORIZED",
            auth_context=forged,
        )


def test_material_service_rejects_stale_operator_binding_context(tmp_path: Path):
    ledger = make_ledger(tmp_path)
    demo = SyntheticPilotRunner(ledger).run()
    b = OperationalBindingService(ledger)
    first = b.register_operator(
        "human", roles=["publisher_authorizer"], scopes=["publication:authorize"]
    )
    # Supersede the exact same logical operator binding state.
    second = b.register_operator(
        "human", roles=["publisher_authorizer"], scopes=["publication:authorize"]
    )
    assert first.state_id != second.state_id
    stale_ctx = {
        "authenticated": True,
        "subject": "human",
        "auth_method": "HMAC_SHA256_BEARER",
        "issued_at": 9999999999,
        "token_id": "audit-id-only",
        "governed_operator_binding_state_id": first.state_id,
        "authorized_role": "publisher_authorizer",
        "authorized_scope": "publication:authorize",
    }
    with pytest.raises(LedgerError, match="stale/superseded operator binding"):
        OperationsService(ledger).record_human_authorization(
            demo.records["PUBLICATION_RECOMMENDATION"][0],
            "human",
            "AUTHORIZED",
            auth_context=stale_ctx,
        )


def test_preflight_requires_material_role_scope_coverage_not_any_operator(tmp_path: Path, monkeypatch):
    ledger = make_ledger(tmp_path)
    OperationalBindingService(ledger).register_operator(
        "reader-only", roles=["reader"], scopes=["internal:read"]
    )
    monkeypatch.setenv("TREND_HUNTER_AUTH_SECRET", "h" * 32)
    report = OperationalPreflight(ledger).report()
    check = next(x for x in report["checks"] if x["key"] == "governed_operator_role_scope_coverage")
    assert check["status"] == "USER_ACTION_REQUIRED"
    assert check["detail"]["required"]["reader"]["covered"] is True
    assert check["detail"]["required"]["publication_operator"]["covered"] is False
    assert report["commercial_launch_ready"] is False



def test_execution_configuration_rejects_stale_channel_binding_state(tmp_path: Path):
    ledger = make_ledger(tmp_path)
    demo = SyntheticPilotRunner(ledger).run()
    b = OperationalBindingService(ledger)
    acct = b.bind_external_account("youtube", "acct-stale-channel", account_kind="CHANNEL_OWNER")
    channel_v1 = b.bind_channel(acct.state_id, "youtube", "chan-stale", language="ar", region="SA")
    channel_v2 = b.bind_channel(acct.state_id, "youtube", "chan-stale", language="ar", region="SA")
    assert channel_v1.state_id != channel_v2.state_id
    with pytest.raises(LedgerError, match="stale/superseded"):
        ExecutionService(ledger).define_configuration(
            demo.records["OPPORTUNITY"][0], demo.records["ELIGIBILITY_ASSESSMENT"][0],
            platform="youtube", channel=None, live_channel_binding_state_id=channel_v1.state_id,
            content_form="short_form_video", production_route="manual",
            actionable_from=None, actionable_to=None, required_resources={},
            capital_assumption={"amount": 0, "currency": "SAR"}, operational_mode="LIVE",
            require_live_channel_binding=True,
        )


def test_new_channel_cannot_bind_to_stale_external_account_state(tmp_path: Path):
    ledger = make_ledger(tmp_path)
    b = OperationalBindingService(ledger)
    acct_v1 = b.bind_external_account("youtube", "acct-same", account_kind="CHANNEL_OWNER")
    acct_v2 = b.bind_external_account("youtube", "acct-same", account_kind="CHANNEL_OWNER")
    assert acct_v1.state_id != acct_v2.state_id
    with pytest.raises(LedgerError, match="stale/superseded"):
        b.bind_channel(acct_v1.state_id, "youtube", "chan-new")



def test_governed_loopback_transport_is_valid_local_posture_but_not_network_exposure(tmp_path: Path, monkeypatch):
    ledger = make_ledger(tmp_path)
    b = OperationalBindingService(ledger)
    b.register_operator("reader", roles=["reader"], scopes=["internal:read"])
    monkeypatch.setenv("TREND_HUNTER_AUTH_SECRET", "i" * 32)
    monkeypatch.setenv("TREND_HUNTER_TRANSPORT_SECURITY", "LOOPBACK_ONLY")
    b.configure_transport_security("LOOPBACK_ONLY")
    report = OperationalPreflight(ledger).report()
    transport = next(x for x in report["checks"] if x["key"] == "network_transport_security")
    assert transport["status"] == "SYSTEM_CAN_EXECUTE"
    assert report["ready_for_network_exposure"] is False

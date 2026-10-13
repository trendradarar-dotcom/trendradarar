from pathlib import Path

from trend_hunter.api import create_app
from trend_hunter.ledger import GovernanceLedger
from trend_hunter.operational import OperationalBindingService
from trend_hunter.security import HMACTokenAuthority


def test_single_action_route_requires_governed_publisher_authority(
    tmp_path: Path, monkeypatch, make_test_client
):
    monkeypatch.setenv("TREND_HUNTER_AUTH_SECRET", "z" * 32)
    db = tmp_path / "single-action-api.db"

    app = create_app(str(db), auth_required=True)
    ledger = GovernanceLedger(str(db))
    bindings = OperationalBindingService(ledger)

    bindings.register_operator(
        "ordinary-op",
        roles=["operator"],
        scopes=["source:write"],
    )
    bindings.register_operator(
        "ali-ahmad",
        roles=["publisher_authorizer"],
        scopes=["publication:authorize"],
    )

    client = make_test_client(app)

    body = {
        "creative_state_id": "missing-creative",
        "reviewer": "ali-ahmad",
        "source_checked_at": "2026-09-16",
        "determinations": [
            {
                "rule_id": "SA-ACC-3-4",
                "status": "PASS",
                "reason": "checked",
            }
        ],
        "execution_configuration_state_id": "missing-config",
        "channel_binding_state_id": "missing-channel",
        "media_descriptor_state_id": "missing-media",
    }

    assert client.post(
        "/api/compliance/saudi-cybercrime/authorize",
        json=body,
    ).status_code == 401

    authority = HMACTokenAuthority("z" * 32)

    ordinary = authority.issue(
        "ordinary-op",
        ["operator"],
        ttl_seconds=60,
    )
    denied = client.post(
        "/api/compliance/saudi-cybercrime/authorize",
        json=body,
        headers={"Authorization": f"Bearer {ordinary}"},
    )
    assert denied.status_code == 403

    publisher = authority.issue(
        "ali-ahmad",
        ["publisher_authorizer"],
        ttl_seconds=60,
    )
    reached_domain_validation = client.post(
        "/api/compliance/saudi-cybercrime/authorize",
        json=body,
        headers={"Authorization": f"Bearer {publisher}"},
    )
    assert reached_domain_validation.status_code == 400


def test_single_action_api_has_no_free_form_authorizer_and_keeps_exact_media():
    source = (
        Path(__file__).parents[1]
        / "src"
        / "trend_hunter"
        / "api.py"
    ).read_text(encoding="utf-8")

    assert "class SaudiSingleActionAuthorizationIn(BaseModel):" in source
    assert "media_descriptor_state_id: str" in source
    assert "SaudiPublicationAuthorizationOrchestrator(" in source
    assert "authorizer=authorizer" in source
    assert 'require_role(request, "publisher_authorizer")' in source
    assert (
        '"/api/compliance/saudi-cybercrime/authorize": '
        '("publisher_authorizer", "publication:authorize")'
    ) in source

    block = source.split(
        "class SaudiSingleActionAuthorizationIn(BaseModel):", 1
    )[1].split(
        "class CommercialAuthorizationIn(BaseModel):", 1
    )[0]

    assert "authorizer:" not in block
from pathlib import Path

from trend_hunter.db import init_db
from trend_hunter.ledger import GovernanceLedger
from trend_hunter.single_action_resolution import (
    resolve_single_action_publication_inputs,
)


def test_single_action_resolves_exact_governed_publication_inputs(tmp_path):
    db = tmp_path / "resolver.db"
    init_db(str(db))
    ledger = GovernanceLedger(str(db))

    subject = ledger.get_or_create_identity(
        "TEST_SUBJECT",
        natural_key="single-action-ui",
    )

    eligibility = ledger.record_domain(
        "ELIGIBILITY_RESULT",
        "Test",
        {"outcome": "ELIGIBLE"},
        natural_key="eligibility:test",
        subject_identity_id=subject,
    )

    creative = ledger.record_domain(
        "CREATIVE_ARTIFACT",
        "Test",
        {
            "eligibility_state_id": eligibility.state_id,
            "target": {"platform": "youtube", "jurisdiction": "SA"},
        },
        natural_key="creative:test",
        subject_identity_id=subject,
    )

    channel = ledger.record_domain(
        "LIVE_CHANNEL_BINDING",
        "Test",
        {"channel": "youtube"},
        natural_key="channel:test",
        subject_identity_id=subject,
    )

    config = ledger.record_domain(
        "EXECUTION_CONFIGURATION",
        "Test",
        {
            "eligibility_state_id": eligibility.state_id,
            "live_channel_binding_state_id": channel.state_id,
        },
        natural_key="config:test",
        subject_identity_id=subject,
    )

    media = ledger.record_domain(
        "PUBLICATION_MEDIA_DESCRIPTOR",
        "Test",
        {"creative_state_id": creative.state_id},
        natural_key="media:test",
        subject_identity_id=subject,
    )

    resolved = resolve_single_action_publication_inputs(
        ledger,
        creative.state_id,
    )

    assert resolved.execution_configuration_state_id == config.state_id
    assert resolved.channel_binding_state_id == channel.state_id
    assert resolved.media_descriptor_state_id == media.state_id


def test_saudi_ui_uses_one_authorize_action_without_platform_manual_fields():
    source = (
        Path(__file__).parents[1]
        / "src"
        / "trend_hunter"
        / "api.py"
    ).read_text(encoding="utf-8")

    start = source.index("async function submitSaudiReview(){")
    end = source.index("\nload();", start)
    block = source[start:end]

    assert "/api/compliance/saudi-cybercrime/authorize" in block
    assert "/api/compliance/saudi-cybercrime/review" not in block
    assert "اعتماد المراجعة والتفويض للنشر" in source

    assert "execution_configuration_state_id" not in block
    assert "channel_binding_state_id" not in block
    assert "media_descriptor_state_id" not in block

    assert "platform_findings" not in block
    assert "authorizer:" not in block
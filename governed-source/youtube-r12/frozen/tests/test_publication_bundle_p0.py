from __future__ import annotations

from pathlib import Path

from trend_hunter.bootstrap import bootstrap_governance
from trend_hunter.db import init_db
from trend_hunter.ledger import GovernanceLedger
from trend_hunter.operational import OperationalBindingService
from trend_hunter.publication_bundle import PublicationBundlePreparationService
from trend_hunter.single_action_resolution import resolve_single_action_publication_inputs


def _build(tmp_path: Path):
    db = tmp_path / "data" / "trend_hunter.db"
    db.parent.mkdir(parents=True, exist_ok=True)
    init_db(str(db))
    ledger = GovernanceLedger(str(db))
    bootstrap_governance(ledger)

    subject = ledger.get_or_create_identity("OPPORTUNITY_SUBJECT", "p0-subject")
    opportunity = ledger.record_domain(
        "OPPORTUNITY",
        "Test",
        {"candidate_key": "p0"},
        natural_key="p0:opportunity",
        subject_identity_id=subject,
        record_state="CANDIDATE",
    )
    eligibility = ledger.record_domain(
        "ELIGIBILITY_ASSESSMENT",
        "Test",
        {
            "opportunity_state_id": opportunity.state_id,
            "outcome": "ELIGIBLE",
            "target": {"platform": "youtube"},
        },
        natural_key="p0:eligibility",
        subject_identity_id=subject,
        record_state="ELIGIBLE",
        upstream_states=[(opportunity.state_id, "ELIGIBILITY_TARGET")],
    )
    creative = ledger.record_domain(
        "CREATIVE_ARTIFACT",
        "Test",
        {
            "eligibility_state_id": eligibility.state_id,
            "target": {
                "global_publication_v1": True,
                "target_schema_version": "GLOBAL_PUBLICATION_TARGET_V1",
                "source_language": "tr",
                "publication_language": "ar",
                "target_market": "SA",
                "jurisdiction": "SA",
                "platform": "youtube",
            },
            "title": "اختبار الفيديو الحقيقي",
            "hook": "افتتاحية",
            "body": "هذا نص عربي تجريبي لإنشاء فيديو محلي محكوم وربطه بالبصمة قبل التفويض.",
            "description": "وصف",
            "hashtags": ["#اختبار"],
            "cta": "شارك رأيك",
            "content_format": "short_form_video",
        },
        natural_key="p0:creative",
        subject_identity_id=subject,
        record_state="DRAFTED",
        upstream_states=[(eligibility.state_id, "CREATIVE_ELIGIBILITY_GATE")],
    )

    bindings = OperationalBindingService(ledger)
    account = bindings.bind_external_account("youtube", "acct-p0", account_kind="channel")
    # The channel intentionally has its own operational subject identity.
    channel = bindings.bind_channel(account.state_id, "youtube", "UC_P0", language="ar", region="SA")
    assert ledger.subject_identity_for_state(channel.state_id) != subject
    return ledger, creative, eligibility, channel


def test_p0_prepares_exact_bundle_with_operational_channel_subject(tmp_path: Path):
    ledger, creative, eligibility, channel = _build(tmp_path)
    svc = PublicationBundlePreparationService(ledger, project_root=tmp_path)
    result = svc.prepare(creative.state_id)

    assert result.eligibility_state_id == eligibility.state_id
    assert result.channel_binding_state_id == channel.state_id
    assert Path(result.media_path).is_file()
    assert Path(result.media_path).stat().st_size > 0

    resolved = resolve_single_action_publication_inputs(ledger, creative.state_id)
    assert resolved.execution_configuration_state_id == result.execution_configuration_state_id
    assert resolved.channel_binding_state_id == channel.state_id
    assert resolved.media_descriptor_state_id == result.media_descriptor_state_id


def test_p0_prepare_is_idempotent_for_unchanged_exact_bundle(tmp_path: Path):
    ledger, creative, _, _ = _build(tmp_path)
    svc = PublicationBundlePreparationService(ledger, project_root=tmp_path)
    first = svc.prepare(creative.state_id)
    second = svc.prepare(creative.state_id)
    assert second.execution_configuration_state_id == first.execution_configuration_state_id
    assert second.channel_binding_state_id == first.channel_binding_state_id
    assert second.media_descriptor_state_id == first.media_descriptor_state_id
    assert second.media_path == first.media_path


def test_arabic_renderer_falls_back_when_raqm_is_unavailable(tmp_path, monkeypatch):
    from trend_hunter import media_renderer

    monkeypatch.setattr(media_renderer, "_raqm_available", lambda: False)
    out = tmp_path / "arabic-fallback.png"
    media_renderer._slide_png(
        out,
        title="اختبار عربي",
        body="هذا نص عربي للتحقق من التشكيل والاتجاه دون libraqm",
        footer="youtube · ar · SA",
        width=720,
        height=1280,
    )
    assert out.is_file()
    assert out.stat().st_size > 0

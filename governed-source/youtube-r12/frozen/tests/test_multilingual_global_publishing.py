from __future__ import annotations

import inspect
import pytest

from trend_hunter.publishing_target import (
    APPROVED_PUBLICATION_LANGUAGES,
    PublicationTargetError,
    build_publication_target,
    candidate_language_targets,
    normalize_publication_target,
)
from trend_hunter.creative import CreativeService
from trend_hunter.compliance import ComplianceService


def test_approved_languages_exact_contract():
    assert APPROVED_PUBLICATION_LANGUAGES == (
        "ar", "en", "fr", "hi", "zh-Hans", "es"
    )


def test_any_source_language_can_generate_all_approved_publication_languages():
    targets = candidate_language_targets(
        source_language="ko",
        platform="youtube",
        discovery_market="KR",
    )
    assert {x["publication_language"] for x in targets} == set(APPROVED_PUBLICATION_LANGUAGES)
    assert {x["source_language"] for x in targets} == {"ko"}
    assert {x["discovery_market"] for x in targets} == {"KR"}


def test_saudi_review_is_jurisdiction_bound_not_language_bound():
    french_for_saudi = build_publication_target(
        source_language="ja",
        publication_language="fr",
        target_market="SA",
        jurisdiction="SA",
        platform="youtube",
    )
    arabic_global = build_publication_target(
        source_language="ko",
        publication_language="ar",
        target_market="GLOBAL",
        jurisdiction="GLOBAL",
        platform="youtube",
    )
    assert french_for_saudi["saudi_legal_review_required"] is True
    assert arabic_global["saudi_legal_review_required"] is False


def test_legacy_target_with_existing_jurisdiction_and_platform_is_preserved():
    legacy = {"jurisdiction": "US", "platform": "youtube"}
    assert normalize_publication_target(legacy) == legacy


def test_global_target_fails_closed_for_unapproved_publication_language():
    with pytest.raises(PublicationTargetError):
        build_publication_target(
            source_language="de",
            publication_language="de",
            target_market="GLOBAL",
            jurisdiction="GLOBAL",
            platform="youtube",
        )


def test_creative_and_compliance_share_same_target_normalizer():
    creative_src = inspect.getsource(CreativeService.create)
    compliance_src = inspect.getsource(ComplianceService.assess)
    assert "normalize_publication_target(target)" in creative_src
    assert "normalize_publication_target(target)" in compliance_src

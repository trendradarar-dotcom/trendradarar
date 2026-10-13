from __future__ import annotations

import pytest

from trend_hunter.platform_policy import (
    PLATFORM_POLICY_CATALOG_VERSION,
    PLATFORM_POLICY_RULES,
    platform_findings_for_review,
    platform_policy_rules,
    supported_platforms,
)


def test_supported_platforms_are_exact():
    assert supported_platforms() == ("instagram", "snapchat", "tiktok", "youtube")


@pytest.mark.parametrize("platform", ["youtube", "tiktok", "instagram", "snapchat"])
def test_catalog_is_nonempty_and_unique(platform):
    rules = platform_policy_rules(platform)
    assert rules
    ids = [r["rule_id"] for r in rules]
    assert len(ids) == len(set(ids))
    for rule in rules:
        assert rule["title"]
        assert rule["review_prompt"]
        assert rule["source_url"].startswith("https://")
        assert rule["source_kind"] == "OFFICIAL_PLATFORM_POLICY"
        assert rule["catalog_version"] == PLATFORM_POLICY_CATALOG_VERSION


@pytest.mark.parametrize("platform", ["youtube", "tiktok", "instagram", "snapchat"])
def test_review_findings_never_auto_pass(platform):
    findings = platform_findings_for_review(platform)
    assert findings
    for finding in findings:
        assert finding["status"] == "UNRESOLVED"
        assert finding["reason"]
        assert finding["evidence_state_ids"] == []


def test_result_is_defensive_copy():
    first = platform_policy_rules("youtube")
    first[0]["title"] = "mutated"
    second = platform_policy_rules("youtube")
    assert second[0]["title"] != "mutated"


def test_unknown_platform_fails_closed():
    with pytest.raises(ValueError):
        platform_findings_for_review("unknown-platform")


def test_catalog_rule_ids_are_globally_unique():
    ids = [rule["rule_id"] for rules in PLATFORM_POLICY_RULES.values() for rule in rules]
    assert len(ids) == len(set(ids))
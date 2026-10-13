from __future__ import annotations

from typing import Any

from .ledger import GovernanceLedger
from .story import StoryService
from .measurement import TrendMeasurementService
from .opportunity import OpportunityService


def _payload_dict(state: dict[str, Any]) -> dict[str, Any]:
    payload = state.get("payload") or {}
    if not isinstance(payload, dict):
        return {}
    nested = payload.get("payload")
    if isinstance(nested, dict):
        merged = dict(nested)
        merged.update(payload)
        return merged
    return dict(payload)


def _first_text(payload: dict[str, Any], *keys: str) -> str | None:
    for key in keys:
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def _scope(payload: dict[str, Any], source_name: str) -> dict[str, Any]:
    scope: dict[str, Any] = {"source": source_name}
    region = _first_text(payload, "region", "market", "country", "geo")
    language = _first_text(payload, "language", "lang")
    platform = _first_text(payload, "platform", "provider_surface")
    if region:
        scope["region"] = region
    if language:
        scope["language"] = language
    if platform:
        scope["platform"] = platform
    return scope


def promote_source(
    ledger: GovernanceLedger,
    *,
    source_state_id: str,
    signal_state_id: str,
    source_name: str,
):
    source_state = ledger.get_state(source_state_id)
    if source_state.get("state_type") != "SOURCE_RECORD":
        raise ValueError("live promotion requires SOURCE_RECORD")

    payload = _payload_dict(source_state)
    title = _first_text(
        payload,
        "title",
        "trend",
        "query",
        "search_term",
        "topic",
        "name",
    )
    if not title:
        raise ValueError("live promotion requires an observed title/topic")

    observed_at = (
        _first_text(payload, "observed_at", "started", "started_at", "published_at")
        or str(source_state.get("recorded_at") or "")
    )
    scope = _scope(payload, source_name)
    window = {"basis": "SOURCE_OBSERVATION", "observed_at": observed_at}

    story_key = f"live:{source_name}:{source_state_id}"
    story = StoryService(ledger).bind_story(
        story_key,
        [source_state_id],
        basis="AUTOMATED_LIVE_SOURCE_RECORD_BASIS",
        human_reviewed=False,
    )

    measurement = TrendMeasurementService(ledger).measure(
        story.state_id,
        [signal_state_id],
        scope=scope,
        window=window,
    )

    candidate_key = f"live:{source_name}:{source_state_id}"
    thesis = (
        f"Governed live observation for '{title}' warrants downstream opportunity "
        "assessment; no popularity, saturation, profitability, or eligibility "
        "claim is asserted at this stage."
    )
    factor_assertions = {
        "source_state_id": source_state_id,
        "signal_state_id": signal_state_id,
        "trend_measurement_state_id": measurement.state_id,
        "saturation_state": "NOT_ASSESSED_WITHOUT_GOVERNED_BASELINE",
        "observed_title": title,
        "source_name": source_name,
    }

    return OpportunityService(ledger).create_candidate(
        candidate_key,
        story_state_id=story.state_id,
        role_bound_scope=scope,
        thesis=thesis,
        factor_state_ids=[measurement.state_id],
        factor_assertions=factor_assertions,
    )

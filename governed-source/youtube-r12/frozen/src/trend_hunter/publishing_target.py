from __future__ import annotations

from copy import deepcopy
from typing import Any


TARGET_SCHEMA_VERSION = "GLOBAL_PUBLICATION_TARGET_V1"

APPROVED_PUBLICATION_LANGUAGES: tuple[str, ...] = (
    "ar",
    "en",
    "fr",
    "hi",
    "zh-Hans",
    "es",
)

_LANGUAGE_ALIASES = {
    "arabic": "ar",
    "ar-sa": "ar",
    "english": "en",
    "en-us": "en",
    "en-gb": "en",
    "french": "fr",
    "fr-fr": "fr",
    "hindi": "hi",
    "hi-in": "hi",
    "chinese": "zh-Hans",
    "zh": "zh-Hans",
    "zh-cn": "zh-Hans",
    "zh-hans": "zh-Hans",
    "spanish": "es",
    "es-es": "es",
    "es-mx": "es",
}

# Existing historical targets already contain fields such as jurisdiction/platform.
# Only the new publishing contract fields activate strict V1 normalization.
_GLOBAL_TRIGGER_FIELDS = {
    "global_publication_v1",
    "target_schema_version",
    "source_language",
    "publication_language",
    "target_market",
    "discovery_market",
}


class PublicationTargetError(ValueError):
    pass


def canonical_publication_language(value: str) -> str:
    raw = str(value or "").strip()
    if not raw:
        raise PublicationTargetError("publication_language is required")
    if raw in APPROVED_PUBLICATION_LANGUAGES:
        return raw
    alias = _LANGUAGE_ALIASES.get(raw.lower())
    if alias:
        return alias
    raise PublicationTargetError(
        "unsupported publication_language; allowed="
        + ",".join(APPROVED_PUBLICATION_LANGUAGES)
    )


def _iso_or_global(value: Any, field: str) -> str:
    raw = str(value or "").strip().upper()
    if raw == "GLOBAL":
        return raw
    if len(raw) == 2 and raw.isalpha():
        return raw
    raise PublicationTargetError(f"{field} must be ISO alpha-2 or GLOBAL")


def normalize_publication_target(target: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(target, dict):
        raise PublicationTargetError("target must be a dict")

    out = deepcopy(target)

    if not any(key in out for key in _GLOBAL_TRIGGER_FIELDS):
        return out

    source_language = str(out.get("source_language") or "und").strip() or "und"
    publication_language = canonical_publication_language(out.get("publication_language"))
    target_market = _iso_or_global(out.get("target_market"), "target_market")
    jurisdiction = _iso_or_global(out.get("jurisdiction"), "jurisdiction")
    platform = str(out.get("platform") or "").strip().lower()
    if not platform:
        raise PublicationTargetError("platform is required")

    out.update(
        {
            "target_schema_version": TARGET_SCHEMA_VERSION,
            "global_publication_v1": True,
            "source_language": source_language,
            "publication_language": publication_language,
            "target_market": target_market,
            "jurisdiction": jurisdiction,
            "platform": platform,
            "localization_mode": "ADAPTIVE_NOT_LITERAL",
            "source_language_independent_of_publication_language": True,
            "publication_language_independent_of_target_market": True,
            "target_market_independent_of_jurisdiction": True,
            "saudi_legal_review_required": jurisdiction == "SA",
        }
    )
    return out


def build_publication_target(
    *,
    source_language: str | None,
    publication_language: str,
    target_market: str,
    jurisdiction: str,
    platform: str,
    discovery_market: str | None = None,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    target: dict[str, Any] = dict(extra or {})
    target.update(
        {
            "global_publication_v1": True,
            "source_language": str(source_language or "und").strip() or "und",
            "publication_language": publication_language,
            "target_market": target_market,
            "jurisdiction": jurisdiction,
            "platform": platform,
        }
    )
    if discovery_market:
        target["discovery_market"] = str(discovery_market).strip().upper()
    return normalize_publication_target(target)


def candidate_language_targets(
    *,
    source_language: str | None,
    platform: str,
    target_market: str = "GLOBAL",
    jurisdiction: str = "GLOBAL",
    discovery_market: str | None = None,
) -> list[dict[str, Any]]:
    """Generate automatic publication-language candidates independent of source language."""
    return [
        build_publication_target(
            source_language=source_language,
            publication_language=language,
            target_market=target_market,
            jurisdiction=jurisdiction,
            platform=platform,
            discovery_market=discovery_market,
        )
        for language in APPROVED_PUBLICATION_LANGUAGES
    ]

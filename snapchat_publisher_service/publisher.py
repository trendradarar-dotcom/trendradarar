import os
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, Optional
from urllib.parse import urlparse

import requests


AYRSHARE_BASE_URL = "https://api.ayrshare.com/api"
ARAB_MARKETS = {
    "DZ", "BH", "KM", "DJ", "EG", "IQ", "JO", "KW", "LB", "LY", "MR",
    "MA", "OM", "PS", "QA", "SA", "SO", "SD", "SY", "TN", "AE", "YE",
}
GLOBAL_MARKET = "GLOBAL_SELECTED"
ALL_MARKETS = ARAB_MARKETS | {GLOBAL_MARKET}


class PublicationGateClosed(RuntimeError):
    pass


class EnvelopeValidationError(ValueError):
    def __init__(self, errors):
        self.errors = list(errors)
        super().__init__(";".join(self.errors))


@dataclass(frozen=True)
class SpotlightEnvelope:
    market: str
    language: str
    headline: str
    description: str
    media_url: str
    duration_seconds: float
    width: int
    height: int
    originality_passed: bool
    rights_passed: bool
    trend_id: str
    saudi_filter_passed: Optional[bool] = None
    global_selected: Optional[bool] = None

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "SpotlightEnvelope":
        return cls(
            market=str(data.get("market", "")).strip().upper(),
            language=str(data.get("language", "")).strip().lower(),
            headline=str(data.get("headline", "")).strip(),
            description=str(data.get("description", "")).strip(),
            media_url=str(data.get("media_url", "")).strip(),
            duration_seconds=float(data.get("duration_seconds", 0) or 0),
            width=int(data.get("width", 0) or 0),
            height=int(data.get("height", 0) or 0),
            originality_passed=bool(data.get("originality_passed", False)),
            rights_passed=bool(data.get("rights_passed", False)),
            trend_id=str(data.get("trend_id", "")).strip(),
            saudi_filter_passed=data.get("saudi_filter_passed"),
            global_selected=data.get("global_selected"),
        )


def _env_bool(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def validate_envelope(envelope: SpotlightEnvelope):
    errors = []

    if envelope.market not in ALL_MARKETS:
        errors.append("unsupported_market")
    if envelope.language != "ar":
        errors.append("current_activation_requires_arabic")
    if not envelope.trend_id:
        errors.append("trend_id_required")
    if not envelope.headline:
        errors.append("headline_required")
    if len(envelope.description) > 160:
        errors.append("spotlight_description_exceeds_160_characters")

    parsed = urlparse(envelope.media_url)
    if parsed.scheme != "https" or not parsed.netloc:
        errors.append("https_media_url_required")

    # Internal monetization-oriented production target.
    if envelope.duration_seconds < 30:
        errors.append("duration_below_internal_30_second_floor")
    if envelope.duration_seconds > 60:
        errors.append("duration_above_internal_60_second_ceiling")

    if envelope.width < 540 or envelope.height < 960:
        errors.append("resolution_below_540x960")

    if envelope.width > 0 and envelope.height > 0:
        ratio = envelope.width / envelope.height
        target = 9 / 16
        if abs(ratio - target) > 0.035:
            errors.append("portrait_ratio_not_9_16_target")

    if not envelope.originality_passed:
        errors.append("originality_gate_failed")
    if not envelope.rights_passed:
        errors.append("rights_gate_failed")

    if envelope.market == "SA" and envelope.saudi_filter_passed is not True:
        errors.append("saudi_filter_required")

    if envelope.market == GLOBAL_MARKET and envelope.global_selected is not True:
        errors.append("global_selection_required")

    return errors


def _normalize_schedule_time(value: Optional[str]) -> Optional[str]:
    if not value:
        return None
    candidate = value.strip()
    if candidate.endswith("Z"):
        parsed = datetime.fromisoformat(candidate[:-1] + "+00:00")
    else:
        parsed = datetime.fromisoformat(candidate)
        if parsed.tzinfo is None:
            raise ValueError("schedule_time_must_include_timezone")
        parsed = parsed.astimezone(timezone.utc)
    if parsed.tzinfo is None:
        raise ValueError("schedule_time_must_include_timezone")
    return parsed.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def build_ayrshare_payload(
    envelope: SpotlightEnvelope,
    schedule_time: Optional[str] = None,
) -> Dict[str, Any]:
    errors = validate_envelope(envelope)
    if errors:
        raise EnvelopeValidationError(errors)

    # The country/global identity is carried in the produced video/board and
    # editorial text. Snapchat is still a single owned Trend Radar profile.
    payload: Dict[str, Any] = {
        "post": envelope.description,
        "platforms": ["snapchat"],
        "mediaUrls": [envelope.media_url],
        "snapChatOptions": {"spotlight": True},
    }

    normalized = _normalize_schedule_time(schedule_time)
    if normalized:
        payload["scheduleDate"] = normalized

    return payload


class AyrshareSpotlightPublisher:
    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        session: Any = requests,
    ):
        self.api_key = api_key or os.getenv("AYRSHARE_API_KEY")
        self.base_url = (base_url or os.getenv("AYRSHARE_BASE_URL") or AYRSHARE_BASE_URL).rstrip("/")
        self.session = session

    def readiness(self) -> Dict[str, Any]:
        return {
            "provider": "ayrshare",
            "api_key_configured": bool(self.api_key),
            "publication_enabled": _env_bool("SNAPCHAT_PUBLICATION_ENABLED", False),
            "supported_runtime_human_actions": 0,
            "markets": sorted(ALL_MARKETS),
        }

    def publish(
        self,
        envelope: SpotlightEnvelope,
        schedule_time: Optional[str] = None,
    ) -> Dict[str, Any]:
        if not _env_bool("SNAPCHAT_PUBLICATION_ENABLED", False):
            raise PublicationGateClosed("publication_gate_closed")
        if not self.api_key:
            raise PublicationGateClosed("ayrshare_api_key_not_configured")

        payload = build_ayrshare_payload(envelope, schedule_time=schedule_time)
        response = self.session.post(
            f"{self.base_url}/post",
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            json=payload,
            timeout=60,
        )

        try:
            body = response.json()
        except Exception:
            body = {"raw": response.text[:2000]}

        if response.status_code >= 400:
            raise RuntimeError(f"ayrshare_http_{response.status_code}:{body}")

        return {
            "ok": True,
            "provider": "ayrshare",
            "market": envelope.market,
            "trend_id": envelope.trend_id,
            "scheduled": bool(schedule_time),
            "provider_response": body,
        }


def selected_publisher():
    provider = (os.getenv("SNAPCHAT_PUBLISH_PROVIDER") or "ayrshare").strip().lower()
    if provider != "ayrshare":
        raise PublicationGateClosed(f"unsupported_provider:{provider}")
    return AyrshareSpotlightPublisher()

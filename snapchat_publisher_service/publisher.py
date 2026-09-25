import hashlib
import os
import threading
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

_submission_lock = threading.Lock()
_inflight_publication_ids = set()


class PublicationGateClosed(RuntimeError):
    pass


class EnvelopeValidationError(ValueError):
    def __init__(self, errors):
        self.errors = list(errors)
        super().__init__(";".join(self.errors))


def _native_true(value: Any) -> bool:
    return value is True


@dataclass(frozen=True)
class SpotlightEnvelope:
    publication_id: str
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
    human_origin_passed: bool
    visual_template_id: str
    trend_id: str
    saudi_filter_passed: Optional[bool] = None
    global_selected: Optional[bool] = None

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "SpotlightEnvelope":
        return cls(
            publication_id=str(data.get("publication_id", "")).strip(),
            market=str(data.get("market", "")).strip().upper(),
            language=str(data.get("language", "")).strip().lower(),
            headline=str(data.get("headline", "")).strip(),
            description=str(data.get("description", "")).strip(),
            media_url=str(data.get("media_url", "")).strip(),
            duration_seconds=float(data.get("duration_seconds", 0) or 0),
            width=int(data.get("width", 0) or 0),
            height=int(data.get("height", 0) or 0),
            originality_passed=_native_true(data.get("originality_passed")),
            rights_passed=_native_true(data.get("rights_passed")),
            human_origin_passed=_native_true(data.get("human_origin_passed")),
            visual_template_id=str(data.get("visual_template_id", "")).strip(),
            trend_id=str(data.get("trend_id", "")).strip(),
            saudi_filter_passed=_native_true(data.get("saudi_filter_passed")),
            global_selected=_native_true(data.get("global_selected")),
        )


def _env_bool(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def validate_envelope(envelope: SpotlightEnvelope):
    errors = []

    if not envelope.publication_id:
        errors.append("publication_id_required")
    if envelope.market not in ALL_MARKETS:
        errors.append("unsupported_market")
    if envelope.language != "ar":
        errors.append("current_activation_requires_arabic")
    if not envelope.trend_id:
        errors.append("trend_id_required")
    if not envelope.headline:
        errors.append("headline_required")
    if not envelope.visual_template_id:
        errors.append("visual_template_id_required")
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
    if not envelope.human_origin_passed:
        errors.append("snapchat_human_origin_gate_failed")

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


def _idempotency_key(envelope: SpotlightEnvelope) -> str:
    digest = hashlib.sha256(envelope.publication_id.encode("utf-8")).hexdigest()
    return f"trendradar-snap-{digest[:40]}"


def build_ayrshare_payload(
    envelope: SpotlightEnvelope,
    schedule_time: Optional[str] = None,
) -> Dict[str, Any]:
    errors = validate_envelope(envelope)
    if errors:
        raise EnvelopeValidationError(errors)

    payload: Dict[str, Any] = {
        "post": envelope.description,
        "platforms": ["snapchat"],
        "mediaUrls": [envelope.media_url],
        "snapChatOptions": {"spotlight": True},
        "idempotencyKey": _idempotency_key(envelope),
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

    def _headers(self) -> Dict[str, str]:
        if not self.api_key:
            raise PublicationGateClosed("ayrshare_api_key_not_configured")
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

    def readiness(self) -> Dict[str, Any]:
        return {
            "provider": "ayrshare",
            "api_key_configured": bool(self.api_key),
            "publication_enabled": _env_bool("SNAPCHAT_PUBLICATION_ENABLED", False),
            "provider_validation_required": True,
            "professional_profile_required": True,
            "supported_runtime_human_actions": 0,
            "markets": sorted(ALL_MARKETS),
        }

    def validate_provider(
        self,
        envelope: SpotlightEnvelope,
        schedule_time: Optional[str] = None,
    ) -> Dict[str, Any]:
        payload = build_ayrshare_payload(envelope, schedule_time=schedule_time)
        response = self.session.post(
            f"{self.base_url}/validate/post",
            headers=self._headers(),
            json=payload,
            timeout=60,
        )
        try:
            body = response.json()
        except Exception:
            body = {"raw": response.text[:2000]}

        if response.status_code >= 400:
            raise RuntimeError(f"ayrshare_validation_http_{response.status_code}:{body}")

        return {
            "ok": body.get("status") == "success",
            "provider": "ayrshare",
            "provider_response": body,
            "external_publication_side_effect": "NONE",
        }

    def get_post_status(self, post_id: str) -> Dict[str, Any]:
        if not post_id:
            raise ValueError("post_id_required")
        response = self.session.get(
            f"{self.base_url}/post/{post_id}",
            headers=self._headers(),
            timeout=30,
        )
        try:
            body = response.json()
        except Exception:
            body = {"raw": response.text[:2000]}
        if response.status_code >= 400:
            raise RuntimeError(f"ayrshare_status_http_{response.status_code}:{body}")
        return body

    def publish(
        self,
        envelope: SpotlightEnvelope,
        schedule_time: Optional[str] = None,
    ) -> Dict[str, Any]:
        if not _env_bool("SNAPCHAT_PUBLICATION_ENABLED", False):
            raise PublicationGateClosed("publication_gate_closed")
        if not self.api_key:
            raise PublicationGateClosed("ayrshare_api_key_not_configured")

        validation = self.validate_provider(envelope, schedule_time=schedule_time)
        if not validation.get("ok"):
            raise PublicationGateClosed("provider_validation_failed")

        payload = build_ayrshare_payload(envelope, schedule_time=schedule_time)

        with _submission_lock:
            if envelope.publication_id in _inflight_publication_ids:
                raise PublicationGateClosed("duplicate_publication_inflight")
            _inflight_publication_ids.add(envelope.publication_id)

        try:
            response = self.session.post(
                f"{self.base_url}/post",
                headers=self._headers(),
                json=payload,
                timeout=60,
            )
        finally:
            with _submission_lock:
                _inflight_publication_ids.discard(envelope.publication_id)

        try:
            body = response.json()
        except Exception:
            body = {"raw": response.text[:2000]}

        if response.status_code >= 400:
            raise RuntimeError(f"ayrshare_http_{response.status_code}:{body}")

        post_id = body.get("id")
        return {
            "ok": True,
            "provider": "ayrshare",
            "market": envelope.market,
            "trend_id": envelope.trend_id,
            "publication_id": envelope.publication_id,
            "scheduled": bool(schedule_time),
            "provider_post_id": post_id,
            "provider_response": body,
        }


def selected_publisher():
    provider = (os.getenv("SNAPCHAT_PUBLISH_PROVIDER") or "ayrshare").strip().lower()
    if provider != "ayrshare":
        raise PublicationGateClosed(f"unsupported_provider:{provider}")
    return AyrshareSpotlightPublisher()

import hashlib
import os
import re
import threading
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, Optional
from urllib.parse import urlparse

import requests


AYRSHARE_BASE_URL = "https://api.ayrshare.com/api"

ARAB_MARKET_LABELS = {
    "DZ": "الجزائر",
    "BH": "البحرين",
    "KM": "جزر القمر",
    "DJ": "جيبوتي",
    "EG": "مصر",
    "IQ": "العراق",
    "JO": "الأردن",
    "KW": "الكويت",
    "LB": "لبنان",
    "LY": "ليبيا",
    "MR": "موريتانيا",
    "MA": "المغرب",
    "OM": "عُمان",
    "PS": "فلسطين",
    "QA": "قطر",
    "SA": "السعودية",
    "SO": "الصومال",
    "SD": "السودان",
    "SY": "سوريا",
    "TN": "تونس",
    "AE": "الإمارات",
    "YE": "اليمن",
}
ARAB_MARKETS = set(ARAB_MARKET_LABELS)
GLOBAL_MARKET = "GLOBAL_SELECTED"
GLOBAL_LABEL = "ترند عالمي"
ALL_MARKETS = ARAB_MARKETS | {GLOBAL_MARKET}

COUNTRY_TEMPLATE_ID = "snap-country-board-v1"
GLOBAL_TEMPLATE_ID = "snap-global-board-v1"
ALLOWED_TEMPLATE_IDS = {COUNTRY_TEMPLATE_ID, GLOBAL_TEMPLATE_ID}
ALLOWED_ORIGIN_TYPES = {"human_original", "human_source_ai_assisted"}

PUBLICATION_ID_RE = re.compile(r"^[A-Za-z0-9._:-]{8,160}$")
PROVIDER_POST_ID_RE = re.compile(r"^[A-Za-z0-9_-]{1,160}$")

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


def _env_bool(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class SpotlightEnvelope:
    publication_id: str
    market: str
    market_label: str
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
    content_origin_type: str
    visual_template_id: str
    trend_id: str
    saudi_filter_passed: Optional[bool] = None
    global_selected: Optional[bool] = None

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "SpotlightEnvelope":
        return cls(
            publication_id=str(data.get("publication_id", "")).strip(),
            market=str(data.get("market", "")).strip().upper(),
            market_label=str(data.get("market_label", "")).strip(),
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
            content_origin_type=str(data.get("content_origin_type", "")).strip().lower(),
            visual_template_id=str(data.get("visual_template_id", "")).strip(),
            trend_id=str(data.get("trend_id", "")).strip(),
            saudi_filter_passed=_native_true(data.get("saudi_filter_passed")),
            global_selected=_native_true(data.get("global_selected")),
        )


def control_state() -> Dict[str, Any]:
    return {
        "publication_enabled": _env_bool("SNAPCHAT_PUBLICATION_ENABLED", False),
        "kill_switch": _env_bool("SNAPCHAT_KILL_SWITCH", True),
        "emergency_read_only": _env_bool("SNAPCHAT_EMERGENCY_READ_ONLY", True),
        "target_account_verified": _env_bool("SNAPCHAT_TARGET_ACCOUNT_VERIFIED", False),
        "durable_reconciliation_ready": _env_bool("SNAPCHAT_DURABLE_RECONCILIATION_READY", False),
        "alerting_ready": _env_bool("SNAPCHAT_ALERTING_READY", False),
        "production_assurance_ready": _env_bool("SNAPCHAT_PRODUCTION_ASSURANCE_READY", False),
    }


def _publication_gate_errors() -> list[str]:
    state = control_state()
    errors = []
    if not state["publication_enabled"]:
        errors.append("publication_gate_closed")
    if state["kill_switch"]:
        errors.append("kill_switch_active")
    if state["emergency_read_only"]:
        errors.append("emergency_read_only_active")
    if not state["target_account_verified"]:
        errors.append("target_account_not_verified")
    if not state["durable_reconciliation_ready"]:
        errors.append("durable_reconciliation_not_ready")
    if not state["alerting_ready"]:
        errors.append("alerting_not_ready")
    if not state["production_assurance_ready"]:
        errors.append("production_assurance_not_ready")
    return errors


def validate_envelope(envelope: SpotlightEnvelope):
    errors = []

    if not PUBLICATION_ID_RE.fullmatch(envelope.publication_id):
        errors.append("publication_id_invalid")

    if envelope.market not in ALL_MARKETS:
        errors.append("unsupported_market")

    if envelope.language != "ar":
        errors.append("current_activation_requires_arabic")

    if not envelope.trend_id:
        errors.append("trend_id_required")

    if not envelope.headline:
        errors.append("headline_required")

    if not envelope.description:
        errors.append("description_required")
    elif len(envelope.description) > 160:
        errors.append("spotlight_description_exceeds_160_characters")

    if envelope.visual_template_id not in ALLOWED_TEMPLATE_IDS:
        errors.append("visual_template_id_unrecognized")

    if envelope.market == GLOBAL_MARKET:
        if envelope.visual_template_id != GLOBAL_TEMPLATE_ID:
            errors.append("global_lane_requires_global_template")
        if envelope.market_label != GLOBAL_LABEL:
            errors.append("global_market_label_mismatch")
        if envelope.global_selected is not True:
            errors.append("global_selection_required")
    elif envelope.market in ARAB_MARKETS:
        if envelope.visual_template_id != COUNTRY_TEMPLATE_ID:
            errors.append("country_lane_requires_country_template")
        if envelope.market_label != ARAB_MARKET_LABELS[envelope.market]:
            errors.append("country_market_label_mismatch")

    parsed = urlparse(envelope.media_url)
    if parsed.scheme != "https" or not parsed.netloc:
        errors.append("https_media_url_required")

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
    if envelope.content_origin_type not in ALLOWED_ORIGIN_TYPES:
        errors.append("content_origin_type_not_recommendation_eligible")

    if envelope.market == "SA" and envelope.saudi_filter_passed is not True:
        errors.append("saudi_filter_required")

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


class DisabledSpotlightPublisher:
    provider_name = "disabled"

    @property
    def provider_validation_available(self) -> bool:
        return False

    def readiness(self) -> Dict[str, Any]:
        state = control_state()
        return {
            "provider": self.provider_name,
            "provider_configured": False,
            "publication_enabled": state["publication_enabled"],
            "kill_switch": state["kill_switch"],
            "emergency_read_only": state["emergency_read_only"],
            "target_account_verified": state["target_account_verified"],
            "durable_reconciliation_ready": state["durable_reconciliation_ready"],
            "alerting_ready": state["alerting_ready"],
            "production_assurance_ready": state["production_assurance_ready"],
            "normal_runtime_human_actions_target": 0,
            "markets": sorted(ALL_MARKETS),
            "reason": "no_approved_zero_routine_human_no_new_paid_provider_path_selected",
        }

    def validate_provider(self, *args, **kwargs):
        raise PublicationGateClosed("provider_not_selected")

    def get_post_status(self, *args, **kwargs):
        raise PublicationGateClosed("provider_not_selected")

    def publish(self, *args, **kwargs):
        raise PublicationGateClosed("provider_not_selected")


class AyrshareSpotlightPublisher:
    provider_name = "ayrshare"

    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        session: Any = requests,
    ):
        self.api_key = api_key or os.getenv("AYRSHARE_API_KEY")
        self.base_url = (base_url or os.getenv("AYRSHARE_BASE_URL") or AYRSHARE_BASE_URL).rstrip("/")
        self.session = session

    @property
    def provider_validation_available(self) -> bool:
        return bool(self.api_key)

    def _headers(self) -> Dict[str, str]:
        if not self.api_key:
            raise PublicationGateClosed("ayrshare_api_key_not_configured")
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

    def readiness(self) -> Dict[str, Any]:
        state = control_state()
        return {
            "provider": self.provider_name,
            "provider_configured": bool(self.api_key),
            "publication_enabled": state["publication_enabled"],
            "kill_switch": state["kill_switch"],
            "emergency_read_only": state["emergency_read_only"],
            "target_account_verified": state["target_account_verified"],
            "durable_reconciliation_ready": state["durable_reconciliation_ready"],
            "alerting_ready": state["alerting_ready"],
            "production_assurance_ready": state["production_assurance_ready"],
            "provider_validation_required": True,
            "professional_profile_required": True,
            "normal_runtime_human_actions_target": 0,
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
            body = {"raw": response.text[:1000]}

        if response.status_code >= 400:
            raise RuntimeError(f"ayrshare_validation_http_{response.status_code}")

        return {
            "ok": body.get("status") == "success",
            "provider": self.provider_name,
            "provider_response": body,
            "external_publication_side_effect": "NONE",
        }

    def get_post_status(self, post_id: str) -> Dict[str, Any]:
        if not PROVIDER_POST_ID_RE.fullmatch(post_id or ""):
            raise ValueError("post_id_invalid")
        response = self.session.get(
            f"{self.base_url}/post/{post_id}",
            headers=self._headers(),
            timeout=30,
        )
        try:
            body = response.json()
        except Exception:
            body = {"raw": response.text[:1000]}
        if response.status_code >= 400:
            raise RuntimeError(f"ayrshare_status_http_{response.status_code}")
        return body

    def publish(
        self,
        envelope: SpotlightEnvelope,
        schedule_time: Optional[str] = None,
    ) -> Dict[str, Any]:
        gate_errors = _publication_gate_errors()
        if gate_errors:
            raise PublicationGateClosed(",".join(gate_errors))
        if not self.api_key:
            raise PublicationGateClosed("ayrshare_api_key_not_configured")

        validation = self.validate_provider(envelope, schedule_time=schedule_time)
        if not validation.get("ok"):
            raise PublicationGateClosed("provider_validation_failed")

        payload = build_ayrshare_payload(envelope, schedule_time=schedule_time)

        # Serialize every publication submission in-process. Provider idempotency
        # remains the cross-retry protection. Durable local reconciliation is
        # still required before production acceptance.
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
                _inflight_publication_ids.discard(envelope.publication_id)

        try:
            body = response.json()
        except Exception:
            body = {"raw": response.text[:1000]}

        if response.status_code >= 400:
            raise RuntimeError(f"ayrshare_http_{response.status_code}")

        post_id = body.get("id")
        return {
            "ok": True,
            "provider": self.provider_name,
            "market": envelope.market,
            "trend_id": envelope.trend_id,
            "publication_id": envelope.publication_id,
            "scheduled": bool(schedule_time),
            "provider_post_id": post_id,
            "provider_response": body,
        }


def selected_publisher():
    provider = (os.getenv("SNAPCHAT_PUBLISH_PROVIDER") or "disabled").strip().lower()
    if provider in {"disabled", "none", "off"}:
        return DisabledSpotlightPublisher()
    if provider == "ayrshare":
        return AyrshareSpotlightPublisher()
    raise PublicationGateClosed(f"unsupported_provider:{provider}")

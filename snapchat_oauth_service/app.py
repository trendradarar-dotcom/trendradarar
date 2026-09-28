import base64
import hashlib
import hmac
import json
import logging
import os
import re
import secrets
import tempfile
import threading
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlencode

import requests
from cryptography.fernet import Fernet, InvalidToken
from cryptography.hazmat.primitives import padding
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from flask import Flask, jsonify, make_response, redirect, request

from audit import audit, safe_correlation_id
from media_probe import MediaProbeError, probe_video, validate_spotlight_media
from state_store import DurableStateStore, StateStoreError

APP_VERSION = "snapchat-oauth-service-20260928.1"
AUTH_URL = "https://accounts.snapchat.com/login/oauth2/authorize"
OAUTH_EXCHANGE_URL = "https://accounts.snapchat.com/login/oauth2/access_token"
BUSINESS_API = "https://businessapi.snapchat.com"
SCOPE = "snapchat-profile-api"
CHUNK_SIZE = 32 * 1024 * 1024
MAX_MEDIA_BYTES = 1024 * 1024 * 1024
STATE_TTL_SECONDS = 900
INTENT_TTL_SECONDS = 300
LOCALE_RE = re.compile(r"^[a-z]{2}_[A-Z]{2}$")
PUBLICATION_ID_RE = re.compile(r"^[A-Za-z0-9._:-]{8,160}$")
SPOTLIGHT_ID_RE = re.compile(r"^[A-Za-z0-9_\-]{8,300}$")
EXPECTED_USERNAME_DEFAULT = "trendradarar"

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = MAX_MEDIA_BYTES + (8 * 1024 * 1024)

_token_lock = threading.Lock()
_runtime_tokens = {}
_store_lock = threading.Lock()
_store_instance = None
_store_url = None


def _env_bool(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _env_int(name: str, default: int, minimum: int, maximum: int) -> int:
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        value = int(raw)
    except ValueError as exc:
        raise RuntimeError(f"{name}_invalid") from exc
    if value < minimum or value > maximum:
        raise RuntimeError(f"{name}_out_of_range")
    return value


def _limits() -> dict:
    return {
        "max_posts_per_hour": _env_int("SNAPCHAT_MAX_POSTS_PER_HOUR", 2, 1, 100),
        "max_posts_per_day": _env_int("SNAPCHAT_MAX_POSTS_PER_DAY", 10, 1, 1000),
        "max_concurrent_publishes": _env_int("SNAPCHAT_MAX_CONCURRENT_PUBLISHES", 1, 1, 10),
        "max_attempts_per_publication": _env_int("SNAPCHAT_MAX_ATTEMPTS_PER_PUBLICATION", 2, 1, 10),
        "retry_horizon_seconds": _env_int("SNAPCHAT_RETRY_HORIZON_SECONDS", 1800, 60, 86400),
    }


def _database_url() -> str:
    return (os.getenv("SNAPCHAT_DATABASE_URL") or os.getenv("DATABASE_URL") or "").strip()


def _store() -> DurableStateStore:
    global _store_instance, _store_url
    url = _database_url()
    if not url:
        raise StateStoreError("database_url_not_configured")
    with _store_lock:
        if _store_instance is None or _store_url != url:
            candidate = DurableStateStore(url)
            candidate.init_schema()
            _store_instance = candidate
            _store_url = url
    return _store_instance


def _state_store_status() -> dict:
    try:
        store = _store()
        ready = bool(store.ping())
        token_status = store.token_status()
        return {
            "ready": ready,
            "production_durable": bool(store.production_durable),
            "credential_record_present": token_status["persisted"],
            "connected": token_status["connected"],
            "refresh_credential_present": token_status["refresh_credential_present"],
        }
    except Exception:
        return {
            "ready": False,
            "production_durable": False,
            "credential_record_present": False,
            "connected": False,
            "refresh_credential_present": False,
        }


def _direct_connection_gate():
    if not _env_bool("SNAPCHAT_DIRECT_API_ENABLED", False):
        return jsonify({
            "ok": False,
            "error": "direct_api_disabled",
            "external_side_effect": "BLOCKED",
        }), 503
    return None


def _production_gate_errors() -> list[str]:
    errors = []
    if not _env_bool("SNAPCHAT_PUBLICATION_ENABLED", False):
        errors.append("publication_gate_closed")
    if _env_bool("SNAPCHAT_KILL_SWITCH", True):
        errors.append("kill_switch_active")
    if _env_bool("SNAPCHAT_EMERGENCY_READ_ONLY", True):
        errors.append("emergency_read_only_active")
    if not _env_bool("SNAPCHAT_TARGET_ACCOUNT_VERIFIED", False):
        errors.append("target_account_not_verified")
    if not _env_bool("SNAPCHAT_DURABLE_RECONCILIATION_READY", False):
        errors.append("durable_reconciliation_not_ready")
    if not _env_bool("SNAPCHAT_ALERTING_READY", False):
        errors.append("alerting_not_ready")
    if not _env_bool("SNAPCHAT_PRODUCTION_ASSURANCE_READY", False):
        errors.append("production_assurance_not_ready")
    if not _env_bool("SNAPCHAT_HARD_LIMITS_VERIFIED", False):
        errors.append("hard_limits_not_verified")

    state = _state_store_status()
    if not state["ready"]:
        errors.append("durable_state_store_unavailable")
    elif not state["production_durable"]:
        errors.append("production_requires_postgresql_state_store")
    if not state["connected"] or not state["refresh_credential_present"]:
        errors.append("durable_oauth_connection_not_ready")
    return errors


def _publication_control_gate():
    errors = _production_gate_errors()
    if errors:
        return jsonify({
            "ok": False,
            "error": "publication_gate_closed",
            "blocking_controls": errors,
            "external_publication_side_effect": "BLOCKED",
        }), 403
    return None


def _required_env(*names):
    return [name for name in names if not os.getenv(name)]


def _token_fingerprint(token: str | None):
    if not token:
        return None
    return hashlib.sha256(token.encode("utf-8")).hexdigest()[:12]


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _owner_authorized() -> bool:
    expected = os.getenv("SNAPCHAT_OWNER_KEY")
    supplied = request.headers.get("X-Owner-Key")
    return bool(expected and supplied and hmac.compare_digest(expected, supplied))


def _require_owner():
    if not _owner_authorized():
        audit(
            "owner_authorization_denied",
            correlation_id=_correlation_id(),
            route=request.path,
            http_status=401,
            external_publication_side_effect="NONE",
        )
        return jsonify({"ok": False, "error": "owner_authorization_required"}), 401
    return None


def _correlation_id() -> str:
    supplied = safe_correlation_id(request.headers.get("X-Correlation-ID"))
    return supplied or str(uuid.uuid4())


def _sign_state(ts: int, nonce: str) -> str:
    secret = os.environ["SNAPCHAT_STATE_SECRET"].encode("utf-8")
    payload = f"{ts}.{nonce}".encode("utf-8")
    sig = hmac.new(secret, payload, hashlib.sha256).hexdigest()
    raw = f"{ts}.{nonce}.{sig}".encode("utf-8")
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def _verify_state_signature(state: str) -> bool:
    try:
        padded = state + "=" * (-len(state) % 4)
        decoded = base64.urlsafe_b64decode(padded.encode("ascii")).decode("utf-8")
        ts_s, nonce, sig = decoded.split(".", 2)
        ts = int(ts_s)
        if time.time() - ts > STATE_TTL_SECONDS or ts > time.time() + 60:
            return False
        expected = hmac.new(
            os.environ["SNAPCHAT_STATE_SECRET"].encode("utf-8"),
            f"{ts}.{nonce}".encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()
        return hmac.compare_digest(expected, sig)
    except Exception:
        return False


def _fernet() -> Fernet:
    raw = os.getenv("SNAPCHAT_TOKEN_ENCRYPTION_KEY")
    if not raw:
        raise RuntimeError("token_encryption_key_not_configured")
    try:
        return Fernet(raw.encode("ascii"))
    except Exception as exc:
        raise RuntimeError("token_encryption_key_invalid") from exc


def _encrypt_token(token: str) -> str:
    return _fernet().encrypt(token.encode("utf-8")).decode("ascii")


def _decrypt_token(ciphertext: str) -> str:
    try:
        return _fernet().decrypt(ciphertext.encode("ascii")).decode("utf-8")
    except InvalidToken as exc:
        raise RuntimeError("token_decryption_failed") from exc


def _scope_ok(scope_value: str | None) -> bool:
    scopes = {item.strip() for item in (scope_value or "").split() if item.strip()}
    return SCOPE in scopes


def _store_tokens(payload: dict, profile_id: str, username: str):
    access_token = payload.get("access_token")
    refresh_token = payload.get("refresh_token")
    if not access_token or not refresh_token:
        raise RuntimeError("oauth_tokens_incomplete")
    scope = payload.get("scope") or ""
    if not _scope_ok(scope):
        raise RuntimeError("required_scope_missing")
    expires_at = int(time.time()) + int(payload.get("expires_in", 3600)) - 60

    access_cipher = _encrypt_token(access_token)
    refresh_cipher = _encrypt_token(refresh_token)
    _store().save_tokens(
        access_cipher=access_cipher,
        refresh_cipher=refresh_cipher,
        expires_at=expires_at,
        scope=scope,
        profile_id=profile_id,
        username=username,
    )
    with _token_lock:
        _runtime_tokens.clear()
        _runtime_tokens.update({
            "access_token": access_token,
            "refresh_token": refresh_token,
            "expires_at": expires_at,
            "scope": scope,
            "profile_id": profile_id,
            "username": username,
        })


def _exchange_code(code: str) -> dict:
    response = requests.post(
        OAUTH_EXCHANGE_URL,
        data={
            "grant_type": "authorization_code",
            "client_id": os.environ["SNAPCHAT_CLIENT_ID"],
            "client_secret": os.environ["SNAPCHAT_CLIENT_SECRET"],
            "code": code,
            "redirect_uri": os.environ["SNAPCHAT_REDIRECT_URI"],
        },
        timeout=30,
    )
    response.raise_for_status()
    payload = response.json()
    if not payload.get("access_token") or not payload.get("refresh_token"):
        raise RuntimeError("oauth_tokens_incomplete")
    return payload


def _load_persistent_tokens() -> dict:
    row = _store().load_tokens()
    if not row or int(row.get("connected") or 0) != 1:
        raise RuntimeError("oauth_connection_not_configured")
    if not row.get("access_cipher") or not row.get("refresh_cipher"):
        raise RuntimeError("oauth_tokens_not_persisted")
    return {
        "access_token": _decrypt_token(row["access_cipher"]),
        "refresh_token": _decrypt_token(row["refresh_cipher"]),
        "expires_at": int(row.get("expires_at") or 0),
        "scope": row.get("scope") or "",
        "profile_id": row.get("profile_id"),
        "username": row.get("username"),
    }


def _refresh_access_token() -> str:
    persisted = _load_persistent_tokens()
    refresh_token = persisted["refresh_token"]
    response = requests.post(
        OAUTH_EXCHANGE_URL,
        data={
            "grant_type": "refresh_token",
            "client_id": os.environ["SNAPCHAT_CLIENT_ID"],
            "client_secret": os.environ["SNAPCHAT_CLIENT_SECRET"],
            "refresh_token": refresh_token,
        },
        timeout=30,
    )
    response.raise_for_status()
    payload = response.json()
    if not payload.get("refresh_token"):
        payload["refresh_token"] = refresh_token
    profile_id = persisted.get("profile_id") or _expected_profile_id()
    username = persisted.get("username") or _expected_username()
    _store_tokens(payload, profile_id, username)
    return payload["access_token"]


def _access_token() -> str:
    now = int(time.time())
    with _token_lock:
        runtime_access = _runtime_tokens.get("access_token")
        expires_at = int(_runtime_tokens.get("expires_at") or 0)
    if runtime_access and expires_at > now:
        return runtime_access

    persisted = _load_persistent_tokens()
    if persisted["access_token"] and persisted["expires_at"] > now:
        with _token_lock:
            _runtime_tokens.clear()
            _runtime_tokens.update(persisted)
        return persisted["access_token"]

    return _refresh_access_token()


def _headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _snap_json(response: requests.Response):
    try:
        payload = response.json()
    except Exception:
        payload = {"raw": response.text[:2000]}
    if response.status_code >= 400:
        raise RuntimeError(f"snap_http_{response.status_code}")
    return payload


def _expected_profile_id() -> str:
    value = (os.getenv("SNAPCHAT_PUBLIC_PROFILE_ID") or "").strip()
    if not value:
        raise RuntimeError("SNAPCHAT_PUBLIC_PROFILE_ID_not_configured")
    return value


def _expected_username() -> str:
    return (os.getenv("SNAPCHAT_EXPECTED_USERNAME") or EXPECTED_USERNAME_DEFAULT).strip().lower()


def _extract_public_profile(payload: dict) -> dict:
    if not isinstance(payload, dict):
        raise RuntimeError("profile_payload_invalid")

    if isinstance(payload.get("public_profile"), dict):
        return payload["public_profile"]
    if isinstance(payload.get("profile"), dict):
        return payload["profile"]

    candidates = []
    for item in payload.get("public_profiles") or []:
        if not isinstance(item, dict):
            continue
        if item.get("sub_request_status") not in {None, "SUCCESS"}:
            continue
        profile = item.get("public_profile")
        if isinstance(profile, dict):
            candidates.append(profile)
    if len(candidates) != 1:
        raise RuntimeError("profile_payload_not_exactly_one")
    return candidates[0]


def _verify_exact_profile_payload(payload: dict) -> dict:
    profile = _extract_public_profile(payload)
    actual_id = str(profile.get("id") or profile.get("profile_id") or "").strip()
    actual_username = str(profile.get("snap_user_name") or profile.get("username") or "").strip().lower()
    expected_id = _expected_profile_id()
    expected_username = _expected_username()
    if actual_id != expected_id:
        raise RuntimeError("public_profile_id_mismatch")
    if actual_username != expected_username:
        raise RuntimeError("public_profile_username_mismatch")
    return {
        "id": actual_id,
        "username": actual_username,
        "display_name": profile.get("display_name"),
    }


def _fetch_exact_public_profile(token: str) -> dict:
    profile_id = _expected_profile_id()
    response = requests.get(
        f"{BUSINESS_API}/public/v1/public_profiles/{profile_id}",
        headers=_headers(token),
        timeout=30,
    )
    payload = _snap_json(response)
    if payload.get("request_status") not in {None, "SUCCESS"}:
        raise RuntimeError("profile_read_not_success")
    return _verify_exact_profile_payload(payload)


def _verify_authorized_profile_access(token: str) -> None:
    profile_id = _expected_profile_id()
    response = requests.get(
        f"{BUSINESS_API}/v1/public_profiles/{profile_id}/spotlights",
        headers=_headers(token),
        params={"limit": 1},
        timeout=30,
    )
    payload = _snap_json(response)
    if payload.get("request_status") != "SUCCESS":
        raise RuntimeError("authorized_profile_access_failed")


def _validate_spotlight_input(file_storage, description: str, locale: str, publication_id: str | None = None):
    errors = []
    if publication_id is not None and not PUBLICATION_ID_RE.fullmatch(publication_id or ""):
        errors.append("publication_id_invalid")
    if not file_storage or not file_storage.filename:
        errors.append("video_required")
    elif not file_storage.filename.lower().endswith(".mp4"):
        errors.append("mp4_required")
    if file_storage and file_storage.mimetype and file_storage.mimetype not in {"video/mp4", "application/octet-stream"}:
        errors.append("content_type_not_mp4")
    if len(description or "") > 160:
        errors.append("description_exceeds_160_characters")
    if not LOCALE_RE.match(locale or ""):
        errors.append("locale_must_match_language_COUNTRY_example_ar_SA")
    return errors


def _hash_file(path: str) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        while True:
            block = handle.read(1024 * 1024)
            if not block:
                break
            digest.update(block)
    return digest.hexdigest()


def _encrypt_file(src_path: str, dst_path: str, key: bytes, iv: bytes):
    cipher = Cipher(algorithms.AES(key), modes.CBC(iv))
    encryptor = cipher.encryptor()
    padder = padding.PKCS7(algorithms.AES.block_size).padder()
    with open(src_path, "rb") as src, open(dst_path, "wb") as dst:
        while True:
            block = src.read(1024 * 1024)
            if not block:
                break
            padded = padder.update(block)
            if padded:
                dst.write(encryptor.update(padded))
        final_padded = padder.finalize()
        dst.write(encryptor.update(final_padded) + encryptor.finalize())


def _create_media(token: str, profile_id: str, name: str, key: bytes, iv: bytes):
    response = requests.post(
        f"{BUSINESS_API}/v1/public_profiles/{profile_id}/media",
        headers={**_headers(token), "Content-Type": "application/json"},
        json={
            "type": "VIDEO",
            "name": name[:120] or "trend-radar-spotlight",
            "key": base64.b64encode(key).decode("ascii"),
            "iv": base64.b64encode(iv).decode("ascii"),
        },
        timeout=30,
    )
    payload = _snap_json(response)
    if payload.get("request_status") != "SUCCESS" or not payload.get("media_id"):
        raise RuntimeError("create_media_failed")
    return payload


def _absolute_business_path(path: str) -> str:
    if path.startswith("http://") or path.startswith("https://"):
        if not path.startswith(BUSINESS_API + "/"):
            raise RuntimeError("unexpected_upload_host")
        return path
    if not path.startswith("/"):
        path = "/" + path
    return BUSINESS_API + path


def _upload_encrypted_media(token: str, encrypted_path: str, add_path: str, finalize_path: str):
    part_number = 1
    with open(encrypted_path, "rb") as handle:
        while True:
            chunk = handle.read(CHUNK_SIZE)
            if not chunk:
                break
            if part_number > 35:
                raise RuntimeError("encrypted_media_exceeds_35_parts")
            response = requests.post(
                _absolute_business_path(add_path),
                headers=_headers(token),
                data={"action": "ADD", "part_number": str(part_number)},
                files={"file": (f"video.enc.part{part_number}", chunk, "application/octet-stream")},
                timeout=180,
            )
            payload = _snap_json(response)
            if payload.get("request_status") != "SUCCESS":
                raise RuntimeError(f"multipart_add_failed_part_{part_number}")
            part_number += 1

    response = requests.post(
        _absolute_business_path(finalize_path),
        headers=_headers(token),
        data={"action": "FINALIZE"},
        timeout=60,
    )
    payload = _snap_json(response)
    if payload.get("request_status") != "SUCCESS":
        raise RuntimeError("multipart_finalize_failed")
    return payload


def _post_spotlight(token: str, profile_id: str, media_id: str, description: str, locale: str, skip_save_to_profile: bool):
    response = requests.post(
        f"{BUSINESS_API}/v1/public_profiles/{profile_id}/spotlights",
        headers={**_headers(token), "Content-Type": "application/json"},
        json={
            "media_id": media_id,
            "skip_save_to_profile": bool(skip_save_to_profile),
            "description": description,
            "locale": locale,
        },
        timeout=60,
    )
    payload = _snap_json(response)
    if payload.get("request_status") != "SUCCESS" or not payload.get("spotlight_id"):
        raise RuntimeError("spotlight_post_failed")
    return payload


def _get_spotlight(token: str, profile_id: str, spotlight_id: str) -> dict:
    response = requests.get(
        f"{BUSINESS_API}/v1/public_profiles/{profile_id}/spotlights/{spotlight_id}",
        headers=_headers(token),
        timeout=30,
    )
    payload = _snap_json(response)
    if payload.get("request_status") != "SUCCESS":
        raise RuntimeError("spotlight_status_not_success")
    return payload


def _extract_spotlight(payload: dict) -> dict:
    candidates = []
    for item in payload.get("spotlights") or []:
        if not isinstance(item, dict):
            continue
        if item.get("sub_request_status") not in {None, "SUCCESS"}:
            continue
        spotlight = item.get("spotlight")
        if isinstance(spotlight, dict):
            candidates.append(spotlight)
    if len(candidates) != 1:
        raise RuntimeError("spotlight_payload_not_exactly_one")
    return candidates[0]


def _provider_state(remote_state: str) -> str:
    value = (remote_state or "").upper()
    if value in {"SUBMITTED", "LIVE", "REJECTED"}:
        return value
    raise RuntimeError("unexpected_remote_spotlight_state")


def _parse_snap_timestamp(value: str | None) -> int | None:
    if not value:
        return None
    try:
        normalized = value.replace("Z", "+00:00")
        return int(datetime.fromisoformat(normalized).timestamp())
    except Exception:
        return None


@app.after_request
def _security_headers(response):
    response.headers["Cache-Control"] = "no-store"
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "no-referrer"
    return response


@app.get("/")
def index():
    state = _state_store_status()
    return jsonify({
        "service": "Trend Radar Snapchat Public Profile API bridge",
        "version": APP_VERSION,
        "scope": SCOPE,
        "direct_api_enabled": _env_bool("SNAPCHAT_DIRECT_API_ENABLED", False),
        "publication_enabled": _env_bool("SNAPCHAT_PUBLICATION_ENABLED", False),
        "kill_switch": _env_bool("SNAPCHAT_KILL_SWITCH", True),
        "emergency_read_only": _env_bool("SNAPCHAT_EMERGENCY_READ_ONLY", True),
        "durable_state_store": state["production_durable"] and state["ready"],
        "public_side_effect_default": "BLOCKED",
    })


@app.get("/health")
def health():
    state = _state_store_status()
    try:
        limits = _limits()
    except Exception:
        limits = {"configuration": "INVALID"}
    return jsonify({
        "ok": True,
        "version": APP_VERSION,
        "config": {
            "client_id": bool(os.getenv("SNAPCHAT_CLIENT_ID")),
            "client_secret": bool(os.getenv("SNAPCHAT_CLIENT_SECRET")),
            "redirect_uri": bool(os.getenv("SNAPCHAT_REDIRECT_URI")),
            "state_secret": bool(os.getenv("SNAPCHAT_STATE_SECRET")),
            "token_encryption_key": bool(os.getenv("SNAPCHAT_TOKEN_ENCRYPTION_KEY")),
            "profile_id": bool(os.getenv("SNAPCHAT_PUBLIC_PROFILE_ID")),
            "expected_username": _expected_username(),
            "owner_key": bool(os.getenv("SNAPCHAT_OWNER_KEY")),
            "direct_api_enabled": _env_bool("SNAPCHAT_DIRECT_API_ENABLED", False),
            "publication_enabled": _env_bool("SNAPCHAT_PUBLICATION_ENABLED", False),
            "kill_switch": _env_bool("SNAPCHAT_KILL_SWITCH", True),
            "emergency_read_only": _env_bool("SNAPCHAT_EMERGENCY_READ_ONLY", True),
            "target_account_verified": _env_bool("SNAPCHAT_TARGET_ACCOUNT_VERIFIED", False),
            "durable_reconciliation_ready": _env_bool("SNAPCHAT_DURABLE_RECONCILIATION_READY", False),
            "alerting_ready": _env_bool("SNAPCHAT_ALERTING_READY", False),
            "production_assurance_ready": _env_bool("SNAPCHAT_PRODUCTION_ASSURANCE_READY", False),
            "hard_limits_verified": _env_bool("SNAPCHAT_HARD_LIMITS_VERIFIED", False),
            "durable_store_ready": state["ready"],
            "durable_store_production": state["production_durable"],
            "oauth_connected": state["connected"],
            "refresh_credential_persisted": state["refresh_credential_present"],
        },
        "limits": limits,
        "publication_gate_errors": _production_gate_errors(),
        "external_publication_side_effect": "NONE",
    })


@app.post("/admin/oauth-intent")
def create_oauth_intent():
    blocked = _direct_connection_gate()
    if blocked:
        return blocked
    denied = _require_owner()
    if denied:
        return denied
    missing = _required_env(
        "SNAPCHAT_CLIENT_ID",
        "SNAPCHAT_CLIENT_SECRET",
        "SNAPCHAT_REDIRECT_URI",
        "SNAPCHAT_STATE_SECRET",
        "SNAPCHAT_TOKEN_ENCRYPTION_KEY",
        "SNAPCHAT_PUBLIC_PROFILE_ID",
    )
    if missing:
        return jsonify({"ok": False, "error": "missing_configuration", "missing": missing}), 503
    intent = secrets.token_urlsafe(32)
    _store().create_oauth_intent(_sha256_text(intent), INTENT_TTL_SECONDS)
    start_url = request.host_url.rstrip("/") + "/auth/start?" + urlencode({"intent": intent})
    audit("oauth_intent_created", correlation_id=_correlation_id(), status="CREATED", external_publication_side_effect="NONE")
    return jsonify({
        "ok": True,
        "start_url": start_url,
        "expires_in": INTENT_TTL_SECONDS,
        "one_time": True,
        "external_publication_side_effect": "NONE",
    })


@app.get("/auth/start")
def auth_start():
    blocked = _direct_connection_gate()
    if blocked:
        return blocked
    missing = _required_env("SNAPCHAT_CLIENT_ID", "SNAPCHAT_REDIRECT_URI", "SNAPCHAT_STATE_SECRET")
    if missing:
        return jsonify({"ok": False, "error": "missing_configuration", "missing": missing}), 503

    intent = request.args.get("intent", "")
    if not intent or not _store().consume_oauth_intent(_sha256_text(intent)):
        return jsonify({"ok": False, "error": "invalid_or_expired_oauth_intent"}), 403

    state = _sign_state(int(time.time()), secrets.token_urlsafe(24))
    browser_nonce = secrets.token_urlsafe(32)
    _store().create_oauth_state(
        _sha256_text(state),
        _sha256_text(browser_nonce),
        STATE_TTL_SECONDS,
    )
    query = urlencode({
        "response_type": "code",
        "client_id": os.environ["SNAPCHAT_CLIENT_ID"],
        "redirect_uri": os.environ["SNAPCHAT_REDIRECT_URI"],
        "scope": SCOPE,
        "state": state,
    })
    response = make_response(redirect(f"{AUTH_URL}?{query}", code=302))
    response.set_cookie(
        "snap_oauth_flow",
        browser_nonce,
        max_age=STATE_TTL_SECONDS,
        secure=True,
        httponly=True,
        samesite="Lax",
        path="/auth/callback",
    )
    return response


@app.get("/auth/callback")
def auth_callback():
    blocked = _direct_connection_gate()
    if blocked:
        return blocked
    missing = _required_env(
        "SNAPCHAT_CLIENT_ID",
        "SNAPCHAT_CLIENT_SECRET",
        "SNAPCHAT_REDIRECT_URI",
        "SNAPCHAT_STATE_SECRET",
        "SNAPCHAT_TOKEN_ENCRYPTION_KEY",
        "SNAPCHAT_PUBLIC_PROFILE_ID",
    )
    if missing:
        return jsonify({"ok": False, "error": "missing_configuration", "missing": missing}), 503

    state = request.args.get("state", "")
    browser_nonce = request.cookies.get("snap_oauth_flow", "")
    if (
        not state
        or not browser_nonce
        or not _verify_state_signature(state)
        or not _store().consume_oauth_state(_sha256_text(state), _sha256_text(browser_nonce))
    ):
        return jsonify({"ok": False, "error": "invalid_expired_or_replayed_oauth_state"}), 400

    if request.args.get("error"):
        return jsonify({"ok": False, "error": "oauth_authorization_denied"}), 400

    code = request.args.get("code")
    if not code:
        return jsonify({"ok": False, "error": "authorization_code_missing"}), 400

    try:
        payload = _exchange_code(code)
        if not _scope_ok(payload.get("scope")):
            raise RuntimeError("required_scope_missing")
        profile = _fetch_exact_public_profile(payload["access_token"])
        _verify_authorized_profile_access(payload["access_token"])
        _store_tokens(payload, profile["id"], profile["username"])
        audit(
            "oauth_binding_verified",
            correlation_id=_correlation_id(),
            profile_id=profile["id"],
            username=profile["username"],
            oauth_scope=payload.get("scope"),
            status="PASS",
            external_publication_side_effect="NONE",
        )
        response = make_response(jsonify({
            "ok": True,
            "oauth": "PASS",
            "exact_profile_binding": "PASS",
            "authorized_profile_access": "PASS",
            "profile_id": profile["id"],
            "username": profile["username"],
            "scope": payload.get("scope", SCOPE),
            "expires_in": payload.get("expires_in"),
            "access_token_fingerprint": _token_fingerprint(payload.get("access_token")),
            "refresh_credential_persisted": True,
            "credentials_exposed": False,
            "next_gate": "ALLOWLIST_AND_PRODUCTION_ASSURANCE",
        }))
        response.delete_cookie("snap_oauth_flow", path="/auth/callback")
        return response
    except requests.HTTPError as exc:
        status = exc.response.status_code if exc.response is not None else None
        audit("oauth_binding_failed", correlation_id=_correlation_id(), status="FAIL", error="HTTPError", http_status=status, external_publication_side_effect="NONE")
        return jsonify({"ok": False, "error": "oauth_binding_failed", "provider_http_status": status}), 502
    except Exception as exc:
        audit("oauth_binding_failed", correlation_id=_correlation_id(), status="FAIL", error=type(exc).__name__, external_publication_side_effect="NONE")
        return jsonify({"ok": False, "error": "oauth_binding_failed", "reason": str(exc)}), 502


@app.get("/admin/token-status")
def token_status():
    blocked = _direct_connection_gate()
    if blocked:
        return blocked
    denied = _require_owner()
    if denied:
        return denied
    try:
        status = _store().token_status()
        return jsonify({
            "ok": True,
            "persisted": status["persisted"],
            "connected": status["connected"],
            "access_credential_present": status["access_credential_present"],
            "refresh_credential_present": status["refresh_credential_present"],
            "expires_at": status["expires_at"],
            "scope": status["scope"],
            "profile_id": status["profile_id"],
            "username": status["username"],
            "credentials_exposed": False,
        })
    except Exception:
        return jsonify({"ok": False, "error": "token_status_failed"}), 503


@app.post("/admin/disconnect")
def disconnect():
    blocked = _direct_connection_gate()
    if blocked:
        return blocked
    denied = _require_owner()
    if denied:
        return denied
    _store().clear_tokens()
    with _token_lock:
        _runtime_tokens.clear()
    audit("oauth_disconnected", correlation_id=_correlation_id(), status="DISCONNECTED", external_publication_side_effect="NONE")
    return jsonify({
        "ok": True,
        "connected": False,
        "local_credentials_invalidated": True,
        "new_publications_blocked": True,
        "provider_revocation": "REQUIRES_EXTERNAL_APP_OR_ACCOUNT_REVOCATION_WHERE_APPLICABLE",
        "external_publication_side_effect": "NONE",
    })


@app.get("/readiness/profile-binding")
def profile_binding_readiness():
    blocked = _direct_connection_gate()
    if blocked:
        return blocked
    denied = _require_owner()
    if denied:
        return denied
    try:
        token = _access_token()
        profile = _fetch_exact_public_profile(token)
        _verify_authorized_profile_access(token)
        return jsonify({
            "ok": True,
            "binding": "PASS",
            "authorized_access": "PASS",
            "profile_id": profile["id"],
            "display_name": profile.get("display_name"),
            "username": profile["username"],
            "external_publication_side_effect": "NONE",
        }), 200
    except RuntimeError as exc:
        return jsonify({
            "ok": False,
            "binding": "FAILED",
            "authorized_access": "NOT_VERIFIED",
            "error": str(exc),
            "external_publication_side_effect": "NONE",
        }), 503
    except Exception as exc:
        return jsonify({
            "ok": False,
            "binding": "FAILED",
            "authorized_access": "NOT_VERIFIED",
            "error": type(exc).__name__,
            "external_publication_side_effect": "NONE",
        }), 502


@app.get("/profiles/<profile_id>")
def get_profile(profile_id):
    blocked = _direct_connection_gate()
    if blocked:
        return blocked
    denied = _require_owner()
    if denied:
        return denied
    if profile_id != _expected_profile_id():
        return jsonify({"ok": False, "error": "profile_target_mismatch"}), 403
    try:
        token = _access_token()
        profile = _fetch_exact_public_profile(token)
        return jsonify({"ok": True, "profile": profile, "external_publication_side_effect": "NONE"}), 200
    except Exception:
        return jsonify({"ok": False, "error": "profile_read_failed"}), 502


@app.post("/spotlight/validate")
def validate_spotlight():
    blocked = _direct_connection_gate()
    if blocked:
        return blocked
    denied = _require_owner()
    if denied:
        return denied

    publication_id = request.form.get("publication_id", "")
    video = request.files.get("video")
    description = request.form.get("description", "")
    locale = request.form.get("locale", "ar_SA")
    errors = _validate_spotlight_input(video, description, locale, publication_id)
    if errors:
        return jsonify({"ok": False, "errors": errors, "external_publication_side_effect": "NONE"}), 400

    try:
        with tempfile.TemporaryDirectory(prefix="trendradar-snap-validate-") as tmpdir:
            raw_path = str(Path(tmpdir) / "video.mp4")
            video.save(raw_path)
            raw_size = os.path.getsize(raw_path)
            if raw_size > MAX_MEDIA_BYTES:
                errors.append("file_exceeds_1gb_upload_limit")
                meta = {}
            else:
                meta = probe_video(raw_path)
                errors.extend(validate_spotlight_media(meta))
        return jsonify({
            "ok": not errors,
            "errors": errors,
            "filename": getattr(video, "filename", None),
            "size_bytes": raw_size,
            "description_length": len(description),
            "locale": locale,
            "publication_id": publication_id,
            "probed_media": meta,
            "external_publication_side_effect": "NONE",
        }), (200 if not errors else 400)
    except MediaProbeError as exc:
        return jsonify({"ok": False, "errors": [str(exc)], "external_publication_side_effect": "NONE"}), 400


@app.get("/spotlight/status/<spotlight_id>")
def spotlight_status(spotlight_id):
    blocked = _direct_connection_gate()
    if blocked:
        return blocked
    denied = _require_owner()
    if denied:
        return denied
    if not SPOTLIGHT_ID_RE.fullmatch(spotlight_id or ""):
        return jsonify({"ok": False, "error": "spotlight_id_invalid"}), 400
    try:
        token = _access_token()
        profile_id = _expected_profile_id()
        payload = _get_spotlight(token, profile_id, spotlight_id)
        spotlight = _extract_spotlight(payload)
        if str(spotlight.get("profile_id") or "") != profile_id:
            raise RuntimeError("remote_profile_mismatch")
        return jsonify({
            "ok": True,
            "spotlight": spotlight,
            "external_publication_side_effect": "NONE",
        }), 200
    except Exception:
        return jsonify({"ok": False, "error": "spotlight_status_failed"}), 502


@app.get("/admin/publications/<publication_id>")
def publication_record(publication_id):
    blocked = _direct_connection_gate()
    if blocked:
        return blocked
    denied = _require_owner()
    if denied:
        return denied
    if not PUBLICATION_ID_RE.fullmatch(publication_id or ""):
        return jsonify({"ok": False, "error": "publication_id_invalid"}), 400
    row = _store().get_publication(_expected_profile_id(), publication_id)
    if not row:
        return jsonify({"ok": False, "error": "publication_not_found"}), 404
    row.pop("description", None)
    return jsonify({"ok": True, "publication": row, "external_publication_side_effect": "NONE"})


@app.post("/admin/publications/<publication_id>/reconcile")
def reconcile_publication(publication_id):
    blocked = _direct_connection_gate()
    if blocked:
        return blocked
    denied = _require_owner()
    if denied:
        return denied
    if not PUBLICATION_ID_RE.fullmatch(publication_id or ""):
        return jsonify({"ok": False, "error": "publication_id_invalid"}), 400

    profile_id = _expected_profile_id()
    store = _store()
    row = store.get_publication(profile_id, publication_id)
    if not row:
        return jsonify({"ok": False, "error": "publication_not_found"}), 404

    token = _access_token()
    remote_id = row.get("remote_spotlight_id")
    if remote_id:
        try:
            payload = _get_spotlight(token, profile_id, remote_id)
            spotlight = _extract_spotlight(payload)
            if str(spotlight.get("profile_id") or "") != profile_id:
                raise RuntimeError("remote_profile_mismatch")
            state = _provider_state(str(spotlight.get("status") or ""))
            updated = store.transition(
                profile_id=profile_id,
                publication_id=publication_id,
                allowed_from=(row["state"],),
                new_state=state,
                remote_spotlight_id=remote_id,
                mark_final=state in {"LIVE", "REJECTED"},
            )
            return jsonify({"ok": True, "reconciliation": "EXACT_REMOTE_ID", "state": updated["state"], "external_publication_side_effect": "NONE"})
        except Exception:
            return jsonify({"ok": False, "reconciliation": "FAILED", "state": row["state"], "external_publication_side_effect": "NONE"}), 502

    if row["state"] not in {"UNKNOWN", "SUBMITTING"}:
        return jsonify({"ok": True, "reconciliation": "NOT_REQUIRED", "state": row["state"], "external_publication_side_effect": "NONE"})

    submit_started = int(row.get("submit_started_at") or row.get("updated_at") or 0)
    try:
        response = requests.get(
            f"{BUSINESS_API}/v1/public_profiles/{profile_id}/spotlights",
            headers=_headers(token),
            params={"limit": 20},
            timeout=30,
        )
        payload = _snap_json(response)
        candidates = []
        expected_description = row.get("description") or ""
        for item in payload.get("spotlights") or []:
            spotlight = item.get("spotlight") if isinstance(item, dict) else None
            if not isinstance(spotlight, dict):
                continue
            if str(spotlight.get("profile_id") or "") != profile_id:
                continue
            created_at = _parse_snap_timestamp(spotlight.get("created_at"))
            if not created_at or abs(created_at - submit_started) > 300:
                continue
            text_fields = {
                str(spotlight.get("caption") or ""),
                str(spotlight.get("title") or ""),
            }
            if expected_description and expected_description not in text_fields:
                continue
            candidates.append(spotlight)

        if len(candidates) != 1:
            return jsonify({
                "ok": False,
                "reconciliation": "AMBIGUOUS_OR_NOT_FOUND",
                "candidate_count": len(candidates),
                "state": "UNKNOWN",
                "external_publication_side_effect": "NONE",
            }), 409

        spotlight = candidates[0]
        remote_id = str(spotlight.get("id") or "")
        if not remote_id:
            raise RuntimeError("reconciled_spotlight_missing_id")
        state = _provider_state(str(spotlight.get("status") or ""))
        updated = store.transition(
            profile_id=profile_id,
            publication_id=publication_id,
            allowed_from=(row["state"],),
            new_state=state,
            remote_spotlight_id=remote_id,
            mark_final=state in {"LIVE", "REJECTED"},
        )
        return jsonify({
            "ok": True,
            "reconciliation": "UNIQUE_REMOTE_MATCH",
            "state": updated["state"],
            "remote_spotlight_id": remote_id,
            "external_publication_side_effect": "NONE",
        })
    except StateStoreError:
        raise
    except Exception:
        return jsonify({"ok": False, "reconciliation": "FAILED", "state": "UNKNOWN", "external_publication_side_effect": "NONE"}), 502


@app.post("/spotlight/publish")
def spotlight_publish():
    correlation_id = _correlation_id()
    blocked = _direct_connection_gate()
    if blocked:
        return blocked
    denied = _require_owner()
    if denied:
        return denied
    blocked = _publication_control_gate()
    if blocked:
        return blocked

    profile_id = _expected_profile_id()
    publication_id = request.form.get("publication_id", "").strip()
    video = request.files.get("video")
    description = request.form.get("description", "")
    locale = request.form.get("locale", "ar_SA")
    skip_save = request.form.get("skip_save_to_profile", "false").lower() in {"1", "true", "yes"}
    errors = _validate_spotlight_input(video, description, locale, publication_id)
    if errors:
        return jsonify({"ok": False, "errors": errors, "external_publication_side_effect": "NONE"}), 400

    phase = "VALIDATION"
    ledger_started = False
    try:
        token = _access_token()
        exact_profile = _fetch_exact_public_profile(token)
        _verify_authorized_profile_access(token)
        if exact_profile["id"] != profile_id:
            raise RuntimeError("exact_profile_binding_failed")

        with tempfile.TemporaryDirectory(prefix="trendradar-snap-") as tmpdir:
            raw_path = str(Path(tmpdir) / "video.mp4")
            enc_path = str(Path(tmpdir) / "video.enc")
            video.save(raw_path)
            raw_size = os.path.getsize(raw_path)
            if raw_size > MAX_MEDIA_BYTES:
                return jsonify({"ok": False, "error": "file_exceeds_1gb_upload_limit", "external_publication_side_effect": "NONE"}), 400

            meta = probe_video(raw_path)
            media_errors = validate_spotlight_media(meta)
            if media_errors:
                return jsonify({"ok": False, "errors": media_errors, "external_publication_side_effect": "NONE"}), 400
            media_sha256 = _hash_file(raw_path)

            limits = _limits()
            admission = _store().begin_publication(
                profile_id=profile_id,
                publication_id=publication_id,
                correlation_id=correlation_id,
                description=description,
                media_sha256=media_sha256,
                duration=float(meta["duration_seconds"]),
                width=int(meta["width"]),
                height=int(meta["height"]),
                max_hour=limits["max_posts_per_hour"],
                max_day=limits["max_posts_per_day"],
                max_concurrent=limits["max_concurrent_publishes"],
                max_attempts=limits["max_attempts_per_publication"],
                retry_horizon_seconds=limits["retry_horizon_seconds"],
            )
            ledger_started = True
            row = admission["row"]
            if not admission["created"] and not admission["retry_admitted"]:
                audit(
                    "spotlight_duplicate_blocked",
                    correlation_id=correlation_id,
                    publication_id=publication_id,
                    profile_id=profile_id,
                    status=row["state"],
                    attempt_count=row.get("attempt_count"),
                    external_publication_side_effect="NONE",
                )
                return jsonify({
                    "ok": False,
                    "error": "duplicate_or_unreconciled_publication",
                    "publication_id": publication_id,
                    "state": row["state"],
                    "remote_spotlight_id": row.get("remote_spotlight_id"),
                    "external_publication_side_effect": "BLOCKED",
                }), 409

            _store().transition(
                profile_id=profile_id,
                publication_id=publication_id,
                allowed_from=("RECEIVED",),
                new_state="VALIDATED",
            )
            phase = "MEDIA_CREATING"
            _store().transition(
                profile_id=profile_id,
                publication_id=publication_id,
                allowed_from=("VALIDATED",),
                new_state="MEDIA_CREATING",
            )

            key = secrets.token_bytes(32)
            iv = secrets.token_bytes(16)
            _encrypt_file(raw_path, enc_path, key, iv)
            media = _create_media(token, profile_id, Path(video.filename).stem, key, iv)
            remote_media_id = str(media["media_id"])
            _store().transition(
                profile_id=profile_id,
                publication_id=publication_id,
                allowed_from=("MEDIA_CREATING",),
                new_state="MEDIA_UPLOADING",
                remote_media_id=remote_media_id,
            )

            phase = "MEDIA_UPLOADING"
            _upload_encrypted_media(token, enc_path, media["add_path"], media["finalize_path"])

            phase = "SUBMITTING"
            _store().transition(
                profile_id=profile_id,
                publication_id=publication_id,
                allowed_from=("MEDIA_UPLOADING",),
                new_state="SUBMITTING",
                remote_media_id=remote_media_id,
                mark_submit_started=True,
            )
            posted = _post_spotlight(token, profile_id, remote_media_id, description, locale, skip_save)
            remote_spotlight_id = str(posted["spotlight_id"])
            row = _store().transition(
                profile_id=profile_id,
                publication_id=publication_id,
                allowed_from=("SUBMITTING",),
                new_state="SUBMITTED",
                remote_media_id=remote_media_id,
                remote_spotlight_id=remote_spotlight_id,
            )

        audit(
            "spotlight_submit_success",
            correlation_id=correlation_id,
            publication_id=publication_id,
            profile_id=profile_id,
            remote_media_id=remote_media_id,
            remote_spotlight_id=remote_spotlight_id,
            status="SUBMITTED",
            attempt_count=row.get("attempt_count"),
            http_status=201,
            external_publication_side_effect="PROVIDER_REQUEST_SENT",
        )
        return jsonify({
            "ok": True,
            "publication_id": publication_id,
            "state": "SUBMITTED",
            "request_status": posted.get("request_status"),
            "spotlight_id": remote_spotlight_id,
            "profile_id": profile_id,
            "correlation_id": correlation_id,
            "initial_provider_state": "SUBMITTED",
        }), 201

    except StateStoreError as exc:
        audit(
            "spotlight_publish_blocked_state",
            correlation_id=correlation_id,
            publication_id=publication_id,
            profile_id=profile_id,
            status="BLOCKED",
            error=str(exc),
            external_publication_side_effect="NONE",
        )
        return jsonify({"ok": False, "error": str(exc), "external_publication_side_effect": "BLOCKED"}), 409
    except MediaProbeError as exc:
        return jsonify({"ok": False, "error": str(exc), "external_publication_side_effect": "NONE"}), 400
    except Exception as exc:
        error_name = type(exc).__name__
        if ledger_started:
            try:
                row = _store().get_publication(profile_id, publication_id)
                if row:
                    current = row["state"]
                    if phase == "SUBMITTING" or current == "SUBMITTING":
                        _store().transition(
                            profile_id=profile_id,
                            publication_id=publication_id,
                            allowed_from=(current,),
                            new_state="UNKNOWN",
                            last_error=error_name,
                        )
                        side_effect = "UNKNOWN_REQUIRES_RECONCILIATION"
                    elif current in {"RECEIVED", "VALIDATED", "MEDIA_CREATING", "MEDIA_UPLOADING"}:
                        _store().transition(
                            profile_id=profile_id,
                            publication_id=publication_id,
                            allowed_from=(current,),
                            new_state="FAILED_PRE_SUBMIT",
                            last_error=error_name,
                        )
                        side_effect = "NO_PUBLICATION_REQUEST_SENT"
                    else:
                        side_effect = "UNKNOWN_REQUIRES_RECONCILIATION"
                else:
                    side_effect = "NONE"
            except Exception:
                side_effect = "UNKNOWN_REQUIRES_RECONCILIATION"
        else:
            side_effect = "NONE"

        audit(
            "spotlight_publish_failed",
            correlation_id=correlation_id,
            publication_id=publication_id,
            profile_id=profile_id,
            status="ERROR",
            error=error_name,
            http_status=502,
            external_publication_side_effect=side_effect,
        )
        return jsonify({
            "ok": False,
            "error": "spotlight_publish_failed",
            "publication_id": publication_id,
            "correlation_id": correlation_id,
            "external_publication_side_effect": side_effect,
        }), 502


if __name__ == "__main__":
    port = int(os.getenv("PORT", "10000"))
    app.run(host=os.getenv("HOST", "127.0.0.1"), port=port)

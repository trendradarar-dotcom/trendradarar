import base64
import hashlib
import hmac
import os
import re
import secrets
import tempfile
import threading
import time
from pathlib import Path
from urllib.parse import urlencode

import requests
from cryptography.hazmat.primitives import padding
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from flask import Flask, jsonify, redirect, request

APP_VERSION = "snapchat-oauth-service-20260925.2"
AUTH_URL = "https://accounts.snapchat.com/login/oauth2/authorize"
OAUTH_EXCHANGE_URL = "https://accounts.snapchat.com/login/oauth2/access_token"
BUSINESS_API = "https://businessapi.snapchat.com"
SCOPE = "snapchat-profile-api"
CHUNK_SIZE = 32 * 1024 * 1024
MAX_MEDIA_BYTES = 1024 * 1024 * 1024
STATE_TTL_SECONDS = 900
LOCALE_RE = re.compile(r"^[a-z]{2}_[A-Z]{2}$")

app = Flask(__name__)
_token_lock = threading.Lock()
_runtime_tokens = {}


def _env_bool(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _direct_connection_gate():
    if not _env_bool("SNAPCHAT_DIRECT_API_ENABLED", False):
        return jsonify({
            "ok": False,
            "error": "direct_api_disabled",
            "external_side_effect": "BLOCKED",
        }), 503
    return None


def _publication_control_gate():
    if not _env_bool("SNAPCHAT_PUBLICATION_ENABLED", False):
        return jsonify({"ok": False, "error": "publication_gate_closed", "external_publication_side_effect": "BLOCKED"}), 403
    if _env_bool("SNAPCHAT_KILL_SWITCH", True):
        return jsonify({"ok": False, "error": "kill_switch_active", "external_publication_side_effect": "BLOCKED"}), 403
    if _env_bool("SNAPCHAT_EMERGENCY_READ_ONLY", True):
        return jsonify({"ok": False, "error": "emergency_read_only_active", "external_publication_side_effect": "BLOCKED"}), 403
    return None


def _required_env(*names):
    return [name for name in names if not os.getenv(name)]


def _token_fingerprint(token: str | None):
    if not token:
        return None
    return hashlib.sha256(token.encode("utf-8")).hexdigest()[:12]


def _owner_authorized() -> bool:
    expected = os.getenv("SNAPCHAT_OWNER_KEY")
    supplied = request.headers.get("X-Owner-Key")
    return bool(expected and supplied and hmac.compare_digest(expected, supplied))


def _require_owner():
    if not _owner_authorized():
        return jsonify({"ok": False, "error": "owner_authorization_required"}), 401
    return None


def _sign_state(ts: int, nonce: str) -> str:
    secret = os.environ["SNAPCHAT_STATE_SECRET"].encode("utf-8")
    payload = f"{ts}.{nonce}".encode("utf-8")
    sig = hmac.new(secret, payload, hashlib.sha256).hexdigest()
    raw = f"{ts}.{nonce}.{sig}".encode("utf-8")
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def _verify_state(state: str) -> bool:
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


def _store_tokens(payload: dict):
    now = int(time.time())
    with _token_lock:
        if payload.get("access_token"):
            _runtime_tokens["access_token"] = payload["access_token"]
        if payload.get("refresh_token"):
            _runtime_tokens["refresh_token"] = payload["refresh_token"]
        _runtime_tokens["expires_at"] = now + int(payload.get("expires_in", 3600)) - 60
        _runtime_tokens["scope"] = payload.get("scope") or _runtime_tokens.get("scope")


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
    _store_tokens(payload)
    return payload


def _refresh_access_token() -> str:
    with _token_lock:
        runtime_refresh = _runtime_tokens.get("refresh_token")
    refresh_token = runtime_refresh or os.getenv("SNAPCHAT_REFRESH_TOKEN")
    if not refresh_token:
        raise RuntimeError("refresh_token_not_configured")

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
    _store_tokens(payload)
    return payload["access_token"]


def _access_token() -> str:
    now = int(time.time())
    with _token_lock:
        runtime_access = _runtime_tokens.get("access_token")
        expires_at = int(_runtime_tokens.get("expires_at") or 0)
    if runtime_access and expires_at > now:
        return runtime_access

    configured_access = os.getenv("SNAPCHAT_ACCESS_TOKEN")
    if configured_access:
        return configured_access
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


def _validate_spotlight_input(file_storage, description: str, locale: str):
    errors = []
    if not file_storage or not file_storage.filename:
        errors.append("video_required")
    elif not file_storage.filename.lower().endswith(".mp4"):
        errors.append("mp4_required")

    if len(description or "") > 160:
        errors.append("description_exceeds_160_characters")
    if not LOCALE_RE.match(locale or ""):
        errors.append("locale_must_match_language_COUNTRY_example_ar_SA")
    return errors


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
        raise RuntimeError(f"create_media_failed:{payload}")
    return payload


def _absolute_business_path(path: str) -> str:
    if path.startswith("http://") or path.startswith("https://"):
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
                raise RuntimeError(f"multipart_add_failed_part_{part_number}:{payload}")
            part_number += 1

    response = requests.post(
        _absolute_business_path(finalize_path),
        headers=_headers(token),
        data={"action": "FINALIZE"},
        timeout=60,
    )
    payload = _snap_json(response)
    if payload.get("request_status") != "SUCCESS":
        raise RuntimeError(f"multipart_finalize_failed:{payload}")
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
        raise RuntimeError(f"spotlight_post_failed:{payload}")
    return payload


@app.get("/")
def index():
    return jsonify({
        "service": "Trend Radar Snapchat Public Profile API bridge",
        "version": APP_VERSION,
        "scope": SCOPE,
        "direct_api_enabled": _env_bool("SNAPCHAT_DIRECT_API_ENABLED", False),
        "publication_enabled": _env_bool("SNAPCHAT_PUBLICATION_ENABLED", False),
        "kill_switch": _env_bool("SNAPCHAT_KILL_SWITCH", True),
        "emergency_read_only": _env_bool("SNAPCHAT_EMERGENCY_READ_ONLY", True),
        "public_side_effect_default": "BLOCKED",
    })


@app.get("/health")
def health():
    return jsonify({
        "ok": True,
        "version": APP_VERSION,
        "config": {
            "client_id": bool(os.getenv("SNAPCHAT_CLIENT_ID")),
            "client_secret": bool(os.getenv("SNAPCHAT_CLIENT_SECRET")),
            "redirect_uri": bool(os.getenv("SNAPCHAT_REDIRECT_URI")),
            "state_secret": bool(os.getenv("SNAPCHAT_STATE_SECRET")),
            "profile_id": bool(os.getenv("SNAPCHAT_PUBLIC_PROFILE_ID")),
            "refresh_token": bool(os.getenv("SNAPCHAT_REFRESH_TOKEN") or _runtime_tokens.get("refresh_token")),
            "owner_key": bool(os.getenv("SNAPCHAT_OWNER_KEY")),
            "direct_api_enabled": _env_bool("SNAPCHAT_DIRECT_API_ENABLED", False),
            "publication_enabled": _env_bool("SNAPCHAT_PUBLICATION_ENABLED", False),
            "kill_switch": _env_bool("SNAPCHAT_KILL_SWITCH", True),
            "emergency_read_only": _env_bool("SNAPCHAT_EMERGENCY_READ_ONLY", True),
        },
    })


@app.get("/auth/start")
def auth_start():
    blocked = _direct_connection_gate()
    if blocked:
        return blocked
    missing = _required_env("SNAPCHAT_CLIENT_ID", "SNAPCHAT_REDIRECT_URI", "SNAPCHAT_STATE_SECRET")
    if missing:
        return jsonify({"ok": False, "error": "missing_configuration", "missing": missing}), 503
    state = _sign_state(int(time.time()), secrets.token_urlsafe(24))
    query = urlencode({
        "response_type": "code",
        "client_id": os.environ["SNAPCHAT_CLIENT_ID"],
        "redirect_uri": os.environ["SNAPCHAT_REDIRECT_URI"],
        "scope": SCOPE,
        "state": state,
    })
    return redirect(f"{AUTH_URL}?{query}", code=302)


@app.get("/auth/callback")
def auth_callback():
    blocked = _direct_connection_gate()
    if blocked:
        return blocked
    missing = _required_env("SNAPCHAT_CLIENT_ID", "SNAPCHAT_CLIENT_SECRET", "SNAPCHAT_REDIRECT_URI", "SNAPCHAT_STATE_SECRET")
    if missing:
        return jsonify({"ok": False, "error": "missing_configuration", "missing": missing}), 503

    if request.args.get("error"):
        return jsonify({"ok": False, "error": request.args.get("error"), "description": request.args.get("error_description")}), 400

    code = request.args.get("code")
    state = request.args.get("state")
    if not code or not state or not _verify_state(state):
        return jsonify({"ok": False, "error": "invalid_or_expired_oauth_state"}), 400

    try:
        payload = _exchange_code(code)
    except requests.HTTPError as exc:
        return jsonify({"ok": False, "error": "token_exchange_failed", "status": exc.response.status_code}), 502
    except Exception:
        return jsonify({"ok": False, "error": "token_exchange_failed"}), 502

    return jsonify({
        "ok": True,
        "oauth": "PASS",
        "scope": payload.get("scope", SCOPE),
        "expires_in": payload.get("expires_in"),
        "access_token_fingerprint": _token_fingerprint(payload.get("access_token")),
        "refresh_token_received": bool(payload.get("refresh_token")),
        "tokens_exposed": False,
        "next_gate": "PUBLIC_PROFILE_API_ALLOWLIST_AND_EXACT_PROFILE_BINDING",
    })


@app.get("/admin/token-status")
def token_status():
    blocked = _direct_connection_gate()
    if blocked:
        return blocked
    denied = _require_owner()
    if denied:
        return denied
    with _token_lock:
        access = _runtime_tokens.get("access_token")
        refresh = _runtime_tokens.get("refresh_token")
        expires_at = _runtime_tokens.get("expires_at")
        scope = _runtime_tokens.get("scope")
    return jsonify({
        "ok": True,
        "runtime_access_token": bool(access),
        "runtime_refresh_token": bool(refresh),
        "access_token_fingerprint": _token_fingerprint(access),
        "refresh_token_fingerprint": _token_fingerprint(refresh),
        "expires_at": expires_at,
        "scope": scope,
    })


@app.get("/profiles/<profile_id>")
def get_profile(profile_id):
    blocked = _direct_connection_gate()
    if blocked:
        return blocked
    denied = _require_owner()
    if denied:
        return denied
    try:
        token = _access_token()
        response = requests.get(
            f"{BUSINESS_API}/public/v1/public_profiles/{profile_id}",
            headers=_headers(token),
            timeout=30,
        )
        return jsonify(_snap_json(response)), response.status_code
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
    video = request.files.get("video")
    description = request.form.get("description", "")
    locale = request.form.get("locale", "ar_SA")
    errors = _validate_spotlight_input(video, description, locale)
    size = None
    if video and video.stream:
        pos = video.stream.tell()
        video.stream.seek(0, os.SEEK_END)
        size = video.stream.tell()
        video.stream.seek(pos)
        if size > MAX_MEDIA_BYTES:
            errors.append("file_exceeds_1gb_upload_limit")
    return jsonify({
        "ok": not errors,
        "errors": errors,
        "filename": getattr(video, "filename", None),
        "size_bytes": size,
        "description_length": len(description),
        "locale": locale,
        "official_spotlight_constraints": {
            "format": "MP4",
            "duration_seconds": "6-60",
            "minimum_resolution": "540x960",
            "description_max_characters": 160,
        },
        "duration_resolution_probe": "not_run_by_this_endpoint",
        "external_publication_side_effect": "NONE",
    }), (200 if not errors else 400)


@app.get("/spotlight/status/<spotlight_id>")
def spotlight_status(spotlight_id):
    blocked = _direct_connection_gate()
    if blocked:
        return blocked
    denied = _require_owner()
    if denied:
        return denied
    profile_id = os.getenv("SNAPCHAT_PUBLIC_PROFILE_ID")
    if not profile_id:
        return jsonify({"ok": False, "error": "SNAPCHAT_PUBLIC_PROFILE_ID_not_configured"}), 503
    try:
        token = _access_token()
        response = requests.get(
            f"{BUSINESS_API}/v1/public_profiles/{profile_id}/spotlights/{spotlight_id}",
            headers=_headers(token),
            timeout=30,
        )
        return jsonify(_snap_json(response)), response.status_code
    except Exception:
        return jsonify({"ok": False, "error": "spotlight_status_failed"}), 502


@app.post("/spotlight/publish")
def spotlight_publish():
    blocked = _direct_connection_gate()
    if blocked:
        return blocked
    denied = _require_owner()
    if denied:
        return denied
    blocked = _publication_control_gate()
    if blocked:
        return blocked

    profile_id = os.getenv("SNAPCHAT_PUBLIC_PROFILE_ID")
    if not profile_id:
        return jsonify({"ok": False, "error": "SNAPCHAT_PUBLIC_PROFILE_ID_not_configured"}), 503

    video = request.files.get("video")
    description = request.form.get("description", "")
    locale = request.form.get("locale", "ar_SA")
    skip_save = request.form.get("skip_save_to_profile", "false").lower() in {"1", "true", "yes"}
    errors = _validate_spotlight_input(video, description, locale)
    if errors:
        return jsonify({"ok": False, "errors": errors}), 400

    try:
        token = _access_token()
        with tempfile.TemporaryDirectory(prefix="trendradar-snap-") as tmpdir:
            raw_path = str(Path(tmpdir) / "video.mp4")
            enc_path = str(Path(tmpdir) / "video.enc")
            video.save(raw_path)
            raw_size = os.path.getsize(raw_path)
            if raw_size > MAX_MEDIA_BYTES:
                return jsonify({"ok": False, "error": "file_exceeds_1gb_upload_limit"}), 400

            key = secrets.token_bytes(32)
            iv = secrets.token_bytes(16)
            _encrypt_file(raw_path, enc_path, key, iv)
            media = _create_media(token, profile_id, Path(video.filename).stem, key, iv)
            _upload_encrypted_media(token, enc_path, media["add_path"], media["finalize_path"])
            posted = _post_spotlight(token, profile_id, media["media_id"], description, locale, skip_save)

        return jsonify({
            "ok": True,
            "request_status": posted.get("request_status"),
            "spotlight_id": posted.get("spotlight_id"),
            "profile_id": profile_id,
            "initial_provider_state": "SUBMITTED_EXPECTED",
        }), 201
    except Exception:
        return jsonify({
            "ok": False,
            "error": "spotlight_publish_failed",
            "external_publication_side_effect": "UNKNOWN_REQUIRES_RECONCILIATION",
        }), 502


if __name__ == "__main__":
    port = int(os.getenv("PORT", "10000"))
    app.run(host=os.getenv("HOST", "127.0.0.1"), port=port)

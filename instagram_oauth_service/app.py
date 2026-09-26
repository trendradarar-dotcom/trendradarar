import base64
import hashlib
import hmac
import json
import os
import secrets
import tempfile
import time
import uuid
from pathlib import Path
from urllib.parse import urlencode

import requests
import psycopg
from cryptography.fernet import Fernet, InvalidToken
from flask import Flask, Response, jsonify, redirect, request, send_file, session, url_for

APP_NAME = "Trend Radar — Instagram Reels"
API_VERSION = os.getenv("INSTAGRAM_API_VERSION", "v26.0").strip() or "v26.0"
APP_ID = os.getenv("INSTAGRAM_APP_ID", "").strip()
APP_SECRET = os.getenv("INSTAGRAM_APP_SECRET", "").strip()
REDIRECT_URI = os.getenv("INSTAGRAM_REDIRECT_URI", "").strip()
PUBLIC_BASE_URL = os.getenv("PUBLIC_BASE_URL", "").strip().rstrip("/")
SESSION_SECRET = os.getenv("SESSION_SECRET", "").strip()
EXPECTED_USERNAME = os.getenv("INSTAGRAM_EXPECTED_USERNAME", "").strip().lstrip("@").lower()
PUBLIC_OAUTH_REDIRECT_URI = os.getenv(
    "INSTAGRAM_PUBLIC_OAUTH_REDIRECT_URI", REDIRECT_URI
).strip()
OAUTH_PUBLIC_ORIGIN = os.getenv(
    "INSTAGRAM_OAUTH_PUBLIC_ORIGIN", "https://trendradar.com.co"
).strip().rstrip("/")
OAUTH_GATEWAY_SECRET = os.getenv("INSTAGRAM_OAUTH_GATEWAY_SECRET", "").strip()
DATABASE_URL = os.getenv("INSTAGRAM_DATABASE_URL", os.getenv("DATABASE_URL", "")).strip()
TOKEN_ENCRYPTION_KEY = os.getenv("INSTAGRAM_TOKEN_ENCRYPTION_KEY", "").strip()
REFRESH_SECRET = os.getenv("INSTAGRAM_REFRESH_SECRET", "").strip()
PERSISTENCE_REQUIRED = os.getenv("INSTAGRAM_PERSISTENCE_REQUIRED", "false").lower() == "true"
SCOPES = (
    "instagram_business_basic",
    "instagram_business_content_publish",
)
PUBLIC_PUBLISH_AUTHORIZED = os.getenv(
    "INSTAGRAM_PUBLIC_PUBLISH_AUTHORIZED", "false"
).lower() == "true"

app = Flask(__name__)
app.secret_key = SESSION_SECRET or secrets.token_urlsafe(48)
app.config["MAX_CONTENT_LENGTH"] = 120 * 1024 * 1024

TOKEN_STORE = {}
MEDIA_STORE = {}
DELETION_STORE = {}
MEDIA_DIR = Path(tempfile.gettempdir()) / "trendradar_instagram_review_media"
MEDIA_DIR.mkdir(parents=True, exist_ok=True)


def _configured():
    return bool(APP_ID and APP_SECRET and REDIRECT_URI and SESSION_SECRET)


def _sid():
    sid = session.get("sid")
    if not sid:
        sid = secrets.token_urlsafe(24)
        session["sid"] = sid
    return sid


def _persistence_configured():
    return bool(DATABASE_URL and TOKEN_ENCRYPTION_KEY)


def _fernet():
    if not TOKEN_ENCRYPTION_KEY:
        return None
    try:
        return Fernet(TOKEN_ENCRYPTION_KEY.encode("utf-8"))
    except Exception:
        return None


def _db_connect():
    if not DATABASE_URL:
        return None
    return psycopg.connect(DATABASE_URL, connect_timeout=10)


def _ensure_token_table():
    if not _persistence_configured():
        return False
    with _db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS instagram_oauth_tokens (
                    account_key TEXT PRIMARY KEY,
                    ciphertext BYTEA NOT NULL,
                    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                )
                """
            )
        conn.commit()
    return True


def _persist_token_record(rec):
    if not _persistence_configured():
        return not PERSISTENCE_REQUIRED
    f = _fernet()
    if not f:
        return False
    safe_rec = dict(rec)
    payload = json.dumps(safe_rec, separators=(",", ":"), sort_keys=True).encode("utf-8")
    ciphertext = f.encrypt(payload)
    account_key = str(safe_rec.get("username") or EXPECTED_USERNAME or "").strip().lower()
    if not account_key:
        return False
    try:
        _ensure_token_table()
        with _db_connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO instagram_oauth_tokens(account_key, ciphertext, updated_at)
                    VALUES (%s, %s, NOW())
                    ON CONFLICT (account_key)
                    DO UPDATE SET ciphertext = EXCLUDED.ciphertext, updated_at = NOW()
                    """,
                    (account_key, ciphertext),
                )
            conn.commit()
        return True
    except Exception:
        return False


def _load_persisted_token_record():
    if not _persistence_configured():
        return None
    f = _fernet()
    if not f:
        return None
    account_key = (EXPECTED_USERNAME or "").strip().lower()
    if not account_key:
        return None
    try:
        _ensure_token_table()
        with _db_connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT ciphertext FROM instagram_oauth_tokens WHERE account_key = %s",
                    (account_key,),
                )
                row = cur.fetchone()
        if not row:
            return None
        raw = bytes(row[0]) if not isinstance(row[0], bytes) else row[0]
        return json.loads(f.decrypt(raw).decode("utf-8"))
    except (InvalidToken, Exception):
        return None


def _token_record():
    rec = TOKEN_STORE.get(_sid())
    if rec:
        return rec
    rec = _load_persisted_token_record()
    if rec:
        TOKEN_STORE[_sid()] = rec
    return rec


def _base_url():
    if PUBLIC_BASE_URL:
        return PUBLIC_BASE_URL
    return request.url_root.rstrip("/")


def _cleanup_media():
    now = time.time()
    for media_id, record in list(MEDIA_STORE.items()):
        if now - record["created_at"] > 3600:
            try:
                Path(record["path"]).unlink(missing_ok=True)
            except Exception:
                pass
            MEDIA_STORE.pop(media_id, None)


def _graph(method, path, token, *, params=None, data=None, timeout=45):
    url = f"https://graph.instagram.com/{API_VERSION}/{path.lstrip('/')}"
    headers = {"Authorization": f"Bearer {token}"}
    response = requests.request(
        method,
        url,
        params=params,
        data=data,
        headers=headers,
        timeout=timeout,
    )
    try:
        payload = response.json()
    except Exception:
        payload = {"raw": response.text[:2000]}
    return response.status_code, payload


def _refresh_long_lived_token(rec):
    token = str((rec or {}).get("access_token") or "").strip()
    if not token:
        return 400, {"ok": False, "error": "MISSING_PERSISTED_TOKEN"}
    response = requests.get(
        "https://graph.instagram.com/refresh_access_token",
        params={
            "grant_type": "ig_refresh_token",
            "access_token": token,
        },
        timeout=45,
    )
    try:
        payload = response.json()
    except Exception:
        payload = {}
    if response.status_code >= 400 or not payload.get("access_token"):
        return 502, {
            "ok": False,
            "stage": "LONG_TOKEN_REFRESH",
            "http": response.status_code,
            "provider_error": payload.get("error") if isinstance(payload, dict) else None,
        }

    refreshed = dict(rec)
    refreshed["access_token"] = payload["access_token"]
    refreshed["expires_in"] = payload.get("expires_in")
    refreshed["refreshed_at"] = int(time.time())

    profile_http, profile = _graph(
        "GET",
        "me",
        refreshed["access_token"],
        params={"fields": "id,user_id,username,account_type"},
    )
    if profile_http >= 400:
        return 502, {"ok": False, "stage": "REFRESH_PROFILE_VERIFY", "http": profile_http}

    actual_username = str(profile.get("username") or "").strip().lstrip("@").lower()
    account_type = str(profile.get("account_type") or "").strip()
    normalized_account_type = account_type.replace(" ", "_").upper()
    professional_user_id = profile.get("user_id")
    if EXPECTED_USERNAME and actual_username != EXPECTED_USERNAME:
        return 403, {"ok": False, "error": "INSTAGRAM_ACCOUNT_MISMATCH"}
    if not professional_user_id or normalized_account_type not in {"BUSINESS", "MEDIA_CREATOR"}:
        return 422, {"ok": False, "error": "INSTAGRAM_PROFESSIONAL_ACCOUNT_REQUIRED"}

    refreshed["username"] = profile.get("username")
    refreshed["account_type"] = account_type
    refreshed["user_id"] = professional_user_id
    refreshed["app_scoped_user_id"] = profile.get("id") or refreshed.get("app_scoped_user_id")
    if not _persist_token_record(refreshed):
        return 503, {"ok": False, "error": "TOKEN_PERSISTENCE_FAILED"}
    return 200, refreshed


def _b64url_decode(value):
    value += "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode(value.encode("utf-8"))


def _b64url_encode(value):
    return base64.urlsafe_b64encode(value).decode("utf-8").rstrip("=")


def _make_public_oauth_state():
    payload = {
        "aud": "trendradar-instagram-public-oauth",
        "iat": int(time.time()),
        "nonce": secrets.token_urlsafe(18),
        "redirect_uri": PUBLIC_OAUTH_REDIRECT_URI,
    }
    encoded_payload = _b64url_encode(
        json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
    )
    signature = hmac.new(
        SESSION_SECRET.encode("utf-8"),
        encoded_payload.encode("utf-8"),
        hashlib.sha256,
    ).digest()
    return f"{encoded_payload}.{_b64url_encode(signature)}"


def _verify_public_oauth_state(state, max_age_seconds=900):
    if not SESSION_SECRET or not state or "." not in state:
        return None
    encoded_payload, encoded_sig = state.split(".", 1)
    try:
        supplied_sig = _b64url_decode(encoded_sig)
        expected_sig = hmac.new(
            SESSION_SECRET.encode("utf-8"),
            encoded_payload.encode("utf-8"),
            hashlib.sha256,
        ).digest()
        if not hmac.compare_digest(supplied_sig, expected_sig):
            return None
        payload = json.loads(_b64url_decode(encoded_payload).decode("utf-8"))
        now = int(time.time())
        issued_at = int(payload.get("iat", 0))
        if payload.get("aud") != "trendradar-instagram-public-oauth":
            return None
        if payload.get("redirect_uri") != PUBLIC_OAUTH_REDIRECT_URI:
            return None
        if issued_at <= 0 or now - issued_at < 0 or now - issued_at > max_age_seconds:
            return None
        return payload
    except Exception:
        return None


def _complete_oauth(code, redirect_uri):
    token_response = requests.post(
        "https://api.instagram.com/oauth/access_token",
        data={
            "client_id": APP_ID,
            "client_secret": APP_SECRET,
            "grant_type": "authorization_code",
            "redirect_uri": redirect_uri,
            "code": code,
        },
        timeout=45,
    )
    try:
        token_payload = token_response.json()
    except Exception:
        token_payload = {}
    if token_response.status_code >= 400 or not token_payload.get("access_token"):
        provider_error = token_payload.get("error_message") or token_payload.get("error_type")
        return 502, {
            "ok": False,
            "stage": "SHORT_TOKEN_EXCHANGE",
            "http": token_response.status_code,
            "provider_error": provider_error or "Instagram short-token exchange failed",
        }

    short_token = token_payload["access_token"]
    app_scoped_user_id = token_payload.get("user_id")
    raw_permissions = token_payload.get("permissions") or []
    if isinstance(raw_permissions, str):
        granted_permissions = [p.strip() for p in raw_permissions.split(",") if p.strip()]
    elif isinstance(raw_permissions, list):
        granted_permissions = [str(p).strip() for p in raw_permissions if str(p).strip()]
    else:
        granted_permissions = []

    long_response = requests.get(
        "https://graph.instagram.com/access_token",
        params={
            "grant_type": "ig_exchange_token",
            "client_secret": APP_SECRET,
            "access_token": short_token,
        },
        timeout=45,
    )
    try:
        long_payload = long_response.json()
    except Exception:
        long_payload = {}

    if long_response.status_code >= 400 or not long_payload.get("access_token"):
        safe_error = long_payload.get("error") if isinstance(long_payload, dict) else None
        if isinstance(safe_error, dict):
            safe_error = {
                "type": safe_error.get("type"),
                "code": safe_error.get("code"),
                "message": safe_error.get("message"),
            }
        else:
            safe_error = {"message": "Long-lived token exchange failed"}
        return 502, {
            "ok": False,
            "stage": "LONG_TOKEN_EXCHANGE",
            "http": long_response.status_code,
            "provider_error": safe_error,
        }

    token = long_payload["access_token"]
    expires_in = long_payload.get("expires_in")

    profile_http, profile = _graph(
        "GET",
        "me",
        token,
        params={"fields": "id,user_id,username,account_type"},
    )
    if profile_http >= 400:
        provider_error = profile.get("error") if isinstance(profile, dict) else None
        return 502, {
            "ok": False,
            "stage": "PROFILE_VERIFY",
            "http": profile_http,
            "provider_error": provider_error,
        }

    app_scoped_user_id = profile.get("id") or app_scoped_user_id
    professional_user_id = profile.get("user_id")
    account_type = str(profile.get("account_type") or "").strip()
    normalized_account_type = account_type.replace(" ", "_").upper()
    actual_username = str(profile.get("username") or "").strip().lstrip("@").lower()

    if EXPECTED_USERNAME and actual_username != EXPECTED_USERNAME:
        return 403, {
            "ok": False,
            "stage": "PROFILE_VERIFY",
            "error": "INSTAGRAM_ACCOUNT_MISMATCH",
            "expected_username": EXPECTED_USERNAME,
            "actual_username": actual_username or None,
        }
    if not professional_user_id:
        return 502, {
            "ok": False,
            "stage": "PROFILE_VERIFY",
            "error": "MISSING_PROFESSIONAL_USER_ID",
        }
    if normalized_account_type not in {"BUSINESS", "MEDIA_CREATOR"}:
        return 422, {
            "ok": False,
            "stage": "PROFILE_VERIFY",
            "error": "INSTAGRAM_PROFESSIONAL_ACCOUNT_REQUIRED",
            "account_type": account_type or None,
        }

    return 200, {
        "access_token": token,
        "user_id": professional_user_id,
        "app_scoped_user_id": app_scoped_user_id,
        "username": profile.get("username"),
        "account_type": account_type,
        "expires_in": expires_in,
        "granted_permissions": granted_permissions,
        "connected_at": int(time.time()),
    }


def _gateway_authorized():
    supplied = request.headers.get("X-TrendRadar-Gateway", "")
    return bool(
        OAUTH_GATEWAY_SECRET
        and supplied
        and hmac.compare_digest(supplied, OAUTH_GATEWAY_SECRET)
    )


def _parse_signed_request(signed_request):
    if not APP_SECRET or not signed_request or "." not in signed_request:
        return None
    encoded_sig, encoded_payload = signed_request.split(".", 1)
    try:
        sig = _b64url_decode(encoded_sig)
        payload_bytes = _b64url_decode(encoded_payload)
        expected = hmac.new(
            APP_SECRET.encode("utf-8"),
            encoded_payload.encode("utf-8"),
            hashlib.sha256,
        ).digest()
        if not hmac.compare_digest(sig, expected):
            return None
        payload = json.loads(payload_bytes.decode("utf-8"))
        if payload.get("algorithm", "HMAC-SHA256").upper() != "HMAC-SHA256":
            return None
        return payload
    except Exception:
        return None


def _delete_user(user_id):
    deleted = 0
    for sid, rec in list(TOKEN_STORE.items()):
        if str(rec.get("user_id")) == str(user_id):
            TOKEN_STORE.pop(sid, None)
            deleted += 1
    return deleted


@app.after_request
def security_headers(response):
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
    origin = request.headers.get("Origin", "").rstrip("/")
    if request.path.startswith("/api/public-oauth/") and origin == OAUTH_PUBLIC_ORIGIN:
        response.headers["Access-Control-Allow-Origin"] = OAUTH_PUBLIC_ORIGIN
        response.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
        response.headers["Access-Control-Allow-Headers"] = "Content-Type"
        response.headers["Vary"] = "Origin"
    return response


@app.post("/internal/refresh-instagram-token")
def refresh_instagram_token():
    supplied = request.headers.get("X-TrendRadar-Refresh", "")
    if not REFRESH_SECRET or not supplied or not hmac.compare_digest(supplied, REFRESH_SECRET):
        return jsonify({"ok": False, "error": "UNAUTHORIZED"}), 403
    if not _persistence_configured():
        return jsonify({"ok": False, "error": "PERSISTENCE_NOT_CONFIGURED"}), 503
    rec = _load_persisted_token_record()
    if not rec:
        return jsonify({"ok": False, "error": "NO_PERSISTED_TOKEN"}), 404
    status, refreshed = _refresh_long_lived_token(rec)
    if status != 200:
        return jsonify(refreshed), status
    return jsonify({
        "ok": True,
        "status": "REFRESHED_VERIFIED",
        "username": refreshed.get("username"),
        "account_type": refreshed.get("account_type"),
        "professional_user_id": refreshed.get("user_id"),
        "expires_in": refreshed.get("expires_in"),
        "public_publish_authorized": PUBLIC_PUBLISH_AUTHORIZED,
    })


@app.get("/health")
def health():
    return jsonify(
        {
            "ok": True,
            "service": "trendradar-instagram-oauth",
            "api_version": API_VERSION,
            "configured": _configured(),
            "persistence_configured": _persistence_configured(),
            "persistence_required": PERSISTENCE_REQUIRED,
            "public_publish_authorized": PUBLIC_PUBLISH_AUTHORIZED,
        }
    )


@app.get("/")
def home():
    configured = "READY" if _configured() else "WAITING FOR META APP CREDENTIALS"
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{APP_NAME}</title>
<style>
body{{font-family:Arial,sans-serif;max-width:760px;margin:40px auto;padding:0 18px;line-height:1.55}}
.card{{border:1px solid #ddd;border-radius:14px;padding:22px;margin:16px 0}}
a.button{{display:inline-block;padding:12px 18px;border-radius:10px;background:#111;color:#fff;text-decoration:none}}
small{{color:#555}}
</style></head><body>
<h1>Trend Radar — Instagram Reels</h1>
<div class="card">
<p>Creator-authorized Instagram integration for original Trend Radar short-form content.</p>
<p><strong>Configuration:</strong> {configured}</p>
<p><strong>Publishing safety:</strong> public publishing is {"enabled" if PUBLIC_PUBLISH_AUTHORIZED else "disabled"}.</p>
<p><a class="button" href="/auth/instagram/start">Connect Instagram Professional Account</a></p>
</div>
<p><a href="/privacy">Privacy</a> · <a href="/terms">Terms</a> · <a href="/data-deletion">Data deletion</a></p>
<small>Instagram Professional (Business or Creator) accounts only.</small>
</body></html>"""


@app.route("/api/public-oauth/start", methods=["GET", "OPTIONS"])
def public_oauth_start():
    if request.method == "OPTIONS":
        return ("", 204)
    if not _gateway_authorized():
        return jsonify({"ok": False, "error": "GATEWAY_UNAUTHORIZED"}), 403
    if not _configured() or not PUBLIC_OAUTH_REDIRECT_URI:
        return jsonify({"ok": False, "error": "META_APP_NOT_CONFIGURED"}), 503
    state = _make_public_oauth_state()
    params = {
        "client_id": APP_ID,
        "redirect_uri": PUBLIC_OAUTH_REDIRECT_URI,
        "response_type": "code",
        "scope": ",".join(SCOPES),
        "state": state,
        "enable_fb_login": "false",
    }
    return jsonify(
        {
            "ok": True,
            "authorization_url": "https://www.instagram.com/oauth/authorize?" + urlencode(params),
        }
    )


@app.route("/api/public-oauth/callback", methods=["POST", "OPTIONS"])
def public_oauth_callback():
    if request.method == "OPTIONS":
        return ("", 204)
    if not _gateway_authorized():
        return jsonify({"ok": False, "error": "GATEWAY_UNAUTHORIZED"}), 403
    payload = request.get_json(silent=True) or {}
    if payload.get("error"):
        return jsonify(
            {
                "ok": False,
                "error": payload.get("error"),
                "error_description": payload.get("error_description"),
            }
        ), 400

    state = str(payload.get("state") or "")
    if not _verify_public_oauth_state(state):
        return jsonify({"ok": False, "error": "INVALID_OAUTH_STATE"}), 400

    code = str(payload.get("code") or "").split("#", 1)[0].strip()
    if not code:
        return jsonify({"ok": False, "error": "MISSING_AUTHORIZATION_CODE"}), 400

    status, result = _complete_oauth(code, PUBLIC_OAUTH_REDIRECT_URI)
    if status != 200:
        return jsonify(result), status

    if not _persist_token_record(result):
        return jsonify({"ok": False, "error": "TOKEN_PERSISTENCE_FAILED"}), 503
    connection_id = secrets.token_urlsafe(24)
    TOKEN_STORE[f"public:{connection_id}"] = result
    return jsonify(
        {
            "ok": True,
            "status": "CONNECTED_VERIFIED",
            "connection_id": connection_id,
            "username": result.get("username"),
            "account_type": result.get("account_type"),
            "professional_user_id": result.get("user_id"),
            "public_publish_authorized": PUBLIC_PUBLISH_AUTHORIZED,
        }
    )


@app.get("/auth/instagram/start")
def instagram_start():
    if not _configured():
        return jsonify(
            {
                "ok": False,
                "error": "META_APP_NOT_CONFIGURED",
                "required_env": [
                    "INSTAGRAM_APP_ID",
                    "INSTAGRAM_APP_SECRET",
                    "INSTAGRAM_REDIRECT_URI",
                ],
            }
        ), 503
    state = secrets.token_urlsafe(32)
    session["oauth_state"] = state
    _sid()
    params = {
        "client_id": APP_ID,
        "redirect_uri": REDIRECT_URI,
        "response_type": "code",
        "scope": ",".join(SCOPES),
        "state": state,
        "enable_fb_login": "false",
    }
    return redirect("https://www.instagram.com/oauth/authorize?" + urlencode(params))


@app.get("/auth/instagram/callback")
def instagram_callback():
    if request.args.get("error"):
        return jsonify(
            {
                "ok": False,
                "error": request.args.get("error"),
                "error_reason": request.args.get("error_reason"),
                "error_description": request.args.get("error_description"),
            }
        ), 400

    state = request.args.get("state", "")
    if not state or state != session.pop("oauth_state", None):
        return jsonify({"ok": False, "error": "INVALID_OAUTH_STATE"}), 400

    code = request.args.get("code", "").split("#", 1)[0].strip()
    if not code:
        return jsonify({"ok": False, "error": "MISSING_AUTHORIZATION_CODE"}), 400

    status, rec = _complete_oauth(code, REDIRECT_URI)
    if status != 200:
        return jsonify(rec), status

    if not _persist_token_record(rec):
        return jsonify({"ok": False, "error": "TOKEN_PERSISTENCE_FAILED"}), 503
    TOKEN_STORE[_sid()] = rec
    return redirect(url_for("share"))


@app.get("/share")
def share():
    rec = _token_record()
    if not rec:
        return redirect(url_for("home"))
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Share to Instagram — Trend Radar</title>
<style>
body{{font-family:Arial,sans-serif;max-width:760px;margin:36px auto;padding:0 18px;line-height:1.5}}
.card{{border:1px solid #ddd;border-radius:14px;padding:20px;margin:16px 0}}
button{{padding:12px 18px;border:0;border-radius:10px;background:#111;color:white;cursor:pointer}}
textarea{{width:100%;min-height:100px}} input[type=file]{{width:100%}}
.warn{{background:#fff8df;padding:12px;border-radius:10px}}
</style></head><body>
<h1>Share to Instagram Reels</h1>
<div class="card">
<p><strong>Connected account:</strong> @{rec.get("username") or "unknown"}</p>
<p><strong>Account type:</strong> {rec.get("account_type") or "unknown"}</p>
<p><strong>Professional user ID:</strong> {rec.get("user_id") or "unknown"}</p>
<p><strong>Granted permissions:</strong> {", ".join(rec.get("granted_permissions") or []) or "not returned by token response"}</p>
</div>
<div class="card">
<form method="post" action="/api/reel" enctype="multipart/form-data">
<label>Original MP4</label><br><input type="file" name="video" accept="video/mp4" required><br><br>
<label>Caption</label><br><textarea name="caption" maxlength="2200"></textarea><br><br>
<label><input type="checkbox" name="consent" value="true" required> I confirm this is original/authorized media and I explicitly request this Instagram operation.</label><br><br>
<button type="submit">Prepare Reel</button>
</form>
</div>
<div class="warn">
Public publication is currently <strong>{"ENABLED" if PUBLIC_PUBLISH_AUTHORIZED else "DISABLED"}</strong>.
When disabled, Trend Radar creates and verifies the Reel container but does not call media_publish.
</div>
<p><a href="/disconnect">Disconnect</a></p>
</body></html>"""


@app.post("/api/reel")
def prepare_reel():
    _cleanup_media()
    rec = _token_record()
    if not rec:
        return jsonify({"ok": False, "error": "NOT_CONNECTED"}), 401
    if request.form.get("consent") != "true":
        return jsonify({"ok": False, "error": "EXPLICIT_CONSENT_REQUIRED"}), 400

    upload = request.files.get("video")
    if not upload or not upload.filename:
        return jsonify({"ok": False, "error": "VIDEO_REQUIRED"}), 400
    if not upload.filename.lower().endswith(".mp4"):
        return jsonify({"ok": False, "error": "MP4_REQUIRED"}), 400

    media_id = uuid.uuid4().hex
    path = MEDIA_DIR / f"{media_id}.mp4"
    upload.save(path)
    size = path.stat().st_size
    if size <= 0:
        path.unlink(missing_ok=True)
        return jsonify({"ok": False, "error": "EMPTY_VIDEO"}), 400

    MEDIA_STORE[media_id] = {
        "path": str(path),
        "created_at": time.time(),
        "owner_sid": _sid(),
    }
    video_url = f"{_base_url()}/media/{media_id}.mp4"
    caption = (request.form.get("caption") or "").strip()

    create_http, create_payload = _graph(
        "POST",
        f"{rec['user_id']}/media",
        rec["access_token"],
        data={
            "media_type": "REELS",
            "video_url": video_url,
            "caption": caption,
            "share_to_feed": "false",
        },
    )
    container_id = create_payload.get("id")
    if create_http >= 400 or not container_id:
        return jsonify(
            {
                "ok": False,
                "stage": "CREATE_CONTAINER",
                "http": create_http,
                "provider": create_payload,
            }
        ), 502

    status_payload = {}
    for _ in range(20):
        time.sleep(3)
        status_http, status_payload = _graph(
            "GET",
            container_id,
            rec["access_token"],
            params={"fields": "status_code,status"},
        )
        if status_http >= 400:
            return jsonify(
                {
                    "ok": False,
                    "stage": "POLL_CONTAINER",
                    "http": status_http,
                    "provider": status_payload,
                    "container_id": container_id,
                }
            ), 502
        code = status_payload.get("status_code")
        if code == "FINISHED":
            break
        if code in {"ERROR", "EXPIRED"}:
            return jsonify(
                {
                    "ok": False,
                    "stage": "PROCESS_CONTAINER",
                    "provider": status_payload,
                    "container_id": container_id,
                }
            ), 502
    else:
        return jsonify(
            {
                "ok": False,
                "stage": "PROCESS_CONTAINER",
                "error": "TIMEOUT_WAITING_FOR_FINISHED",
                "provider": status_payload,
                "container_id": container_id,
            }
        ), 504

    if not PUBLIC_PUBLISH_AUTHORIZED:
        return jsonify(
            {
                "ok": True,
                "status": "PREPARED_NOT_PUBLISHED",
                "container_id": container_id,
                "provider_status": status_payload,
                "public_publish_authorized": False,
                "message": "Container is FINISHED. media_publish was intentionally not called.",
            }
        ), 201

    publish_http, publish_payload = _graph(
        "POST",
        f"{rec['user_id']}/media_publish",
        rec["access_token"],
        data={"creation_id": container_id},
    )
    if publish_http >= 400 or not publish_payload.get("id"):
        return jsonify(
            {
                "ok": False,
                "stage": "MEDIA_PUBLISH",
                "http": publish_http,
                "provider": publish_payload,
                "container_id": container_id,
            }
        ), 502

    try:
        path.unlink(missing_ok=True)
        MEDIA_STORE.pop(media_id, None)
    except Exception:
        pass

    return jsonify(
        {
            "ok": True,
            "status": "PUBLISHED",
            "container_id": container_id,
            "media_id": publish_payload.get("id"),
            "public_publish_authorized": True,
        }
    ), 201


@app.get("/media/<media_id>.mp4")
def media(media_id):
    _cleanup_media()
    rec = MEDIA_STORE.get(media_id)
    if not rec:
        return jsonify({"ok": False, "error": "MEDIA_NOT_FOUND_OR_EXPIRED"}), 404
    path = Path(rec["path"])
    if not path.exists():
        return jsonify({"ok": False, "error": "MEDIA_NOT_FOUND_OR_EXPIRED"}), 404
    return send_file(path, mimetype="video/mp4", conditional=True)


@app.get("/disconnect")
def disconnect():
    TOKEN_STORE.pop(_sid(), None)
    session.clear()
    return redirect(url_for("home"))


@app.route("/deauthorize", methods=["GET", "POST"])
def deauthorize():
    signed = request.values.get("signed_request", "")
    payload = _parse_signed_request(signed)
    if payload and payload.get("user_id"):
        _delete_user(payload["user_id"])
    else:
        TOKEN_STORE.pop(_sid(), None)
    session.clear()
    return jsonify({"ok": True, "status": "DEAUTHORIZED"})


@app.route("/data-deletion", methods=["GET", "POST"])
def data_deletion():
    if request.method == "GET":
        return Response(
            """<!doctype html><html><head><meta charset="utf-8"><title>Trend Radar Data Deletion</title></head>
<body><h1>Instagram data deletion</h1>
<p>Disconnecting Instagram removes the active server-side authorization record for the connected account.</p>
<p>Meta may also send a signed data-deletion request to this endpoint. Trend Radar verifies that request and deletes matching authorization data.</p>
<p>Contact: trendradarar@gmail.com</p></body></html>""",
            mimetype="text/html",
        )

    payload = _parse_signed_request(request.values.get("signed_request", ""))
    if not payload or not payload.get("user_id"):
        return jsonify({"ok": False, "error": "INVALID_SIGNED_REQUEST"}), 400
    user_id = str(payload["user_id"])
    _delete_user(user_id)
    confirmation = secrets.token_urlsafe(18)
    DELETION_STORE[confirmation] = {"user_id": user_id, "status": "deleted"}
    return jsonify(
        {
            "url": f"{_base_url()}/data-deletion/status/{confirmation}",
            "confirmation_code": confirmation,
        }
    )


@app.get("/data-deletion/status/<confirmation>")
def deletion_status(confirmation):
    rec = DELETION_STORE.get(confirmation)
    if not rec:
        return jsonify({"status": "unknown"}), 404
    return jsonify({"status": rec["status"], "confirmation_code": confirmation})


@app.get("/privacy")
def privacy():
    return Response(
        """<!doctype html><html><head><meta charset="utf-8"><title>Privacy — Trend Radar Instagram</title></head>
<body><h1>Privacy — Trend Radar Instagram integration</h1>
<p>Trend Radar uses the Instagram API with Instagram Login for creator-authorized access to Instagram Professional accounts.</p>
<p>Requested permissions are limited to basic professional-account identity and content publishing. Access tokens are handled server-side and are not intentionally exposed in browser responses.</p>
<p>Instagram data is used only to identify the authorized professional account and to perform publishing actions explicitly requested by the authorized user. Trend Radar does not sell Instagram user data.</p>
<p>Users can disconnect the integration and request deletion through the data-deletion endpoint. Contact: trendradarar@gmail.com.</p>
</body></html>""",
        mimetype="text/html",
    )


@app.get("/terms")
def terms():
    return Response(
        """<!doctype html><html><head><meta charset="utf-8"><title>Terms — Trend Radar Instagram</title></head>
<body><h1>Terms — Trend Radar Instagram integration</h1>
<p>The integration is intended for authorized creators/businesses using Instagram Professional accounts and for original or otherwise authorized media.</p>
<p>The user controls account authorization and each publishing request. Content must comply with Instagram/Meta policies and applicable law.</p>
<p>Trend Radar does not claim ownership of user media and does not authorize public publication unless the governed publishing gate is enabled.</p>
<p>Contact: trendradarar@gmail.com.</p>
</body></html>""",
        mimetype="text/html",
    )


if __name__ == "__main__":
    port = int(os.getenv("PORT", "10000"))
    app.run(host="0.0.0.0", port=port)

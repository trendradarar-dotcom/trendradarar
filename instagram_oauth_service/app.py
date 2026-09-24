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
from flask import Flask, Response, jsonify, redirect, request, send_file, session, url_for

APP_NAME = "Trend Radar — Instagram Reels"
API_VERSION = os.getenv("INSTAGRAM_API_VERSION", "v26.0").strip() or "v26.0"
APP_ID = os.getenv("INSTAGRAM_APP_ID", "").strip()
APP_SECRET = os.getenv("INSTAGRAM_APP_SECRET", "").strip()
REDIRECT_URI = os.getenv("INSTAGRAM_REDIRECT_URI", "").strip()
PUBLIC_BASE_URL = os.getenv("PUBLIC_BASE_URL", "").strip().rstrip("/")
SCOPES = (
    "instagram_business_basic",
    "instagram_business_content_publish",
)
PUBLIC_PUBLISH_AUTHORIZED = os.getenv(
    "INSTAGRAM_PUBLIC_PUBLISH_AUTHORIZED", "false"
).lower() == "true"

app = Flask(__name__)
app.secret_key = os.getenv("SESSION_SECRET") or secrets.token_urlsafe(48)
app.config["MAX_CONTENT_LENGTH"] = 120 * 1024 * 1024

TOKEN_STORE = {}
MEDIA_STORE = {}
DELETION_STORE = {}
MEDIA_DIR = Path(tempfile.gettempdir()) / "trendradar_instagram_review_media"
MEDIA_DIR.mkdir(parents=True, exist_ok=True)


def _configured():
    return bool(APP_ID and APP_SECRET and REDIRECT_URI)


def _sid():
    sid = session.get("sid")
    if not sid:
        sid = secrets.token_urlsafe(24)
        session["sid"] = sid
    return sid


def _token_record():
    return TOKEN_STORE.get(_sid())


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


def _b64url_decode(value):
    value += "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode(value.encode("utf-8"))


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
    return response


@app.get("/health")
def health():
    return jsonify(
        {
            "ok": True,
            "service": "trendradar-instagram-oauth",
            "api_version": API_VERSION,
            "configured": _configured(),
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
        "enable_fb_login": "0",
        "force_authentication": "1",
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

    token_response = requests.post(
        "https://api.instagram.com/oauth/access_token",
        data={
            "client_id": APP_ID,
            "client_secret": APP_SECRET,
            "grant_type": "authorization_code",
            "redirect_uri": REDIRECT_URI,
            "code": code,
        },
        timeout=45,
    )
    try:
        token_payload = token_response.json()
    except Exception:
        token_payload = {"raw": token_response.text[:1000]}
    if token_response.status_code >= 400 or not token_payload.get("access_token"):
        return jsonify(
            {
                "ok": False,
                "stage": "SHORT_TOKEN_EXCHANGE",
                "http": token_response.status_code,
                "provider": token_payload,
            }
        ), 502

    short_token = token_payload["access_token"]
    user_id = token_payload.get("user_id")

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
        long_payload = {"raw": long_response.text[:1000]}

    token = long_payload.get("access_token") or short_token
    expires_in = long_payload.get("expires_in")

    profile_http, profile = _graph(
        "GET",
        "me",
        token,
        params={"fields": "id,username,account_type"},
    )
    if profile_http >= 400:
        return jsonify(
            {
                "ok": False,
                "stage": "PROFILE_VERIFY",
                "http": profile_http,
                "provider": profile,
            }
        ), 502

    user_id = profile.get("id") or user_id
    rec = {
        "access_token": token,
        "user_id": user_id,
        "username": profile.get("username"),
        "account_type": profile.get("account_type"),
        "expires_in": expires_in,
        "connected_at": int(time.time()),
    }
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

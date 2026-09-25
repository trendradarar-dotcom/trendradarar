import os

import requests
from flask import Flask, jsonify, request

UPSTREAM_URL = os.getenv(
    "INSTAGRAM_OAUTH_UPSTREAM_URL",
    "https://trendradar-instagram-oauth.onrender.com",
).strip().rstrip("/")
GATEWAY_SECRET = os.getenv("INSTAGRAM_OAUTH_GATEWAY_SECRET", "").strip()
PUBLIC_ORIGIN = os.getenv(
    "INSTAGRAM_OAUTH_PUBLIC_ORIGIN",
    "https://trendradar.com.co",
).strip().rstrip("/")

app = Flask(__name__)


def _origin_allowed():
    return request.headers.get("Origin", "").rstrip("/") == PUBLIC_ORIGIN


def _configured():
    return bool(UPSTREAM_URL and GATEWAY_SECRET and PUBLIC_ORIGIN)


@app.after_request
def security_headers(response):
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
    origin = request.headers.get("Origin", "").rstrip("/")
    if request.path.startswith("/oauth/") and origin == PUBLIC_ORIGIN:
        response.headers["Access-Control-Allow-Origin"] = PUBLIC_ORIGIN
        response.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
        response.headers["Access-Control-Allow-Headers"] = "Content-Type"
        response.headers["Vary"] = "Origin"
    return response


@app.get("/health")
def health():
    return jsonify(
        {
            "ok": True,
            "service": "trendradar-instagram-gateway",
            "configured": _configured(),
        }
    )


@app.route("/oauth/start", methods=["GET", "OPTIONS"])
def oauth_start():
    if request.method == "OPTIONS":
        return ("", 204)
    if not _configured():
        return jsonify({"ok": False, "error": "GATEWAY_NOT_CONFIGURED"}), 503
    if not _origin_allowed():
        return jsonify({"ok": False, "error": "ORIGIN_NOT_ALLOWED"}), 403

    try:
        upstream = requests.get(
            f"{UPSTREAM_URL}/api/public-oauth/start",
            headers={
                "X-TrendRadar-Gateway": GATEWAY_SECRET,
                "Accept": "application/json",
            },
            timeout=30,
        )
        payload = upstream.json()
    except Exception:
        return jsonify({"ok": False, "error": "UPSTREAM_UNAVAILABLE"}), 502

    if upstream.status_code >= 400:
        return jsonify(
            {
                "ok": False,
                "error": payload.get("error", "UPSTREAM_REJECTED"),
            }
        ), upstream.status_code

    return jsonify(
        {
            "ok": True,
            "authorization_url": payload.get("authorization_url"),
        }
    )


@app.route("/oauth/callback", methods=["POST", "OPTIONS"])
def oauth_callback():
    if request.method == "OPTIONS":
        return ("", 204)
    if not _configured():
        return jsonify({"ok": False, "error": "GATEWAY_NOT_CONFIGURED"}), 503
    if not _origin_allowed():
        return jsonify({"ok": False, "error": "ORIGIN_NOT_ALLOWED"}), 403

    browser_payload = request.get_json(silent=True) or {}
    allowed_payload = {
        "code": str(browser_payload.get("code") or ""),
        "state": str(browser_payload.get("state") or ""),
        "error": str(browser_payload.get("error") or ""),
        "error_description": str(browser_payload.get("error_description") or ""),
    }

    try:
        upstream = requests.post(
            f"{UPSTREAM_URL}/api/public-oauth/callback",
            headers={
                "X-TrendRadar-Gateway": GATEWAY_SECRET,
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
            json=allowed_payload,
            timeout=60,
        )
        payload = upstream.json()
    except Exception:
        return jsonify({"ok": False, "error": "UPSTREAM_UNAVAILABLE"}), 502

    safe_payload = {
        "ok": bool(payload.get("ok")),
        "status": payload.get("status"),
        "error": payload.get("error"),
        "stage": payload.get("stage"),
        "username": payload.get("username"),
        "account_type": payload.get("account_type"),
        "professional_user_id": payload.get("professional_user_id"),
        "public_publish_authorized": payload.get("public_publish_authorized"),
    }
    return jsonify(safe_payload), upstream.status_code


if __name__ == "__main__":
    port = int(os.getenv("PORT", "10000"))
    app.run(host="0.0.0.0", port=port)

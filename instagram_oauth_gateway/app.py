import html
import os

import requests
from flask import Flask, Response, jsonify, redirect, request

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
    response.headers["Cache-Control"] = "no-store"
    response.headers["Content-Security-Policy"] = "default-src 'none'; style-src 'unsafe-inline'; base-uri 'none'; form-action 'none'"
    origin = request.headers.get("Origin", "").rstrip("/")
    if request.path.startswith("/oauth/") and origin == PUBLIC_ORIGIN:
        response.headers["Access-Control-Allow-Origin"] = PUBLIC_ORIGIN
        response.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
        response.headers["Access-Control-Allow-Headers"] = "Content-Type"
        response.headers["Vary"] = "Origin"
    return response


@app.get("/")
def home():
    return Response(
        """<!doctype html><html lang="ar" dir="rtl"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="robots" content="noindex,nofollow"><title>Trend Radar — Instagram</title>
<style>body{font-family:system-ui;background:#0b1020;color:#fff;display:grid;place-items:center;min-height:100vh;margin:0}
main{max-width:620px;padding:28px}.btn{display:block;text-align:center;padding:14px;border-radius:12px;background:#fff;color:#111;text-decoration:none;font-weight:700}</style>
</head><body><main><h1>ربط Instagram مع رادار الترند</h1>
<p>يتم التفويض مباشرة عبر Instagram. النشر العام معطّل.</p>
<a class="btn" href="/oauth/browser/start">متابعة إلى Instagram</a></main></body></html>""",
        mimetype="text/html",
    )


@app.get("/oauth/browser/start")
def oauth_browser_start():
    if not _configured():
        return jsonify({"ok": False, "error": "GATEWAY_NOT_CONFIGURED"}), 503
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

    authorization_url = str(payload.get("authorization_url") or "")
    if upstream.status_code >= 400 or not authorization_url.startswith(
        "https://www.instagram.com/oauth/authorize?"
    ):
        return jsonify(
            {
                "ok": False,
                "error": payload.get("error", "UPSTREAM_REJECTED"),
            }
        ), upstream.status_code if upstream.status_code >= 400 else 502

    return redirect(authorization_url, code=302)


@app.get("/oauth/browser/callback")
def oauth_browser_callback():
    if not _configured():
        return jsonify({"ok": False, "error": "GATEWAY_NOT_CONFIGURED"}), 503

    allowed_payload = {
        "code": str(request.args.get("code") or ""),
        "state": str(request.args.get("state") or ""),
        "error": str(request.args.get("error") or ""),
        "error_description": str(request.args.get("error_description") or ""),
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
        upstream_status = upstream.status_code
    except Exception:
        payload = {"ok": False, "error": "UPSTREAM_UNAVAILABLE"}
        upstream_status = 502

    if upstream_status >= 400 or not payload.get("ok"):
        error_code = html.escape(
            str(payload.get("error") or payload.get("stage") or "OAUTH_CALLBACK_FAILED")
        )
        return Response(
            f"""<!doctype html><html lang="ar" dir="rtl"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="robots" content="noindex,nofollow"><title>تعذر ربط Instagram</title>
<style>body{{font-family:system-ui;background:#0b1020;color:#fff;display:grid;place-items:center;min-height:100vh;margin:0}}
main{{max-width:620px;padding:28px}}.box{{padding:18px;border:1px solid #c66;border-radius:14px}}</style>
</head><body><main><div class="box"><h1>لم يكتمل الربط</h1>
<p>لم يتم نشر أي محتوى.</p><p>الرمز: {error_code}</p></div></main></body></html>""",
            status=upstream_status,
            mimetype="text/html",
        )

    username = html.escape(str(payload.get("username") or "trendradarar"))
    account_type = html.escape(str(payload.get("account_type") or "Professional"))
    return Response(
        f"""<!doctype html><html lang="ar" dir="rtl"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="robots" content="noindex,nofollow"><title>تم ربط Instagram</title>
<style>body{{font-family:system-ui;background:#0b1020;color:#fff;display:grid;place-items:center;min-height:100vh;margin:0}}
main{{max-width:620px;padding:28px}}.box{{padding:18px;border:1px solid #3c8;border-radius:14px}}</style>
</head><body><main><div class="box"><h1>تم الربط والتحقق بنجاح</h1>
<p>الحساب: @{username}</p><p>النوع: {account_type}</p>
<p>النشر العام ما زال معطّلًا.</p></div></main></body></html>""",
        mimetype="text/html",
    )


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

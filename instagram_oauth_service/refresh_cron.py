import json
import os
import sys

import requests

URL = os.getenv("INSTAGRAM_REFRESH_URL", "").strip()
SECRET = os.getenv("INSTAGRAM_REFRESH_SECRET", "").strip()

if not URL or not SECRET:
    print(json.dumps({"ok": False, "status": "MISSING_CRON_CONFIGURATION"}))
    raise SystemExit(2)

try:
    response = requests.post(
        URL,
        headers={"X-TrendRadar-Refresh": SECRET},
        timeout=60,
    )
    try:
        payload = response.json()
    except Exception:
        payload = {}

    safe = {
        "ok": bool(payload.get("ok")),
        "status": payload.get("status") or payload.get("error") or "UNKNOWN",
        "http": response.status_code,
        "username": payload.get("username"),
        "account_type": payload.get("account_type"),
        "professional_user_id": payload.get("professional_user_id"),
        "expires_in": payload.get("expires_in"),
        "public_publish_authorized": payload.get("public_publish_authorized"),
    }
    print(json.dumps(safe, sort_keys=True))

    if response.status_code != 200:
        raise SystemExit(1)
    if payload.get("status") != "REFRESHED_VERIFIED":
        raise SystemExit(1)
    if str(payload.get("username") or "").lower() != "trendradarar":
        raise SystemExit(1)
    if str(payload.get("account_type") or "").upper() not in {"BUSINESS", "MEDIA_CREATOR"}:
        raise SystemExit(1)
    if payload.get("public_publish_authorized") is not False:
        raise SystemExit(1)
except requests.RequestException as exc:
    print(json.dumps({
        "ok": False,
        "status": "REFRESH_REQUEST_FAILED",
        "exception_type": type(exc).__name__,
    }))
    raise SystemExit(1)

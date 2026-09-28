import hashlib
import hmac
import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request


class WatchdogError(RuntimeError):
    pass


def _is_allowed_url(url):
    try:
        parsed = urllib.parse.urlparse(str(url or ""))
    except Exception:
        return False
    if parsed.scheme == "https" and parsed.netloc:
        return True
    return parsed.scheme == "http" and parsed.hostname in {"127.0.0.1", "localhost", "::1"}


def _json_request(url, method="GET", body=None, headers=None, timeout=15):
    if not _is_allowed_url(url):
        raise WatchdogError("URL must be HTTPS (localhost HTTP allowed for tests)")
    raw = None
    request_headers = {"Accept": "application/json", "User-Agent": "TrendRadar-TikTok-OpsWatchdog/1"}
    request_headers.update(headers or {})
    if body is not None:
        raw = json.dumps(body, sort_keys=True, separators=(",", ":")).encode("utf-8")
        request_headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=raw, headers=request_headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as response:
            status = int(response.status)
            payload_raw = response.read()
    except urllib.error.HTTPError as exc:
        status = int(exc.code)
        payload_raw = exc.read()
    except Exception as exc:
        raise WatchdogError("network_error") from exc
    try:
        payload = json.loads(payload_raw.decode("utf-8")) if payload_raw else {}
    except Exception as exc:
        raise WatchdogError("invalid_json_response") from exc
    return status, payload


def fetch_health(url, timeout=15):
    try:
        status, payload = _json_request(url, timeout=timeout)
        if not isinstance(payload, dict):
            raise WatchdogError("health_payload_not_object")
        attention = bool(
            status >= 500
            or payload.get("attention_required")
            or payload.get("durable_state_ready") is False
            or payload.get("ok") is False
        )
        return {
            "reachable": True,
            "http_status": status,
            "attention_required": attention,
            "health": {
                "ok": payload.get("ok"),
                "durable_state_ready": payload.get("durable_state_ready"),
                "attention_required": payload.get("attention_required"),
                "unknown_count": payload.get("unknown_count"),
                "stale_nonterminal_count": payload.get("stale_nonterminal_count"),
                "active_count": payload.get("active_count"),
                "kill_switch_active": payload.get("kill_switch_active"),
                "mutations_allowed": payload.get("mutations_allowed"),
            },
        }
    except WatchdogError as exc:
        return {
            "reachable": False,
            "http_status": 0,
            "attention_required": True,
            "error": str(exc),
            "health": {},
        }


def build_alert(health_result, now=None):
    now = int(time.time() if now is None else now)
    return {
        "schema": "trendradar.tiktok.ops_alert.v1",
        "occurred_at": now,
        "severity": "critical" if not health_result.get("reachable") else "warning",
        "component": "tiktok-publisher",
        "attention_required": True,
        "reachable": bool(health_result.get("reachable")),
        "http_status": int(health_result.get("http_status") or 0),
        "health": dict(health_result.get("health") or {}),
        "error": health_result.get("error"),
    }


def _signature(secret, body_bytes):
    return "sha256=" + hmac.new(
        secret.encode("utf-8"), body_bytes, hashlib.sha256
    ).hexdigest()


def send_alert(webhook_url, webhook_secret, alert, timeout=15):
    if not webhook_secret:
        raise WatchdogError("TIKTOK_ALERT_WEBHOOK_SECRET is required")
    if not _is_allowed_url(webhook_url):
        raise WatchdogError("alert webhook must be HTTPS")
    body = json.dumps(alert, sort_keys=True, separators=(",", ":")).encode("utf-8")
    headers = {
        "Content-Type": "application/json",
        "X-TrendRadar-Signature": _signature(webhook_secret, body),
        "X-TrendRadar-Event": "tiktok-ops-alert",
    }
    req = urllib.request.Request(webhook_url, data=body, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as response:
            status = int(response.status)
            response.read()
    except urllib.error.HTTPError as exc:
        status = int(exc.code)
        exc.read()
    except Exception as exc:
        raise WatchdogError("alert_delivery_network_error") from exc
    if status < 200 or status >= 300:
        raise WatchdogError("alert_delivery_http_error")
    return status


def main():
    health_url = os.environ.get("TIKTOK_OPS_HEALTH_URL", "").strip()
    webhook_url = os.environ.get("TIKTOK_ALERT_WEBHOOK_URL", "").strip()
    webhook_secret = os.environ.get("TIKTOK_ALERT_WEBHOOK_SECRET", "").strip()
    if not health_url:
        raise SystemExit("TIKTOK_OPS_HEALTH_URL is required")

    result = fetch_health(health_url)
    if not result["attention_required"]:
        print(json.dumps({"ok": True, "alert_sent": False, "health": result}, sort_keys=True))
        return

    if not webhook_url or not webhook_secret:
        print(json.dumps({
            "ok": False,
            "alert_sent": False,
            "reason": "alert_delivery_not_configured",
            "health": result,
        }, sort_keys=True))
        raise SystemExit(2)

    alert = build_alert(result)
    try:
        status = send_alert(webhook_url, webhook_secret, alert)
    except WatchdogError as exc:
        print(json.dumps({
            "ok": False,
            "alert_sent": False,
            "reason": str(exc),
            "health": result,
        }, sort_keys=True))
        raise SystemExit(3)

    print(json.dumps({
        "ok": False,
        "alert_sent": True,
        "alert_http_status": status,
        "health": result,
    }, sort_keys=True))
    raise SystemExit(1)


if __name__ == "__main__":
    main()

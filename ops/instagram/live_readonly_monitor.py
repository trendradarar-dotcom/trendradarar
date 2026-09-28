import argparse
import json
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path


BACKEND_URL = "https://trendradar-instagram-oauth.onrender.com/health"
GATEWAY_URL = "https://auth.trendradar.com.co/health"


def fetch_json(url, *, attempts=8, delay=10, timeout=20):
    errors = []
    for attempt in range(1, attempts + 1):
        try:
            request = urllib.request.Request(
                url,
                headers={"User-Agent": "TrendRadar-Instagram-ReadOnly-Monitor/1.0"},
                method="GET",
            )
            with urllib.request.urlopen(request, timeout=timeout) as response:
                body = json.loads(response.read().decode("utf-8"))
                return {
                    "attempt": attempt,
                    "status": response.status,
                    "body": body,
                    "errors_before_success": errors,
                }
        except Exception as exc:
            errors.append({
                "attempt": attempt,
                "type": type(exc).__name__,
                "message": str(exc)[:300],
            })
            if attempt < attempts:
                time.sleep(delay)
    raise RuntimeError({"url": url, "errors": errors})


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--expected-backend-revision", required=True)
    parser.add_argument("--evidence", required=True)
    args = parser.parse_args()

    backend = fetch_json(BACKEND_URL)
    gateway = fetch_json(GATEWAY_URL)

    b = backend["body"]
    g = gateway["body"]

    expected_backend = {
        "service": "trendradar-instagram-oauth",
        "build_revision": args.expected_backend_revision,
        "ok": True,
        "public_publish_authorized": False,
        "instagram_publish_enabled": False,
        "browser_public_publish_enabled": False,
        "exact_account_binding_configured": True,
        "oauth_relink_hard_disabled": True,
        "persistence_configured": True,
        "persistence_required": True,
        "publisher_m2m_configured": True,
    }
    for key, expected in expected_backend.items():
        if b.get(key) != expected:
            raise AssertionError({
                "component": "backend",
                "field": key,
                "expected": expected,
                "actual": b.get(key),
            })

    if g.get("service") != "trendradar-instagram-gateway" or g.get("ok") is not True:
        raise AssertionError({"component": "gateway", "body": g})

    evidence = {
        "captured_at": datetime.now(timezone.utc).isoformat(),
        "mode": "READ_ONLY",
        "backend": backend,
        "gateway": gateway,
        "assertions": {
            "backend_expected_revision": True,
            "public_publish_authorized_false": True,
            "instagram_publish_enabled_false": True,
            "browser_public_publish_enabled_false": True,
            "exact_account_binding_configured": True,
            "oauth_relink_hard_disabled": True,
            "persistence_configured": True,
            "persistence_required": True,
            "publisher_m2m_configured": True,
            "gateway_healthy": True,
        },
        "result": "PASS",
    }
    Path(args.evidence).write_text(
        json.dumps(evidence, indent=2, sort_keys=True),
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()

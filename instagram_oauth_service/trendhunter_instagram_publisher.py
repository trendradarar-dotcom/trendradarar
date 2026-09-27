import argparse
import hashlib
import json
import os
import sys
import time
from pathlib import Path

import requests


TERMINAL_SUCCESS = {"VERIFIED"}
TERMINAL_FAIL_CLOSED = {
    "UNKNOWN",
    "FAILED_FINAL",
    "PUBLISHED_UNVERIFIED",
    "HOLD_PUBLIC_DISABLED",
    "HOLD_MEDIA_HOST",
    "HOLD_CREDENTIAL",
    "HOLD_RATE_LIMIT",
    "HOLD_BLAST_RADIUS",
    "HOLD_CONCURRENCY",
    "HOLD_CIRCUIT_OPEN",
    "HOLD_KILL_SWITCH",
    "HOLD_QUEUE_LIMIT",
    "HOLD_MUTATION_RATE",
    "HOLD_ATTEMPT_LIMIT",
}


class InstagramPublisherClient:
    def __init__(self, base_url=None, secret=None, timeout=75):
        self.base_url = (
            base_url
            or os.getenv("INSTAGRAM_PUBLISHER_BASE_URL", "")
        ).strip().rstrip("/")
        self.secret = (
            secret
            or os.getenv("INSTAGRAM_PUBLISH_M2M_SECRET", "")
        ).strip()
        self.timeout = int(timeout)
        if not self.base_url or not self.secret:
            raise RuntimeError("INSTAGRAM_PUBLISHER_CLIENT_NOT_CONFIGURED")

    @property
    def headers(self):
        return {
            "X-TrendRadar-Publish": self.secret,
            "Accept": "application/json",
        }

    def _request_with_cold_start_retry(self, method, path, **kwargs):
        delays = (0, 5, 15, 30)
        last_error = None
        for delay in delays:
            if delay:
                time.sleep(delay)
            try:
                response = requests.request(
                    method,
                    self.base_url + path,
                    headers={**self.headers, **kwargs.pop("headers", {})},
                    timeout=self.timeout,
                    **kwargs,
                )
                if response.status_code not in {502, 503, 504}:
                    return response
                last_error = RuntimeError(f"TEMPORARY_HTTP_{response.status_code}")
            except requests.RequestException as exc:
                last_error = exc
        raise RuntimeError("PUBLISHER_UNAVAILABLE_AFTER_RETRY") from last_error

    @staticmethod
    def _json(response):
        try:
            return response.json()
        except Exception as exc:
            raise RuntimeError("PUBLISHER_NON_JSON_RESPONSE") from exc

    def upload_media(self, *, video_path, content_asset_id, media_metadata):
        path = Path(video_path)
        data = path.read_bytes()
        sha256 = hashlib.sha256(data).hexdigest()
        response = self._request_with_cold_start_retry(
            "POST",
            "/internal/publish/media",
            files={"video": (path.name, data, "video/mp4")},
            data={
                "content_asset_id": content_asset_id,
                "asset_sha256": sha256,
                "media_metadata": json.dumps(media_metadata, separators=(",", ":"), sort_keys=True),
            },
        )
        payload = self._json(response)
        if response.status_code not in {200, 201} or not payload.get("ok"):
            raise RuntimeError(payload.get("error") or f"MEDIA_UPLOAD_HTTP_{response.status_code}")
        if payload.get("asset_sha256") != sha256:
            raise RuntimeError("MEDIA_UPLOAD_SHA256_MISMATCH")
        return payload

    def submit_intent(self, intent):
        # Replaying this request is safe: the server persists the idempotency key
        # before any provider publication side effect.
        response = self._request_with_cold_start_retry(
            "POST",
            "/internal/publish/reel",
            json=intent,
            headers={"Content-Type": "application/json"},
        )
        payload = self._json(response)
        if response.status_code >= 500:
            raise RuntimeError(payload.get("error") or f"PUBLISH_START_HTTP_{response.status_code}")
        if response.status_code >= 400:
            raise RuntimeError(payload.get("error") or f"PUBLISH_START_HTTP_{response.status_code}")
        return payload

    def reconcile_once(self, idempotency_key):
        response = self._request_with_cold_start_retry(
            "POST",
            "/internal/publish/reconcile",
            json={"idempotency_key": idempotency_key},
            headers={"Content-Type": "application/json"},
        )
        payload = self._json(response)
        if response.status_code >= 500 and payload.get("status") not in TERMINAL_FAIL_CLOSED:
            raise RuntimeError(payload.get("error") or f"RECONCILE_HTTP_{response.status_code}")
        return payload

    def publish_manifest(self, manifest, *, poll_interval=60, max_polls=5):
        required = (
            "publication_id",
            "content_asset_id",
            "video_path",
            "caption",
            "market",
            "language",
            "rights_status",
            "policy_status",
            "legal_status",
            "commercial_status",
            "idempotency_key",
            "correlation_id",
            "media",
        )
        missing = [k for k in required if k not in manifest]
        if missing:
            raise RuntimeError("MISSING_MANIFEST_FIELDS:" + ",".join(missing))

        media_result = self.upload_media(
            video_path=manifest["video_path"],
            content_asset_id=manifest["content_asset_id"],
            media_metadata=manifest["media"],
        )
        intent = {
            "publication_id": manifest["publication_id"],
            "content_asset_id": manifest["content_asset_id"],
            "video_uri": media_result["video_uri"],
            "asset_sha256": media_result["asset_sha256"],
            "caption": manifest.get("caption", ""),
            "hashtags": manifest.get("hashtags", []),
            "market": manifest["market"],
            "language": manifest["language"],
            "rights_status": manifest["rights_status"],
            "policy_status": manifest["policy_status"],
            "legal_status": manifest["legal_status"],
            "commercial_status": manifest["commercial_status"],
            "scheduled_time": manifest.get("scheduled_time"),
            "idempotency_key": manifest["idempotency_key"],
            "correlation_id": manifest["correlation_id"],
            "is_ai_generated": bool(manifest.get("is_ai_generated", True)),
            "media": manifest["media"],
        }

        result = self.submit_intent(intent)
        status = result.get("status")
        if status in TERMINAL_SUCCESS:
            return result
        if status in TERMINAL_FAIL_CLOSED:
            return result

        for _ in range(int(max_polls)):
            time.sleep(int(poll_interval))
            result = self.reconcile_once(manifest["idempotency_key"])
            status = result.get("status")
            if status in TERMINAL_SUCCESS or status in TERMINAL_FAIL_CLOSED:
                return result

        # Never create a second publication intent merely because processing is slow.
        return {
            "ok": False,
            "status": "PROCESSING_TIMEOUT_HOLD",
            "idempotency_key": manifest["idempotency_key"],
            "correlation_id": manifest["correlation_id"],
        }


def main():
    parser = argparse.ArgumentParser(description="TrendHunter -> Instagram governed publisher bridge")
    parser.add_argument("manifest", help="Path to governed publication manifest JSON")
    parser.add_argument("--poll-interval", type=int, default=60)
    parser.add_argument("--max-polls", type=int, default=5)
    args = parser.parse_args()

    manifest = json.loads(Path(args.manifest).read_text(encoding="utf-8"))
    client = InstagramPublisherClient()
    result = client.publish_manifest(
        manifest,
        poll_interval=args.poll_interval,
        max_polls=args.max_polls,
    )
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))

    if result.get("status") == "VERIFIED":
        return 0
    if result.get("status") == "HOLD_PUBLIC_DISABLED":
        return 2
    return 1


if __name__ == "__main__":
    sys.exit(main())

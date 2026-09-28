import hashlib
import hmac
import ipaddress
import json
import os
import re
import socket
import time
from urllib.parse import urlparse

import psycopg
import requests
from flask import jsonify, request


IDEMPOTENCY_RE = re.compile(r"^[A-Za-z0-9._:-]{12,160}$")
TERMINAL_PUBLISH_STATES = {"PUBLISHED", "VERIFIED", "PUBLISH_FAILED_HOLD", "UNKNOWN"}
RETRYABLE_PREPUBLISH_STATES = {"NEW", "VALIDATED", "CONTAINER_CREATED", "PROCESSING", "READY", "FAILED_RETRYABLE"}


def _env_flag(name, default=False):
    raw = os.getenv(name, "true" if default else "false").strip().lower()
    return raw == "true"


def _env_csv(name):
    return [x.strip().lower() for x in os.getenv(name, "").split(",") if x.strip()]


def _db_url():
    return os.getenv("INSTAGRAM_DATABASE_URL", os.getenv("DATABASE_URL", "")).strip()


def _db_connect():
    url = _db_url()
    if not url:
        return None
    return psycopg.connect(url, connect_timeout=10)


def _ensure_publish_tables():
    with _db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS instagram_publish_jobs (
                    idempotency_key TEXT PRIMARY KEY,
                    publication_id TEXT NOT NULL,
                    content_asset_id TEXT NOT NULL,
                    correlation_id TEXT NOT NULL,
                    request_hash TEXT NOT NULL,
                    account_key TEXT NOT NULL,
                    video_uri TEXT NOT NULL,
                    caption_hash TEXT NOT NULL,
                    market TEXT NOT NULL,
                    language TEXT NOT NULL,
                    rights_status TEXT NOT NULL,
                    policy_status TEXT NOT NULL,
                    legal_status TEXT NOT NULL,
                    commercial_content BOOLEAN NOT NULL DEFAULT FALSE,
                    is_ai_generated BOOLEAN NOT NULL DEFAULT TRUE,
                    status TEXT NOT NULL,
                    container_id TEXT,
                    media_id TEXT,
                    provider_permalink TEXT,
                    provider_media_product_type TEXT,
                    attempt_count INTEGER NOT NULL DEFAULT 0,
                    last_error TEXT,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    published_at TIMESTAMPTZ
                )
                """
            )
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS instagram_publish_events (
                    id BIGSERIAL PRIMARY KEY,
                    idempotency_key TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    safe_payload JSONB NOT NULL DEFAULT '{}'::jsonb,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                )
                """
            )
            cur.execute(
                "CREATE INDEX IF NOT EXISTS idx_instagram_publish_jobs_status_created "
                "ON instagram_publish_jobs(status, created_at)"
            )
            cur.execute(
                "CREATE INDEX IF NOT EXISTS idx_instagram_publish_events_key "
                "ON instagram_publish_events(idempotency_key, created_at)"
            )
        conn.commit()


def _canonical_request(payload):
    relevant = {
        "publication_id": payload.get("publication_id"),
        "content_asset_id": payload.get("content_asset_id"),
        "video_uri": payload.get("video_uri"),
        "caption": payload.get("caption", ""),
        "hashtags": payload.get("hashtags", []),
        "market": payload.get("market"),
        "language": payload.get("language"),
        "rights_status": payload.get("rights_status"),
        "policy_status": payload.get("policy_status"),
        "legal_status": payload.get("legal_status"),
        "scheduled_time": payload.get("scheduled_time"),
        "idempotency_key": payload.get("idempotency_key"),
        "correlation_id": payload.get("correlation_id"),
        "commercial_content": payload.get("commercial_content", False),
        "is_ai_generated": payload.get("is_ai_generated"),
        "media": payload.get("media", {}),
    }
    return json.dumps(relevant, separators=(",", ":"), sort_keys=True, ensure_ascii=False)


def request_hash(payload):
    return hashlib.sha256(_canonical_request(payload).encode("utf-8")).hexdigest()


def verify_machine_signature(secret, timestamp, signature, raw_body, now=None, max_skew_seconds=300):
    if not secret or not timestamp or not signature:
        return False
    try:
        ts = int(timestamp)
    except (TypeError, ValueError):
        return False
    current = int(time.time() if now is None else now)
    if abs(current - ts) > max_skew_seconds:
        return False
    signed = str(ts).encode("ascii") + b"." + raw_body
    expected = hmac.new(secret.encode("utf-8"), signed, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature.strip().lower())


def _host_allowed(hostname, allowed_hosts):
    host = (hostname or "").lower().rstrip(".")
    for allowed in allowed_hosts:
        allowed = allowed.lower().rstrip(".")
        if allowed.startswith("."):
            if host.endswith(allowed) and host != allowed[1:]:
                return True
        elif host == allowed:
            return True
    return False


def _host_resolves_public(hostname):
    try:
        infos = socket.getaddrinfo(hostname, 443, proto=socket.IPPROTO_TCP)
    except OSError:
        return False
    if not infos:
        return False
    for info in infos:
        addr = info[4][0]
        try:
            ip = ipaddress.ip_address(addr)
        except ValueError:
            return False
        if (
            ip.is_private
            or ip.is_loopback
            or ip.is_link_local
            or ip.is_multicast
            or ip.is_reserved
            or ip.is_unspecified
        ):
            return False
    return True


def validate_publish_payload(payload, now=None):
    if not isinstance(payload, dict):
        return False, "JSON_OBJECT_REQUIRED"

    required_text = [
        "publication_id",
        "content_asset_id",
        "video_uri",
        "market",
        "language",
        "rights_status",
        "policy_status",
        "legal_status",
        "idempotency_key",
        "correlation_id",
    ]
    for field in required_text:
        if not str(payload.get(field) or "").strip():
            return False, f"MISSING_{field.upper()}"

    key = str(payload["idempotency_key"]).strip()
    if not IDEMPOTENCY_RE.fullmatch(key):
        return False, "INVALID_IDEMPOTENCY_KEY"

    if str(payload["rights_status"]).upper() != "PASS":
        return False, "RIGHTS_GATE_HOLD"
    if str(payload["policy_status"]).upper() != "PASS":
        return False, "POLICY_GATE_HOLD"
    if str(payload["legal_status"]).upper() != "PASS":
        return False, "LEGAL_GATE_HOLD"

    allowed_markets = _env_csv("INSTAGRAM_ALLOWED_MARKETS") or ["sa"]
    if str(payload["market"]).lower() not in allowed_markets:
        return False, "MARKET_NOT_AUTHORIZED"

    allowed_languages = _env_csv("INSTAGRAM_ALLOWED_LANGUAGES") or ["ar"]
    if str(payload["language"]).lower() not in allowed_languages:
        return False, "LANGUAGE_NOT_AUTHORIZED"

    commercial = payload.get("commercial_content", False)
    if not isinstance(commercial, bool):
        return False, "COMMERCIAL_CONTENT_FLAG_REQUIRED"
    if commercial and not _env_flag("INSTAGRAM_COMMERCIAL_CONTENT_AUTHORIZED", False):
        return False, "COMMERCIAL_CONTENT_HOLD"

    if not isinstance(payload.get("is_ai_generated"), bool):
        return False, "AI_DISCLOSURE_FLAG_REQUIRED"

    caption = str(payload.get("caption") or "")
    hashtags = payload.get("hashtags") or []
    if not isinstance(hashtags, (list, tuple)):
        return False, "HASHTAGS_MUST_BE_LIST"
    hashtag_text = " ".join(str(x).strip() for x in hashtags if str(x).strip())
    final_caption = (caption + (" " + hashtag_text if hashtag_text else "")).strip()
    if len(final_caption) > 2200:
        return False, "CAPTION_TOO_LONG"

    scheduled = payload.get("scheduled_time")
    if scheduled is not None:
        try:
            scheduled_epoch = int(scheduled)
        except (TypeError, ValueError):
            return False, "INVALID_SCHEDULED_TIME"
        current = int(time.time() if now is None else now)
        if scheduled_epoch > current + 300:
            return False, "PUBLICATION_NOT_DUE"

    parsed = urlparse(str(payload["video_uri"]).strip())
    if parsed.scheme.lower() != "https" or not parsed.hostname:
        return False, "HTTPS_VIDEO_URI_REQUIRED"

    allowed_hosts = _env_csv("INSTAGRAM_MEDIA_ALLOWED_HOSTS")
    if not allowed_hosts:
        return False, "MEDIA_ALLOWLIST_NOT_CONFIGURED"
    if not _host_allowed(parsed.hostname, allowed_hosts):
        return False, "MEDIA_HOST_NOT_AUTHORIZED"

    media = payload.get("media")
    if not isinstance(media, dict):
        return False, "MEDIA_METADATA_REQUIRED"
    try:
        size_bytes = int(media.get("size_bytes", 0))
        duration = float(media.get("duration_seconds", 0))
        width = int(media.get("width", 0))
        height = int(media.get("height", 0))
        fps = float(media.get("fps", 0))
    except (TypeError, ValueError):
        return False, "INVALID_MEDIA_METADATA"

    codec = str(media.get("codec") or "").strip().lower()
    mime = str(media.get("mime") or "").strip().lower()
    if size_bytes <= 0 or size_bytes > 100 * 1024 * 1024:
        return False, "MEDIA_SIZE_OUT_OF_RANGE"
    if duration < 3 or duration > 900:
        return False, "MEDIA_DURATION_OUT_OF_RANGE"
    if width < 320 or height < 320 or width > 7680 or height > 7680:
        return False, "MEDIA_DIMENSIONS_OUT_OF_RANGE"
    if fps <= 0 or fps > 60:
        return False, "MEDIA_FPS_OUT_OF_RANGE"
    if codec not in {"h264", "avc1", "hevc", "h265"}:
        return False, "MEDIA_CODEC_NOT_ALLOWED"
    if mime not in {"video/mp4", "application/mp4"}:
        return False, "MEDIA_MIME_NOT_ALLOWED"

    return True, "PASS"


def _remote_media_preflight(video_uri, expected_size):
    allowed_hosts = _env_csv("INSTAGRAM_MEDIA_ALLOWED_HOSTS")
    parsed = urlparse(video_uri)
    if not _host_allowed(parsed.hostname, allowed_hosts) or not _host_resolves_public(parsed.hostname):
        return False, {"stage": "MEDIA_PREFLIGHT", "error": "MEDIA_HOST_RESOLUTION_REJECTED"}

    try:
        head = requests.head(video_uri, allow_redirects=True, timeout=20)
        if head.status_code >= 400 and head.status_code not in {405, 501}:
            return False, {"stage": "MEDIA_PREFLIGHT", "error": "MEDIA_HEAD_FAILED", "http": head.status_code}
        final = urlparse(head.url or video_uri)
        if not _host_allowed(final.hostname, allowed_hosts) or not _host_resolves_public(final.hostname):
            return False, {"stage": "MEDIA_PREFLIGHT", "error": "MEDIA_REDIRECT_HOST_REJECTED"}

        content_type = str(head.headers.get("Content-Type") or "").split(";", 1)[0].strip().lower()
        if content_type and content_type not in {"video/mp4", "application/mp4", "application/octet-stream"}:
            return False, {"stage": "MEDIA_PREFLIGHT", "error": "MEDIA_CONTENT_TYPE_REJECTED"}

        content_length = head.headers.get("Content-Length")
        if content_length:
            try:
                remote_size = int(content_length)
            except ValueError:
                remote_size = 0
            if remote_size <= 0 or remote_size > 100 * 1024 * 1024:
                return False, {"stage": "MEDIA_PREFLIGHT", "error": "MEDIA_REMOTE_SIZE_REJECTED"}
            tolerance = max(4096, int(expected_size * 0.01))
            if abs(remote_size - expected_size) > tolerance:
                return False, {"stage": "MEDIA_PREFLIGHT", "error": "MEDIA_SIZE_MISMATCH"}

        probe = requests.get(
            video_uri,
            headers={"Range": "bytes=0-4095"},
            allow_redirects=True,
            timeout=20,
            stream=True,
        )
        if probe.status_code not in {200, 206}:
            return False, {"stage": "MEDIA_PREFLIGHT", "error": "MEDIA_RANGE_PROBE_FAILED", "http": probe.status_code}
        final_probe = urlparse(probe.url or video_uri)
        if not _host_allowed(final_probe.hostname, allowed_hosts):
            return False, {"stage": "MEDIA_PREFLIGHT", "error": "MEDIA_PROBE_REDIRECT_REJECTED"}
        first = next(probe.iter_content(chunk_size=4096), b"")
        if len(first) < 12 or b"ftyp" not in first[:64]:
            return False, {"stage": "MEDIA_PREFLIGHT", "error": "MP4_SIGNATURE_NOT_FOUND"}
        return True, {"stage": "MEDIA_PREFLIGHT", "status": "PASS"}
    except requests.RequestException as exc:
        return False, {"stage": "MEDIA_PREFLIGHT", "error": "MEDIA_PREFLIGHT_REQUEST_FAILED", "exception_type": type(exc).__name__}


def _audit(idempotency_key, event_type, safe_payload=None):
    with _db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO instagram_publish_events(idempotency_key,event_type,safe_payload) VALUES (%s,%s,%s::jsonb)",
                (idempotency_key, event_type, json.dumps(safe_payload or {}, separators=(",", ":"), sort_keys=True)),
            )
        conn.commit()


def _read_job(idempotency_key):
    with _db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT idempotency_key, publication_id, content_asset_id, correlation_id,
                       request_hash, account_key, video_uri, caption_hash, market, language,
                       rights_status, policy_status, legal_status, commercial_content,
                       is_ai_generated, status, container_id, media_id,
                       provider_permalink, provider_media_product_type, attempt_count,
                       last_error, created_at, updated_at, published_at
                FROM instagram_publish_jobs WHERE idempotency_key=%s
                """,
                (idempotency_key,),
            )
            row = cur.fetchone()
    if not row:
        return None
    keys = [
        "idempotency_key","publication_id","content_asset_id","correlation_id",
        "request_hash","account_key","video_uri","caption_hash","market","language",
        "rights_status","policy_status","legal_status","commercial_content",
        "is_ai_generated","status","container_id","media_id",
        "provider_permalink","provider_media_product_type","attempt_count",
        "last_error","created_at","updated_at","published_at"
    ]
    return dict(zip(keys, row))


def _create_or_validate_job(payload, req_hash, account_key):
    key = payload["idempotency_key"]
    existing = _read_job(key)
    if existing:
        if existing["request_hash"] != req_hash:
            return False, "IDEMPOTENCY_KEY_REUSED_WITH_DIFFERENT_REQUEST", existing
        return True, "EXISTING", existing

    caption = str(payload.get("caption") or "")
    hashtags = " ".join(str(x).strip() for x in (payload.get("hashtags") or []) if str(x).strip())
    final_caption = (caption + (" " + hashtags if hashtags else "")).strip()
    caption_hash = hashlib.sha256(final_caption.encode("utf-8")).hexdigest()

    with _db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO instagram_publish_jobs(
                    idempotency_key, publication_id, content_asset_id, correlation_id,
                    request_hash, account_key, video_uri, caption_hash, market, language,
                    rights_status, policy_status, legal_status, commercial_content,
                    is_ai_generated, status
                ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,'NEW')
                ON CONFLICT (idempotency_key) DO NOTHING
                """,
                (
                    key, payload["publication_id"], payload["content_asset_id"], payload["correlation_id"],
                    req_hash, account_key, payload["video_uri"], caption_hash,
                    str(payload["market"]).upper(), str(payload["language"]).lower(),
                    str(payload["rights_status"]).upper(), str(payload["policy_status"]).upper(),
                    str(payload["legal_status"]).upper(), bool(payload.get("commercial_content", False)),
                    bool(payload["is_ai_generated"]),
                ),
            )
        conn.commit()
    existing = _read_job(key)
    if not existing:
        return False, "JOB_CREATION_FAILED", None
    if existing["request_hash"] != req_hash:
        return False, "IDEMPOTENCY_KEY_REUSED_WITH_DIFFERENT_REQUEST", existing
    _audit(key, "JOB_CREATED", {"publication_id": payload["publication_id"], "correlation_id": payload["correlation_id"]})
    return True, "CREATED", existing


def _update_job(key, *, status=None, container_id=None, media_id=None, permalink=None, product_type=None, error=None, increment_attempt=False, published=False):
    fields = ["updated_at=NOW()"]
    params = []
    if status is not None:
        fields.append("status=%s"); params.append(status)
    if container_id is not None:
        fields.append("container_id=%s"); params.append(container_id)
    if media_id is not None:
        fields.append("media_id=%s"); params.append(media_id)
    if permalink is not None:
        fields.append("provider_permalink=%s"); params.append(permalink)
    if product_type is not None:
        fields.append("provider_media_product_type=%s"); params.append(product_type)
    if error is not None:
        fields.append("last_error=%s"); params.append(str(error)[:1000])
    if increment_attempt:
        fields.append("attempt_count=attempt_count+1")
    if published:
        fields.append("published_at=NOW()")
    params.append(key)
    with _db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(f"UPDATE instagram_publish_jobs SET {', '.join(fields)} WHERE idempotency_key=%s", params)
        conn.commit()


def _try_job_lock(key):
    conn = _db_connect()
    if conn is None:
        return None
    cur = conn.cursor()
    cur.execute("SELECT pg_try_advisory_lock(hashtext(%s))", (key,))
    locked = bool(cur.fetchone()[0])
    cur.close()
    if not locked:
        conn.close()
        return None
    return conn


def _release_job_lock(conn, key):
    if not conn:
        return
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT pg_advisory_unlock(hashtext(%s))", (key,))
        conn.commit()
    finally:
        conn.close()


def _internal_published_count_24h():
    with _db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT COUNT(*) FROM instagram_publish_jobs "
                "WHERE status IN ('PUBLISHED','VERIFIED') AND published_at > NOW() - INTERVAL '24 hours'"
            )
            return int(cur.fetchone()[0])


def _find_quota_usage(obj):
    if isinstance(obj, dict):
        for k, v in obj.items():
            if str(k).lower() in {"quota_usage", "usage", "publish_count"} and isinstance(v, (int, float)):
                return float(v)
            found = _find_quota_usage(v)
            if found is not None:
                return found
    elif isinstance(obj, list):
        for v in obj:
            found = _find_quota_usage(v)
            if found is not None:
                return found
    return None


def register_production_publisher(app, *, load_token, graph):
    @app.get("/internal/publish-readiness")
    def instagram_publish_readiness():
        secret_configured = bool(os.getenv("INSTAGRAM_PUBLISH_SECRET", "").strip())
        allowed_hosts = _env_csv("INSTAGRAM_MEDIA_ALLOWED_HOSTS")
        return jsonify({
            "ok": True,
            "service": "trendradar-instagram-production-publisher",
            "publish_secret_configured": secret_configured,
            "media_allowlist_configured": bool(allowed_hosts),
            "publish_enabled": _env_flag("INSTAGRAM_PUBLISH_ENABLED", False),
            "public_publish_authorized": _env_flag("INSTAGRAM_PUBLIC_PUBLISH_AUTHORIZED", False),
            "commercial_content_authorized": _env_flag("INSTAGRAM_COMMERCIAL_CONTENT_AUTHORIZED", False),
            "max_daily_publishes": int(os.getenv("INSTAGRAM_MAX_DAILY_PUBLISHES", "10")),
        })

    @app.get("/api/v1/instagram/publish/<idempotency_key>")
    def instagram_publish_status(idempotency_key):
        secret = os.getenv("INSTAGRAM_PUBLISH_SECRET", "").strip()
        raw = b""
        if not verify_machine_signature(
            secret,
            request.headers.get("X-TrendRadar-Timestamp", ""),
            request.headers.get("X-TrendRadar-Signature", ""),
            raw,
        ):
            return jsonify({"ok": False, "error": "UNAUTHORIZED"}), 403
        if not IDEMPOTENCY_RE.fullmatch(idempotency_key):
            return jsonify({"ok": False, "error": "INVALID_IDEMPOTENCY_KEY"}), 400
        _ensure_publish_tables()
        job = _read_job(idempotency_key)
        if not job:
            return jsonify({"ok": False, "error": "JOB_NOT_FOUND"}), 404
        return jsonify({
            "ok": True,
            "idempotency_key": idempotency_key,
            "publication_id": job["publication_id"],
            "correlation_id": job["correlation_id"],
            "status": job["status"],
            "container_id": job["container_id"],
            "media_id": job["media_id"],
            "attempt_count": job["attempt_count"],
            "published_at": job["published_at"].isoformat() if job["published_at"] else None,
            "provider_permalink": job["provider_permalink"],
            "provider_media_product_type": job["provider_media_product_type"],
        })

    @app.post("/api/v1/instagram/publish")
    def instagram_machine_publish():
        raw = request.get_data(cache=True)
        secret = os.getenv("INSTAGRAM_PUBLISH_SECRET", "").strip()
        if not verify_machine_signature(
            secret,
            request.headers.get("X-TrendRadar-Timestamp", ""),
            request.headers.get("X-TrendRadar-Signature", ""),
            raw,
        ):
            return jsonify({"ok": False, "error": "UNAUTHORIZED"}), 403

        if not _db_url():
            return jsonify({"ok": False, "error": "PUBLISH_DATABASE_NOT_CONFIGURED"}), 503

        payload = request.get_json(silent=True)
        valid, reason = validate_publish_payload(payload)
        if not valid:
            return jsonify({"ok": False, "status": "HOLD", "error": reason}), 422

        if not _env_flag("INSTAGRAM_PUBLISH_ENABLED", False):
            return jsonify({"ok": False, "status": "HOLD", "error": "INSTAGRAM_PUBLISH_KILL_SWITCH"}), 423

        token_rec = load_token()
        if not token_rec:
            return jsonify({"ok": False, "status": "HOLD", "error": "INSTAGRAM_CREDENTIAL_NOT_READY"}), 503

        account_key = str(token_rec.get("username") or "").strip().lower()
        expected_username = os.getenv("INSTAGRAM_EXPECTED_USERNAME", "").strip().lstrip("@").lower()
        if not expected_username or account_key != expected_username:
            return jsonify({"ok": False, "status": "HOLD", "error": "EXACT_ACCOUNT_BINDING_FAILED"}), 403

        _ensure_publish_tables()
        req_hash = request_hash(payload)
        key = str(payload["idempotency_key"]).strip()

        lock_conn = _try_job_lock(key)
        if not lock_conn:
            return jsonify({"ok": False, "status": "IN_PROGRESS", "error": "IDEMPOTENCY_LOCK_BUSY"}), 409

        try:
            ok, state, job = _create_or_validate_job(payload, req_hash, account_key)
            if not ok:
                return jsonify({"ok": False, "status": "HOLD", "error": state}), 409

            if job["status"] in {"PUBLISHED", "VERIFIED"}:
                _audit(key, "IDEMPOTENT_REPLAY_RETURNED_EXISTING_RESULT", {"status": job["status"]})
                return jsonify({
                    "ok": True,
                    "status": job["status"],
                    "idempotent_replay": True,
                    "idempotency_key": key,
                    "container_id": job["container_id"],
                    "media_id": job["media_id"],
                    "provider_permalink": job["provider_permalink"],
                }), 200

            if job["status"] in {"PUBLISH_REQUESTED", "PUBLISH_FAILED_HOLD", "UNKNOWN"}:
                return jsonify({
                    "ok": False,
                    "status": "HOLD",
                    "error": "PUBLISH_RECONCILIATION_REQUIRED",
                    "idempotency_key": key,
                    "container_id": job["container_id"],
                }), 409

            daily_cap = int(os.getenv("INSTAGRAM_MAX_DAILY_PUBLISHES", "10"))
            published_count = _internal_published_count_24h()
            if published_count >= daily_cap:
                _audit(key, "INTERNAL_RATE_LIMIT_HOLD", {"published_24h": published_count, "cap": daily_cap})
                return jsonify({"ok": False, "status": "HOLD", "error": "INTERNAL_DAILY_PUBLISH_CAP"}), 429

            limit_http, limit_payload = graph(
                "GET",
                f"{token_rec['user_id']}/content_publishing_limit",
                token_rec["access_token"],
            )
            if limit_http >= 400:
                _audit(key, "PROVIDER_RATE_LIMIT_PREFLIGHT_FAILED", {"http": limit_http})
                return jsonify({"ok": False, "status": "HOLD", "error": "PROVIDER_LIMIT_PREFLIGHT_FAILED"}), 502
            quota_usage = _find_quota_usage(limit_payload)
            provider_hard_cap = int(os.getenv("INSTAGRAM_PROVIDER_PUBLISH_HARD_CAP", "100"))
            if quota_usage is not None and quota_usage >= provider_hard_cap:
                _audit(key, "PROVIDER_RATE_LIMIT_HOLD", {"quota_usage": quota_usage, "cap": provider_hard_cap})
                return jsonify({"ok": False, "status": "HOLD", "error": "PROVIDER_DAILY_PUBLISH_CAP"}), 429

            media_ok, media_evidence = _remote_media_preflight(
                str(payload["video_uri"]),
                int(payload["media"]["size_bytes"]),
            )
            if not media_ok:
                _update_job(key, status="FAILED_RETRYABLE", error=media_evidence.get("error"))
                _audit(key, "MEDIA_PREFLIGHT_FAILED", media_evidence)
                return jsonify({"ok": False, "status": "HOLD", **media_evidence}), 422

            _update_job(key, status="VALIDATED", increment_attempt=True, error="")
            _audit(key, "PUBLISH_INTENT_VALIDATED", {
                "publication_id": payload["publication_id"],
                "content_asset_id": payload["content_asset_id"],
                "correlation_id": payload["correlation_id"],
                "market": payload["market"],
                "language": payload["language"],
                "quota_usage": quota_usage,
            })

            caption = str(payload.get("caption") or "")
            hashtags = " ".join(str(x).strip() for x in (payload.get("hashtags") or []) if str(x).strip())
            final_caption = (caption + (" " + hashtags if hashtags else "")).strip()

            create_data = {
                "media_type": "REELS",
                "video_url": payload["video_uri"],
                "caption": final_caption,
                "share_to_feed": "false",
                "is_ai_generated": "true" if payload["is_ai_generated"] else "false",
            }
            create_http, create_payload = graph(
                "POST",
                f"{token_rec['user_id']}/media",
                token_rec["access_token"],
                data=create_data,
            )
            container_id = create_payload.get("id") if isinstance(create_payload, dict) else None
            if create_http >= 400 or not container_id:
                _update_job(key, status="FAILED_RETRYABLE", error=f"CREATE_CONTAINER_HTTP_{create_http}")
                _audit(key, "CREATE_CONTAINER_FAILED", {"http": create_http})
                return jsonify({"ok": False, "status": "HOLD", "stage": "CREATE_CONTAINER", "http": create_http}), 502

            _update_job(key, status="CONTAINER_CREATED", container_id=container_id)
            _audit(key, "CONTAINER_CREATED", {"container_id": container_id})

            status_payload = {}
            poll_attempts = int(os.getenv("INSTAGRAM_CONTAINER_POLL_ATTEMPTS", "5"))
            poll_seconds = int(os.getenv("INSTAGRAM_CONTAINER_POLL_SECONDS", "60"))
            for attempt in range(poll_attempts):
                if attempt:
                    time.sleep(poll_seconds)
                status_http, status_payload = graph(
                    "GET",
                    container_id,
                    token_rec["access_token"],
                    params={"fields": "status_code,status"},
                )
                if status_http >= 400:
                    _update_job(key, status="FAILED_RETRYABLE", error=f"POLL_HTTP_{status_http}")
                    _audit(key, "POLL_CONTAINER_FAILED", {"http": status_http, "attempt": attempt + 1})
                    return jsonify({"ok": False, "status": "HOLD", "stage": "POLL_CONTAINER", "http": status_http}), 502
                code = str(status_payload.get("status_code") or "")
                if code == "FINISHED":
                    break
                if code in {"ERROR", "EXPIRED"}:
                    _update_job(key, status="FAILED_FINAL", error=f"CONTAINER_{code}")
                    _audit(key, "CONTAINER_FINAL_FAILURE", {"provider_status": code})
                    return jsonify({"ok": False, "status": "FAILED_FINAL", "stage": "PROCESS_CONTAINER", "provider_status": code}), 502
                _update_job(key, status="PROCESSING")
            else:
                _update_job(key, status="FAILED_RETRYABLE", error="PROCESSING_TIMEOUT")
                _audit(key, "CONTAINER_PROCESSING_TIMEOUT", {"attempts": poll_attempts})
                return jsonify({"ok": False, "status": "HOLD", "stage": "PROCESS_CONTAINER", "error": "TIMEOUT"}), 504

            _update_job(key, status="READY")
            _audit(key, "CONTAINER_READY", {"container_id": container_id})

            if not _env_flag("INSTAGRAM_PUBLIC_PUBLISH_AUTHORIZED", False):
                return jsonify({
                    "ok": True,
                    "status": "PREPARED_NOT_PUBLISHED",
                    "idempotency_key": key,
                    "container_id": container_id,
                    "public_publish_authorized": False,
                }), 201

            _update_job(key, status="PUBLISH_REQUESTED")
            _audit(key, "MEDIA_PUBLISH_REQUESTED", {"container_id": container_id})

            try:
                publish_http, publish_payload = graph(
                    "POST",
                    f"{token_rec['user_id']}/media_publish",
                    token_rec["access_token"],
                    data={"creation_id": container_id},
                    timeout=60,
                )
            except Exception as exc:
                _update_job(key, status="UNKNOWN", error=f"PUBLISH_TRANSPORT_{type(exc).__name__}")
                _audit(key, "MEDIA_PUBLISH_AMBIGUOUS", {"exception_type": type(exc).__name__})
                return jsonify({
                    "ok": False,
                    "status": "UNKNOWN",
                    "error": "PUBLISH_RECONCILIATION_REQUIRED",
                    "idempotency_key": key,
                    "container_id": container_id,
                }), 503

            media_id = publish_payload.get("id") if isinstance(publish_payload, dict) else None
            if publish_http >= 400 or not media_id:
                _update_job(key, status="PUBLISH_FAILED_HOLD", error=f"MEDIA_PUBLISH_HTTP_{publish_http}")
                _audit(key, "MEDIA_PUBLISH_FAILED_HOLD", {"http": publish_http})
                return jsonify({
                    "ok": False,
                    "status": "HOLD",
                    "stage": "MEDIA_PUBLISH",
                    "error": "PUBLISH_RECONCILIATION_REQUIRED",
                    "http": publish_http,
                    "container_id": container_id,
                }), 502

            _update_job(key, status="PUBLISHED", media_id=media_id, published=True)
            _audit(key, "MEDIA_PUBLISHED", {"media_id": media_id, "container_id": container_id})

            verify_http, verify_payload = graph(
                "GET",
                media_id,
                token_rec["access_token"],
                params={"fields": "id,media_type,media_product_type,permalink,timestamp"},
            )
            if verify_http >= 400 or str(verify_payload.get("id") or "") != str(media_id):
                _update_job(key, status="PUBLISHED", error=f"VERIFY_HTTP_{verify_http}")
                _audit(key, "POST_PUBLISH_VERIFY_FAILED", {"http": verify_http, "media_id": media_id})
                return jsonify({
                    "ok": True,
                    "status": "PUBLISHED_VERIFY_PENDING",
                    "idempotency_key": key,
                    "container_id": container_id,
                    "media_id": media_id,
                }), 202

            permalink = verify_payload.get("permalink")
            product_type = verify_payload.get("media_product_type")
            _update_job(
                key,
                status="VERIFIED",
                media_id=media_id,
                permalink=permalink,
                product_type=product_type,
                error="",
            )
            _audit(key, "MEDIA_VERIFIED", {
                "media_id": media_id,
                "media_product_type": product_type,
            })
            return jsonify({
                "ok": True,
                "status": "VERIFIED",
                "idempotency_key": key,
                "publication_id": payload["publication_id"],
                "correlation_id": payload["correlation_id"],
                "container_id": container_id,
                "media_id": media_id,
                "provider_permalink": permalink,
                "media_product_type": product_type,
                "public_publish_authorized": True,
            }), 201
        finally:
            _release_job_lock(lock_conn, key)

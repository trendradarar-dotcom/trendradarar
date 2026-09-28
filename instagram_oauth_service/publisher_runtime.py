import hashlib
import hmac
import json
from contextlib import contextmanager
from urllib.parse import urlparse


GOVERNED_USERNAME = "trendradarar"
GOVERNED_PROFESSIONAL_USER_ID = "17841428134382903"
GOVERNED_ACCOUNT_TYPE = "BUSINESS"


TERMINAL_STATUSES = {
    "VERIFIED",
    "VERIFIED_RECOVERED",
    "FAILED_FINAL",
    "UNKNOWN",
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


class IntentValidationError(ValueError):
    pass


class PublisherRuntime:
    """Fail-closed Instagram publisher control plane.

    Browser review upload is intentionally outside this class. This runtime accepts
    only machine publication intents and persists their state before provider calls.
    """

    def __init__(
        self,
        *,
        db_connect,
        load_token_record,
        graph,
        expected_username,
        expected_professional_user_id,
        publish_secret,
        public_publish_authorized,
        publish_enabled,
        media_host_allowlist,
        allowed_markets,
        allowed_languages,
        max_daily_publications=10,
        max_inflight=1,
        circuit_failure_threshold=3,
        max_unpublished_queue=5,
        max_api_mutations_per_minute=10,
        max_provider_mutations_per_job=2,
        media_asset_probe=None,
    ):
        self.db_connect = db_connect
        self.load_token_record = load_token_record
        self.graph = graph
        self.expected_username = (expected_username or "").strip().lstrip("@").lower()
        self.expected_professional_user_id = str(expected_professional_user_id or "").strip()
        self.governed_account_binding_valid = (
            self.expected_username == GOVERNED_USERNAME
            and self.expected_professional_user_id == GOVERNED_PROFESSIONAL_USER_ID
        )
        self.publish_secret = publish_secret or ""
        self.public_publish_authorized = bool(public_publish_authorized)
        self.publish_enabled = bool(publish_enabled)
        self.media_host_allowlist = {
            h.strip().lower().rstrip(".")
            for h in (media_host_allowlist or [])
            if h and h.strip()
        }
        self.allowed_markets = {x.strip() for x in (allowed_markets or []) if x.strip()}
        self.allowed_languages = {x.strip() for x in (allowed_languages or []) if x.strip()}
        self.max_daily_publications = int(max_daily_publications)
        self.max_inflight = int(max_inflight)
        self.circuit_failure_threshold = int(circuit_failure_threshold)
        self.max_unpublished_queue = int(max_unpublished_queue)
        self.max_api_mutations_per_minute = int(max_api_mutations_per_minute)
        self.max_provider_mutations_per_job = int(max_provider_mutations_per_job)
        self.media_asset_probe = media_asset_probe

    def configured(self):
        return bool(
            self.publish_secret
            and self.governed_account_binding_valid
            and self.expected_username
            and self.expected_professional_user_id
            and self.media_host_allowlist
            and self.allowed_markets
            and self.allowed_languages
        )

    def authorize(self, supplied):
        return bool(
            self.publish_secret
            and supplied
            and hmac.compare_digest(str(supplied), self.publish_secret)
        )

    @staticmethod
    def _canonical_hash(payload):
        canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    @staticmethod
    def _safe_text(value, *, name, min_len=1, max_len=4096):
        if not isinstance(value, str):
            raise IntentValidationError(f"{name}_REQUIRED")
        value = value.strip()
        if len(value) < min_len:
            raise IntentValidationError(f"{name}_REQUIRED")
        if len(value) > max_len:
            raise IntentValidationError(f"{name}_TOO_LONG")
        return value

    def _validate_video_uri(self, value):
        uri = self._safe_text(value, name="VIDEO_URI", max_len=2048)
        parsed = urlparse(uri)
        if parsed.scheme.lower() != "https" or not parsed.hostname:
            raise IntentValidationError("VIDEO_URI_HTTPS_REQUIRED")
        if parsed.username or parsed.password:
            raise IntentValidationError("VIDEO_URI_USERINFO_FORBIDDEN")
        host = parsed.hostname.lower().rstrip(".")
        allowed = any(host == h or host.endswith("." + h) for h in self.media_host_allowlist)
        if not allowed:
            raise IntentValidationError("VIDEO_URI_HOST_NOT_ALLOWED")
        # Never permit the ephemeral review media route to become the production source.
        if host == "trendradar-instagram-oauth.onrender.com":
            if not parsed.path.startswith("/publisher-media/"):
                raise IntentValidationError("BACKEND_MEDIA_PATH_NOT_ALLOWED")
        return uri

    def validate_intent(self, payload):
        if not isinstance(payload, dict):
            raise IntentValidationError("JSON_OBJECT_REQUIRED")

        hashtags = payload.get("hashtags", [])
        if hashtags is None:
            hashtags = []
        if not isinstance(hashtags, list) or len(hashtags) > 30:
            raise IntentValidationError("HASHTAGS_INVALID")
        clean_tags = []
        for tag in hashtags:
            if not isinstance(tag, str):
                raise IntentValidationError("HASHTAGS_INVALID")
            tag = tag.strip().lstrip("#")
            if tag:
                if len(tag) > 100:
                    raise IntentValidationError("HASHTAG_TOO_LONG")
                clean_tags.append(tag)

        media = payload.get("media")
        if not isinstance(media, dict):
            raise IntentValidationError("MEDIA_METADATA_REQUIRED")
        mime_type = str(media.get("mime_type") or "").strip().lower()
        if mime_type not in {"video/mp4", "application/mp4"}:
            raise IntentValidationError("MEDIA_MIME_NOT_ALLOWED")
        try:
            size_bytes = int(media.get("size_bytes"))
            duration_seconds = float(media.get("duration_seconds"))
            width = int(media.get("width"))
            height = int(media.get("height"))
            fps = float(media.get("fps"))
        except (TypeError, ValueError):
            raise IntentValidationError("MEDIA_METADATA_INVALID")
        if size_bytes <= 0 or size_bytes > 100 * 1024 * 1024:
            raise IntentValidationError("MEDIA_SIZE_OUT_OF_RANGE")
        # Meta Reels: 3s minimum, 15m maximum.
        if duration_seconds < 3 or duration_seconds > 900:
            raise IntentValidationError("MEDIA_DURATION_OUT_OF_RANGE")
        # Current governed profile is H.264 MP4, narrower than Meta's H.264/HEVC allowance.
        if width < 320 or width > 1920 or height < 320 or height > 4096:
            raise IntentValidationError("MEDIA_DIMENSIONS_OUT_OF_RANGE")
        if fps < 23 or fps > 60:
            raise IntentValidationError("MEDIA_FPS_OUT_OF_RANGE")

        video_codec = str(media.get("video_codec") or "").strip().lower()
        if video_codec not in {"h264", "avc", "avc1"}:
            raise IntentValidationError("MEDIA_VIDEO_CODEC_NOT_ALLOWED")
        audio_codec = str(media.get("audio_codec") or "").strip().lower()
        if audio_codec not in {"", "none", "aac", "mp4a"}:
            raise IntentValidationError("MEDIA_AUDIO_CODEC_NOT_ALLOWED")
        try:
            video_bitrate_bps = int(media.get("video_bitrate_bps"))
            audio_sample_rate_hz = int(media.get("audio_sample_rate_hz") or 0)
            audio_bitrate_bps = int(media.get("audio_bitrate_bps") or 0)
        except (TypeError, ValueError):
            raise IntentValidationError("MEDIA_BITRATE_METADATA_INVALID")
        if video_bitrate_bps <= 0 or video_bitrate_bps > 25_000_000:
            raise IntentValidationError("MEDIA_VIDEO_BITRATE_OUT_OF_RANGE")
        if audio_codec in {"aac", "mp4a"}:
            if audio_sample_rate_hz != 48_000:
                raise IntentValidationError("MEDIA_AUDIO_SAMPLE_RATE_INVALID")
            if audio_bitrate_bps <= 0 or audio_bitrate_bps > 128_000:
                raise IntentValidationError("MEDIA_AUDIO_BITRATE_OUT_OF_RANGE")
        elif audio_sample_rate_hz != 0 or audio_bitrate_bps != 0:
            raise IntentValidationError("MEDIA_AUDIO_METADATA_WITHOUT_AUDIO")

        market = self._safe_text(payload.get("market"), name="MARKET", max_len=16)
        language = self._safe_text(payload.get("language"), name="LANGUAGE", max_len=32)
        if market not in self.allowed_markets:
            raise IntentValidationError("MARKET_NOT_ALLOWED")
        if language not in self.allowed_languages:
            raise IntentValidationError("LANGUAGE_NOT_ALLOWED")

        for gate in ("rights_status", "policy_status", "legal_status"):
            if str(payload.get(gate) or "").strip().upper() != "PASS":
                raise IntentValidationError(f"{gate.upper()}_NOT_PASS")
        if str(payload.get("commercial_status") or "").strip().upper() != "EDITORIAL_ORIGINAL":
            raise IntentValidationError("COMMERCIAL_CONTENT_HOLD")

        asset_sha256 = self._safe_text(
            payload.get("asset_sha256"), name="ASSET_SHA256", min_len=64, max_len=64
        ).lower()
        if any(c not in "0123456789abcdef" for c in asset_sha256):
            raise IntentValidationError("ASSET_SHA256_INVALID")

        scheduled_time = payload.get("scheduled_time")
        if scheduled_time is not None and not isinstance(scheduled_time, str):
            raise IntentValidationError("SCHEDULED_TIME_INVALID")

        normalized = {
            "publication_id": self._safe_text(
                payload.get("publication_id"), name="PUBLICATION_ID", max_len=200
            ),
            "content_asset_id": self._safe_text(
                payload.get("content_asset_id"), name="CONTENT_ASSET_ID", max_len=200
            ),
            "video_uri": self._validate_video_uri(payload.get("video_uri")),
            "asset_sha256": asset_sha256,
            "caption": str(payload.get("caption") or "").strip()[:2200],
            "hashtags": clean_tags,
            "market": market,
            "language": language,
            "rights_status": "PASS",
            "policy_status": "PASS",
            "legal_status": "PASS",
            "commercial_status": "EDITORIAL_ORIGINAL",
            "scheduled_time": scheduled_time,
            "idempotency_key": self._safe_text(
                payload.get("idempotency_key"), name="IDEMPOTENCY_KEY", max_len=200
            ),
            "correlation_id": self._safe_text(
                payload.get("correlation_id"), name="CORRELATION_ID", max_len=200
            ),
            "is_ai_generated": bool(payload.get("is_ai_generated", True)),
            "media": {
                "mime_type": mime_type,
                "size_bytes": size_bytes,
                "duration_seconds": duration_seconds,
                "width": width,
                "height": height,
                "fps": fps,
                "video_codec": video_codec,
                "audio_codec": audio_codec,
                "video_bitrate_bps": video_bitrate_bps,
                "audio_sample_rate_hz": audio_sample_rate_hz,
                "audio_bitrate_bps": audio_bitrate_bps,
            },
        }
        normalized["contract_sha256"] = self._canonical_hash(normalized)
        if self.media_asset_probe is not None:
            ok, error = self.media_asset_probe(
                normalized["content_asset_id"],
                normalized["video_uri"],
                normalized["asset_sha256"],
                normalized["media"],
            )
            if not ok:
                raise IntentValidationError(error or "MEDIA_ASSET_NOT_ADMITTED")
        return normalized

    def _ensure_tables(self):
        with self.db_connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    CREATE TABLE IF NOT EXISTS instagram_publication_jobs (
                        idempotency_key TEXT PRIMARY KEY,
                        publication_id TEXT NOT NULL UNIQUE,
                        content_asset_id TEXT NOT NULL,
                        correlation_id TEXT NOT NULL,
                        contract_sha256 TEXT NOT NULL,
                        account_key TEXT NOT NULL,
                        video_uri TEXT NOT NULL,
                        asset_sha256 TEXT NOT NULL,
                        caption TEXT NOT NULL,
                        hashtags_json JSONB NOT NULL,
                        market TEXT NOT NULL,
                        language TEXT NOT NULL,
                        rights_status TEXT NOT NULL,
                        policy_status TEXT NOT NULL,
                        legal_status TEXT NOT NULL,
                        commercial_status TEXT NOT NULL,
                        is_ai_generated BOOLEAN NOT NULL,
                        status TEXT NOT NULL,
                        container_id TEXT,
                        media_id TEXT,
                        provider_status TEXT,
                        attempt_count INTEGER NOT NULL DEFAULT 0,
                        last_error_code TEXT,
                        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                        updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                    )
                    """
                )
                cur.execute(
                    """
                    CREATE TABLE IF NOT EXISTS instagram_publication_events (
                        event_id BIGSERIAL PRIMARY KEY,
                        idempotency_key TEXT NOT NULL,
                        event_type TEXT NOT NULL,
                        safe_detail JSONB NOT NULL DEFAULT '{}'::jsonb,
                        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                    )
                    """
                )
                # Strict Phase-1 duplicate prevention: the same governed asset or exact bytes
                # cannot be reserved twice for the same Instagram account.
                cur.execute(
                    """
                    CREATE UNIQUE INDEX IF NOT EXISTS instagram_publication_unique_content_asset
                    ON instagram_publication_jobs(account_key, content_asset_id)
                    """
                )
                cur.execute(
                    """
                    CREATE UNIQUE INDEX IF NOT EXISTS instagram_publication_unique_asset_hash
                    ON instagram_publication_jobs(account_key, asset_sha256)
                    """
                )
            conn.commit()

    @staticmethod
    def _job_columns():
        return (
            "idempotency_key, publication_id, content_asset_id, correlation_id, "
            "contract_sha256, account_key, video_uri, asset_sha256, caption, "
            "hashtags_json, market, language, rights_status, policy_status, "
            "legal_status, commercial_status, is_ai_generated, status, container_id, "
            "media_id, provider_status, attempt_count, last_error_code, created_at, updated_at"
        )

    @classmethod
    def _row_to_job(cls, row):
        if not row:
            return None
        names = [
            "idempotency_key", "publication_id", "content_asset_id", "correlation_id",
            "contract_sha256", "account_key", "video_uri", "asset_sha256", "caption",
            "hashtags", "market", "language", "rights_status", "policy_status",
            "legal_status", "commercial_status", "is_ai_generated", "status",
            "container_id", "media_id", "provider_status", "attempt_count",
            "last_error_code", "created_at", "updated_at",
        ]
        return dict(zip(names, row))

    def _get_job(self, idempotency_key):
        self._ensure_tables()
        with self.db_connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    f"SELECT {self._job_columns()} FROM instagram_publication_jobs "
                    "WHERE idempotency_key = %s",
                    (idempotency_key,),
                )
                return self._row_to_job(cur.fetchone())

    def _get_job_by_content_identity(self, content_asset_id, asset_sha256):
        self._ensure_tables()
        with self.db_connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    f"SELECT {self._job_columns()} FROM instagram_publication_jobs "
                    "WHERE account_key = %s AND (content_asset_id = %s OR asset_sha256 = %s) "
                    "ORDER BY created_at ASC LIMIT 1",
                    (self.expected_username, content_asset_id, asset_sha256),
                )
                return self._row_to_job(cur.fetchone())

    def _insert_job(self, intent, status):
        self._ensure_tables()
        with self.db_connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO instagram_publication_jobs(
                        idempotency_key, publication_id, content_asset_id, correlation_id,
                        contract_sha256, account_key, video_uri, asset_sha256, caption,
                        hashtags_json, market, language, rights_status, policy_status,
                        legal_status, commercial_status, is_ai_generated, status
                    ) VALUES (
                        %s,%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb,%s,%s,%s,%s,%s,%s,%s,%s
                    )
                    ON CONFLICT DO NOTHING
                    RETURNING idempotency_key
                    """,
                    (
                        intent["idempotency_key"], intent["publication_id"],
                        intent["content_asset_id"], intent["correlation_id"],
                        intent["contract_sha256"], self.expected_username,
                        intent["video_uri"], intent["asset_sha256"], intent["caption"],
                        json.dumps(intent["hashtags"]), intent["market"], intent["language"],
                        intent["rights_status"], intent["policy_status"], intent["legal_status"],
                        intent["commercial_status"], intent["is_ai_generated"], status,
                    ),
                )
                inserted = cur.fetchone() is not None
                if inserted:
                    cur.execute(
                        "INSERT INTO instagram_publication_events"
                        "(idempotency_key,event_type,safe_detail) "
                        "VALUES (%s,%s,%s::jsonb)",
                        (
                            intent["idempotency_key"],
                            "JOB_CREATED",
                            json.dumps({"status": status}, sort_keys=True),
                        ),
                    )
            conn.commit()
        return inserted

    def _reservation_conflict_response(self, intent):
        existing = self._get_job(intent["idempotency_key"])
        if existing:
            if existing["contract_sha256"] == intent["contract_sha256"]:
                return 200, self._safe_job(existing, replayed=True)
            return 409, {"ok": False, "error": "IDEMPOTENCY_CONFLICT"}
        existing = self._get_job_by_content_identity(
            intent["content_asset_id"], intent["asset_sha256"]
        )
        if existing:
            return 409, {
                "ok": False,
                "error": "CONTENT_ALREADY_BOUND_TO_PUBLICATION",
                "existing_publication_id": existing.get("publication_id"),
                "existing_status": existing.get("status"),
            }
        return 409, {"ok": False, "error": "PUBLICATION_RESERVATION_CONFLICT"}

    def _reserve_job(self, intent, status):
        if self._insert_job(intent, status):
            return None
        return self._reservation_conflict_response(intent)

    def _event(self, key, event_type, detail=None):
        self._ensure_tables()
        safe_detail = detail or {}
        with self.db_connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "INSERT INTO instagram_publication_events(idempotency_key,event_type,safe_detail) "
                    "VALUES (%s,%s,%s::jsonb)",
                    (key, event_type, json.dumps(safe_detail, sort_keys=True)),
                )
            conn.commit()

    def _transition(self, key, status, *, container_id=None, media_id=None,
                    provider_status=None, error_code=None, increment_attempt=False):
        fields = ["status = %s", "updated_at = NOW()"]
        values = [status]
        if container_id is not None:
            fields.append("container_id = %s")
            values.append(container_id)
        if media_id is not None:
            fields.append("media_id = %s")
            values.append(media_id)
        if provider_status is not None:
            fields.append("provider_status = %s")
            values.append(provider_status)
        if error_code is not None:
            fields.append("last_error_code = %s")
            values.append(error_code)
        if increment_attempt:
            fields.append("attempt_count = attempt_count + 1")
        values.append(key)
        safe_detail = {
            "status": status,
            "provider_status": provider_status,
            "error_code": error_code,
        }
        with self.db_connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "UPDATE instagram_publication_jobs SET " + ", ".join(fields)
                    + " WHERE idempotency_key = %s",
                    tuple(values),
                )
                cur.execute(
                    "INSERT INTO instagram_publication_events"
                    "(idempotency_key,event_type,safe_detail) "
                    "VALUES (%s,%s,%s::jsonb)",
                    (
                        key,
                        "STATE_TRANSITION",
                        json.dumps(safe_detail, sort_keys=True),
                    ),
                )
            conn.commit()

    def _count_guard(self):
        with self.db_connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT COUNT(*) FROM instagram_publication_jobs
                    WHERE status IN (
                        'PUBLISH_REQUESTED','UNKNOWN','PUBLISHED','VERIFIED',
                        'VERIFIED_RECOVERED','PUBLISHED_UNVERIFIED'
                    )
                      AND updated_at >= NOW() - INTERVAL '24 hours'
                    """
                )
                published_24h = int(cur.fetchone()[0])
                cur.execute(
                    """
                    SELECT COUNT(*) FROM instagram_publication_jobs
                    WHERE status IN (
                        'NEW','CONTAINER_CREATE_REQUESTED','CONTAINER_CREATED',
                        'PROCESSING','READY','PUBLISH_REQUESTED'
                    )
                    """
                )
                inflight = int(cur.fetchone()[0])
                cur.execute(
                    """
                    SELECT COUNT(*) FROM instagram_publication_jobs
                    WHERE status IN ('FAILED_FINAL','UNKNOWN','PUBLISHED_UNVERIFIED')
                      AND updated_at >= NOW() - INTERVAL '15 minutes'
                    """
                )
                failures_15m = int(cur.fetchone()[0])
                cur.execute(
                    """
                    SELECT COUNT(*) FROM instagram_publication_jobs
                    WHERE status NOT IN (
                        'VERIFIED','FAILED_FINAL','UNKNOWN','PUBLISHED_UNVERIFIED',
                        'HOLD_QUEUE_LIMIT'
                    )
                    """
                )
                unpublished_queue = int(cur.fetchone()[0])
                cur.execute(
                    """
                    SELECT COUNT(*) FROM instagram_publication_events
                    WHERE event_type = 'PROVIDER_MUTATION'
                      AND created_at >= NOW() - INTERVAL '1 minute'
                    """
                )
                mutations_1m = int(cur.fetchone()[0])
        return published_24h, inflight, failures_15m, unpublished_queue, mutations_1m

    @contextmanager
    def _advisory_lock(self, name):
        # PostgreSQL transaction advisory lock serializes cross-worker hard-limit decisions.
        with self.db_connect() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT pg_advisory_xact_lock(hashtext(%s))", (str(name),))
            try:
                yield
            finally:
                conn.commit()

    def _unresolved_ambiguity_exists(self, exclude_key=None):
        self._ensure_tables()
        with self.db_connect() as conn:
            with conn.cursor() as cur:
                if exclude_key:
                    cur.execute(
                        "SELECT COUNT(*) FROM instagram_publication_jobs "
                        "WHERE status IN (
                        'UNKNOWN','PUBLISHED_UNVERIFIED','PUBLISH_REQUESTED',
                        'CONTAINER_CREATE_REQUESTED'
                    ) "
                        "AND idempotency_key <> %s",
                        (exclude_key,),
                    )
                else:
                    cur.execute(
                        "SELECT COUNT(*) FROM instagram_publication_jobs "
                        "WHERE status IN (
                        'UNKNOWN','PUBLISHED_UNVERIFIED','PUBLISH_REQUESTED',
                        'CONTAINER_CREATE_REQUESTED'
                    )"
                    )
                return int(cur.fetchone()[0]) > 0

    def _provider_mutation_allowed(self, key, job):
        with self._advisory_lock("trendradar-instagram-provider-mutation"):
            if int(job.get("attempt_count") or 0) >= self.max_provider_mutations_per_job:
                self._transition(key, "HOLD_ATTEMPT_LIMIT", error_code="MAX_PROVIDER_MUTATIONS_PER_JOB")
                return False, "MAX_PROVIDER_MUTATIONS_PER_JOB"
            _, _, _, _, mutations_1m = self._count_guard()
            if mutations_1m >= self.max_api_mutations_per_minute:
                self._transition(key, "HOLD_MUTATION_RATE", error_code="MAX_API_MUTATIONS_PER_MINUTE")
                return False, "MAX_API_MUTATIONS_PER_MINUTE"
            self._event(key, "PROVIDER_MUTATION", {"allowed": True})
            return True, None

    def _credential_gate(self):
        if not self.governed_account_binding_valid:
            return None, "GOVERNED_ACCOUNT_BINDING_INVALID"
        rec = self.load_token_record()
        if not rec:
            return None, "NO_PERSISTED_TOKEN"
        username = str(rec.get("username") or "").strip().lstrip("@").lower()
        account_type = str(rec.get("account_type") or "").strip().replace(" ", "_").upper()
        user_id = rec.get("user_id")
        perms = {str(p) for p in (rec.get("granted_permissions") or [])}
        if username != GOVERNED_USERNAME:
            return None, "ACCOUNT_MISMATCH"
        if not user_id or account_type != "BUSINESS":
            return None, "BUSINESS_ACCOUNT_REQUIRED"
        if str(user_id) != GOVERNED_PROFESSIONAL_USER_ID:
            return None, "PROFESSIONAL_USER_ID_MISMATCH"
        if not {"instagram_business_basic", "instagram_business_content_publish"}.issubset(perms):
            return None, "PUBLISH_PERMISSION_MISSING"
        try:
            http, profile = self.graph(
                "GET", "me", rec["access_token"],
                params={"fields": "id,user_id,username,account_type"},
            )
        except Exception:
            return None, "CREDENTIAL_PROVIDER_CHECK_FAILED"
        if http >= 400:
            return None, "CREDENTIAL_PROVIDER_REJECTED"
        live_username = str(profile.get("username") or "").strip().lstrip("@").lower()
        live_type = str(profile.get("account_type") or "").strip().replace(" ", "_").upper()
        live_user_id = profile.get("user_id")
        if live_username != GOVERNED_USERNAME or str(live_user_id) != str(user_id):
            return None, "LIVE_ACCOUNT_BINDING_MISMATCH"
        if str(live_user_id) != GOVERNED_PROFESSIONAL_USER_ID:
            return None, "LIVE_PROFESSIONAL_USER_ID_MISMATCH"
        if live_type != GOVERNED_ACCOUNT_TYPE:
            return None, "LIVE_ACCOUNT_NOT_BUSINESS"
        return rec, None

    def _provider_quota_gate(self, rec):
        try:
            http, payload = self.graph(
                "GET",
                f"{rec['user_id']}/content_publishing_limit",
                rec["access_token"],
                params={"fields": "quota_usage"},
            )
        except Exception:
            return False, "PUBLISHING_LIMIT_CHECK_FAILED"
        if http >= 400:
            return False, "PUBLISHING_LIMIT_CHECK_REJECTED"
        data = payload.get("data") if isinstance(payload, dict) else None
        usage = None
        if isinstance(data, list) and data and isinstance(data[0], dict):
            usage = data[0].get("quota_usage")
        elif isinstance(payload, dict):
            usage = payload.get("quota_usage")
        try:
            usage = int(usage)
        except (TypeError, ValueError):
            return False, "PUBLISHING_LIMIT_UNKNOWN"
        if usage >= 100:
            return False, "PROVIDER_PUBLISHING_LIMIT_REACHED"
        return True, usage

    @staticmethod
    def _final_caption(intent):
        tags = " ".join("#" + t for t in intent.get("hashtags", []) if t)
        caption = intent.get("caption", "")
        value = (caption + ("\n\n" + tags if tags else "")).strip()
        return value[:2200]

    def _safe_job(self, job, *, replayed=False):
        if not job:
            return None
        return {
            "ok": True,
            "replayed": replayed,
            "idempotency_key": job.get("idempotency_key"),
            "publication_id": job.get("publication_id"),
            "content_asset_id": job.get("content_asset_id"),
            "correlation_id": job.get("correlation_id"),
            "status": job.get("status"),
            "container_id": job.get("container_id"),
            "media_id": job.get("media_id"),
            "provider_status": job.get("provider_status"),
            "attempt_count": job.get("attempt_count"),
            "last_error_code": job.get("last_error_code"),
            "public_publish_authorized": self.public_publish_authorized,
            "publish_enabled": self.publish_enabled,
        }

    def _create_container_for_job(self, key, job, rec):
        quota_ok, quota = self._provider_quota_gate(rec)
        if not quota_ok:
            self._transition(key, "HOLD_RATE_LIMIT", error_code=quota)
            return 429, self._safe_job(self._get_job(key))

        mutation_ok, _ = self._provider_mutation_allowed(key, job)
        if not mutation_ok:
            return 429, self._safe_job(self._get_job(key))

        # Persist the pre-side-effect marker before the provider mutation.
        # A restart from this state is ambiguous and must never blindly retry.
        self._transition(
            key,
            "CONTAINER_CREATE_REQUESTED",
            provider_status="REQUESTED",
            increment_attempt=True,
        )
        data = {
            "media_type": "REELS",
            "video_url": job["video_uri"],
            "caption": self._final_caption(job),
            "share_to_feed": "false",
            "is_ai_generated": "true" if job["is_ai_generated"] else "false",
        }
        try:
            http, provider = self.graph(
                "POST", f"{rec['user_id']}/media", rec["access_token"], data=data
            )
        except Exception:
            self._transition(
                key, "UNKNOWN",
                error_code="CREATE_CONTAINER_AMBIGUOUS",
            )
            return 502, self._safe_job(self._get_job(key))

        container_id = provider.get("id") if isinstance(provider, dict) else None
        if http >= 500:
            self._transition(
                key, "UNKNOWN",
                error_code="CREATE_CONTAINER_PROVIDER_5XX",
            )
            return 502, self._safe_job(self._get_job(key))
        if http >= 400 or not container_id:
            self._transition(
                key, "FAILED_FINAL",
                error_code="CREATE_CONTAINER_REJECTED",
            )
            return 422, self._safe_job(self._get_job(key))

        self._transition(
            key, "CONTAINER_CREATED",
            container_id=str(container_id), provider_status="CREATED",
        )
        return 202, self._safe_job(self._get_job(key))

    def start(self, payload):
        intent = self.validate_intent(payload)
        existing = self._get_job(intent["idempotency_key"])
        if existing:
            if existing["contract_sha256"] != intent["contract_sha256"]:
                return 409, {"ok": False, "error": "IDEMPOTENCY_CONFLICT"}
            return 200, self._safe_job(existing, replayed=True)

        existing_content = self._get_job_by_content_identity(
            intent["content_asset_id"], intent["asset_sha256"]
        )
        if existing_content:
            return 409, {
                "ok": False,
                "error": "CONTENT_ALREADY_BOUND_TO_PUBLICATION",
                "existing_publication_id": existing_content.get("publication_id"),
                "existing_status": existing_content.get("status"),
            }

        if not self.public_publish_authorized:
            conflict = self._reserve_job(intent, "HOLD_PUBLIC_DISABLED")
            if conflict:
                return conflict
            return 202, self._safe_job(self._get_job(intent["idempotency_key"]))
        if not self.publish_enabled:
            conflict = self._reserve_job(intent, "HOLD_KILL_SWITCH")
            if conflict:
                return conflict
            return 202, self._safe_job(self._get_job(intent["idempotency_key"]))

        if self._unresolved_ambiguity_exists():
            conflict = self._reserve_job(intent, "HOLD_CIRCUIT_OPEN")
            if conflict:
                return conflict
            self._transition(
                intent["idempotency_key"],
                "HOLD_CIRCUIT_OPEN",
                error_code="UNRESOLVED_PUBLICATION_AMBIGUITY",
            )
            return 503, self._safe_job(self._get_job(intent["idempotency_key"]))

        published_24h, inflight, failures_15m, unpublished_queue, mutations_1m = self._count_guard()
        if unpublished_queue >= self.max_unpublished_queue:
            conflict = self._reserve_job(intent, "HOLD_QUEUE_LIMIT")
            if conflict:
                return conflict
            self._transition(intent["idempotency_key"], "HOLD_QUEUE_LIMIT", error_code="MAX_UNPUBLISHED_QUEUE")
            return 429, self._safe_job(self._get_job(intent["idempotency_key"]))

        conflict = self._reserve_job(intent, "NEW")
        if conflict:
            return conflict

        if not self.configured():
            self._transition(intent["idempotency_key"], "HOLD_MEDIA_HOST", error_code="PUBLISHER_NOT_CONFIGURED")
            return 503, self._safe_job(self._get_job(intent["idempotency_key"]))

        published_24h, inflight, failures_15m, unpublished_queue, mutations_1m = self._count_guard()
        if published_24h >= self.max_daily_publications:
            self._transition(intent["idempotency_key"], "HOLD_BLAST_RADIUS", error_code="MAX_DAILY_PUBLICATIONS")
            return 429, self._safe_job(self._get_job(intent["idempotency_key"]))
        if inflight > self.max_inflight:
            self._transition(intent["idempotency_key"], "HOLD_CONCURRENCY", error_code="MAX_INFLIGHT")
            return 429, self._safe_job(self._get_job(intent["idempotency_key"]))
        if failures_15m >= self.circuit_failure_threshold:
            self._transition(intent["idempotency_key"], "HOLD_CIRCUIT_OPEN", error_code="RECENT_FAILURE_THRESHOLD")
            return 503, self._safe_job(self._get_job(intent["idempotency_key"]))

        rec, credential_error = self._credential_gate()
        if credential_error:
            self._transition(intent["idempotency_key"], "HOLD_CREDENTIAL", error_code=credential_error)
            return 503, self._safe_job(self._get_job(intent["idempotency_key"]))

        job = self._get_job(intent["idempotency_key"])
        return self._create_container_for_job(
            intent["idempotency_key"], job, rec
        )

    def reconcile(self, idempotency_key):
        key = str(idempotency_key or "").strip()
        if not key:
            return 400, {"ok": False, "error": "IDEMPOTENCY_KEY_REQUIRED"}
        job = self._get_job(key)
        if not job:
            return 404, {"ok": False, "error": "PUBLICATION_JOB_NOT_FOUND"}

        if job["status"] in TERMINAL_STATUSES:
            return 200, self._safe_job(job)
        if job["status"] == "PUBLISH_REQUESTED":
            self._transition(key, "UNKNOWN", error_code="PUBLISH_OUTCOME_AMBIGUOUS_AFTER_RESTART")
            return 409, self._safe_job(self._get_job(key))
        if job["status"] == "CONTAINER_CREATE_REQUESTED":
            self._transition(
                key,
                "UNKNOWN",
                error_code="CREATE_CONTAINER_OUTCOME_AMBIGUOUS_AFTER_RESTART",
            )
            return 409, self._safe_job(self._get_job(key))

        if job["status"] == "NEW":
            if not self.public_publish_authorized:
                self._transition(key, "HOLD_PUBLIC_DISABLED", error_code="PUBLIC_PUBLISH_DISABLED")
                return 202, self._safe_job(self._get_job(key))
            if not self.publish_enabled:
                self._transition(key, "HOLD_KILL_SWITCH", error_code="PUBLISH_KILL_SWITCH_DISABLED")
                return 202, self._safe_job(self._get_job(key))
            if not self.configured():
                self._transition(key, "HOLD_CREDENTIAL", error_code="PUBLISHER_NOT_CONFIGURED")
                return 503, self._safe_job(self._get_job(key))
            if self._unresolved_ambiguity_exists(exclude_key=key):
                self._transition(key, "HOLD_CIRCUIT_OPEN", error_code="UNRESOLVED_PUBLICATION_AMBIGUITY")
                return 503, self._safe_job(self._get_job(key))
            published_24h, inflight, failures_15m, _, _ = self._count_guard()
            if published_24h >= self.max_daily_publications:
                self._transition(key, "HOLD_BLAST_RADIUS", error_code="MAX_DAILY_PUBLICATIONS")
                return 429, self._safe_job(self._get_job(key))
            if inflight > self.max_inflight:
                self._transition(key, "HOLD_CONCURRENCY", error_code="MAX_INFLIGHT")
                return 429, self._safe_job(self._get_job(key))
            if failures_15m >= self.circuit_failure_threshold:
                self._transition(key, "HOLD_CIRCUIT_OPEN", error_code="RECENT_FAILURE_THRESHOLD")
                return 503, self._safe_job(self._get_job(key))

        rec, credential_error = self._credential_gate()
        if credential_error:
            self._transition(key, "HOLD_CREDENTIAL", error_code=credential_error)
            return 503, self._safe_job(self._get_job(key))

        if job["status"] == "NEW":
            return self._create_container_for_job(
                key, self._get_job(key), rec
            )

        if job["status"] in {"CONTAINER_CREATED", "PROCESSING"}:
            try:
                http, payload = self.graph(
                    "GET", job["container_id"], rec["access_token"],
                    params={"fields": "status_code,status"},
                )
            except Exception:
                self._transition(key, "PROCESSING", error_code="CONTAINER_STATUS_TEMPORARY_FAILURE")
                return 503, self._safe_job(self._get_job(key))
            if http >= 500:
                self._transition(key, "PROCESSING", error_code="CONTAINER_STATUS_PROVIDER_5XX")
                return 503, self._safe_job(self._get_job(key))
            if http >= 400:
                self._transition(key, "FAILED_FINAL", error_code="CONTAINER_STATUS_REJECTED")
                return 422, self._safe_job(self._get_job(key))
            status_code = str(payload.get("status_code") or "").upper()
            if status_code == "FINISHED":
                self._transition(key, "READY", provider_status=status_code)
            elif status_code in {"ERROR", "EXPIRED"}:
                self._transition(key, "FAILED_FINAL", provider_status=status_code, error_code="CONTAINER_NOT_PUBLISHABLE")
                return 422, self._safe_job(self._get_job(key))
            else:
                self._transition(key, "PROCESSING", provider_status=status_code or "IN_PROGRESS")
                return 202, self._safe_job(self._get_job(key))
            job = self._get_job(key)

        if job["status"] == "READY":
            # Serialize the irreversible media_publish decision across workers.
            with self._advisory_lock("trendradar-instagram-media-publish"):
                job = self._get_job(key)
                if job["status"] != "READY":
                    return 200, self._safe_job(job)
                if self._unresolved_ambiguity_exists(exclude_key=key):
                    self._transition(
                        key, "HOLD_CIRCUIT_OPEN",
                        error_code="UNRESOLVED_PUBLICATION_AMBIGUITY",
                    )
                    return 503, self._safe_job(self._get_job(key))
                if not self.public_publish_authorized:
                    self._transition(key, "HOLD_PUBLIC_DISABLED", error_code="PUBLIC_PUBLISH_DISABLED")
                    return 202, self._safe_job(self._get_job(key))
                if not self.publish_enabled:
                    self._transition(key, "HOLD_KILL_SWITCH", error_code="PUBLISH_KILL_SWITCH_DISABLED")
                    return 202, self._safe_job(self._get_job(key))

                # Potentially-public UNKNOWN/PUBLISH_REQUESTED outcomes consume daily blast radius.
                exposure_24h, _, failures_15m, _, _ = self._count_guard()
                if exposure_24h >= self.max_daily_publications:
                    self._transition(key, "HOLD_BLAST_RADIUS", error_code="MAX_DAILY_PUBLICATIONS")
                    return 429, self._safe_job(self._get_job(key))
                if failures_15m >= self.circuit_failure_threshold:
                    self._transition(key, "HOLD_CIRCUIT_OPEN", error_code="RECENT_FAILURE_THRESHOLD")
                    return 503, self._safe_job(self._get_job(key))

                mutation_ok, _ = self._provider_mutation_allowed(key, job)
                if not mutation_ok:
                    return 429, self._safe_job(self._get_job(key))
                self._transition(key, "PUBLISH_REQUESTED", provider_status="REQUESTED", increment_attempt=True)
                try:
                    http, payload = self.graph(
                        "POST", f"{rec['user_id']}/media_publish", rec["access_token"],
                        data={"creation_id": job["container_id"]},
                    )
                except Exception:
                    self._transition(key, "UNKNOWN", error_code="MEDIA_PUBLISH_AMBIGUOUS")
                    return 502, self._safe_job(self._get_job(key))

                media_id = payload.get("id") if isinstance(payload, dict) else None
                if http >= 500:
                    self._transition(key, "UNKNOWN", error_code="MEDIA_PUBLISH_PROVIDER_5XX")
                    return 502, self._safe_job(self._get_job(key))
                if http >= 400 or not media_id:
                    self._transition(key, "FAILED_FINAL", error_code="MEDIA_PUBLISH_REJECTED")
                    return 422, self._safe_job(self._get_job(key))

                self._transition(key, "PUBLISHED", media_id=str(media_id), provider_status="PUBLISHED")
                job = self._get_job(key)

        if job["status"] == "PUBLISHED":
            try:
                http, payload = self.graph(
                    "GET", job["media_id"], rec["access_token"],
                    params={"fields": "id,media_type,media_product_type,permalink,timestamp"},
                )
            except Exception:
                self._transition(key, "PUBLISHED_UNVERIFIED", error_code="VERIFY_REQUEST_FAILED")
                return 503, self._safe_job(self._get_job(key))
            if http >= 400 or str(payload.get("id") or "") != str(job["media_id"]):
                self._transition(key, "PUBLISHED_UNVERIFIED", error_code="VERIFY_REJECTED")
                return 503, self._safe_job(self._get_job(key))
            self._transition(key, "VERIFIED", provider_status=str(payload.get("media_product_type") or "VERIFIED"))
            return 200, self._safe_job(self._get_job(key))

        return 200, self._safe_job(self._get_job(key))

    def recover_unknown(self, idempotency_key, candidate_media_id):
        key = str(idempotency_key or "").strip()
        candidate = str(candidate_media_id or "").strip()
        if not key or not candidate:
            return 400, {"ok": False, "error": "RECOVERY_IDENTIFIERS_REQUIRED"}
        job = self._get_job(key)
        if not job:
            return 404, {"ok": False, "error": "PUBLICATION_JOB_NOT_FOUND"}
        if job["status"] not in {"UNKNOWN", "PUBLISHED_UNVERIFIED"}:
            return 409, {
                "ok": False,
                "error": "PUBLICATION_NOT_RECOVERABLE",
                "status": job["status"],
            }

        rec, credential_error = self._credential_gate()
        if credential_error:
            return 503, {"ok": False, "error": credential_error}
        try:
            http, payload = self.graph(
                "GET",
                f"{rec['user_id']}/media",
                rec["access_token"],
                params={
                    "fields": "id,caption,media_type,media_product_type,timestamp",
                    "limit": "100",
                },
            )
        except Exception:
            return 503, {"ok": False, "error": "RECOVERY_PROVIDER_CHECK_FAILED"}
        if http >= 400 or not isinstance(payload, dict):
            return 503, {"ok": False, "error": "RECOVERY_PROVIDER_CHECK_REJECTED"}

        matches = [
            item for item in (payload.get("data") or [])
            if isinstance(item, dict) and str(item.get("id") or "") == candidate
        ]
        if len(matches) != 1:
            return 409, {"ok": False, "error": "RECOVERY_MEDIA_NOT_FOUND_ON_ACCOUNT"}
        media = matches[0]
        if str(media.get("media_product_type") or "").upper() != "REELS":
            return 409, {"ok": False, "error": "RECOVERY_MEDIA_NOT_REEL"}
        if str(media.get("caption") or "").strip() != self._final_caption(job):
            return 409, {"ok": False, "error": "RECOVERY_CAPTION_MISMATCH"}

        self._transition(
            key,
            "VERIFIED_RECOVERED",
            media_id=candidate,
            provider_status="RECOVERED_VERIFIED",
        )
        self._event(key, "RECOVERY_VERIFIED", {"candidate_media_id": candidate})
        return 200, self._safe_job(self._get_job(key))

    def status(self, idempotency_key):
        key = str(idempotency_key or "").strip()
        if not key:
            return 400, {"ok": False, "error": "IDEMPOTENCY_KEY_REQUIRED"}
        job = self._get_job(key)
        if not job:
            return 404, {"ok": False, "error": "PUBLICATION_JOB_NOT_FOUND"}
        return 200, self._safe_job(job)

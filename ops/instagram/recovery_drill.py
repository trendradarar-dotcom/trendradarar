import argparse
import hashlib
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import psycopg


ROOT = Path(__file__).resolve().parents[2]
SERVICE_DIR = ROOT / "instagram_oauth_service"
if str(SERVICE_DIR) not in sys.path:
    sys.path.insert(0, str(SERVICE_DIR))

TABLE_ORDER = {
    "instagram_oauth_tokens": "account_key",
    "instagram_oauth_state_nonces": "nonce_hash",
    "instagram_media_assets": "content_asset_id",
    "instagram_publication_jobs": "idempotency_key",
    "instagram_publication_events": "event_id",
}


def _configure_app_env(dsn):
    os.environ["INSTAGRAM_DATABASE_URL"] = dsn
    os.environ["DATABASE_URL"] = dsn
    os.environ.setdefault("SESSION_SECRET", "synthetic-recovery-drill-session-secret")
    os.environ.setdefault("INSTAGRAM_TOKEN_ENCRYPTION_KEY", "MDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDA=")
    os.environ.setdefault("INSTAGRAM_APP_ID", "synthetic-app-id")
    os.environ.setdefault("INSTAGRAM_APP_SECRET", "synthetic-app-secret")
    os.environ.setdefault("INSTAGRAM_REDIRECT_URI", "https://example.invalid/callback")
    os.environ.setdefault("PUBLIC_BASE_URL", "https://example.invalid")
    os.environ.setdefault("INSTAGRAM_PUBLIC_PUBLISH_AUTHORIZED", "false")
    os.environ.setdefault("INSTAGRAM_PUBLISH_ENABLED", "false")
    os.environ.setdefault("INSTAGRAM_PUBLISH_M2M_SECRET", "synthetic-m2m-secret")
    os.environ.setdefault("INSTAGRAM_MEDIA_HOST_ALLOWLIST", "media.trendradar.com.co")
    os.environ.setdefault("INSTAGRAM_ALLOWED_MARKETS", "SA")
    os.environ.setdefault("INSTAGRAM_ALLOWED_LANGUAGES", "ar")


def _load_runtime_modules(dsn):
    _configure_app_env(dsn)
    import app as service_app
    from publisher_runtime import PublisherRuntime
    return service_app, PublisherRuntime


def _connect(dsn):
    return psycopg.connect(dsn, connect_timeout=10)


def _ensure_schema(dsn):
    service_app, PublisherRuntime = _load_runtime_modules(dsn)
    if not service_app._ensure_token_table():
        raise RuntimeError("token table was not created")
    if not service_app._ensure_publisher_media_table():
        raise RuntimeError("media table was not created")
    if not service_app._ensure_public_oauth_state_table():
        raise RuntimeError("oauth nonce table was not created")
    runtime = PublisherRuntime(
        db_connect=lambda: _connect(dsn),
        load_token_record=lambda: None,
        graph=lambda *a, **k: (_ for _ in ()).throw(RuntimeError("provider access forbidden")),
        expected_username="trendradarar",
        expected_professional_user_id="17841428134382903",
        publish_secret="synthetic-m2m-secret",
        public_publish_authorized=False,
        publish_enabled=False,
        media_host_allowlist=["media.trendradar.com.co"],
        allowed_markets=["SA"],
        allowed_languages=["ar"],
    )
    runtime._ensure_tables()


def _seed(dsn):
    _ensure_schema(dsn)
    with _connect(dsn) as conn:
        with conn.cursor() as cur:
            for table in reversed(list(TABLE_ORDER)):
                cur.execute(f"DELETE FROM {table}")

            cur.execute(
                """
                INSERT INTO instagram_oauth_tokens(account_key,ciphertext,updated_at)
                VALUES (%s,%s,%s)
                """,
                (
                    "trendradarar",
                    b"synthetic-ciphertext-not-a-real-secret",
                    datetime(2026, 9, 28, 0, 0, tzinfo=timezone.utc),
                ),
            )
            cur.execute(
                """
                INSERT INTO instagram_oauth_state_nonces(nonce_hash,expires_at,created_at)
                VALUES (%s,%s,%s)
                """,
                (
                    "0" * 64,
                    datetime(2099, 1, 1, 0, 0, tzinfo=timezone.utc),
                    datetime(2026, 9, 28, 0, 0, tzinfo=timezone.utc),
                ),
            )
            cur.execute(
                """
                INSERT INTO instagram_media_assets(
                    content_asset_id,public_token,sha256,mime_type,size_bytes,
                    metadata_json,data,created_at,expires_at
                ) VALUES (%s,%s,%s,%s,%s,%s::jsonb,%s,%s,%s)
                """,
                (
                    "recovery-asset-media",
                    "synthetic-public-token",
                    "d" * 64,
                    "video/mp4",
                    21,
                    json.dumps({
                        "mime_type": "video/mp4",
                        "duration_seconds": 4,
                        "video_codec": "h264",
                        "audio_codec": "aac",
                        "decoded_video_frames": 120,
                        "decoded_audio_frames": 188,
                    }, sort_keys=True),
                    b"synthetic-media-bytes",
                    datetime(2026, 9, 28, 0, 0, tzinfo=timezone.utc),
                    datetime(2099, 1, 1, 0, 0, tzinfo=timezone.utc),
                ),
            )

            jobs = [
                ("idem-verified","pub-verified","asset-verified","corr-verified","a"*64,"VERIFIED","container-v","media-v",None),
                ("idem-unknown","pub-unknown","asset-unknown","corr-unknown","b"*64,"UNKNOWN","container-u",None,"PUBLISH_OUTCOME_AMBIGUOUS"),
                ("idem-create","pub-create","asset-create","corr-create","c"*64,"CONTAINER_CREATE_REQUESTED",None,None,None),
            ]
            for key,pub,asset,corr,sha,status,container_id,media_id,error_code in jobs:
                cur.execute(
                    """
                    INSERT INTO instagram_publication_jobs(
                        idempotency_key,publication_id,content_asset_id,correlation_id,
                        contract_sha256,account_key,video_uri,asset_sha256,caption,
                        hashtags_json,market,language,rights_status,policy_status,
                        legal_status,commercial_status,is_ai_generated,status,
                        container_id,media_id,provider_status,attempt_count,last_error_code,
                        created_at,updated_at
                    ) VALUES (
                        %s,%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb,%s,%s,%s,%s,%s,%s,%s,%s,
                        %s,%s,%s,%s,%s,%s,%s
                    )
                    """,
                    (
                        key,pub,asset,corr,hashlib.sha256(key.encode()).hexdigest(),
                        "trendradarar","https://media.trendradar.com.co/recovery.mp4",
                        sha,"Synthetic recovery drill",json.dumps(["trendradar"]),
                        "SA","ar","PASS","PASS","PASS","EDITORIAL_ORIGINAL",True,status,
                        container_id,media_id,
                        "REQUESTED" if status == "CONTAINER_CREATE_REQUESTED" else None,
                        1 if status == "CONTAINER_CREATE_REQUESTED" else 0,
                        error_code,
                        datetime(2026, 9, 28, 0, 0, tzinfo=timezone.utc),
                        datetime(2026, 9, 28, 0, 0, tzinfo=timezone.utc),
                    ),
                )
                cur.execute(
                    """
                    INSERT INTO instagram_publication_events(
                        idempotency_key,event_type,safe_detail,created_at
                    ) VALUES (%s,%s,%s::jsonb,%s)
                    """,
                    (
                        key,
                        "DRILL_SEED",
                        json.dumps({"status": status}, sort_keys=True),
                        datetime(2026, 9, 28, 0, 0, tzinfo=timezone.utc),
                    ),
                )
        conn.commit()


def _normalize(value):
    if isinstance(value, (bytes, bytearray, memoryview)):
        data = bytes(value)
        return {"bytes_sha256": hashlib.sha256(data).hexdigest(), "length": len(data)}
    if isinstance(value, datetime):
        return value.astimezone(timezone.utc).isoformat()
    if isinstance(value, (dict, list)):
        return value
    return value


def _snapshot(dsn):
    snapshot = {"tables": {}, "indexes": []}
    with _connect(dsn) as conn:
        with conn.cursor() as cur:
            for table, order_by in TABLE_ORDER.items():
                cur.execute(f"SELECT * FROM {table} ORDER BY {order_by}")
                columns = [desc.name for desc in cur.description]
                rows = []
                for row in cur.fetchall():
                    rows.append({
                        name: _normalize(value)
                        for name, value in zip(columns, row)
                    })
                snapshot["tables"][table] = rows

            cur.execute(
                """
                SELECT tablename,indexname,indexdef
                FROM pg_indexes
                WHERE schemaname='public'
                  AND tablename = ANY(%s)
                ORDER BY tablename,indexname
                """,
                (list(TABLE_ORDER),),
            )
            snapshot["indexes"] = [
                {"table": row[0], "name": row[1], "definition": row[2]}
                for row in cur.fetchall()
            ]

    canonical = json.dumps(snapshot, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    snapshot["canonical_sha256"] = hashlib.sha256(canonical.encode()).hexdigest()
    return snapshot


def _write_json(path, data):
    Path(path).write_text(json.dumps(data, indent=2, sort_keys=True), encoding="utf-8")


def _verify_recovery_semantics(dsn):
    _, PublisherRuntime = _load_runtime_modules(dsn)
    provider_calls = []

    def forbidden_graph(*args, **kwargs):
        provider_calls.append((args, kwargs))
        raise AssertionError("provider mutation/read must not occur in restored ambiguity drill")

    runtime = PublisherRuntime(
        db_connect=lambda: _connect(dsn),
        load_token_record=lambda: {
            "username": "trendradarar",
            "account_type": "BUSINESS",
            "user_id": "17841428134382903",
            "granted_permissions": [
                "instagram_business_basic",
                "instagram_business_content_publish",
            ],
            "access_token": "synthetic-token",
        },
        graph=forbidden_graph,
        expected_username="trendradarar",
        expected_professional_user_id="17841428134382903",
        publish_secret="synthetic-m2m-secret",
        public_publish_authorized=True,
        publish_enabled=True,
        media_host_allowlist=["media.trendradar.com.co"],
        allowed_markets=["SA"],
        allowed_languages=["ar"],
    )

    status, job = runtime.reconcile("idem-create")
    if status != 409 or job.get("status") != "UNKNOWN":
        raise AssertionError((status, job))
    if job.get("last_error_code") != "CREATE_CONTAINER_OUTCOME_AMBIGUOUS_AFTER_RESTART":
        raise AssertionError(job)
    if provider_calls:
        raise AssertionError("provider was called during restored ambiguous reconciliation")

    with _connect(dsn) as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT status FROM instagram_publication_jobs WHERE idempotency_key='idem-unknown'"
            )
            if cur.fetchone()[0] != "UNKNOWN":
                raise AssertionError("restored UNKNOWN state was not preserved")

    return {
        "restored_container_create_requested_reconciles_to": "UNKNOWN",
        "blind_provider_retry_calls": len(provider_calls),
        "preexisting_unknown_preserved": True,
    }


def main():
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)

    seed = sub.add_parser("seed")
    seed.add_argument("--dsn", required=True)
    seed.add_argument("--evidence", required=True)

    snap = sub.add_parser("snapshot")
    snap.add_argument("--dsn", required=True)
    snap.add_argument("--evidence", required=True)

    verify = sub.add_parser("verify")
    verify.add_argument("--dsn", required=True)
    verify.add_argument("--expected", required=True)
    verify.add_argument("--evidence", required=True)

    args = parser.parse_args()

    if args.command == "seed":
        _seed(args.dsn)
        evidence = _snapshot(args.dsn)
        evidence["phase"] = "seeded_source_database"
        _write_json(args.evidence, evidence)
        return

    if args.command == "snapshot":
        _write_json(args.evidence, _snapshot(args.dsn))
        return

    expected = json.loads(Path(args.expected).read_text(encoding="utf-8"))
    restored = _snapshot(args.dsn)
    if restored["canonical_sha256"] != expected["canonical_sha256"]:
        raise AssertionError({
            "expected": expected["canonical_sha256"],
            "restored": restored["canonical_sha256"],
        })

    required_indexes = {
        "instagram_publication_unique_content_asset",
        "instagram_publication_unique_asset_hash",
    }
    restored_indexes = {item["name"] for item in restored["indexes"]}
    missing = sorted(required_indexes - restored_indexes)
    if missing:
        raise AssertionError({"missing_indexes": missing})

    semantics = _verify_recovery_semantics(args.dsn)
    evidence = {
        "phase": "restored_database_verified",
        "pre_reconcile_snapshot_sha256": restored["canonical_sha256"],
        "expected_snapshot_sha256": expected["canonical_sha256"],
        "required_unique_indexes_present": True,
        "recovery_semantics": semantics,
        "result": "PASS",
    }
    _write_json(args.evidence, evidence)


if __name__ == "__main__":
    main()

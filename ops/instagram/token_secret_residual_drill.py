#!/usr/bin/env python3
"""
Instagram-only synthetic credential rotation drill.
No production secrets, provider mutations, Render mutations, or production DB access.
Outputs status-only evidence; secret values are never printed or written.
"""
import base64
import hashlib
import hmac
import importlib
import json
import os
import secrets
import sys
from pathlib import Path

from cryptography.fernet import Fernet, InvalidToken
import psycopg

ROOT = Path(__file__).resolve().parents[2]
SERVICE = ROOT / "instagram_oauth_service"
GATEWAY = ROOT / "instagram_oauth_gateway"
EVIDENCE_DIR = ROOT / "evidence" / "instagram-token-secret-security"
EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)

RESULTS = {}

def record(name, ok, detail=None):
    RESULTS[name] = {"status": "PASS" if ok else "FAIL"}
    if detail:
        RESULTS[name]["detail"] = detail
    if not ok:
        raise AssertionError(name)

def b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")

def signed_request(secret: str, user_id: str) -> str:
    payload = json.dumps({"user_id": user_id}, separators=(",", ":"), sort_keys=True).encode()
    encoded_payload = b64url(payload)
    sig = hmac.new(secret.encode(), encoded_payload.encode(), hashlib.sha256).digest()
    return f"{b64url(sig)}.{encoded_payload}"

def clear_modules():
    for name in ["app", "publisher_runtime", "trendhunter_instagram_publisher"]:
        sys.modules.pop(name, None)

def load_backend(config):
    clear_modules()
    for key in [
        "INSTAGRAM_APP_ID", "INSTAGRAM_APP_SECRET", "INSTAGRAM_REDIRECT_URI",
        "SESSION_SECRET", "INSTAGRAM_OAUTH_GATEWAY_SECRET",
        "INSTAGRAM_TOKEN_ENCRYPTION_KEY", "INSTAGRAM_REFRESH_SECRET",
        "INSTAGRAM_PUBLISH_M2M_SECRET", "INSTAGRAM_DATABASE_URL", "DATABASE_URL",
        "INSTAGRAM_PUBLIC_PUBLISH_AUTHORIZED", "INSTAGRAM_PUBLISH_ENABLED",
        "INSTAGRAM_PERSISTENCE_REQUIRED", "INSTAGRAM_REFRESH_SELF_TEST",
        "INSTAGRAM_PUBLISHER_SELF_TEST",
    ]:
        os.environ.pop(key, None)
    os.environ.update({
        "INSTAGRAM_APP_ID": "synthetic-app-id",
        "INSTAGRAM_REDIRECT_URI": "https://example.invalid/callback",
        "INSTAGRAM_PUBLIC_PUBLISH_AUTHORIZED": "false",
        "INSTAGRAM_PUBLISH_ENABLED": "false",
        "INSTAGRAM_PERSISTENCE_REQUIRED": "false",
        "INSTAGRAM_REFRESH_SELF_TEST": "false",
        "INSTAGRAM_PUBLISHER_SELF_TEST": "false",
        **config,
    })
    sys.path.insert(0, str(SERVICE))
    try:
        mod = importlib.import_module("app")
    finally:
        if sys.path[0] == str(SERVICE):
            sys.path.pop(0)
    return mod

def load_gateway(secret):
    sys.modules.pop("app", None)
    os.environ["INSTAGRAM_OAUTH_GATEWAY_SECRET"] = secret
    os.environ["INSTAGRAM_OAUTH_UPSTREAM_URL"] = "https://example.invalid"
    os.environ["INSTAGRAM_OAUTH_PUBLIC_ORIGIN"] = "https://trendradar.com.co"
    sys.path.insert(0, str(GATEWAY))
    try:
        mod = importlib.import_module("app")
    finally:
        if sys.path[0] == str(GATEWAY):
            sys.path.pop(0)
    return mod

def probe_backend_rotation():
    old = {
        "INSTAGRAM_APP_SECRET": secrets.token_urlsafe(32),
        "SESSION_SECRET": secrets.token_urlsafe(32),
        "INSTAGRAM_OAUTH_GATEWAY_SECRET": secrets.token_urlsafe(32),
        "INSTAGRAM_TOKEN_ENCRYPTION_KEY": Fernet.generate_key().decode(),
        "INSTAGRAM_REFRESH_SECRET": secrets.token_urlsafe(32),
        "INSTAGRAM_PUBLISH_M2M_SECRET": secrets.token_urlsafe(32),
    }
    new = {
        "INSTAGRAM_APP_SECRET": secrets.token_urlsafe(32),
        "SESSION_SECRET": secrets.token_urlsafe(32),
        "INSTAGRAM_OAUTH_GATEWAY_SECRET": secrets.token_urlsafe(32),
        "INSTAGRAM_TOKEN_ENCRYPTION_KEY": Fernet.generate_key().decode(),
        "INSTAGRAM_REFRESH_SECRET": secrets.token_urlsafe(32),
        "INSTAGRAM_PUBLISH_M2M_SECRET": secrets.token_urlsafe(32),
    }

    old_mod = load_backend(old)

    # App-secret signed deauthorization verification.
    old_signed = signed_request(old["INSTAGRAM_APP_SECRET"], "synthetic-user")
    new_signed = signed_request(new["INSTAGRAM_APP_SECRET"], "synthetic-user")
    record("APP_SECRET_OLD_ACCEPTED_BEFORE_ROTATION", bool(old_mod._parse_signed_request(old_signed)))
    record("APP_SECRET_NEW_REJECTED_BEFORE_ROTATION", old_mod._parse_signed_request(new_signed) is None)

    # M2M publisher secret.
    record("M2M_OLD_ACCEPTED_BEFORE_ROTATION", old_mod.PUBLISHER.authorize(old["INSTAGRAM_PUBLISH_M2M_SECRET"]))
    record("M2M_NEW_REJECTED_BEFORE_ROTATION", not old_mod.PUBLISHER.authorize(new["INSTAGRAM_PUBLISH_M2M_SECRET"]))

    # Gateway shared secret at backend boundary.
    with old_mod.app.test_request_context(headers={"X-TrendRadar-Gateway": old["INSTAGRAM_OAUTH_GATEWAY_SECRET"]}):
        record("GATEWAY_OLD_ACCEPTED_BEFORE_ROTATION", old_mod._gateway_authorized())
    with old_mod.app.test_request_context(headers={"X-TrendRadar-Gateway": new["INSTAGRAM_OAUTH_GATEWAY_SECRET"]}):
        record("GATEWAY_NEW_REJECTED_BEFORE_ROTATION", not old_mod._gateway_authorized())

    # Refresh secret: accepted secret gets beyond auth (then fails closed because synthetic DB is absent).
    c = old_mod.app.test_client()
    old_http = c.post("/internal/refresh-instagram-token", headers={"X-TrendRadar-Refresh": old["INSTAGRAM_REFRESH_SECRET"]}).status_code
    new_http = c.post("/internal/refresh-instagram-token", headers={"X-TrendRadar-Refresh": new["INSTAGRAM_REFRESH_SECRET"]}).status_code
    record("REFRESH_OLD_ACCEPTED_BEFORE_ROTATION", old_http != 403, f"http={old_http}")
    record("REFRESH_NEW_REJECTED_BEFORE_ROTATION", new_http == 403, f"http={new_http}")

    # Session/OAuth-state signing.
    old_mod._store_public_oauth_nonce = lambda nonce, ttl_seconds=900: True
    old_mod._consume_public_oauth_nonce = lambda nonce: True
    old_state = old_mod._make_public_oauth_state()
    record("SESSION_OLD_STATE_VALID_BEFORE_ROTATION", old_mod._verify_public_oauth_state(old_state) is not None)

    # Encryption-key behavior and safe re-encryption pattern.
    payload = b'{"access_token":"synthetic-only","user_id":"synthetic-user"}'
    old_fernet = old_mod._fernet()
    old_ciphertext = old_fernet.encrypt(payload)

    new_mod = load_backend(new)
    new_mod._consume_public_oauth_nonce = lambda nonce: True

    record("APP_SECRET_OLD_REJECTED_AFTER_ROTATION", new_mod._parse_signed_request(old_signed) is None)
    record("APP_SECRET_NEW_ACCEPTED_AFTER_ROTATION", bool(new_mod._parse_signed_request(new_signed)))

    record("M2M_OLD_REJECTED_AFTER_ROTATION", not new_mod.PUBLISHER.authorize(old["INSTAGRAM_PUBLISH_M2M_SECRET"]))
    record("M2M_NEW_ACCEPTED_AFTER_ROTATION", new_mod.PUBLISHER.authorize(new["INSTAGRAM_PUBLISH_M2M_SECRET"]))

    with new_mod.app.test_request_context(headers={"X-TrendRadar-Gateway": old["INSTAGRAM_OAUTH_GATEWAY_SECRET"]}):
        record("GATEWAY_OLD_REJECTED_AFTER_ROTATION", not new_mod._gateway_authorized())
    with new_mod.app.test_request_context(headers={"X-TrendRadar-Gateway": new["INSTAGRAM_OAUTH_GATEWAY_SECRET"]}):
        record("GATEWAY_NEW_ACCEPTED_AFTER_ROTATION", new_mod._gateway_authorized())

    c2 = new_mod.app.test_client()
    old_http2 = c2.post("/internal/refresh-instagram-token", headers={"X-TrendRadar-Refresh": old["INSTAGRAM_REFRESH_SECRET"]}).status_code
    new_http2 = c2.post("/internal/refresh-instagram-token", headers={"X-TrendRadar-Refresh": new["INSTAGRAM_REFRESH_SECRET"]}).status_code
    record("REFRESH_OLD_REJECTED_AFTER_ROTATION", old_http2 == 403, f"http={old_http2}")
    record("REFRESH_NEW_ACCEPTED_AFTER_ROTATION", new_http2 != 403, f"http={new_http2}")

    record("SESSION_OLD_STATE_REJECTED_AFTER_ROTATION", new_mod._verify_public_oauth_state(old_state) is None)
    new_mod._store_public_oauth_nonce = lambda nonce, ttl_seconds=900: True
    new_mod._consume_public_oauth_nonce = lambda nonce: True
    new_state = new_mod._make_public_oauth_state()
    record("SESSION_NEW_STATE_ACCEPTED_AFTER_ROTATION", new_mod._verify_public_oauth_state(new_state) is not None)

    new_fernet = new_mod._fernet()
    try:
        new_fernet.decrypt(old_ciphertext)
        old_cipher_rejected = False
    except InvalidToken:
        old_cipher_rejected = True
    record("ENCRYPTION_NAIVE_ROTATION_BREAKS_OLD_CIPHERTEXT", old_cipher_rejected)

    recovered_plaintext = old_fernet.decrypt(old_ciphertext)
    migrated_ciphertext = new_fernet.encrypt(recovered_plaintext)
    record("ENCRYPTION_REENCRYPTION_PRESERVES_PLAINTEXT", new_fernet.decrypt(migrated_ciphertext) == payload)
    try:
        old_fernet.decrypt(migrated_ciphertext)
        old_key_rejected = False
    except InvalidToken:
        old_key_rejected = True
    record("ENCRYPTION_OLD_KEY_REJECTED_AFTER_REENCRYPTION", old_key_rejected)

    old_gateway = load_gateway(old["INSTAGRAM_OAUTH_GATEWAY_SECRET"])
    new_gateway = load_gateway(new["INSTAGRAM_OAUTH_GATEWAY_SECRET"])
    record("GATEWAY_PROCESS_LOADS_ROTATED_SECRET", old_gateway.GATEWAY_SECRET != new_gateway.GATEWAY_SECRET)
    record("GATEWAY_REMAINS_FAIL_CLOSED_FOR_BROWSER_OAUTH", new_gateway.OAUTH_BROWSER_HARD_DISABLED is True)

def probe_database_credential_rotation():
    host = os.environ.get("ROTATION_DB_HOST", "127.0.0.1")
    port = os.environ.get("ROTATION_DB_PORT", "5432")
    dbname = os.environ.get("ROTATION_DB_NAME", "postgres")
    user = os.environ.get("ROTATION_DB_USER", "postgres")
    old_password = os.environ["ROTATION_DB_OLD_PASSWORD"]
    new_password = os.environ["ROTATION_DB_NEW_PASSWORD"]

    def connect(password):
        return psycopg.connect(host=host, port=port, dbname=dbname, user=user, password=password, connect_timeout=5)

    with connect(old_password) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT 1")
            record("DB_OLD_CREDENTIAL_ACCEPTED_BEFORE_ROTATION", cur.fetchone()[0] == 1)
            cur.execute("ALTER ROLE postgres PASSWORD %s", (new_password,))
        conn.commit()

    old_rejected = False
    try:
        with connect(old_password):
            pass
    except Exception:
        old_rejected = True
    record("DB_OLD_CREDENTIAL_REJECTED_AFTER_ROTATION", old_rejected)

    with connect(new_password) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT 1")
            record("DB_NEW_CREDENTIAL_ACCEPTED_AFTER_ROTATION", cur.fetchone()[0] == 1)

def main():
    probe_backend_rotation()
    probe_database_credential_rotation()
    evidence = {
        "scope": "TrendHunter / Trend Radar — Instagram only",
        "mode": "synthetic isolated credential rotation drill",
        "production_secrets_used": False,
        "production_database_touched": False,
        "render_mutation_performed": False,
        "provider_mutation_performed": False,
        "public_publish_authorized": False,
        "instagram_publish_enabled": False,
        "results": RESULTS,
        "summary": {
            "all_pass": all(v["status"] == "PASS" for v in RESULTS.values()),
            "tests": len(RESULTS),
        },
    }
    out = EVIDENCE_DIR / "token-secret-residual-drill.json"
    out.write_text(json.dumps(evidence, indent=2, sort_keys=True), encoding="utf-8")
    print(json.dumps({
        "event": "INSTAGRAM_TOKEN_SECRET_RESIDUAL_DRILL",
        "all_pass": evidence["summary"]["all_pass"],
        "tests": evidence["summary"]["tests"],
        "production_secrets_used": False,
        "production_database_touched": False,
        "render_mutation_performed": False,
        "provider_mutation_performed": False,
    }, sort_keys=True))
    if not evidence["summary"]["all_pass"]:
        raise SystemExit(1)

if __name__ == "__main__":
    main()

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import secrets
import time
from dataclasses import dataclass
from typing import Iterable


class SecurityError(RuntimeError):
    pass


def _b64url_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _b64url_decode(value: str) -> bytes:
    pad = "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode((value + pad).encode("ascii"))


@dataclass(frozen=True)
class AuthenticatedActor:
    subject: str
    roles: frozenset[str]
    issued_at: int
    expires_at: int
    token_id: str
    auth_method: str = "HMAC_SHA256_BEARER"

    def has_role(self, role: str) -> bool:
        return role in self.roles or "admin" in self.roles

    def audit_context(self) -> dict:
        return {
            "authenticated": True,
            "subject": self.subject,
            "roles": sorted(self.roles),
            "issued_at": self.issued_at,
            "expires_at": self.expires_at,
            "token_id": self.token_id,
            "auth_method": self.auth_method,
        }


class HMACTokenAuthority:
    """Small standard-library authentication primitive for operational local/API hardening.

    This is not an identity-provider replacement. It gives the application a cryptographic
    binding between an approval request and an authenticated subject, while the signing secret
    remains external to the ledger/package. Production deployment can later replace this adapter
    with OIDC/SAML without changing the governed authorization payload contract.
    """

    def __init__(self, secret: str | bytes):
        if isinstance(secret, str):
            secret = secret.encode("utf-8")
        if len(secret) < 32:
            raise SecurityError("Authentication signing secret must be at least 32 bytes")
        self._secret = bytes(secret)

    @classmethod
    def from_env(cls, env_name: str = "TREND_HUNTER_AUTH_SECRET") -> "HMACTokenAuthority":
        value = os.environ.get(env_name)
        if not value:
            raise SecurityError(f"Missing required authentication secret environment variable: {env_name}")
        return cls(value)

    def issue(self, subject: str, roles: Iterable[str], *, ttl_seconds: int = 3600, now: int | None = None) -> str:
        subject = subject.strip()
        role_set = sorted({r.strip() for r in roles if r and r.strip()})
        if not subject:
            raise SecurityError("Token subject is required")
        if not role_set:
            raise SecurityError("At least one role is required")
        if ttl_seconds <= 0 or ttl_seconds > 86400:
            raise SecurityError("ttl_seconds must be in 1..86400")
        now_i = int(time.time() if now is None else now)
        payload = {
            "sub": subject,
            "roles": role_set,
            "iat": now_i,
            "exp": now_i + ttl_seconds,
            "jti": secrets.token_hex(16),
            "v": 1,
        }
        encoded = _b64url_encode(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8"))
        sig = _b64url_encode(hmac.new(self._secret, encoded.encode("ascii"), hashlib.sha256).digest())
        return f"th1.{encoded}.{sig}"

    def verify(self, token: str, *, now: int | None = None) -> AuthenticatedActor:
        try:
            prefix, encoded, signature = token.split(".", 2)
        except ValueError as exc:
            raise SecurityError("Malformed bearer token") from exc
        if prefix != "th1":
            raise SecurityError("Unsupported bearer token version")
        expected = hmac.new(self._secret, encoded.encode("ascii"), hashlib.sha256).digest()
        try:
            supplied = _b64url_decode(signature)
        except Exception as exc:
            raise SecurityError("Malformed bearer token signature") from exc
        if not hmac.compare_digest(expected, supplied):
            raise SecurityError("Invalid bearer token signature")
        try:
            payload = json.loads(_b64url_decode(encoded).decode("utf-8"))
        except Exception as exc:
            raise SecurityError("Malformed bearer token payload") from exc
        now_i = int(time.time() if now is None else now)
        if int(payload.get("exp", 0)) <= now_i:
            raise SecurityError("Bearer token expired")
        if int(payload.get("iat", 0)) > now_i + 60:
            raise SecurityError("Bearer token issued in the future")
        subject = str(payload.get("sub", "")).strip()
        roles = payload.get("roles") or []
        if not subject or not isinstance(roles, list) or not roles:
            raise SecurityError("Bearer token missing subject/roles")
        return AuthenticatedActor(
            subject=subject,
            roles=frozenset(str(x) for x in roles),
            issued_at=int(payload["iat"]),
            expires_at=int(payload["exp"]),
            token_id=str(payload.get("jti") or ""),
        )


class SecretResolver:
    """Resolve secrets without persisting plaintext values in governed artifacts."""

    @staticmethod
    def resolve(ref: str) -> str:
        if not ref.startswith("env://"):
            raise SecurityError("Only env:// secret references are admitted in Operationalization O1")
        name = ref[len("env://"):]
        if not name or not name.replace("_", "").isalnum():
            raise SecurityError("Invalid environment secret reference")
        value = os.environ.get(name)
        if not value:
            raise SecurityError(f"Secret dependency is not available: {ref}")
        return value

    @staticmethod
    def is_available(ref: str) -> bool:
        try:
            SecretResolver.resolve(ref)
            return True
        except SecurityError:
            return False

    @staticmethod
    def redacted(ref: str) -> dict:
        return {"secret_ref": ref, "available": SecretResolver.is_available(ref), "plaintext_persisted": False}

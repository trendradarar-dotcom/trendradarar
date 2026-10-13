from __future__ import annotations

import base64
import ctypes
import hashlib
import http.client
import json
import mimetypes
import os
import re
import secrets
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Protocol

from .ledger import GovernanceLedger, LedgerError, ArtifactRef
from .db import connect
from .operational import OperationalBindingService
from .security import SecretResolver
from .util import utcnow

YOUTUBE_UPLOAD_SCOPE = "https://www.googleapis.com/auth/youtube.upload"
GOOGLE_AUTH_ENDPOINT = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_ENDPOINT = "https://oauth2.googleapis.com/token"
YOUTUBE_CHANNELS_ENDPOINT = "https://www.googleapis.com/youtube/v3/channels"
YOUTUBE_RESUMABLE_INIT_ENDPOINT = "https://www.googleapis.com/upload/youtube/v3/videos"
_ALLOWED_OAUTH_HOSTS = frozenset({"accounts.google.com", "oauth2.googleapis.com", "www.googleapis.com"})
_ALLOWED_UPLOAD_SESSION_HOSTS = frozenset({"www.googleapis.com"})
OAUTH_ATTEMPT_TTL_SECONDS = 10 * 60
YOUTUBE_RESUMABLE_CHUNK_BYTES = 8 * 1024 * 1024


@dataclass(frozen=True)
class OAuthAuthorizationRequest:
    authorization_url: str
    state: str
    code_verifier: str
    code_challenge: str
    redirect_uri: str
    scopes: tuple[str, ...]


@dataclass(frozen=True)
class OAuthTokenBundle:
    access_token: str
    refresh_token: str | None
    token_type: str
    expires_in: int
    scopes: tuple[str, ...]
    token_receipt_state_id: str | None = None


class RefreshTokenStore(Protocol):
    def put(self, key: str, secret: str) -> str: ...
    def get(self, ref: str) -> str: ...


class InMemoryRefreshTokenStore:
    """Test-only secret sink. Never use for persistence."""
    def __init__(self): self._items: dict[str, str] = {}
    def put(self, key: str, secret: str) -> str:
        ref = f"memory://{key}"
        self._items[ref] = secret
        return ref
    def get(self, ref: str) -> str:
        if ref not in self._items: raise LedgerError("Refresh token secret is unavailable")
        return self._items[ref]


class WindowsDPAPIRefreshTokenStore:
    """Windows user-scoped DPAPI storage outside the project/package tree.

    The ledger stores only the returned ``dpapi-user://`` reference. Plaintext refresh tokens are
    never written into the ledger, logs, package, or project directory.
    """
    _SAFE = re.compile(r"[^A-Za-z0-9_.-]+")

    def __init__(self, root: str | Path | None = None):
        if os.name != "nt":
            raise LedgerError("Windows DPAPI refresh-token store is only available on Windows")
        base = Path(root) if root else Path(os.environ.get("LOCALAPPDATA") or Path.home()) / "TrendHunter" / "secrets"
        self.root = base
        self.root.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def _crypt(data: bytes, *, protect: bool) -> bytes:
        from ctypes import wintypes

        class DATA_BLOB(ctypes.Structure):
            _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_byte))]

        in_buf = ctypes.create_string_buffer(data)
        in_blob = DATA_BLOB(len(data), ctypes.cast(in_buf, ctypes.POINTER(ctypes.c_byte)))
        out_blob = DATA_BLOB()
        crypt32 = ctypes.windll.crypt32
        kernel32 = ctypes.windll.kernel32
        flags = 0x1  # CRYPTPROTECT_UI_FORBIDDEN
        if protect:
            ok = crypt32.CryptProtectData(ctypes.byref(in_blob), None, None, None, None, flags, ctypes.byref(out_blob))
        else:
            ok = crypt32.CryptUnprotectData(ctypes.byref(in_blob), None, None, None, None, flags, ctypes.byref(out_blob))
        if not ok:
            raise LedgerError("Windows DPAPI operation failed")
        try:
            return ctypes.string_at(out_blob.pbData, out_blob.cbData)
        finally:
            kernel32.LocalFree(out_blob.pbData)

    def put(self, key: str, secret: str) -> str:
        safe = self._SAFE.sub("_", key).strip("._") or "youtube-refresh"
        path = self.root / f"{safe}.bin"
        encrypted = self._crypt(secret.encode("utf-8"), protect=True)
        tmp = path.with_suffix(".tmp")
        tmp.write_bytes(encrypted)
        try:
            os.chmod(tmp, 0o600)
        except OSError:
            pass
        tmp.replace(path)
        return f"dpapi-user://{path.name}"

    def get(self, ref: str) -> str:
        if not ref.startswith("dpapi-user://"):
            raise LedgerError("Unsupported DPAPI refresh-token reference")
        name = ref[len("dpapi-user://"):]
        if not name or Path(name).name != name:
            raise LedgerError("Invalid DPAPI refresh-token reference")
        path = self.root / name
        if not path.is_file():
            raise LedgerError("Refresh-token ciphertext is unavailable")
        return self._crypt(path.read_bytes(), protect=False).decode("utf-8")


class EnvironmentRefreshTokenStore:
    """Explicit process-environment secret store for Linux/Render runtimes.

    The refresh token is supplied by an owner-controlled secret environment variable.
    The ledger stores only an env:// reference; plaintext is never written to the
    ledger, repository, package, or application logs.

    put is deliberately compare-only: the process cannot mutate provider secret
    configuration. A governed grant can be committed only when the exchanged refresh
    token exactly matches the pre-provisioned secret.
    """

    _SAFE_ENV = re.compile(r"^[A-Z][A-Z0-9_]{2,127}$")

    def __init__(self, secret_env: str = "TREND_HUNTER_YOUTUBE_REFRESH_TOKEN"):
        env_name = str(secret_env or "").strip()
        if not self._SAFE_ENV.fullmatch(env_name):
            raise LedgerError("YouTube environment refresh-token variable name is invalid")
        self.secret_env = env_name
        self.reference = f"env://{env_name}"
        self._read_secret()

    def _read_secret(self) -> str:
        value = os.environ.get(self.secret_env)
        if not value:
            raise LedgerError("YouTube refresh-token secret environment variable is unavailable")
        return value

    def put(self, key: str, secret: str) -> str:
        configured = self._read_secret()
        if not secrets.compare_digest(str(secret), configured):
            raise LedgerError("Exchanged YouTube refresh token does not match the pre-provisioned environment secret")
        return self.reference

    def get(self, ref: str) -> str:
        if not secrets.compare_digest(str(ref or ""), self.reference):
            raise LedgerError("YouTube refresh-token reference does not match the configured environment secret")
        return self._read_secret()


class _AllowlistedRedirectHandler(urllib.request.HTTPRedirectHandler):
    def __init__(self, allowed_hosts: frozenset[str]):
        super().__init__(); self.allowed_hosts = allowed_hosts
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        _assert_https_host(newurl, self.allowed_hosts)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


class NoProxyHTTPTransport:
    """HTTPS transport that deliberately ignores HTTP(S)_PROXY environment variables."""
    def __init__(self, allowed_hosts: frozenset[str] = _ALLOWED_OAUTH_HOSTS):
        self.allowed_hosts = allowed_hosts
        self._opener = urllib.request.build_opener(
            urllib.request.ProxyHandler({}),
            _AllowlistedRedirectHandler(allowed_hosts),
        )

    def _open(self, req: urllib.request.Request, *, timeout: int = 30) -> tuple[int, dict[str, str], bytes]:
        _assert_https_host(req.full_url, self.allowed_hosts)
        try:
            with self._opener.open(req, timeout=timeout) as resp:
                return int(getattr(resp, "status", 200)), dict(resp.headers.items()), resp.read()
        except urllib.error.HTTPError as exc:
            body = exc.read() if hasattr(exc, "read") else b""
            raise LedgerError(f"Google/YouTube HTTP failure: {exc.code}: {body[:500].decode('utf-8','replace')}") from exc
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            raise LedgerError(f"Google/YouTube network failure: {exc}") from exc

    def post_form(self, url: str, values: dict[str, Any]) -> dict[str, Any]:
        data = urllib.parse.urlencode(values).encode("utf-8")
        req = urllib.request.Request(url, data=data, method="POST", headers={"Content-Type":"application/x-www-form-urlencoded","User-Agent":"TrendHunterEngine/C1"})
        _, _, body = self._open(req)
        try: return json.loads(body.decode("utf-8"))
        except Exception as exc: raise LedgerError("Google OAuth token response is not valid JSON") from exc

    def get_json(self, url: str, *, access_token: str) -> dict[str, Any]:
        req = urllib.request.Request(url, headers={"Authorization":f"Bearer {access_token}","Accept":"application/json","User-Agent":"TrendHunterEngine/C1"})
        _, _, body = self._open(req)
        try: return json.loads(body.decode("utf-8"))
        except Exception as exc: raise LedgerError("Google/YouTube response is not valid JSON") from exc

    def post_json_headers(self, url: str, payload: dict[str, Any], *, headers: dict[str,str]) -> tuple[dict[str,str], dict[str,Any] | None]:
        data = json.dumps(payload, separators=(",",":"), ensure_ascii=False).encode("utf-8")
        h = {"Content-Type":"application/json; charset=UTF-8","User-Agent":"TrendHunterEngine/C1", **headers}
        req = urllib.request.Request(url, data=data, method="POST", headers=h)
        _, response_headers, body = self._open(req)
        parsed = None
        if body:
            try: parsed = json.loads(body.decode("utf-8"))
            except Exception: parsed = None
        return response_headers, parsed

    def put_bytes(self, url: str, data: bytes, *, headers: dict[str,str]) -> dict[str, Any]:
        """Compatibility helper for small test payloads; real C1 video upload uses streaming chunks."""
        _assert_https_host(url, _ALLOWED_UPLOAD_SESSION_HOSTS)
        h = {"User-Agent":"TrendHunterEngine/C1", **headers}
        req = urllib.request.Request(url, data=data, method="PUT", headers=h)
        transport = NoProxyHTTPTransport(_ALLOWED_UPLOAD_SESSION_HOSTS)
        _, _, body = transport._open(req, timeout=300)
        try: return json.loads(body.decode("utf-8"))
        except Exception as exc: raise LedgerError("YouTube upload response is not valid JSON") from exc

    def put_file_resumable(
        self,
        url: str,
        file_path: str | Path,
        *,
        access_token: str,
        content_type: str,
        total_size: int,
        chunk_size: int = YOUTUBE_RESUMABLE_CHUNK_BYTES,
    ) -> dict[str, Any]:
        """Upload a file without loading it all into memory.

        Each intermediate chunk must be acknowledged by Google's resumable session with an exact
        308 Range boundary. Redirects are not followed and environment proxies are not consulted.
        """
        parsed = _assert_upload_session_url(url)
        if chunk_size < 256 * 1024 or chunk_size % (256 * 1024) != 0:
            raise LedgerError("YouTube resumable chunk_size must be a positive multiple of 256 KiB")
        path = Path(file_path)
        if not path.is_file() or total_size <= 0 or path.stat().st_size != total_size:
            raise LedgerError("YouTube resumable upload file size does not match the governed media descriptor")
        request_target = parsed.path or "/"
        if parsed.query:
            request_target += "?" + parsed.query
        offset = 0
        with path.open("rb") as fh:
            while offset < total_size:
                chunk = fh.read(min(chunk_size, total_size - offset))
                if not chunk:
                    raise LedgerError("Unexpected EOF during governed YouTube resumable upload")
                end = offset + len(chunk) - 1
                headers = {
                    "Authorization": f"Bearer {access_token}",
                    "Content-Type": content_type,
                    "Content-Length": str(len(chunk)),
                    "Content-Range": f"bytes {offset}-{end}/{total_size}",
                    "User-Agent": "TrendHunterEngine/C1",
                }
                conn = http.client.HTTPSConnection(parsed.hostname, parsed.port or 443, timeout=300)
                try:
                    conn.request("PUT", request_target, body=chunk, headers=headers)
                    resp = conn.getresponse()
                    body = resp.read()
                    status = int(resp.status)
                    if status == 308:
                        ack = str(resp.getheader("Range") or "")
                        m = re.fullmatch(r"bytes=0-(\d+)", ack)
                        if not m or int(m.group(1)) != end:
                            raise LedgerError("YouTube resumable upload returned an ambiguous chunk acknowledgement")
                        offset = end + 1
                        continue
                    if status not in {200, 201}:
                        raise LedgerError(f"YouTube resumable upload failed with HTTP {status}: {body[:500].decode('utf-8','replace')}")
                    if end + 1 != total_size:
                        raise LedgerError("YouTube resumable upload completed before all governed bytes were sent")
                    try:
                        return json.loads(body.decode("utf-8"))
                    except Exception as exc:
                        raise LedgerError("YouTube upload response is not valid JSON") from exc
                finally:
                    conn.close()
        raise LedgerError("YouTube resumable upload ended without a final provider response")


def _assert_https_host(url: str, allowed_hosts: frozenset[str]) -> urllib.parse.ParseResult:
    parsed = urllib.parse.urlparse(str(url))
    try:
        port = parsed.port
    except ValueError as exc:
        raise LedgerError("Outbound Google/YouTube URL has an invalid port") from exc
    if (
        parsed.scheme.lower() != "https"
        or parsed.hostname not in allowed_hosts
        or parsed.username
        or parsed.password
        or port not in {None, 443}
    ):
        raise LedgerError("Outbound Google/YouTube URL is outside the exact HTTPS allowlist")
    return parsed


def _assert_upload_session_url(url: str) -> urllib.parse.ParseResult:
    parsed = _assert_https_host(url, _ALLOWED_UPLOAD_SESSION_HOSTS)
    if not str(parsed.path or "").startswith("/upload/youtube/"):
        raise LedgerError("YouTube resumable session URL is outside the exact YouTube upload path boundary")
    return parsed


def _assert_loopback_redirect(redirect_uri: str) -> urllib.parse.ParseResult:
    p = urllib.parse.urlparse(str(redirect_uri))
    try:
        port = p.port
    except ValueError as exc:
        raise LedgerError("Desktop OAuth redirect URI contains an invalid port") from exc
    if (
        p.scheme.lower() != "http"
        or p.hostname not in {"127.0.0.1", "::1"}
        or not port
        or p.username
        or p.password
        or p.query
        or p.fragment
    ):
        raise LedgerError("Desktop OAuth redirect URI must be an explicit loopback http://127.0.0.1:<port> or http://[::1]:<port> without query/fragment")
    return p


def _b64url_sha256(value: str) -> str:
    return base64.urlsafe_b64encode(hashlib.sha256(value.encode("ascii")).digest()).rstrip(b"=").decode("ascii")


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _sha256_file(path: Path) -> tuple[str, int]:
    h = hashlib.sha256(); size = 0
    with path.open("rb") as fh:
        while True:
            block = fh.read(1024 * 1024)
            if not block: break
            h.update(block); size += len(block)
    return h.hexdigest(), size


def _parse_utc(value: str, *, field: str) -> datetime:
    try:
        dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except Exception as exc:
        raise LedgerError(f"Invalid governed timestamp: {field}") from exc
    if dt.tzinfo is None:
        raise LedgerError(f"Governed timestamp must be timezone-aware: {field}")
    return dt.astimezone(timezone.utc)


def _assert_exact_upload_scope(scopes: tuple[str, ...] | list[str]) -> tuple[str, ...]:
    normalized = tuple(sorted(set(str(x) for x in scopes if str(x))))
    if normalized != (YOUTUBE_UPLOAD_SCOPE,):
        raise LedgerError("OAuth grant must contain exactly the governed youtube.upload scope")
    return normalized


def _latest_state_for_identity(ledger: GovernanceLedger, identity_id: str) -> dict[str, Any]:
    with connect(ledger.db_path) as conn:
        row = conn.execute("SELECT id FROM artifact_state WHERE identity_id=? ORDER BY version DESC LIMIT 1", (identity_id,)).fetchone()
    if not row:
        raise LedgerError("Governed artifact identity has no state")
    return ledger.get_state(row["id"])


def _has_provenance(ledger: GovernanceLedger, from_state_id: str, to_state_id: str, edge_type: str) -> bool:
    with connect(ledger.db_path) as conn:
        row = conn.execute(
            "SELECT 1 FROM provenance_edge WHERE from_state_id=? AND to_state_id=? AND edge_type=? LIMIT 1",
            (from_state_id, to_state_id, edge_type),
        ).fetchone()
    return bool(row)


class YouTubeOAuthService:
    def __init__(self, ledger: GovernanceLedger, *, transport: NoProxyHTTPTransport | Any | None = None):
        self.ledger = ledger
        self.transport = transport or NoProxyHTTPTransport()
        self.bindings = OperationalBindingService(ledger)

    @staticmethod
    def prepare_authorization_request(
        client_id: str,
        redirect_uri: str,
        *,
        state: str | None = None,
        code_verifier: str | None = None,
    ) -> OAuthAuthorizationRequest:
        if not str(client_id or "").strip():
            raise LedgerError("Google OAuth client_id is required")
        _assert_loopback_redirect(redirect_uri)
        state = state or secrets.token_urlsafe(32)
        if not (32 <= len(state) <= 256) or not re.fullmatch(r"[A-Za-z0-9._~-]+", state):
            raise LedgerError("OAuth state must be a high-entropy URL-safe value of 32..256 characters")
        verifier = code_verifier or secrets.token_urlsafe(64)
        if not (43 <= len(verifier) <= 128):
            raise LedgerError("PKCE code_verifier must be 43..128 characters")
        if not re.fullmatch(r"[A-Za-z0-9._~-]+", verifier):
            raise LedgerError("PKCE code_verifier contains invalid characters")
        challenge = _b64url_sha256(verifier)
        params = {
            "client_id": client_id,
            "redirect_uri": redirect_uri,
            "response_type": "code",
            "scope": YOUTUBE_UPLOAD_SCOPE,
            "access_type": "offline",
            "prompt": "consent",
            "state": state,
            "code_challenge": challenge,
            "code_challenge_method": "S256",
        }
        url = GOOGLE_AUTH_ENDPOINT + "?" + urllib.parse.urlencode(params)
        _assert_https_host(url, frozenset({"accounts.google.com"}))
        return OAuthAuthorizationRequest(url, state, verifier, challenge, redirect_uri, (YOUTUBE_UPLOAD_SCOPE,))

    def record_authorization_attempt(
        self,
        channel_binding_state_id: str,
        request: OAuthAuthorizationRequest,
        *,
        client_id: str,
        ttl_seconds: int = OAUTH_ATTEMPT_TTL_SECONDS,
    ) -> ArtifactRef:
        channel = self.bindings.assert_current_channel_binding(channel_binding_state_id)
        if str(channel["payload"].get("platform") or "").lower() != "youtube":
            raise LedgerError("C1 YouTube OAuth requires an exact active YouTube channel binding")
        if not (30 <= int(ttl_seconds) <= 30 * 60):
            raise LedgerError("OAuth authorization attempt TTL must be between 30 and 1800 seconds")
        _assert_exact_upload_scope(request.scopes)
        started = datetime.now(timezone.utc)
        expires = started + timedelta(seconds=int(ttl_seconds))
        return self.ledger.record_domain(
            "YOUTUBE_OAUTH_AUTHORIZATION_ATTEMPT", "C1 YouTube OAuth Authority",
            {
                "channel_binding_state_id": channel_binding_state_id,
                "channel_ref": channel["payload"].get("channel_ref"),
                "client_id_sha256": _sha256_text(client_id),
                "redirect_uri": request.redirect_uri,
                "scopes": list(request.scopes),
                "state_sha256": _sha256_text(request.state),
                "code_challenge": request.code_challenge,
                "code_challenge_method": "S256",
                "status": "AWAITING_CALLBACK",
                "started_at": started.isoformat(),
                "expires_at": expires.isoformat(),
                "plaintext_state_persisted": False,
                "plaintext_code_verifier_persisted": False,
                "client_secret_treated_as_confidential_protection": False,
            },
            natural_key=f"youtube-oauth-attempt:{channel_binding_state_id}",
            subject_identity_id=self.ledger.subject_identity_for_state(channel_binding_state_id),
            record_state="AWAITING_CALLBACK",
            upstream_states=[(channel_binding_state_id,"OAUTH_EXACT_CHANNEL_BINDING")],
        )

    def _assert_awaiting_attempt(self, attempt_state_id: str) -> dict[str, Any]:
        attempt = self.ledger.get_state(attempt_state_id)
        if attempt["state_type"] != "YOUTUBE_OAUTH_AUTHORIZATION_ATTEMPT" or attempt["payload"].get("status") != "AWAITING_CALLBACK":
            raise LedgerError("OAuth callback does not target an awaiting YouTube OAuth attempt")
        latest = _latest_state_for_identity(self.ledger, attempt["identity_id"])
        if latest["id"] != attempt_state_id:
            raise LedgerError("OAuth authorization attempt is stale/superseded")
        expires_at = _parse_utc(str(attempt["payload"].get("expires_at") or ""), field="oauth_attempt.expires_at")
        if datetime.now(timezone.utc) >= expires_at:
            raise LedgerError("OAuth authorization attempt expired; start a new consent flow")
        self.bindings.assert_current_channel_binding(str(attempt["payload"].get("channel_binding_state_id") or ""))
        _assert_exact_upload_scope(tuple(attempt["payload"].get("scopes") or []))
        return attempt

    def exchange_code(
        self,
        attempt_state_id: str,
        *,
        returned_state: str,
        code: str,
        code_verifier: str,
        client_id: str,
        client_secret: str | None = None,
    ) -> OAuthTokenBundle:
        attempt = self._assert_awaiting_attempt(attempt_state_id)
        if not secrets.compare_digest(_sha256_text(returned_state), str(attempt["payload"].get("state_sha256") or "")):
            raise LedgerError("OAuth state mismatch; callback rejected")
        if not secrets.compare_digest(_b64url_sha256(code_verifier), str(attempt["payload"].get("code_challenge") or "")):
            raise LedgerError("PKCE verifier does not match the governed authorization attempt")
        if not secrets.compare_digest(_sha256_text(client_id), str(attempt["payload"].get("client_id_sha256") or "")):
            raise LedgerError("OAuth client_id does not match the governed authorization attempt")
        if not str(code or "").strip():
            raise LedgerError("OAuth authorization code is required")
        values: dict[str,Any] = {
            "client_id": client_id,
            "code": code,
            "code_verifier": code_verifier,
            "grant_type": "authorization_code",
            "redirect_uri": attempt["payload"]["redirect_uri"],
        }
        # Desktop/installed clients cannot rely on client_secret confidentiality. If Google issued one,
        # it may be supplied for protocol compatibility, but PKCE/state remain the security controls.
        if client_secret:
            values["client_secret"] = client_secret
        result = self.transport.post_form(GOOGLE_TOKEN_ENDPOINT, values)
        if result.get("error"):
            raise LedgerError(f"Google OAuth exchange rejected: {result.get('error')}")
        access_token = str(result.get("access_token") or "")
        refresh_token = result.get("refresh_token")
        token_type = str(result.get("token_type") or "")
        try:
            expires_in = int(result.get("expires_in") or 0)
        except Exception as exc:
            raise LedgerError("Google OAuth expires_in is invalid") from exc
        scopes = _assert_exact_upload_scope(tuple(str(result.get("scope") or "").split()))
        if not access_token or token_type.lower() != "bearer" or expires_in <= 0:
            raise LedgerError("Google OAuth exchange did not return a usable bearer access token")
        if not refresh_token:
            raise LedgerError("Initial C1 OAuth grant did not return a refresh token; re-consent with offline access is required")

        channel_binding_state_id = str(attempt["payload"].get("channel_binding_state_id") or "")
        receipt = self.ledger.record_domain(
            "YOUTUBE_OAUTH_TOKEN_EXCHANGE_RECEIPT", "C1 YouTube OAuth Authority",
            {
                "authorization_attempt_state_id": attempt_state_id,
                "channel_binding_state_id": channel_binding_state_id,
                "client_id_sha256": _sha256_text(client_id),
                "access_token_sha256": _sha256_text(access_token),
                "refresh_token_sha256": _sha256_text(str(refresh_token)),
                "token_type": token_type.lower(),
                "expires_in": expires_in,
                "granted_scopes": list(scopes),
                "access_token_plaintext_persisted": False,
                "refresh_token_plaintext_persisted": False,
                "status": "EXCHANGED",
                "exchanged_at": utcnow(),
            },
            natural_key=f"youtube-oauth-exchange:{attempt_state_id}",
            subject_identity_id=self.ledger.subject_identity_for_state(channel_binding_state_id),
            record_state="EXCHANGED",
            upstream_states=[
                (attempt_state_id,"OAUTH_EXCHANGE_FROM_EXACT_ATTEMPT"),
                (channel_binding_state_id,"OAUTH_EXCHANGE_EXACT_CHANNEL"),
            ],
        )
        consumed = self.ledger.record_domain(
            "YOUTUBE_OAUTH_AUTHORIZATION_ATTEMPT", "C1 YouTube OAuth Authority",
            {
                **{k:v for k,v in attempt["payload"].items() if k not in {"status"}},
                "status": "CONSUMED",
                "consumed_at": utcnow(),
                "token_exchange_receipt_state_id": receipt.state_id,
            },
            natural_key=str(attempt["natural_key"]),
            subject_identity_id=self.ledger.subject_identity_for_state(channel_binding_state_id),
            record_state="CONSUMED",
            upstream_states=[
                (attempt_state_id,"OAUTH_ATTEMPT_CONSUMED_FROM"),
                (receipt.state_id,"OAUTH_ATTEMPT_CONSUMED_BY_EXCHANGE"),
            ],
        )
        if consumed.identity_id != attempt["identity_id"]:
            raise LedgerError("OAuth attempt consumption did not preserve governed identity")
        return OAuthTokenBundle(access_token, str(refresh_token), token_type, expires_in, scopes, receipt.state_id)

    def verify_exact_channel(self, access_token: str, channel_binding_state_id: str) -> dict[str,Any]:
        channel = self.bindings.assert_current_channel_binding(channel_binding_state_id)
        if str(channel["payload"].get("platform") or "").lower() != "youtube":
            raise LedgerError("Exact binding is not YouTube")
        query = urllib.parse.urlencode({"part":"id,snippet","mine":"true","maxResults":50})
        result = self.transport.get_json(YOUTUBE_CHANNELS_ENDPOINT + "?" + query, access_token=access_token)
        ids = [str(x.get("id") or "") for x in (result.get("items") or []) if str(x.get("id") or "")]
        expected = str(channel["payload"].get("channel_ref") or "")
        if ids != [expected]:
            raise LedgerError("OAuth identity does not resolve unambiguously to the exact governed YouTube Channel ID")
        return {"channel_id":expected,"resolved_channel_ids":ids,"verified":True}

    def _assert_exchange_receipt(self, attempt_state_id: str, token: OAuthTokenBundle, channel_binding_state_id: str) -> dict[str, Any]:
        if not token.token_receipt_state_id:
            raise LedgerError("OAuth token bundle lacks governed token-exchange receipt")
        receipt = self.ledger.get_state(token.token_receipt_state_id)
        if receipt["state_type"] != "YOUTUBE_OAUTH_TOKEN_EXCHANGE_RECEIPT" or receipt["payload"].get("status") != "EXCHANGED":
            raise LedgerError("OAuth token bundle receipt is not a valid exchange receipt")
        rp = receipt["payload"]
        if rp.get("authorization_attempt_state_id") != attempt_state_id or rp.get("channel_binding_state_id") != channel_binding_state_id:
            raise LedgerError("OAuth token-exchange receipt does not match exact attempt/channel")
        if not _has_provenance(self.ledger, attempt_state_id, receipt["id"], "OAUTH_EXCHANGE_FROM_EXACT_ATTEMPT"):
            raise LedgerError("OAuth token-exchange receipt lacks exact attempt provenance")
        if not secrets.compare_digest(str(rp.get("access_token_sha256") or ""), _sha256_text(token.access_token)):
            raise LedgerError("OAuth access token does not match governed exchange receipt")
        if not token.refresh_token or not secrets.compare_digest(str(rp.get("refresh_token_sha256") or ""), _sha256_text(token.refresh_token)):
            raise LedgerError("OAuth refresh token does not match governed exchange receipt")
        if str(rp.get("token_type") or "") != token.token_type.lower() or int(rp.get("expires_in") or 0) != token.expires_in:
            raise LedgerError("OAuth token metadata does not match governed exchange receipt")
        _assert_exact_upload_scope(token.scopes)
        if tuple(rp.get("granted_scopes") or []) != tuple(token.scopes):
            raise LedgerError("OAuth token scopes do not match governed exchange receipt")
        attempt = self.ledger.get_state(attempt_state_id)
        latest_attempt = _latest_state_for_identity(self.ledger, attempt["identity_id"])
        if latest_attempt["payload"].get("status") != "CONSUMED" or latest_attempt["payload"].get("token_exchange_receipt_state_id") != receipt["id"]:
            raise LedgerError("OAuth authorization attempt is not consumed by this exact exchange receipt")
        return receipt

    def commit_verified_grant(
        self,
        attempt_state_id: str,
        token: OAuthTokenBundle,
        *,
        channel_binding_state_id: str,
        refresh_store: RefreshTokenStore,
        allow_ephemeral_secret_store: bool = False,
    ) -> ArtifactRef:
        attempt = self.ledger.get_state(attempt_state_id)
        if attempt["state_type"] != "YOUTUBE_OAUTH_AUTHORIZATION_ATTEMPT":
            raise LedgerError("Invalid OAuth attempt state")
        if attempt["payload"].get("channel_binding_state_id") != channel_binding_state_id:
            raise LedgerError("OAuth attempt/channel binding mismatch")
        receipt = self._assert_exchange_receipt(attempt_state_id, token, channel_binding_state_id)
        self.bindings.assert_current_channel_binding(channel_binding_state_id)
        self.verify_exact_channel(token.access_token, channel_binding_state_id)
        if not token.refresh_token:
            raise LedgerError("Verified OAuth grant lacks refresh token")
        if isinstance(refresh_store, InMemoryRefreshTokenStore) and not allow_ephemeral_secret_store:
            raise LedgerError("Ephemeral memory refresh-token storage is test-only and forbidden for a governed live grant")
        secret_ref = refresh_store.put(f"youtube-{channel_binding_state_id}", token.refresh_token)
        if str(secret_ref).startswith("memory://") and not allow_ephemeral_secret_store:
            raise LedgerError("Ephemeral memory refresh-token reference is forbidden for a governed live grant")
        if "://" not in str(secret_ref):
            raise LedgerError("Refresh-token store must return an explicit external secret reference")
        expires_at = (datetime.now(timezone.utc) + timedelta(seconds=token.expires_in)).isoformat()
        ref = self.ledger.record_domain(
            "YOUTUBE_OAUTH_GRANT_BINDING", "C1 YouTube OAuth Authority",
            {
                "authorization_attempt_state_id": attempt_state_id,
                "token_exchange_receipt_state_id": receipt["id"],
                "channel_binding_state_id": channel_binding_state_id,
                "channel_ref": self.ledger.get_state(channel_binding_state_id)["payload"].get("channel_ref"),
                "client_id_sha256": attempt["payload"].get("client_id_sha256"),
                "granted_scopes": list(_assert_exact_upload_scope(token.scopes)),
                "access_token_expires_at": expires_at,
                "refresh_token_secret_ref": secret_ref,
                "secret_reference_scheme": str(secret_ref).split("://",1)[0],
                "access_token_persisted": False,
                "refresh_token_plaintext_persisted": False,
                "exact_channel_verified": True,
                "status": "ACTIVE",
                "verified_at": utcnow(),
            },
            natural_key=f"youtube-oauth-grant:{channel_binding_state_id}",
            subject_identity_id=self.ledger.subject_identity_for_state(channel_binding_state_id),
            record_state="ACTIVE",
            upstream_states=[
                (attempt_state_id,"OAUTH_GRANT_FROM_ATTEMPT"),
                (receipt["id"],"OAUTH_GRANT_FROM_EXCHANGE_RECEIPT"),
                (channel_binding_state_id,"OAUTH_GRANT_EXACT_CHANNEL"),
            ],
        )
        return ref

    def _record_refresh_receipt(self, grant: dict[str, Any], token: OAuthTokenBundle) -> ArtifactRef:
        channel_binding_state_id = str(grant["payload"].get("channel_binding_state_id") or "")
        return self.ledger.record_domain(
            "YOUTUBE_OAUTH_REFRESH_RECEIPT", "C1 YouTube OAuth Authority",
            {
                "oauth_grant_state_id": grant["id"],
                "channel_binding_state_id": channel_binding_state_id,
                "access_token_sha256": _sha256_text(token.access_token),
                "token_type": token.token_type.lower(),
                "expires_in": token.expires_in,
                "granted_scopes": list(token.scopes),
                "access_token_plaintext_persisted": False,
                "status": "REFRESHED",
                "refreshed_at": utcnow(),
            },
            natural_key=f"youtube-oauth-refresh:{grant['id']}:{_sha256_text(token.access_token)}",
            subject_identity_id=self.ledger.subject_identity_for_state(channel_binding_state_id),
            record_state="REFRESHED",
            upstream_states=[
                (grant["id"],"OAUTH_REFRESH_FROM_EXACT_GRANT"),
                (channel_binding_state_id,"OAUTH_REFRESH_EXACT_CHANNEL"),
            ],
        )

    def refresh_access_token(
        self,
        grant_state_id: str,
        *,
        client_id: str,
        client_secret: str | None,
        refresh_store: RefreshTokenStore,
    ) -> OAuthTokenBundle:
        grant = self.ledger.get_state(grant_state_id)
        if grant["state_type"] != "YOUTUBE_OAUTH_GRANT_BINDING" or grant["payload"].get("status") != "ACTIVE":
            raise LedgerError("YouTube OAuth grant is not ACTIVE")
        latest = _latest_state_for_identity(self.ledger, grant["identity_id"])
        if latest["id"] != grant_state_id:
            raise LedgerError("YouTube OAuth grant is stale/superseded")
        if not secrets.compare_digest(_sha256_text(client_id), str(grant["payload"].get("client_id_sha256") or "")):
            raise LedgerError("OAuth refresh client_id does not match the governed grant")
        channel_binding_state_id = str(grant["payload"].get("channel_binding_state_id") or "")
        self.bindings.assert_current_channel_binding(channel_binding_state_id)
        _assert_exact_upload_scope(tuple(grant["payload"].get("granted_scopes") or []))
        refresh_token = refresh_store.get(str(grant["payload"].get("refresh_token_secret_ref") or ""))
        values: dict[str,Any] = {"client_id":client_id,"refresh_token":refresh_token,"grant_type":"refresh_token"}
        if client_secret:
            values["client_secret"] = client_secret
        result = self.transport.post_form(GOOGLE_TOKEN_ENDPOINT, values)
        if result.get("error"):
            raise LedgerError(f"Google OAuth refresh rejected: {result.get('error')}")
        access_token = str(result.get("access_token") or "")
        token_type = str(result.get("token_type") or "")
        try:
            expires_in = int(result.get("expires_in") or 0)
        except Exception as exc:
            raise LedgerError("Google OAuth refresh expires_in is invalid") from exc
        response_scope = tuple(str(result.get("scope") or "").split())
        scopes = _assert_exact_upload_scope(response_scope or tuple(grant["payload"].get("granted_scopes") or []))
        if not access_token or token_type.lower() != "bearer" or expires_in <= 0:
            raise LedgerError("Refreshed OAuth token is not usable for youtube.upload")
        self.verify_exact_channel(access_token, channel_binding_state_id)
        provisional = OAuthTokenBundle(access_token, None, token_type, expires_in, scopes, None)
        receipt = self._record_refresh_receipt(grant, provisional)
        return OAuthTokenBundle(access_token, None, token_type, expires_in, scopes, receipt.state_id)

    def assert_token_bound_to_grant(self, grant_state_id: str, token: OAuthTokenBundle) -> dict[str, Any]:
        grant = self.ledger.get_state(grant_state_id)
        if grant["state_type"] != "YOUTUBE_OAUTH_GRANT_BINDING" or grant["payload"].get("status") != "ACTIVE":
            raise LedgerError("Active verified YouTube OAuth grant required")
        if _latest_state_for_identity(self.ledger, grant["identity_id"])["id"] != grant_state_id:
            raise LedgerError("YouTube OAuth grant is stale/superseded")
        receipt_id = str(token.token_receipt_state_id or "")
        if not receipt_id:
            raise LedgerError("Access token lacks governed OAuth receipt")
        receipt = self.ledger.get_state(receipt_id)
        with connect(self.ledger.db_path) as conn:
            latest_refresh = conn.execute(
                """SELECT s.id FROM domain_record d
                   JOIN artifact_state s ON s.id=d.artifact_state_id
                   WHERE d.stage='YOUTUBE_OAUTH_REFRESH_RECEIPT'
                     AND json_extract(s.payload_json,'$.oauth_grant_state_id')=?
                   ORDER BY s.recorded_at DESC, s.version DESC LIMIT 1""",
                (grant_state_id,),
            ).fetchone()
        if receipt["state_type"] == "YOUTUBE_OAUTH_TOKEN_EXCHANGE_RECEIPT":
            if grant["payload"].get("token_exchange_receipt_state_id") != receipt_id:
                raise LedgerError("Initial access token receipt is not the one bound to this OAuth grant")
            if latest_refresh:
                raise LedgerError("Initial OAuth access token was superseded by a governed refresh receipt")
        elif receipt["state_type"] == "YOUTUBE_OAUTH_REFRESH_RECEIPT":
            if receipt["payload"].get("oauth_grant_state_id") != grant_state_id:
                raise LedgerError("Refreshed access token receipt is not bound to this OAuth grant")
            if not _has_provenance(self.ledger, grant_state_id, receipt_id, "OAUTH_REFRESH_FROM_EXACT_GRANT"):
                raise LedgerError("Refreshed access token receipt lacks exact grant provenance")
            if not latest_refresh or latest_refresh["id"] != receipt_id:
                raise LedgerError("Refreshed access token receipt is stale/superseded by a newer refresh")
        else:
            raise LedgerError("Access token receipt is not an accepted C1 OAuth receipt type")
        if not secrets.compare_digest(str(receipt["payload"].get("access_token_sha256") or ""), _sha256_text(token.access_token)):
            raise LedgerError("Access token does not match its governed OAuth receipt")
        _assert_exact_upload_scope(token.scopes)
        if tuple(receipt["payload"].get("granted_scopes") or []) != tuple(token.scopes):
            raise LedgerError("Access token scopes do not match governed OAuth receipt")
        issued_field = "exchanged_at" if receipt["state_type"] == "YOUTUBE_OAUTH_TOKEN_EXCHANGE_RECEIPT" else "refreshed_at"
        issued_at = _parse_utc(str(receipt["payload"].get(issued_field) or ""), field=f"oauth_receipt.{issued_field}")
        receipt_expires = issued_at + timedelta(seconds=int(receipt["payload"].get("expires_in") or 0))
        if datetime.now(timezone.utc) >= receipt_expires:
            raise LedgerError("Access token receipt is expired; refresh before publication")
        return grant


class YouTubePublicationService:
    def __init__(self, ledger: GovernanceLedger, *, transport: NoProxyHTTPTransport | Any | None = None):
        self.ledger = ledger
        self.transport = transport or NoProxyHTTPTransport()
        self.bindings = OperationalBindingService(ledger)

    def create_media_descriptor(self, creative_state_id: str, media_path: str | Path, *, title: str, description: str = "") -> ArtifactRef:
        creative = self.ledger.get_state(creative_state_id)
        if creative["state_type"] != "CREATIVE_ARTIFACT":
            raise LedgerError("Media descriptor requires CREATIVE_ARTIFACT")
        path = Path(media_path)
        if not path.is_file():
            raise LedgerError("Publication media file does not exist")
        digest, size = _sha256_file(path)
        if size <= 0:
            raise LedgerError("C1 YouTube publication media must not be empty")
        mime = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        if not mime.startswith("video/"):
            raise LedgerError("C1 YouTube publication media must be a video file")
        title = str(title or "").strip()
        description = str(description or "")
        if not title or "\x00" in title or "\x00" in description:
            raise LedgerError("C1 YouTube publication metadata requires a non-empty safe title")
        publication_metadata = {"title": title, "description": description, "privacyStatus": "private"}
        metadata_sha256 = hashlib.sha256(
            json.dumps(publication_metadata, sort_keys=True, separators=(",",":"), ensure_ascii=False).encode("utf-8")
        ).hexdigest()
        return self.ledger.record_domain(
            "PUBLICATION_MEDIA_DESCRIPTOR", "C1 Publication Media Authority",
            {
                "creative_state_id": creative_state_id,
                "sha256": digest,
                "size_bytes": size,
                "media_type": mime,
                "basename": path.name,
                "youtube_title": title,
                "youtube_description": description,
                "intended_privacy_status": "private",
                "publication_metadata_sha256": metadata_sha256,
                "local_path_persisted": False,
                "descriptor_created_at": utcnow(),
            },
            natural_key=f"publication-media:{creative_state_id}:{digest}:{metadata_sha256}",
            subject_identity_id=self.ledger.subject_identity_for_state(creative_state_id),
            record_state="FINGERPRINTED",
            upstream_states=[(creative_state_id,"MEDIA_DESCRIPTOR_CREATIVE")],
        )

    def assert_media_matches(self, media_descriptor_state_id: str, media_path: str | Path, *, creative_state_id: str | None = None) -> dict[str,Any]:
        desc = self.ledger.get_state(media_descriptor_state_id)
        if desc["state_type"] != "PUBLICATION_MEDIA_DESCRIPTOR":
            raise LedgerError("Expected PUBLICATION_MEDIA_DESCRIPTOR")
        if creative_state_id and desc["payload"].get("creative_state_id") != creative_state_id:
            raise LedgerError("Media descriptor is not bound to exact creative")
        path = Path(media_path)
        if not path.is_file():
            raise LedgerError("Publication media file does not exist")
        digest, size = _sha256_file(path)
        if digest != desc["payload"].get("sha256") or size != int(desc["payload"].get("size_bytes") or -1):
            raise LedgerError("Publication media bytes changed after fingerprint/authorization")
        return desc

    def _record_safety_incident(
        self,
        *,
        creative_state_id: str,
        channel_binding_state_id: str,
        media_descriptor_state_id: str,
        issue: str,
        video_id: str | None,
        observed_privacy_status: str | None,
        observed_channel_id: str | None,
        detail: str,
        oauth_receipt_state_id: str | None = None,
        publication_attempt_state_id: str | None = None,
    ) -> ArtifactRef:
        upstream = [
            (creative_state_id,"YOUTUBE_INCIDENT_CREATIVE"),
            (channel_binding_state_id,"YOUTUBE_INCIDENT_EXACT_CHANNEL"),
            (media_descriptor_state_id,"YOUTUBE_INCIDENT_EXACT_MEDIA"),
        ]
        if oauth_receipt_state_id:
            upstream.append((oauth_receipt_state_id,"YOUTUBE_INCIDENT_OAUTH_RECEIPT"))
        if publication_attempt_state_id:
            upstream.append((publication_attempt_state_id,"YOUTUBE_INCIDENT_PUBLICATION_ATTEMPT"))
        return self.ledger.record_domain(
            "YOUTUBE_PUBLICATION_SAFETY_INCIDENT", "C1 YouTube Publication Safety Authority",
            {
                "creative_state_id": creative_state_id,
                "channel_binding_state_id": channel_binding_state_id,
                "media_descriptor_state_id": media_descriptor_state_id,
                "oauth_receipt_state_id": oauth_receipt_state_id,
                "publication_attempt_state_id": publication_attempt_state_id,
                "issue": issue,
                "video_id": video_id,
                "observed_privacy_status": observed_privacy_status,
                "observed_channel_id": observed_channel_id,
                "required_action": "EMERGENCY_HUMAN_ACTION_REQUIRED",
                "automatic_privacy_remediation_performed": False,
                "broader_oauth_scope_auto_requested": False,
                "detail": detail,
                "recorded_at": utcnow(),
            },
            natural_key=f"youtube-publication-incident:{video_id or self.ledger.get_state(media_descriptor_state_id)['payload'].get('sha256')}:{issue}:{publication_attempt_state_id or 'none'}",
            subject_identity_id=self.ledger.subject_identity_for_state(creative_state_id),
            record_state="EMERGENCY_HUMAN_ACTION_REQUIRED",
            upstream_states=upstream,
        )

    def prepare_publication_attempt(
        self,
        *,
        operations,
        creative_state_id: str,
        authorization_state_id: str,
        oauth_grant_state_id: str,
        oauth_token: OAuthTokenBundle,
        media_path: str | Path,
        monetization_activation_state_id: str | None = None,
        auth_context: dict[str, Any] | None = None,
    ) -> ArtifactRef:
        auth = self.ledger.get_state(authorization_state_id)
        if auth["state_type"] != "HUMAN_AUTHORIZATION" or auth["payload"].get("decision") != "AUTHORIZED":
            raise LedgerError("Exact human publication authorization is required")
        if auth["payload"].get("creative_state_id") != creative_state_id:
            raise LedgerError("Human authorization does not target the exact creative state")
        media_descriptor_state_id = str(auth["payload"].get("media_descriptor_state_id") or "")
        channel_binding_state_id = str(auth["payload"].get("channel_binding_state_id") or "")
        if not media_descriptor_state_id or not channel_binding_state_id:
            raise LedgerError("C1 YouTube execution requires human authorization bound to exact media and channel")
        desc = self.assert_media_matches(media_descriptor_state_id, media_path, creative_state_id=creative_state_id)
        if auth["payload"].get("media_sha256") != desc["payload"].get("sha256"):
            raise LedgerError("Human authorization media hash does not match the exact publication descriptor")
        if auth["payload"].get("publication_metadata_sha256") != desc["payload"].get("publication_metadata_sha256"):
            raise LedgerError("Human authorization publication metadata does not match the exact publication descriptor")
        if auth["payload"].get("intended_privacy_status") != "private" or desc["payload"].get("intended_privacy_status") != "private":
            raise LedgerError("C1 YouTube authorization must bind a private-first publication descriptor")

        operations.validate_publication_execution_gate(
            creative_state_id, authorization_state_id,
            channel_binding_state_id=channel_binding_state_id,
            monetization_activation_state_id=monetization_activation_state_id,
            require_bound_channel=True,
            auth_context=auth_context,
        )
        oauth = YouTubeOAuthService(self.ledger, transport=self.transport)
        grant = oauth.assert_token_bound_to_grant(oauth_grant_state_id, oauth_token)
        if grant["payload"].get("channel_binding_state_id") != channel_binding_state_id:
            raise LedgerError("OAuth grant is not bound to the exact human-authorized channel")
        self.bindings.assert_current_channel_binding(channel_binding_state_id)
        oauth.verify_exact_channel(oauth_token.access_token, channel_binding_state_id)

        # One-use authorization reservation is committed before an attempt can
        # reach upload_private. A crash leaves a manual-reconciliation HOLD.
        self.ledger.claim_youtube_private_authorization_once(authorization_state_id)

        attempt = self.ledger.record_domain(
            "YOUTUBE_PUBLICATION_ATTEMPT", "C1 YouTube Publication Authority",
            {
                "creative_state_id": creative_state_id,
                "authorization_state_id": authorization_state_id,
                "oauth_grant_state_id": oauth_grant_state_id,
                "oauth_token_receipt_state_id": oauth_token.token_receipt_state_id,
                "channel_binding_state_id": channel_binding_state_id,
                "media_descriptor_state_id": media_descriptor_state_id,
                "media_sha256": desc["payload"].get("sha256"),
                "publication_metadata_sha256": desc["payload"].get("publication_metadata_sha256"),
                "intended_privacy_status": "private",
                "monetization_activation_state_id": monetization_activation_state_id,
                "status": "READY_PRIVATE_UPLOAD",
                "prepared_at": utcnow(),
                "automatic_retry_permitted_after_in_flight": False,
            },
            natural_key=f"youtube-publication-attempt:{authorization_state_id}:{media_descriptor_state_id}:{oauth_token.token_receipt_state_id}",
            subject_identity_id=self.ledger.subject_identity_for_state(creative_state_id),
            record_state="READY_PRIVATE_UPLOAD",
            upstream_states=[
                (creative_state_id,"YOUTUBE_ATTEMPT_CREATIVE"),
                (authorization_state_id,"YOUTUBE_ATTEMPT_HUMAN_AUTHORIZATION"),
                (oauth_grant_state_id,"YOUTUBE_ATTEMPT_OAUTH_GRANT"),
                (str(oauth_token.token_receipt_state_id),"YOUTUBE_ATTEMPT_OAUTH_TOKEN_RECEIPT"),
                (channel_binding_state_id,"YOUTUBE_ATTEMPT_EXACT_CHANNEL"),
                (media_descriptor_state_id,"YOUTUBE_ATTEMPT_EXACT_MEDIA"),
            ],
        )
        return attempt

    def _transition_attempt(self, from_state: dict[str, Any], status: str, **updates: Any) -> ArtifactRef:
        payload = {**from_state["payload"], **updates, "status": status, "transitioned_at": utcnow()}
        return self.ledger.record_domain(
            "YOUTUBE_PUBLICATION_ATTEMPT", "C1 YouTube Publication Authority",
            payload,
            natural_key=str(from_state["natural_key"]),
            subject_identity_id=self.ledger.subject_identity_for_state(from_state["id"]),
            record_state=status,
            upstream_states=[(from_state["id"],f"YOUTUBE_ATTEMPT_TRANSITION:{status}")],
        )

    def upload_private(
        self,
        *,
        publication_attempt_state_id: str,
        oauth_token: OAuthTokenBundle,
        media_path: str | Path,
    ) -> dict[str,Any]:
        ready = self.ledger.get_state(publication_attempt_state_id)
        if ready["state_type"] != "YOUTUBE_PUBLICATION_ATTEMPT" or ready["payload"].get("status") != "READY_PRIVATE_UPLOAD":
            raise LedgerError("YouTube provider side effect requires a READY_PRIVATE_UPLOAD governed attempt")
        if _latest_state_for_identity(self.ledger, ready["identity_id"])["id"] != publication_attempt_state_id:
            raise LedgerError("YouTube publication attempt is stale/superseded; automatic retry is forbidden")
        rp = ready["payload"]
        creative_state_id = str(rp.get("creative_state_id") or "")
        channel_binding_state_id = str(rp.get("channel_binding_state_id") or "")
        media_descriptor_state_id = str(rp.get("media_descriptor_state_id") or "")
        oauth_grant_state_id = str(rp.get("oauth_grant_state_id") or "")
        if str(rp.get("oauth_token_receipt_state_id") or "") != str(oauth_token.token_receipt_state_id or ""):
            raise LedgerError("Publication attempt OAuth token receipt mismatch")
        desc = self.assert_media_matches(media_descriptor_state_id, media_path, creative_state_id=creative_state_id)
        if rp.get("media_sha256") != desc["payload"].get("sha256") or rp.get("publication_metadata_sha256") != desc["payload"].get("publication_metadata_sha256"):
            raise LedgerError("Publication attempt no longer matches exact media/metadata descriptor")
        channel = self.bindings.assert_current_channel_binding(channel_binding_state_id)
        oauth = YouTubeOAuthService(self.ledger, transport=self.transport)
        grant = oauth.assert_token_bound_to_grant(oauth_grant_state_id, oauth_token)
        if grant["payload"].get("channel_binding_state_id") != channel_binding_state_id:
            raise LedgerError("Publication attempt OAuth grant/channel mismatch")
        oauth.verify_exact_channel(oauth_token.access_token, channel_binding_state_id)

        # Atomic one-shot guard also protects two workers racing on the SAME
        # READY attempt. Persist before the first provider upload side effect.
        self.ledger.claim_youtube_private_provider_once(publication_attempt_state_id)
        in_flight = self._transition_attempt(ready, "IN_FLIGHT", in_flight_at=utcnow())
        init_url = YOUTUBE_RESUMABLE_INIT_ENDPOINT + "?" + urllib.parse.urlencode({"uploadType":"resumable","part":"snippet,status"})
        payload = {
            "snippet":{
                "title":str(desc["payload"].get("youtube_title") or ""),
                "description":str(desc["payload"].get("youtube_description") or ""),
            },
            "status":{"privacyStatus":"private"},
        }
        try:
            headers, _ = self.transport.post_json_headers(init_url, payload, headers={
                "Authorization":f"Bearer {oauth_token.access_token}",
                "X-Upload-Content-Length":str(desc["payload"]["size_bytes"]),
                "X-Upload-Content-Type":str(desc["payload"]["media_type"]),
            })
            location = headers.get("Location") or headers.get("location")
            if not location:
                raise LedgerError("YouTube resumable upload initiation did not return Location")
            _assert_upload_session_url(location)
            response = self.transport.put_file_resumable(
                location,
                media_path,
                access_token=oauth_token.access_token,
                content_type=str(desc["payload"]["media_type"]),
                total_size=int(desc["payload"]["size_bytes"]),
            )
        except Exception as exc:
            self._transition_attempt(
                self.ledger.get_state(in_flight.state_id),
                "AMBIGUOUS_PROVIDER_STATE",
                ambiguous_since=utcnow(),
                failure_class=type(exc).__name__,
                reconciliation_required=True,
            )
            raise

        video_id = str(response.get("id") or "")
        privacy = str((response.get("status") or {}).get("privacyStatus") or "")
        response_channel = str((response.get("snippet") or {}).get("channelId") or "")
        expected_channel = str(channel["payload"].get("channel_ref") or "")
        if video_id and (privacy != "private" or response_channel != expected_channel):
            hold = self._transition_attempt(
                self.ledger.get_state(in_flight.state_id),
                "SAFETY_HOLD",
                video_id=video_id,
                observed_privacy_status=privacy or None,
                observed_channel_id=response_channel or None,
                reconciliation_required=True,
            )
            self._record_safety_incident(
                creative_state_id=creative_state_id,
                channel_binding_state_id=channel_binding_state_id,
                media_descriptor_state_id=media_descriptor_state_id,
                issue="PROVIDER_RESULT_NOT_EXACT_PRIVATE_TARGET",
                video_id=video_id,
                observed_privacy_status=privacy or None,
                observed_channel_id=response_channel or None,
                detail="YouTube returned a created video that is not verified private on the exact governed channel. Automatic broader-scope remediation is intentionally disabled.",
                oauth_receipt_state_id=oauth_token.token_receipt_state_id,
                publication_attempt_state_id=hold.state_id,
            )
            raise LedgerError("EMERGENCY_HUMAN_ACTION_REQUIRED: YouTube returned a video outside the exact private/channel safety contract")
        if not video_id or privacy != "private" or response_channel != expected_channel:
            self._transition_attempt(
                self.ledger.get_state(in_flight.state_id),
                "AMBIGUOUS_PROVIDER_STATE",
                reconciliation_required=True,
                failure_class="UNVERIFIED_PROVIDER_RESPONSE",
            )
            raise LedgerError("YouTube upload result is not a verified private video on the exact governed channel")
        confirmed = self._transition_attempt(
            self.ledger.get_state(in_flight.state_id),
            "PROVIDER_CONFIRMED_PRIVATE",
            video_id=video_id,
            observed_privacy_status=privacy,
            observed_channel_id=response_channel,
            provider_confirmed_at=utcnow(),
            reconciliation_required=False,
        )
        return {
            "video_id":video_id,
            "privacy_status":privacy,
            "channel_id":response_channel,
            "media_sha256":desc["payload"]["sha256"],
            "publication_attempt_state_id":confirmed.state_id,
        }

    def execute_authorized_private_upload(
        self,
        *,
        operations,
        creative_state_id: str,
        authorization_state_id: str,
        oauth_grant_state_id: str,
        oauth_token: OAuthTokenBundle,
        media_path: str | Path,
        monetization_activation_state_id: str | None = None,
        auth_context: dict[str, Any] | None = None,
    ) -> dict[str, ArtifactRef | dict[str,Any]]:
        attempt = self.prepare_publication_attempt(
            operations=operations,
            creative_state_id=creative_state_id,
            authorization_state_id=authorization_state_id,
            oauth_grant_state_id=oauth_grant_state_id,
            oauth_token=oauth_token,
            media_path=media_path,
            monetization_activation_state_id=monetization_activation_state_id,
            auth_context=auth_context,
        )
        provider = self.upload_private(
            publication_attempt_state_id=attempt.state_id,
            oauth_token=oauth_token,
            media_path=media_path,
        )
        auth = self.ledger.get_state(authorization_state_id)
        media_descriptor_state_id = str(auth["payload"].get("media_descriptor_state_id") or "")
        channel_binding_state_id = str(auth["payload"].get("channel_binding_state_id") or "")
        desc = self.ledger.get_state(media_descriptor_state_id)
        proof = self.ledger.record_domain(
            "YOUTUBE_PUBLICATION_PROOF", "C1 YouTube Publication Evidence Authority",
            {
                "creative_state_id": creative_state_id,
                "authorization_state_id": authorization_state_id,
                "oauth_grant_state_id": oauth_grant_state_id,
                "oauth_token_receipt_state_id": oauth_token.token_receipt_state_id,
                "publication_attempt_state_id": provider["publication_attempt_state_id"],
                "channel_binding_state_id": channel_binding_state_id,
                "channel_id": provider["channel_id"],
                "video_id": provider["video_id"],
                "privacy_status": provider["privacy_status"],
                "media_descriptor_state_id": media_descriptor_state_id,
                "media_sha256": desc["payload"]["sha256"],
                "publication_metadata_sha256": desc["payload"].get("publication_metadata_sha256"),
                "provider": "youtube",
                "verification_status": "PROVIDER_RESPONSE_BOUND",
                "recorded_at": utcnow(),
            },
            natural_key=f"youtube-publication-proof:{provider['video_id']}",
            subject_identity_id=self.ledger.subject_identity_for_state(creative_state_id),
            record_state="VERIFIED_PRIVATE",
            upstream_states=[
                (creative_state_id,"YOUTUBE_PROOF_CREATIVE"),
                (authorization_state_id,"YOUTUBE_PROOF_HUMAN_AUTHORIZATION"),
                (oauth_grant_state_id,"YOUTUBE_PROOF_OAUTH_GRANT"),
                (str(oauth_token.token_receipt_state_id),"YOUTUBE_PROOF_OAUTH_TOKEN_RECEIPT"),
                (provider["publication_attempt_state_id"],"YOUTUBE_PROOF_PUBLICATION_ATTEMPT"),
                (channel_binding_state_id,"YOUTUBE_PROOF_EXACT_CHANNEL"),
                (media_descriptor_state_id,"YOUTUBE_PROOF_EXACT_MEDIA"),
            ],
        )
        try:
            execution = operations.record_publication_execution(
                creative_state_id, authorization_state_id,
                channel_binding_state_id=channel_binding_state_id,
                external_result_ref=f"youtube:{provider['video_id']}",
                monetization_activation_state_id=monetization_activation_state_id,
                require_bound_channel=True,
                auth_context=auth_context,
            )
        except Exception as exc:
            self._record_safety_incident(
                creative_state_id=creative_state_id,
                channel_binding_state_id=channel_binding_state_id,
                media_descriptor_state_id=media_descriptor_state_id,
                issue="POST_UPLOAD_EXECUTION_GATE_REJECTED",
                video_id=provider["video_id"],
                observed_privacy_status=provider["privacy_status"],
                observed_channel_id=provider["channel_id"],
                detail=f"Private upload exists but final governed execution gate rejected: {type(exc).__name__}",
                oauth_receipt_state_id=oauth_token.token_receipt_state_id,
                publication_attempt_state_id=provider["publication_attempt_state_id"],
            )
            raise
        self.ledger.add_provenance(proof.state_id, execution.state_id, "EXECUTION_PROVIDER_PROOF")
        return {"provider_result": provider, "proof": proof, "execution": execution}


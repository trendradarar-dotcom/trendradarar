from __future__ import annotations

import ipaddress
import json
import os
import time
from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from .backup import create_backup, restore_backup
from .db import connect
from .ledger import GovernanceLedger, LedgerError
from .security import AuthenticatedActor, SecretResolver
from .util import utcnow


TRANSPORT_MODES = {
    "LOOPBACK_ONLY",
    "DIRECT_TLS",
    "TRUSTED_TLS_TERMINATING_REVERSE_PROXY",
}

EXTERNAL_CONNECTOR_FAILURES = {
    "CREDENTIAL_MISSING",
    "DNS_UNAVAILABLE",
    "NETWORK_UNAVAILABLE",
    "RATE_LIMITED",
    "UPSTREAM_5XX",
    "UPSTREAM_AUTH_FAILURE",
    "UPSTREAM_CONTRACT_CHANGED",
}
INTERNAL_CONNECTOR_FAILURES = {
    "RESPONSE_PARSE_FAILURE",
    "INTERNAL_CONNECTOR_DEFECT",
}


@dataclass(frozen=True)
class GovernedActorAuthorization:
    actor: AuthenticatedActor
    operator_binding_state_id: str
    operator_binding_identity_id: str
    binding_version: int
    authorized_role: str
    authorized_scope: str
    binding_roles: tuple[str, ...]
    binding_scopes: tuple[str, ...]

    def audit_context(self) -> dict[str, Any]:
        ctx = self.actor.audit_context()
        ctx.update({
            "governed_operator_binding_state_id": self.operator_binding_state_id,
            "governed_operator_binding_identity_id": self.operator_binding_identity_id,
            "governed_operator_binding_version": self.binding_version,
            "authorized_role": self.authorized_role,
            "authorized_scope": self.authorized_scope,
            "binding_roles": list(self.binding_roles),
            "binding_scopes": list(self.binding_scopes),
            "authorization_basis": "CRYPTOGRAPHIC_TOKEN_PLUS_CURRENT_GOVERNED_OPERATOR_BINDING",
        })
        return ctx


class GovernedAuthorizationResolver:
    """Resolve a cryptographically authenticated actor against the exact current governed binding.

    A signed token is only an identity assertion. Authorization additionally requires the latest
    applicable OPERATOR_IDENTITY_BINDING state for the exact subject, an admitted role, and an
    admitted operational scope. Binding supersession/revocation invalidates older tokens through
    token_not_before_epoch.
    """

    def __init__(self, ledger: GovernanceLedger):
        self.ledger = ledger

    def _latest_binding(self, subject: str) -> dict[str, Any] | None:
        with connect(self.ledger.db_path) as conn:
            row = conn.execute(
                """SELECT s.id AS state_id,s.identity_id,s.version,s.effective_from,s.effective_to,
                          s.payload_json,d.record_state
                   FROM artifact_identity i
                   JOIN artifact_state s ON s.identity_id=i.id
                   JOIN domain_record d ON d.artifact_state_id=s.id
                   WHERE i.kind='OPERATOR_IDENTITY_BINDING'
                     AND i.natural_key=?
                     AND d.stage='OPERATOR_IDENTITY_BINDING'
                   ORDER BY s.version DESC LIMIT 1""",
                (f"operator:{subject}",),
            ).fetchone()
        if not row:
            return None
        out = dict(row)
        out["payload"] = json.loads(out.pop("payload_json"))
        return out

    @staticmethod
    def _iso_is_current(effective_from: str | None, effective_to: str | None) -> bool:
        now = datetime.now(timezone.utc)
        try:
            if effective_from and datetime.fromisoformat(effective_from).astimezone(timezone.utc) > now:
                return False
            if effective_to and datetime.fromisoformat(effective_to).astimezone(timezone.utc) <= now:
                return False
        except Exception:
            return False
        return True

    def require(self, actor: AuthenticatedActor, required_role: str, required_scope: str) -> GovernedActorAuthorization:
        if actor is None:
            raise LedgerError("Authenticated actor required")
        # Token assertion itself must contain the requested role (or admin).
        if not actor.has_role(required_role):
            raise LedgerError(f"Token does not assert required role: {required_role}")
        binding = self._latest_binding(actor.subject)
        if not binding:
            raise LedgerError("Authenticated subject has no governed operator identity binding")
        payload = binding["payload"]
        if binding["record_state"] != "ACTIVE" or payload.get("status") != "ACTIVE":
            raise LedgerError("Governed operator identity binding is not ACTIVE")
        if not self._iso_is_current(binding.get("effective_from"), binding.get("effective_to")):
            raise LedgerError("Governed operator identity binding is not currently applicable")
        token_not_before = int(payload.get("token_not_before_epoch") or 0)
        if actor.issued_at < token_not_before:
            raise LedgerError("Bearer token predates current operator-binding supersession/revocation boundary")
        roles = tuple(sorted(set(str(x) for x in payload.get("roles") or [])))
        scopes = tuple(sorted(set(str(x) for x in payload.get("scopes") or [])))
        role_allowed = required_role in roles or "admin" in roles
        if not role_allowed:
            raise LedgerError(f"Current governed operator binding does not authorize role: {required_role}")
        scope_allowed = "*" in scopes or required_scope in scopes
        if not scope_allowed:
            raise LedgerError(f"Current governed operator binding does not authorize scope: {required_scope}")
        return GovernedActorAuthorization(
            actor=actor,
            operator_binding_state_id=binding["state_id"],
            operator_binding_identity_id=binding["identity_id"],
            binding_version=int(binding["version"]),
            authorized_role=required_role,
            authorized_scope=required_scope,
            binding_roles=roles,
            binding_scopes=scopes,
        )


class OperationalBindingService:
    def __init__(self, ledger: GovernanceLedger):
        self.ledger = ledger

    def register_operator(
        self,
        subject: str,
        *,
        display_name: str | None = None,
        roles: list[str] | None = None,
        scopes: list[str] | None = None,
        effective_to: str | None = None,
    ):
        if not subject.strip():
            raise LedgerError("operator subject is required")
        now = utcnow()
        payload = {
            "subject": subject,
            "display_name": display_name,
            "roles": sorted(set(roles or [])),
            "scopes": sorted(set(scopes or ["*"])),
            "status": "ACTIVE",
            "bound_at": now,
            # Every replacement binding invalidates tokens minted before this exact governed state.
            "token_not_before_epoch": int(time.time()),
        }
        return self.ledger.record_domain(
            "OPERATOR_IDENTITY_BINDING",
            "Operationalization Identity Binding",
            payload,
            natural_key=f"operator:{subject}",
            record_state="ACTIVE",
            effective_from=now,
        )

    def revoke_operator(self, subject: str, *, reason: str = ""):
        if not subject.strip():
            raise LedgerError("operator subject is required")
        now = utcnow()
        return self.ledger.record_domain(
            "OPERATOR_IDENTITY_BINDING",
            "Operationalization Identity Binding",
            {
                "subject": subject,
                "roles": [],
                "scopes": [],
                "status": "REVOKED",
                "reason": reason,
                "bound_at": now,
                "token_not_before_epoch": int(time.time()),
            },
            natural_key=f"operator:{subject}",
            record_state="REVOKED",
            effective_from=now,
        )

    def configure_transport_security(self, mode: str, *, endpoint: str | None = None, metadata: dict[str, Any] | None = None):
        mode = mode.strip().upper()
        if mode not in TRANSPORT_MODES:
            raise LedgerError(f"Unsupported transport security mode: {mode}")
        metadata = dict(metadata or {})
        if mode in {"DIRECT_TLS", "TRUSTED_TLS_TERMINATING_REVERSE_PROXY"}:
            parsed = urlparse(str(endpoint or ""))
            if parsed.scheme.lower() != "https" or not parsed.hostname:
                raise LedgerError(f"{mode} requires an explicit https:// governed endpoint")
        if mode == "TRUSTED_TLS_TERMINATING_REVERSE_PROXY":
            peers = [str(x).strip() for x in metadata.get("trusted_proxy_ips", []) if str(x).strip()]
            if not peers:
                raise LedgerError("TRUSTED_TLS_TERMINATING_REVERSE_PROXY requires at least one exact trusted_proxy_ip")
            for peer in peers:
                try:
                    ipaddress.ip_address(peer)
                except ValueError as exc:
                    raise LedgerError(f"Invalid trusted proxy IP: {peer}") from exc
            metadata["trusted_proxy_ips"] = peers
        return self.ledger.record_domain(
            "NETWORK_TRANSPORT_SECURITY_BINDING",
            "Operationalization Network Security Binding",
            {
                "mode": mode,
                "endpoint": endpoint,
                "metadata": metadata,
                "status": "ACTIVE",
                "bound_at": utcnow(),
                "non_loopback_admitted": mode in {"DIRECT_TLS", "TRUSTED_TLS_TERMINATING_REVERSE_PROXY"},
            },
            natural_key="network-transport-security",
            record_state="ACTIVE",
            effective_from=utcnow(),
        )

    def bind_external_account(self, provider: str, account_ref: str, *, account_kind: str, metadata: dict[str, Any] | None = None):
        if not provider.strip() or not account_ref.strip():
            raise LedgerError("provider and account_ref are required")
        return self.ledger.record_domain(
            "EXTERNAL_ACCOUNT_BINDING",
            "Operationalization Account Binding",
            {"provider": provider.lower(), "account_ref": account_ref, "account_kind": account_kind, "metadata": metadata or {}, "status": "ACTIVE", "bound_at": utcnow()},
            natural_key=f"account:{provider.lower()}:{account_ref}", record_state="ACTIVE",
            effective_from=utcnow(),
        )

    def assert_current_external_account_binding(self, account_binding_state_id: str) -> dict[str, Any]:
        state = self.ledger.get_state(account_binding_state_id)
        if state["state_type"] != "EXTERNAL_ACCOUNT_BINDING" or state["payload"].get("status") != "ACTIVE":
            raise LedgerError("Exact external-account binding is not ACTIVE")
        with connect(self.ledger.db_path) as conn:
            row = conn.execute(
                """SELECT s.id FROM artifact_state s
                   JOIN domain_record d ON d.artifact_state_id=s.id
                   WHERE s.identity_id=? AND d.stage='EXTERNAL_ACCOUNT_BINDING'
                   ORDER BY s.version DESC LIMIT 1""",
                (state["identity_id"],),
            ).fetchone()
        if not row or row["id"] != account_binding_state_id:
            raise LedgerError("External-account binding state is stale/superseded")
        return state

    def bind_channel(self, account_binding_state_id: str, platform: str, channel_ref: str, *, language: str | None = None, region: str | None = None, metadata: dict[str, Any] | None = None):
        account = self.assert_current_external_account_binding(account_binding_state_id)
        platform_norm = platform.strip().lower()
        account_provider = str(account["payload"].get("provider") or "").strip().lower()
        metadata = metadata or {}
        compatibility_contract = metadata.get("provider_platform_compatibility_contract_state_id")
        if account_provider != platform_norm and not compatibility_contract:
            raise LedgerError("Channel platform must match external-account provider unless an explicit provider/platform compatibility contract is bound")
        upstream = [(account_binding_state_id, "CHANNEL_ACCOUNT_BINDING")]
        if compatibility_contract:
            contract = self.ledger.get_state(str(compatibility_contract))
            if contract["state_type"] != "GOVERNANCE_CONTRACT_VERSION":
                raise LedgerError("provider/platform compatibility reference must be a governance contract state")
            upstream.append((str(compatibility_contract), "CHANNEL_PROVIDER_PLATFORM_COMPATIBILITY"))
        return self.ledger.record_domain(
            "LIVE_CHANNEL_BINDING",
            "Operationalization Channel Binding",
            {
                "account_binding_state_id": account_binding_state_id,
                "platform": platform_norm,
                "channel_ref": channel_ref,
                "language": language,
                "region": region,
                "metadata": metadata,
                "status": "ACTIVE",
                "bound_at": utcnow(),
            },
            natural_key=f"channel:{platform_norm}:{channel_ref}", record_state="ACTIVE",
            upstream_states=upstream,
        )

    def assert_current_channel_binding(self, channel_binding_state_id: str) -> dict[str, Any]:
        state = self.ledger.get_state(channel_binding_state_id)
        if state["state_type"] != "LIVE_CHANNEL_BINDING" or state["payload"].get("status") != "ACTIVE":
            raise LedgerError("Exact channel binding is not ACTIVE")
        with connect(self.ledger.db_path) as conn:
            row = conn.execute(
                """SELECT s.id FROM artifact_state s
                   JOIN artifact_identity i ON i.id=s.identity_id
                   JOIN domain_record d ON d.artifact_state_id=s.id
                   WHERE i.id=? AND d.stage='LIVE_CHANNEL_BINDING'
                   ORDER BY s.version DESC LIMIT 1""",
                (state["identity_id"],),
            ).fetchone()
        if not row or row["id"] != channel_binding_state_id:
            raise LedgerError("Channel binding state is stale/superseded; reauthorization is required")
        return state

    def record_connector_smoke(self, result: dict[str, Any]):
        provider = str(result.get("provider") or "").strip().lower()
        if not provider:
            raise LedgerError("connector smoke provider is required")
        safe_result = {k: v for k, v in result.items() if "secret" not in k.lower() and "token" not in k.lower()}
        return self.ledger.record_domain(
            "LIVE_CONNECTOR_SMOKE",
            "Operationalization Connector Health",
            {**safe_result, "provider": provider, "recorded_at": utcnow()},
            natural_key=f"connector-smoke:{provider}:{utcnow()}",
            record_state="PASS" if result.get("ok") else "FAIL",
        )


class OperationalPreflight:
    def __init__(self, ledger: GovernanceLedger):
        self.ledger = ledger

    def _domain_count(self, stage: str, state: str = "ACTIVE") -> int:
        with connect(self.ledger.db_path) as conn:
            return int(conn.execute("SELECT COUNT(*) n FROM domain_record WHERE stage=? AND record_state=?", (stage, state)).fetchone()["n"])

    def _current_active_binding_count(self, stage: str) -> int:
        with connect(self.ledger.db_path) as conn:
            rows = conn.execute(
                """SELECT s.identity_id,s.id,s.payload_json,s.effective_from,s.effective_to,d.record_state
                   FROM artifact_state s
                   JOIN domain_record d ON d.artifact_state_id=s.id
                   WHERE d.stage=?
                     AND s.version=(SELECT MAX(s2.version) FROM artifact_state s2 WHERE s2.identity_id=s.identity_id)""",
                (stage,),
            ).fetchall()
        n=0
        for row in rows:
            try:
                payload=json.loads(row["payload_json"])
            except Exception:
                continue
            if row["record_state"]=="ACTIVE" and payload.get("status")=="ACTIVE" and GovernedAuthorizationResolver._iso_is_current(row["effective_from"], row["effective_to"]):
                n+=1
        return n

    def _latest_google_trends_export(self, *, max_age_hours: int = 24) -> dict[str, Any] | None:
        connector = "google_trends_trending_now_export"
        with connect(self.ledger.db_path) as conn:
            rows = conn.execute(
                """SELECT s.id,s.payload_json,s.recorded_at,d.record_state
                   FROM domain_record d
                   JOIN artifact_state s ON s.id=d.artifact_state_id
                   WHERE d.stage='SOURCE_RECORD'
                     AND d.record_state='OBSERVED'
                     AND json_extract(s.payload_json,'$.connector')=?
                   ORDER BY s.recorded_at DESC""",
                (connector,),
            ).fetchall()
        if not rows:
            return None
        latest = rows[0]
        latest_payload: dict[str, Any] = {}
        regions: set[str] = set()
        for idx, row in enumerate(rows):
            try:
                parsed = json.loads(row["payload_json"])
            except Exception:
                parsed = {}
            if idx == 0:
                latest_payload = parsed
            region = (parsed.get("payload") or {}).get("region")
            if region:
                regions.add(str(region))
        try:
            t = datetime.fromisoformat(latest["recorded_at"])
            fresh = datetime.now(timezone.utc) - t.astimezone(timezone.utc) <= timedelta(hours=max_age_hours)
        except Exception:
            fresh = False
        return {
            "mode": "export/import",
            "live_api_credential_required": False,
            "connector": connector,
            "latest_state_id": latest["id"],
            "latest_recorded_at": latest["recorded_at"],
            "fresh": fresh,
            "required_freshness_hours": max_age_hours,
            "observed_record_count": len(rows),
            "regions": sorted(regions),
            "source_observed_at": latest_payload.get("observed_at"),
        }

    def _latest_smoke(self, provider: str, *, max_age_hours: int = 24) -> dict[str, Any] | None:
        with connect(self.ledger.db_path) as conn:
            row = conn.execute(
                """SELECT d.record_state,s.payload_json,s.recorded_at FROM domain_record d
                   JOIN artifact_state s ON s.id=d.artifact_state_id
                   WHERE d.stage='LIVE_CONNECTOR_SMOKE' AND json_extract(s.payload_json,'$.provider')=?
                   ORDER BY s.recorded_at DESC LIMIT 1""",
                (provider,),
            ).fetchone()
        if not row:
            return None
        payload = json.loads(row["payload_json"])
        try:
            t = datetime.fromisoformat(row["recorded_at"])
            fresh = datetime.now(timezone.utc) - t.astimezone(timezone.utc) <= timedelta(hours=max_age_hours)
        except Exception:
            fresh = False
        return {"record_state": row["record_state"], "recorded_at": row["recorded_at"], "fresh": fresh, "payload": payload}

    @staticmethod
    def _connector_status(smoke: dict[str, Any] | None) -> str:
        if not smoke:
            return "EXTERNAL_DEPENDENCY"
        if smoke["record_state"] == "PASS" and smoke["fresh"]:
            return "SYSTEM_CAN_EXECUTE"
        failure_class = str(smoke.get("payload", {}).get("failure_class") or "UNKNOWN_FAILURE")
        if failure_class in EXTERNAL_CONNECTOR_FAILURES:
            return "EXTERNAL_DEPENDENCY"
        if failure_class in INTERNAL_CONNECTOR_FAILURES:
            return "INTERNAL_ENGINEERING_BLOCKER"
        return "UNRESOLVED"

    def _latest_transport_binding(self) -> dict[str, Any] | None:
        with connect(self.ledger.db_path) as conn:
            row = conn.execute(
                """SELECT s.id,s.version,s.payload_json,d.record_state
                   FROM artifact_identity i
                   JOIN artifact_state s ON s.identity_id=i.id
                   JOIN domain_record d ON d.artifact_state_id=s.id
                   WHERE i.kind='NETWORK_TRANSPORT_SECURITY_BINDING'
                     AND i.natural_key='network-transport-security'
                   ORDER BY s.version DESC LIMIT 1"""
            ).fetchone()
        if not row:
            return None
        out = dict(row)
        out["payload"] = json.loads(out.pop("payload_json"))
        return out

    def report(self) -> dict[str, Any]:
        checks: list[dict[str, Any]] = []

        def add(key: str, status: str, detail: Any):
            checks.append({"key": key, "status": status, "detail": detail})

        integrity = self.ledger.integrity_check()
        add("governance_ledger_integrity", "SYSTEM_CAN_EXECUTE" if integrity["ok"] else "INTERNAL_ENGINEERING_BLOCKER", integrity)

        auth_available = bool(os.environ.get("TREND_HUNTER_AUTH_SECRET"))
        add("production_auth_signing_secret", "SYSTEM_CAN_EXECUTE" if auth_available else "USER_ACTION_REQUIRED", {"secret_ref": "env://TREND_HUNTER_AUTH_SECRET", "available": auth_available})

        operator_count = self._current_active_binding_count("OPERATOR_IDENTITY_BINDING")
        add("authenticated_operator_binding", "SYSTEM_CAN_EXECUTE" if operator_count else "USER_ACTION_REQUIRED", {"active_bindings": operator_count})

        # Commercial-launch readiness needs governed coverage of every material operational role/scope,
        # not merely the existence of some unrelated active operator binding.
        required_operator_capabilities = {
            "reader": "internal:read",
            "operator": "source:write",
            "publisher_authorizer": "publication:authorize",
            "commercial_authorizer": "commercial:authorize",
            "commercial_operator": "monetization:activate",
            "publication_operator": "publication:execute",
            "finance_operator": "economics:record",
        }
        capability_coverage: dict[str, dict[str, Any]] = {}
        with connect(self.ledger.db_path) as conn:
            rows = conn.execute(
                """SELECT s.id,s.payload_json,s.effective_from,s.effective_to,d.record_state
                   FROM artifact_identity i
                   JOIN artifact_state s ON s.identity_id=i.id
                   JOIN domain_record d ON d.artifact_state_id=s.id
                   WHERE i.kind='OPERATOR_IDENTITY_BINDING'
                     AND d.stage='OPERATOR_IDENTITY_BINDING'
                   ORDER BY i.id,s.version DESC"""
            ).fetchall()
        # Retain only the latest state for each logical operator identity.
        seen_identities: set[str] = set()
        current_payloads: list[tuple[str, dict[str, Any], str, str | None, str | None]] = []
        for row in rows:
            st = self.ledger.get_state(row["id"])
            if st["identity_id"] in seen_identities:
                continue
            seen_identities.add(st["identity_id"])
            try:
                payload = json.loads(row["payload_json"])
            except Exception:
                payload = {}
            current_payloads.append((row["id"], payload, row["record_state"], row["effective_from"], row["effective_to"]))
        for role, scope in required_operator_capabilities.items():
            matching = []
            for state_id, payload, record_state, effective_from, effective_to in current_payloads:
                roles = set(str(x) for x in payload.get("roles") or [])
                scopes = set(str(x) for x in payload.get("scopes") or [])
                if record_state == "ACTIVE" and payload.get("status") == "ACTIVE" and GovernedAuthorizationResolver._iso_is_current(effective_from, effective_to) and (role in roles or "admin" in roles) and (scope in scopes or "*" in scopes):
                    matching.append(state_id)
            capability_coverage[role] = {"scope": scope, "covered": bool(matching), "binding_state_ids": matching}
        operator_capabilities_ok = all(v["covered"] for v in capability_coverage.values())
        add(
            "governed_operator_role_scope_coverage",
            "SYSTEM_CAN_EXECUTE" if operator_capabilities_ok else "USER_ACTION_REQUIRED",
            {"required": capability_coverage},
        )

        transport_mode = os.environ.get("TREND_HUNTER_TRANSPORT_SECURITY", "LOOPBACK_ONLY").strip().upper()
        transport_binding = self._latest_transport_binding()
        bound_mode = str((transport_binding or {}).get("payload", {}).get("mode") or "").upper()
        binding_active = bool(transport_binding and transport_binding.get("record_state") == "ACTIVE" and (transport_binding.get("payload") or {}).get("status") == "ACTIVE")
        if transport_mode not in TRANSPORT_MODES:
            transport_status = "INTERNAL_ENGINEERING_BLOCKER"
        elif not binding_active or bound_mode != transport_mode:
            # Even LOOPBACK_ONLY is governed explicitly; absence/mismatch is an operator setup action.
            transport_status = "USER_ACTION_REQUIRED"
        else:
            # A governed LOOPBACK_ONLY binding is a valid secure local operating posture.
            # It does NOT imply readiness for non-loopback network exposure.
            transport_status = "SYSTEM_CAN_EXECUTE"
        add("network_transport_security", transport_status, {
            "runtime_mode": transport_mode,
            "governed_binding_state_id": transport_binding.get("id") if transport_binding else None,
            "governed_binding_mode": bound_mode or None,
            "governed_binding_active": binding_active,
            "accepted_non_loopback_modes": ["DIRECT_TLS", "TRUSTED_TLS_TERMINATING_REVERSE_PROXY"],
            "structural_authentication_is_not_transport_security": True,
        })

        account_count = self._current_active_binding_count("EXTERNAL_ACCOUNT_BINDING")
        channel_count = self._current_active_binding_count("LIVE_CHANNEL_BINDING")
        add("live_external_account_binding", "SYSTEM_CAN_EXECUTE" if account_count else "USER_ACTION_REQUIRED", {"active_bindings": account_count})
        add("live_channel_binding", "SYSTEM_CAN_EXECUTE" if channel_count else "USER_ACTION_REQUIRED", {"active_bindings": channel_count})

        youtube = SecretResolver.redacted("env://YOUTUBE_API_KEY")
        add("youtube_api_credential", "SYSTEM_CAN_EXECUTE" if youtube["available"] else "EXTERNAL_DEPENDENCY", youtube)
        gdelt_smoke = self._latest_smoke("gdelt")
        youtube_smoke = self._latest_smoke("youtube")
        add("gdelt_live_connector_smoke", self._connector_status(gdelt_smoke), gdelt_smoke or {"executed": False, "required_freshness_hours": 24})
        add("youtube_live_connector_smoke", self._connector_status(youtube_smoke), youtube_smoke or {"executed": False, "required_freshness_hours": 24})
        google_trends_export = self._latest_google_trends_export()
        add(
            "google_trends_export",
            "SYSTEM_CAN_EXECUTE" if google_trends_export and google_trends_export["fresh"] else "USER_ACTION_REQUIRED",
            google_trends_export or {
                "mode": "export/import",
                "live_api_credential_required": False,
                "requirement": "provide a current governed export when this source is activated",
                "required_freshness_hours": 24,
            },
        )

        by_key = {x["key"]: x for x in checks}
        ready_for_network_exposure = (
            transport_mode in {"DIRECT_TLS", "TRUSTED_TLS_TERMINATING_REVERSE_PROXY"}
            and all(by_key[k]["status"] == "SYSTEM_CAN_EXECUTE" for k in {
                "governance_ledger_integrity", "production_auth_signing_secret", "authenticated_operator_binding", "network_transport_security"
            })
        )
        ready_for_live_source_activation = all(by_key[k]["status"] == "SYSTEM_CAN_EXECUTE" for k in {
            "governance_ledger_integrity", "youtube_api_credential", "gdelt_live_connector_smoke", "youtube_live_connector_smoke"
        })
        commercial_launch_ready = all(x["status"] == "SYSTEM_CAN_EXECUTE" for x in checks)
        return {
            "stage": "OPERATIONALIZATION_ENFORCEMENT_READINESS",
            "generated_at": utcnow(),
            "checks": checks,
            "ready_for_network_exposure": ready_for_network_exposure,
            "ready_for_live_source_activation": ready_for_live_source_activation,
            "commercial_launch_ready": commercial_launch_ready,
        }


def backup_restore_smoke(db_path: str, work_dir: str) -> dict[str, Any]:
    root = Path(work_dir)
    root.mkdir(parents=True, exist_ok=True)
    archive = root / "backup.zip"
    restored = root / "restored"
    if restored.exists():
        import shutil
        shutil.rmtree(restored)
    backup = create_backup(db_path, str(archive))
    restore = restore_backup(str(archive), str(restored))
    return {"backup": backup, "restore": restore, "ok": bool(backup["ok"] and restore["ok"])}

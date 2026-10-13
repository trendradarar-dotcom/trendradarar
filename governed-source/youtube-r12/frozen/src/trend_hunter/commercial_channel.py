from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .db import connect
from .ledger import ArtifactRef, GovernanceLedger, LedgerError
from .operational import OperationalBindingService


@dataclass(frozen=True)
class ChannelTarget:
    platform: str
    language: str
    region: str

    def normalized(self) -> "ChannelTarget":
        platform = str(self.platform or "").strip().lower()
        language = str(self.language or "").strip().lower()
        region = str(self.region or "").strip().upper()
        if not platform or not language or not region:
            raise LedgerError("commercial channel target requires platform, language, and region")
        return ChannelTarget(platform=platform, language=language, region=region)


class CommercialChannelService:
    """Governed C1 commercial-channel selection.

    The service is intentionally narrow: it records/evaluates whether an exact
    existing governed channel may be reused for an exact commercial target and
    binds the decision to the monetization path that was actually assessed.
    It does not create accounts/channels, infer suitability from popularity,
    or replace live platform/commercial authorization.
    """

    ALLOWED_DECISIONS = {"REUSE_EXISTING", "CREATE_NEW", "HOLD"}
    VERIFIED_STATES = {"VERIFIED", "CONFIRMED"}
    SUITABILITY_SCOPE = "COMMERCIAL_CHANNEL_SUITABILITY"

    def __init__(self, ledger: GovernanceLedger):
        self.ledger = ledger

    def _is_current(self, state_id: str) -> bool:
        st = self.ledger.get_state(state_id)
        with connect(self.ledger.db_path) as conn:
            row = conn.execute(
                "SELECT id FROM artifact_state WHERE identity_id=? ORDER BY version DESC LIMIT 1",
                (st["identity_id"],),
            ).fetchone()
        return bool(row and row["id"] == state_id)

    def _require_current(self, state_id: str, label: str) -> dict[str, Any]:
        st = self.ledger.get_state(state_id)
        if not self._is_current(state_id):
            raise LedgerError(f"{label} is stale/superseded")
        if str(st.get("status") or "").upper() not in {"COMMITTED", "ACTIVE"}:
            raise LedgerError(f"{label} is not committed/active")
        return st

    def _domain_record_state(self, state_id: str) -> str | None:
        with connect(self.ledger.db_path) as conn:
            row = conn.execute(
                "SELECT record_state FROM domain_record WHERE artifact_state_id=?", (state_id,)
            ).fetchone()
        return str(row["record_state"]).upper() if row and row["record_state"] is not None else None

    @staticmethod
    def _normalize_path(path: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(path, dict) or not path:
            raise LedgerError("monetization_path must be a non-empty explicit object")
        mechanism = str(path.get("mechanism") or "").strip()
        if not mechanism:
            raise LedgerError("monetization_path.mechanism is required")
        # Preserve exact declared commercial routing fields; normalize only text whitespace.
        normalized: dict[str, Any] = {"mechanism": mechanism}
        for key in ("provider", "account_ref", "offer_or_product_ref", "campaign_ref", "tracked_destination"):
            value = path.get(key)
            normalized[key] = None if value is None else str(value).strip()
        return normalized

    def _validate_suitability_evidence(
        self,
        evidence_state_id: str,
        *,
        channel_state_id: str,
        target: ChannelTarget,
    ) -> dict[str, Any]:
        ev = self._require_current(evidence_state_id, "channel suitability evidence")
        if ev["state_type"] != "EVIDENCE":
            raise LedgerError("channel suitability evidence must be typed EVIDENCE")
        payload = ev.get("payload") or {}
        if payload.get("synthetic") or payload.get("fixture") or payload.get("source_kind") in {"synthetic", "fixture"}:
            raise LedgerError("synthetic/fixture evidence cannot establish channel suitability")
        if str(payload.get("review_scope") or "").upper() != self.SUITABILITY_SCOPE:
            raise LedgerError("channel suitability evidence has wrong review_scope")
        if payload.get("channel_state_id") != channel_state_id:
            raise LedgerError("channel suitability evidence is not bound to the exact channel state")
        if str(payload.get("platform") or "").strip().lower() != target.platform:
            raise LedgerError("channel suitability evidence platform mismatch")
        if str(payload.get("language") or "").strip().lower() != target.language:
            raise LedgerError("channel suitability evidence language mismatch")
        if str(payload.get("region") or "").strip().upper() != target.region:
            raise LedgerError("channel suitability evidence region mismatch")
        if str(payload.get("verification_status") or "").upper() not in self.VERIFIED_STATES:
            raise LedgerError("channel suitability evidence lacks governed verification status")
        if self._domain_record_state(evidence_state_id) not in self.VERIFIED_STATES:
            raise LedgerError("channel suitability evidence domain record is not VERIFIED/CONFIRMED")
        if payload.get("suitable") is not True:
            raise LedgerError("channel suitability evidence does not affirm suitability")
        basis_ids = list(dict.fromkeys(payload.get("basis_state_ids") or []))
        if not basis_ids:
            raise LedgerError("channel suitability evidence requires at least one independent governed basis state")
        for basis_id in basis_ids:
            if basis_id in {evidence_state_id, channel_state_id}:
                raise LedgerError("channel suitability evidence basis is not independent")
            basis = self._require_current(str(basis_id), "channel suitability evidence basis")
            bp = basis.get("payload") or {}
            if bp.get("synthetic") or bp.get("fixture") or bp.get("source_kind") in {"synthetic", "fixture"}:
                raise LedgerError("synthetic/fixture basis cannot establish channel suitability")
            if basis["state_type"] not in {"SOURCE_RECORD", "LIVE_CONNECTOR_SMOKE", "EXTERNAL_ACCOUNT_BINDING", "PERFORMANCE_OBSERVATION"}:
                raise LedgerError("channel suitability evidence basis is not an admitted independent source type")
        return payload

    def evaluate(
        self,
        *,
        opportunity_state_id: str,
        decision: str,
        platform: str,
        language: str,
        region: str,
        monetization_path: dict[str, Any],
        existing_channel_state_id: str | None = None,
        suitability_evidence_state_id: str | None = None,
        rationale: dict[str, Any] | None = None,
    ) -> ArtifactRef:
        opp = self._require_current(opportunity_state_id, "opportunity")
        if opp["state_type"] != "OPPORTUNITY":
            raise LedgerError("commercial channel evaluation requires an OPPORTUNITY state")

        decision = str(decision or "").strip().upper()
        if decision not in self.ALLOWED_DECISIONS:
            raise LedgerError("commercial channel decision must be REUSE_EXISTING, CREATE_NEW, or HOLD")
        target = ChannelTarget(platform, language, region).normalized()
        path = self._normalize_path(monetization_path)

        upstream: list[tuple[str, str]] = [(opportunity_state_id, "COMMERCIAL_CHANNEL_FOR")]
        channel_payload = None

        if decision == "REUSE_EXISTING":
            if not existing_channel_state_id or not suitability_evidence_state_id:
                raise LedgerError("REUSE_EXISTING requires exact current channel and independent suitability evidence")
            channel = OperationalBindingService(self.ledger).assert_current_channel_binding(existing_channel_state_id)
            channel_payload = channel.get("payload") or {}
            if str(channel_payload.get("platform") or "").strip().lower() != target.platform:
                raise LedgerError("existing channel platform does not match exact target")
            if str(channel_payload.get("language") or "").strip().lower() != target.language:
                raise LedgerError("existing channel language does not match exact target")
            if str(channel_payload.get("region") or "").strip().upper() != target.region:
                raise LedgerError("existing channel region does not match exact target")
            self._validate_suitability_evidence(
                suitability_evidence_state_id,
                channel_state_id=existing_channel_state_id,
                target=target,
            )
            upstream.extend([
                (existing_channel_state_id, "EXACT_EXISTING_CHANNEL"),
                (suitability_evidence_state_id, "INDEPENDENT_CHANNEL_SUITABILITY_EVIDENCE"),
            ])
        else:
            if existing_channel_state_id or suitability_evidence_state_id:
                raise LedgerError(f"{decision} must not smuggle an existing-channel reuse proof")

        subject = self.ledger.subject_identity_for_state(opportunity_state_id)
        result = self.ledger.record_domain(
            "COMMERCIAL_CHANNEL_DECISION",
            "Commercial Channel Authority",
            {
                "opportunity_state_id": opportunity_state_id,
                "decision": decision,
                "target": {
                    "platform": target.platform,
                    "language": target.language,
                    "region": target.region,
                },
                "existing_channel_state_id": existing_channel_state_id,
                "suitability_evidence_state_id": suitability_evidence_state_id,
                "evaluated_monetization_path": path,
                "rationale": rationale or {},
                "no_channel_creation_or_activation_claim": True,
                "no_monetization_substitution_after_evaluation": True,
            },
            natural_key=(
                f"commercial-channel:{opportunity_state_id}:{decision}:"
                f"{target.platform}:{target.language}:{target.region}:"
                f"{path['mechanism']}:{path.get('provider')}:{path.get('account_ref')}:{path.get('offer_or_product_ref')}:"
                f"{path.get('campaign_ref')}:{path.get('tracked_destination')}"
            ),
            subject_identity_id=subject,
            scope={"platform": target.platform, "language": target.language, "region": target.region},
            record_state="EVALUATED" if decision != "HOLD" else "HOLD",
            upstream_states=upstream,
        )
        return result

    def assert_monetization_configuration_matches(
        self,
        commercial_channel_decision_state_id: str,
        monetization_configuration_state_id: str,
    ) -> None:
        decision = self._require_current(commercial_channel_decision_state_id, "commercial channel decision")
        if decision["state_type"] != "COMMERCIAL_CHANNEL_DECISION":
            raise LedgerError("requires COMMERCIAL_CHANNEL_DECISION")
        if (decision.get("payload") or {}).get("decision") == "HOLD":
            raise LedgerError("HOLD commercial channel decision cannot authorize monetization use")

        mon = self._require_current(monetization_configuration_state_id, "monetization configuration")
        if mon["state_type"] != "MONETIZATION_CONFIGURATION":
            raise LedgerError("requires MONETIZATION_CONFIGURATION")
        p = mon.get("payload") or {}
        actual = self._normalize_path({
            "mechanism": p.get("mechanism"),
            "provider": p.get("provider"),
            "account_ref": p.get("account_ref"),
            "offer_or_product_ref": p.get("offer_or_product_ref"),
            "campaign_ref": p.get("campaign_ref"),
            "tracked_destination": p.get("tracked_destination"),
        })
        evaluated = self._normalize_path((decision.get("payload") or {}).get("evaluated_monetization_path") or {})
        if actual != evaluated:
            raise LedgerError("actual monetization path differs from the path evaluated for the commercial channel")

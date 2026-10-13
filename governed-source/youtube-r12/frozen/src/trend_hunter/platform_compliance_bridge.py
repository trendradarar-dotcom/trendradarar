from __future__ import annotations

import json
from typing import Any

from .ledger import LedgerError
from .platform_policy import normalize_platform
from .saudi_legal import SaudiCybercrimeReviewService


class PlatformComplianceBridge:
    """
    Server-side bridge from automated platform review into COMPLIANCE_ASSESSMENT.

    Client-supplied platform findings are intentionally not accepted here.
    Platform policy is evaluated by the governed automated reviewer.

    Decision mapping:
      PASS  -> platform findings may proceed to normal compliance gating
      BLOCK -> force compliance gate BLOCK
      HOLD  -> convert platform findings to UNRESOLVED and force an internal
               HUMAN_REVIEW gate. This is an operational hold, not a request
               for the owner to manually review platform policy.

    Saudi legal findings remain separate inputs from the existing human review
    workflow.
    """

    def __init__(self, ledger: Any, compliance_service: Any, platform_review_service: Any):
        self.ledger = ledger
        self.compliance_service = compliance_service
        self.platform_review_service = platform_review_service
        self.enforce_governed_saudi_review = False

    @staticmethod
    def _creative_payload(state: dict[str, Any]) -> dict[str, Any]:
        raw = state.get("payload_json")
        if isinstance(raw, str):
            try:
                payload = json.loads(raw)
            except json.JSONDecodeError as exc:
                raise LedgerError("CREATIVE_ARTIFACT payload_json is invalid JSON") from exc
        elif isinstance(raw, dict):
            payload = raw
        else:
            payload = state.get("payload")

        if not isinstance(payload, dict):
            raise LedgerError("CREATIVE_ARTIFACT requires a structured payload")
        return payload

    @staticmethod
    def _platform_from_target(target: dict[str, Any]) -> str:
        if not isinstance(target, dict):
            raise LedgerError("compliance target must be an object")
        value = str(target.get("platform") or "").strip()
        if not value:
            raise LedgerError("automated platform review requires target.platform")
        try:
            return normalize_platform(value)
        except Exception as exc:
            raise LedgerError(f"unsupported platform for automated review: {value}") from exc

    @staticmethod
    def _hold_findings(findings: list[dict[str, Any]], reason: str) -> list[dict[str, Any]]:
        held: list[dict[str, Any]] = []
        for finding in findings:
            item = dict(finding)
            provider_status = str(item.get("status") or "UNRESOLVED").upper()
            item["provider_status"] = provider_status
            item["status"] = "UNRESOLVED"
            existing_reason = str(item.get("reason") or "").strip()
            item["reason"] = existing_reason or reason or "Automated platform review is unresolved."
            held.append(item)
        return held

    @staticmethod
    def _effective_gate(requested: str, auto_decision: str) -> str:
        requested = str(requested or "").upper()
        auto_decision = str(auto_decision or "").upper()

        if auto_decision == "BLOCK":
            return "BLOCK"
        if auto_decision == "HOLD":
            return "BLOCK" if requested == "BLOCK" else "HUMAN_REVIEW"
        if auto_decision == "PASS":
            return requested

        raise LedgerError(f"unknown automated platform decision: {auto_decision}")

    @staticmethod
    def _effective_coverage(requested: str, auto_decision: str) -> str:
        coverage = str(requested or "").upper()
        if auto_decision == "HOLD" and coverage == "SUFFICIENT":
            return "PARTIAL"
        return requested

    @staticmethod
    def _is_sa_target(target: dict[str, Any]) -> bool:
        return (
            str((target or {}).get("jurisdiction") or "")
            .strip()
            .upper()
            == "SA"
        )

    def _effective_legal_findings(
        self,
        *,
        creative_state_id: str,
        target: dict[str, Any],
        legal_findings: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        supplied = list(legal_findings or [])

        if (
            not self.enforce_governed_saudi_review
            or not self._is_sa_target(target)
        ):
            return supplied

        review = self.ledger.get_latest_state_by_natural_key(
            "EVIDENCE",
            f"saudi-cybercrime-review:{creative_state_id}",
        )

        if review is None:
            raise LedgerError(
                "Saudi human legal review is required "
                "before compliance assessment"
            )

        payload = review.get("payload") or {}

        if payload.get("creative_state_id") != creative_state_id:
            raise LedgerError(
                "Saudi review is not bound "
                "to the exact creative state"
            )

        if (
            str(payload.get("review_scope") or "")
            .strip()
            .lower()
            != "legal"
        ):
            raise LedgerError(
                "Saudi review has invalid review_scope"
            )

        if (
            str(payload.get("verification_status") or "")
            .strip()
            .upper()
            != "HUMAN_REVIEWED"
        ):
            raise LedgerError(
                "Saudi review must be HUMAN_REVIEWED"
            )

        if payload.get("fixture") is True:
            raise LedgerError(
                "Saudi production review cannot be fixture evidence"
            )

        if payload.get("automated_legal_clearance") is not False:
            raise LedgerError(
                "Saudi legal clearance must remain human-controlled"
            )

        return [
            SaudiCybercrimeReviewService(
                self.ledger
            ).compliance_finding(review["id"])
        ]


    def assess(
        self,
        *,
        creative_state_id: str,
        eligibility_state_id: str,
        target: dict[str, Any],
        legal_findings: list[dict[str, Any]],
        coverage_state: str,
        gate_decision: str,
        strict_c1: bool,
    ):
        creative_state = self.ledger.get_state(creative_state_id)
        if creative_state.get("state_type") != "CREATIVE_ARTIFACT":
            raise LedgerError("automated platform review target must be CREATIVE_ARTIFACT")

        creative_payload = self._creative_payload(creative_state)
        platform = self._platform_from_target(target)

        auto = self.platform_review_service.review(
            creative_state_id=creative_state_id,
            platform=platform,
            creative=creative_payload,
        )

        auto_decision = str(auto.decision).upper()
        platform_findings = list(auto.platform_findings)

        if auto_decision == "HOLD":
            platform_findings = self._hold_findings(platform_findings, str(auto.reason))
        elif auto_decision not in {"PASS", "BLOCK"}:
            raise LedgerError(f"unsupported automated platform decision: {auto_decision}")

        effective_legal_findings = self._effective_legal_findings(
            creative_state_id=creative_state_id,
            target=target,
            legal_findings=legal_findings,
        )
        effective_strict_c1 = bool(
            strict_c1
            or (
                self.enforce_governed_saudi_review
                and self._is_sa_target(target)
            )
        )

        return self.compliance_service.assess(
            creative_state_id,
            eligibility_state_id,
            target=target,
            legal_findings=effective_legal_findings,
            platform_findings=platform_findings,
            coverage_state=self._effective_coverage(coverage_state, auto_decision),
            gate_decision=self._effective_gate(gate_decision, auto_decision),
            strict_c1=effective_strict_c1,
        )
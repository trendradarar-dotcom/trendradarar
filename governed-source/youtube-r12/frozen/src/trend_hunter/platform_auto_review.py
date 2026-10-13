from __future__ import annotations

from dataclasses import dataclass
import json
import os
from typing import Any, Protocol
import urllib.request

from .ledger import GovernanceLedger, LedgerError
from .openai_platform_analyzer import OpenAIResponsesAnalyzer
from .platform_policy import (
    PLATFORM_POLICY_CATALOG_VERSION,
    normalize_platform,
    platform_policy_rules,
)


AUTO_REVIEW_ENGINE_VERSION = "1.1.0"

PASS_THRESHOLD = 0.90
BLOCK_THRESHOLD = 0.95

_ALLOWED_RULE_STATUSES = {"PASS", "BLOCK", "HOLD", "UNRESOLVED", "NOT_APPLICABLE"}


class PlatformAnalyzer(Protocol):
    name: str

    def analyze(
        self,
        *,
        platform: str,
        creative: dict[str, Any],
        rules: list[dict[str, Any]],
    ) -> dict[str, Any]:
        ...


@dataclass(frozen=True)
class AutoReviewOutcome:
    decision: str
    platform_findings: list[dict[str, Any]]
    evidence_state_ids: list[str]
    analyzer: str
    reason: str


class ExternalJSONAnalyzer:
    """
    Provider-neutral HTTP adapter.

    Environment:
      TREND_HUNTER_PLATFORM_REVIEW_URL
      TREND_HUNTER_PLATFORM_REVIEW_TOKEN   (optional)

    Expected response:
    {
      "review_complete": true,
      "reviewed_modalities": ["text","image","audio","video"],
      "rules": [
        {"rule_id":"YT-...", "status":"PASS|BLOCK|HOLD|NOT_APPLICABLE",
         "confidence":0.0..1.0, "reason":"..."}
      ]
    }

    Provider failure never becomes PASS.
    """

    name = "external_json"

    def __init__(self, endpoint: str | None = None, token: str | None = None, timeout: int = 60):
        self.endpoint = (endpoint or os.getenv("TREND_HUNTER_PLATFORM_REVIEW_URL") or "").strip()
        self.token = token if token is not None else os.getenv("TREND_HUNTER_PLATFORM_REVIEW_TOKEN")
        self.timeout = timeout

    def analyze(
        self,
        *,
        platform: str,
        creative: dict[str, Any],
        rules: list[dict[str, Any]],
    ) -> dict[str, Any]:
        if not self.endpoint:
            raise RuntimeError("platform review analyzer endpoint is not configured")

        body = json.dumps(
            {
                "engine_contract": "trend-hunter-platform-review-v1",
                "platform": platform,
                "catalog_version": PLATFORM_POLICY_CATALOG_VERSION,
                "creative": creative,
                "rules": rules,
            },
            ensure_ascii=False,
            separators=(",", ":"),
        ).encode("utf-8")

        headers = {
            "Content-Type": "application/json; charset=utf-8",
            "Accept": "application/json",
        }
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"

        request = urllib.request.Request(
            self.endpoint,
            data=body,
            headers=headers,
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=self.timeout) as response:
            if response.status < 200 or response.status >= 300:
                raise RuntimeError(f"platform analyzer HTTP {response.status}")
            return json.loads(response.read().decode("utf-8"))


class PlatformPolicyAutoReviewService:
    """
    Hidden automated platform-policy gate.

    Distinct from the Saudi legal reviewer.
    Fail-closed:
      - complete high-confidence PASS => PASS
      - high-confidence BLOCK => BLOCK
      - missing provider / incomplete review / low confidence / malformed result => HOLD

    Saudi legal review remains a separate human workflow.
    """

    def __init__(self, ledger: GovernanceLedger, analyzer: PlatformAnalyzer | None = None):
        self.ledger = ledger
        self.analyzer = analyzer or OpenAIResponsesAnalyzer()

    @staticmethod
    def _normalize_provider_result(
        *,
        rules: list[dict[str, Any]],
        raw: dict[str, Any],
    ) -> tuple[str, list[dict[str, Any]], str]:
        if not isinstance(raw, dict):
            return "HOLD", [], "analyzer response is not an object"

        if raw.get("review_complete") is not True:
            return "HOLD", [], "analyzer did not attest a complete review"

        returned = raw.get("rules")
        if not isinstance(returned, list):
            return "HOLD", [], "analyzer response has no rule results"

        by_id: dict[str, dict[str, Any]] = {}
        for item in returned:
            if not isinstance(item, dict):
                return "HOLD", [], "analyzer returned a non-object rule result"
            rule_id = str(item.get("rule_id") or "").strip()
            if not rule_id or rule_id in by_id:
                return "HOLD", [], "analyzer rule identifiers are missing or duplicated"
            by_id[rule_id] = item

        expected_ids = [str(r["rule_id"]) for r in rules]
        if set(by_id) != set(expected_ids):
            return "HOLD", [], "analyzer did not resolve the exact governed rule set"

        normalized: list[dict[str, Any]] = []
        any_block = False
        all_passable = True

        for rule in rules:
            item = by_id[rule["rule_id"]]
            status = str(item.get("status") or "").strip().upper()
            reason = str(item.get("reason") or "").strip()

            try:
                confidence = float(item.get("confidence"))
            except (TypeError, ValueError):
                return "HOLD", [], f"{rule['rule_id']} has invalid confidence"

            if confidence < 0.0 or confidence > 1.0:
                return "HOLD", [], f"{rule['rule_id']} confidence is outside 0..1"

            if status not in _ALLOWED_RULE_STATUSES:
                return "HOLD", [], f"{rule['rule_id']} has invalid status"

            if status in {"HOLD", "UNRESOLVED"}:
                all_passable = False

            if status == "BLOCK":
                if confidence >= BLOCK_THRESHOLD:
                    any_block = True
                else:
                    all_passable = False

            if status in {"PASS", "NOT_APPLICABLE"} and confidence < PASS_THRESHOLD:
                all_passable = False

            normalized.append(
                {
                    **rule,
                    "status": status,
                    "reason": reason or (
                        "Automated governed platform-policy review completed."
                        if status in {"PASS", "NOT_APPLICABLE"}
                        else "Automated platform-policy review requires a fail-closed hold."
                    ),
                    "confidence": confidence,
                    "review_mode": "AUTOMATED",
                }
            )

        if any_block:
            return "BLOCK", normalized, "one or more platform-policy rules produced a high-confidence BLOCK"

        if all_passable:
            return "PASS", normalized, "all governed platform-policy rules completed above the automatic PASS threshold"

        return "HOLD", normalized, "platform-policy review is incomplete, uncertain, or below the automatic threshold"

    def _record_rule_evidence(
        self,
        *,
        creative_state_id: str,
        platform: str,
        analyzer_name: str,
        finding: dict[str, Any],
        raw_result: dict[str, Any],
    ) -> str:
        subject_identity = self.ledger.subject_identity_for_state(creative_state_id)

        evidence = self.ledger.record_domain(
            "EVIDENCE",
            "Automated Platform Policy Review Evidence Authority",
            {
                "creative_state_id": creative_state_id,
                "review_scope": "platform",
                "verification_status": "GOVERNED_POLICY_CHECK",
                "platform": platform,
                "rule_id": finding["rule_id"],
                "rule_status": finding["status"],
                "confidence": finding.get("confidence"),
                "reason": finding.get("reason"),
                "analyzer": analyzer_name,
                "auto_review_engine_version": AUTO_REVIEW_ENGINE_VERSION,
                "catalog_version": PLATFORM_POLICY_CATALOG_VERSION,
                "source_url": finding.get("source_url"),
                "provider_result": raw_result,
            },
            natural_key=(
                f"platform-policy-evidence:{creative_state_id}:{platform}:"
                f"{finding['rule_id']}:{AUTO_REVIEW_ENGINE_VERSION}"
            ),
            subject_identity_id=subject_identity,
            scope={
                "creative_state_id": creative_state_id,
                "platform": platform,
                "rule_id": finding["rule_id"],
            },
            record_state="VERIFIED",
            upstream_states=[(creative_state_id, "PLATFORM_POLICY_CREATIVE")],
        )
        return evidence.state_id

    def review(
        self,
        *,
        creative_state_id: str,
        platform: str,
        creative: dict[str, Any],
    ) -> AutoReviewOutcome:
        platform = normalize_platform(platform)

        state = self.ledger.get_state(creative_state_id)
        if state["state_type"] != "CREATIVE_ARTIFACT":
            raise LedgerError("platform auto review target must be CREATIVE_ARTIFACT")

        rules = platform_policy_rules(platform)

        try:
            raw = self.analyzer.analyze(
                platform=platform,
                creative=creative,
                rules=rules,
            )
        except Exception as exc:
            return AutoReviewOutcome(
                decision="HOLD",
                platform_findings=[
                    {
                        **rule,
                        "status": "UNRESOLVED",
                        "reason": f"Automated platform analyzer unavailable: {type(exc).__name__}",
                        "evidence_state_ids": [],
                        "review_mode": "AUTOMATED_FAIL_CLOSED",
                    }
                    for rule in rules
                ],
                evidence_state_ids=[],
                analyzer=getattr(self.analyzer, "name", type(self.analyzer).__name__),
                reason="automated platform analyzer unavailable; fail-closed HOLD",
            )

        decision, findings, reason = self._normalize_provider_result(rules=rules, raw=raw)
        analyzer_name = getattr(self.analyzer, "name", type(self.analyzer).__name__)

        if not findings:
            return AutoReviewOutcome(
                decision="HOLD",
                platform_findings=[
                    {
                        **rule,
                        "status": "UNRESOLVED",
                        "reason": reason,
                        "evidence_state_ids": [],
                        "review_mode": "AUTOMATED_FAIL_CLOSED",
                    }
                    for rule in rules
                ],
                evidence_state_ids=[],
                analyzer=analyzer_name,
                reason=reason,
            )

        evidence_ids: list[str] = []
        bound_findings: list[dict[str, Any]] = []
        for finding in findings:
            evidence_id = self._record_rule_evidence(
                creative_state_id=creative_state_id,
                platform=platform,
                analyzer_name=analyzer_name,
                finding=finding,
                raw_result=raw,
            )
            evidence_ids.append(evidence_id)
            bound_findings.append({**finding, "evidence_state_ids": [evidence_id]})

        return AutoReviewOutcome(
            decision=decision,
            platform_findings=bound_findings,
            evidence_state_ids=evidence_ids,
            analyzer=analyzer_name,
            reason=reason,
        )
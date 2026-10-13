from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .ledger import LedgerError


@dataclass(frozen=True)
class SaudiPublicationAuthorizationResult:
    legal_review_state_id: str
    compliance_state_id: str
    recommendation_state_id: str
    authorization_state_id: str | None
    disposition: str


class SaudiPublicationAuthorizationOrchestrator:
    """
    One human action, two distinct governed records.

    Saudi legal review remains HUMAN_REVIEWED evidence.
    Only when the resulting compliance/recommendation chain reaches
    RECOMMEND_PUBLISH may the same identified human action also create
    the exact HUMAN_AUTHORIZATION record bound to configuration, channel,
    and publication media.

    Platform policy remains server-side through PlatformComplianceBridge.
    This service never performs a provider publication side effect.
    """

    def __init__(
        self,
        ledger: Any,
        saudi_legal_service: Any,
        platform_compliance_bridge: Any,
        recommendation_service: Any,
        operations_service: Any,
    ):
        self.ledger = ledger
        self.saudi_legal_service = saudi_legal_service
        self.platform_compliance_bridge = platform_compliance_bridge
        self.recommendation_service = recommendation_service
        self.operations_service = operations_service

    @staticmethod
    def _legal_gate(status: str) -> str:
        normalized = str(status or "").strip().upper()
        if normalized in {"PASS", "NOT_APPLICABLE"}:
            return "PASS"
        if normalized == "WARNING":
            return "WARNING"
        if normalized == "BLOCK":
            return "BLOCK"
        if normalized == "UNRESOLVED":
            return "HUMAN_REVIEW"
        raise LedgerError(
            f"unsupported Saudi legal review status: {normalized or '<empty>'}"
        )

    @staticmethod
    def _payload(state: dict[str, Any]) -> dict[str, Any]:
        payload = state.get("payload")
        if not isinstance(payload, dict):
            raise LedgerError("CREATIVE_ARTIFACT requires a structured payload")
        return payload

    def approve_and_authorize(
        self,
        *,
        creative_state_id: str,
        eligibility_state_id: str,
        reviewer: str,
        determinations: list[dict[str, Any]],
        source_checked_at: str,
        authorizer: str,
        execution_configuration_state_id: str | None = None,
        channel_binding_state_id: str | None = None,
        media_descriptor_state_id: str | None = None,
        notes: str = "",
        auth_context: dict[str, Any] | None = None,
    ) -> SaudiPublicationAuthorizationResult:
        creative = self.ledger.get_state(creative_state_id)
        if creative.get("state_type") != "CREATIVE_ARTIFACT":
            raise LedgerError(
                "single-action Saudi authorization target must be CREATIVE_ARTIFACT"
            )

        target = self._payload(creative).get("target")
        if not isinstance(target, dict):
            raise LedgerError("creative artifact lacks exact publication target")

        legal_review = self.saudi_legal_service.review(
            creative_state_id,
            reviewer=reviewer,
            determinations=determinations,
            source_checked_at=source_checked_at,
            notes=notes,
        )
        legal_finding = self.saudi_legal_service.compliance_finding(
            legal_review.state_id
        )
        legal_status = str(legal_finding.get("status") or "").strip().upper()

        compliance = self.platform_compliance_bridge.assess(
            creative_state_id=creative_state_id,
            eligibility_state_id=eligibility_state_id,
            target=target,
            legal_findings=[legal_finding],
            coverage_state="SUFFICIENT",
            gate_decision=self._legal_gate(legal_status),
            strict_c1=True,
        )

        recommendation = self.recommendation_service.recommend(
            creative_state_id,
            eligibility_state_id,
            compliance.state_id,
        )
        recommendation_state = self.ledger.get_state(recommendation.state_id)
        recommendation_value = str(
            (recommendation_state.get("payload") or {}).get("recommendation") or ""
        ).strip().upper()

        if recommendation_value != "RECOMMEND_PUBLISH":
            return SaudiPublicationAuthorizationResult(
                legal_review_state_id=legal_review.state_id,
                compliance_state_id=compliance.state_id,
                recommendation_state_id=recommendation.state_id,
                authorization_state_id=None,
                disposition=recommendation_value or "RECOMMEND_HOLD",
            )

        reviewer_id = str(reviewer or "").strip()
        authorizer_id = str(authorizer or "").strip()
        if not reviewer_id or not authorizer_id:
            raise LedgerError(
                "single human action requires identified reviewer/authorizer"
            )
        if reviewer_id != authorizer_id:
            raise LedgerError(
                "single human action cannot silently attribute Saudi review and publication authorization to different humans"
            )

        if (
            not execution_configuration_state_id
            or not channel_binding_state_id
            or not media_descriptor_state_id
        ):
            raise LedgerError(
                "RECOMMEND_PUBLISH requires exact execution configuration, channel binding, and media descriptor before authorization"
            )

        authorization = self.operations_service.record_human_authorization(
            recommendation.state_id,
            authorizer_id,
            "AUTHORIZED",
            notes=notes,
            auth_context=auth_context,
            execution_configuration_state_id=execution_configuration_state_id,
            channel_binding_state_id=channel_binding_state_id,
            media_descriptor_state_id=media_descriptor_state_id,
            require_exact_channel=True,
            require_exact_media=True,
        )

        return SaudiPublicationAuthorizationResult(
            legal_review_state_id=legal_review.state_id,
            compliance_state_id=compliance.state_id,
            recommendation_state_id=recommendation.state_id,
            authorization_state_id=authorization.state_id,
            disposition="AUTHORIZED_FOR_EXACT_PUBLICATION_BUNDLE",
        )
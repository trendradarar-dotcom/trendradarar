from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .db import connect
from .ledger import ArtifactRef, GovernanceLedger, LedgerError


@dataclass(frozen=True)
class RepeatabilityPolicy:
    min_repeatable_outcomes: int

    def validate(self) -> None:
        if isinstance(self.min_repeatable_outcomes, bool) or not isinstance(self.min_repeatable_outcomes, int):
            raise LedgerError("min_repeatable_outcomes must be an integer")
        if self.min_repeatable_outcomes < 2:
            raise LedgerError("SCALE policy cannot be satisfied by a single realized outcome")


class LearningScaleStopService:
    """C1-C6 repeatability gate over verified realized economics.

    SCALE is deliberately narrow: enough exact, comparable, evidence-bound outcomes
    must exist for the same current channel and the same actual monetization path,
    and every included outcome must be profitable.  A viral performance metric alone
    never contributes authority to SCALE.
    """

    ALLOWED_DECISIONS = {"SCALE", "CONTINUE", "PAUSE", "STOP"}

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

    @staticmethod
    def _normalize_path(payload: dict[str, Any]) -> tuple[Any, ...]:
        return (
            str(payload.get("mechanism") or "").strip(),
            None if payload.get("provider") is None else str(payload.get("provider")).strip(),
            None if payload.get("account_ref") is None else str(payload.get("account_ref")).strip(),
            None if payload.get("offer_or_product_ref") is None else str(payload.get("offer_or_product_ref")).strip(),
            None if payload.get("campaign_ref") is None else str(payload.get("campaign_ref")).strip(),
            None if payload.get("tracked_destination") is None else str(payload.get("tracked_destination")).strip(),
        )

    def _outcome_facts(self, state_id: str) -> dict[str, Any]:
        out = self.ledger.get_state(state_id)
        facts: dict[str, Any] = {"state_id": state_id, "blockers": []}
        if out["state_type"] != "REALIZED_ECONOMIC_OUTCOME":
            raise LedgerError("C1-C6 inputs must be REALIZED_ECONOMIC_OUTCOME states")
        if not self._is_current(state_id):
            facts["blockers"].append("STALE_OR_SUPERSEDED_OUTCOME")

        payload = out.get("payload") or {}
        verification = payload.get("profit_verification") or {}
        if verification.get("status") != "SYSTEM_EVIDENCE_BOUND" or verification.get("evidence_status") != "SYSTEM_EVIDENCE_BOUND":
            facts["blockers"].append("UNVERIFIED_ECONOMICS")
        if payload.get("evaluation_blockers"):
            facts["blockers"].append("OUTCOME_HAS_EVALUATION_BLOCKERS")

        profit = payload.get("profit")
        if not isinstance(profit, dict) or profit.get("amount") is None or not profit.get("currency"):
            facts["blockers"].append("NON_DETERMINATE_PROFIT")
            facts["profit_amount"] = None
            facts["currency"] = None
        else:
            try:
                facts["profit_amount"] = float(profit["amount"])
            except (TypeError, ValueError):
                facts["profit_amount"] = None
                facts["blockers"].append("NON_DETERMINATE_PROFIT")
            facts["currency"] = str(profit.get("currency") or "").strip().upper() or None

        evidence_ids = list(dict.fromkeys(verification.get("evidence_state_ids") or []))
        if not evidence_ids:
            facts["blockers"].append("NO_EXACT_ECONOMIC_EVIDENCE")
        for eid in evidence_ids:
            try:
                ev = self.ledger.get_state(str(eid))
            except LedgerError:
                facts["blockers"].append("MISSING_ECONOMIC_EVIDENCE")
                continue
            if ev["state_type"] != "EVIDENCE" or not self._is_current(str(eid)):
                facts["blockers"].append("STALE_OR_WRONG_TYPE_ECONOMIC_EVIDENCE")
                continue
            ep = ev.get("payload") or {}
            with connect(self.ledger.db_path) as conn:
                dr = conn.execute("SELECT record_state FROM domain_record WHERE artifact_state_id=?", (str(eid),)).fetchone()
            if not dr or str(dr["record_state"] or "").upper() != "VERIFIED":
                facts["blockers"].append("UNVERIFIED_ECONOMIC_EVIDENCE_STATE")
            if ep.get("synthetic") or ep.get("fixture") or ep.get("source_kind") in {"synthetic", "fixture"}:
                facts["blockers"].append("SYNTHETIC_ECONOMIC_EVIDENCE")

        publication_state_id = payload.get("publication_state_id")
        if not publication_state_id:
            facts["blockers"].append("MISSING_PUBLICATION_BINDING")
            facts["channel_state_id"] = None
            facts["monetization_path"] = None
            return facts
        try:
            pub = self.ledger.get_state(str(publication_state_id))
        except LedgerError:
            facts["blockers"].append("MISSING_PUBLICATION_BINDING")
            facts["channel_state_id"] = None
            facts["monetization_path"] = None
            return facts
        if pub["state_type"] != "PUBLICATION_EXECUTION":
            facts["blockers"].append("WRONG_PUBLICATION_BINDING")
        pp = pub.get("payload") or {}
        channel_id = pp.get("channel_binding_state_id")
        if not channel_id:
            facts["blockers"].append("MISSING_EXACT_CHANNEL_BINDING")
        else:
            try:
                ch = self.ledger.get_state(str(channel_id))
                if ch["state_type"] != "LIVE_CHANNEL_BINDING" or ch.get("payload", {}).get("status") != "ACTIVE" or not self._is_current(str(channel_id)):
                    facts["blockers"].append("STALE_OR_INACTIVE_CHANNEL_BINDING")
            except LedgerError:
                facts["blockers"].append("MISSING_EXACT_CHANNEL_BINDING")
        facts["channel_state_id"] = channel_id

        activation_id = pp.get("monetization_activation_state_id")
        if not activation_id:
            facts["blockers"].append("MISSING_MONETIZATION_ACTIVATION")
            facts["monetization_path"] = None
            return facts
        try:
            activation = self.ledger.get_state(str(activation_id))
        except LedgerError:
            facts["blockers"].append("MISSING_MONETIZATION_ACTIVATION")
            facts["monetization_path"] = None
            return facts
        if activation["state_type"] != "MONETIZATION_ACTIVATION" or activation.get("payload", {}).get("activation_state") != "ACTIVE" or not self._is_current(str(activation_id)):
            facts["blockers"].append("STALE_OR_INACTIVE_MONETIZATION_ACTIVATION")
        cfg_id = (activation.get("payload") or {}).get("monetization_configuration_state_id")
        if not cfg_id:
            facts["blockers"].append("MISSING_MONETIZATION_CONFIGURATION")
            facts["monetization_path"] = None
            return facts
        try:
            cfg = self.ledger.get_state(str(cfg_id))
        except LedgerError:
            facts["blockers"].append("MISSING_MONETIZATION_CONFIGURATION")
            facts["monetization_path"] = None
            return facts
        if cfg["state_type"] != "MONETIZATION_CONFIGURATION" or not self._is_current(str(cfg_id)):
            facts["blockers"].append("STALE_OR_WRONG_MONETIZATION_CONFIGURATION")
        facts["monetization_path"] = self._normalize_path(cfg.get("payload") or {})
        return facts

    def decide(
        self,
        outcome_state_ids: list[str],
        *,
        policy: RepeatabilityPolicy,
        rationale: dict[str, Any] | None = None,
    ) -> ArtifactRef:
        policy.validate()
        ids = list(dict.fromkeys(str(x) for x in outcome_state_ids if str(x)))
        if not ids:
            raise LedgerError("C1-C6 requires at least one realized outcome input")
        facts = [self._outcome_facts(sid) for sid in ids]

        blockers = sorted({b for f in facts for b in f["blockers"]})
        currencies = {f["currency"] for f in facts if f.get("currency")}
        channels = {f["channel_state_id"] for f in facts if f.get("channel_state_id")}
        paths = {f["monetization_path"] for f in facts if f.get("monetization_path") is not None}
        if len(currencies) > 1:
            blockers.append("NON_COMPARABLE_CURRENCIES")
        if len(channels) > 1:
            blockers.append("MIXED_CHANNELS")
        if len(paths) > 1:
            blockers.append("MIXED_MONETIZATION_PATHS")
        blockers = sorted(set(blockers))

        determinate = [f["profit_amount"] for f in facts if f.get("profit_amount") is not None]
        enough = len(facts) >= policy.min_repeatable_outcomes
        every_profitable = len(determinate) == len(facts) and all(x > 0 for x in determinate)
        cumulative = sum(determinate) if len(determinate) == len(facts) and len(currencies) <= 1 else None

        if blockers:
            decision = "PAUSE"
            reason = "EVIDENCE_OR_COMPARABILITY_BLOCKER"
        elif not enough:
            decision = "CONTINUE"
            reason = "REPEATABILITY_THRESHOLD_NOT_YET_MET"
        elif every_profitable:
            decision = "SCALE"
            reason = "REPEATABLE_VERIFIED_PROFIT_ON_SAME_CHANNEL_AND_MONETIZATION_PATH"
        elif cumulative is not None and cumulative <= 0:
            decision = "STOP"
            reason = "REPEATABLE_SAMPLE_HAS_NON_POSITIVE_CUMULATIVE_REALIZED_PROFIT"
        else:
            decision = "CONTINUE"
            reason = "PROFIT_NOT_YET_REPEATABLE_ACROSS_REQUIRED_SAMPLE"

        subject_ids = {self.ledger.subject_identity_for_state(sid) for sid in ids}
        if len(subject_ids) != 1:
            decision = "PAUSE"
            blockers = sorted(set(blockers + ["MIXED_GOVERNED_SUBJECTS"]))
            reason = "EVIDENCE_OR_COMPARABILITY_BLOCKER"
        subject = next(iter(subject_ids)) if len(subject_ids) == 1 else None

        return self.ledger.record_domain(
            "LEARNING_SCALE_STOP_DECISION",
            "Economic Outcome & Learning Authority",
            {
                "decision": decision,
                "reason": reason,
                "outcome_state_ids": ids,
                "policy": {"min_repeatable_outcomes": policy.min_repeatable_outcomes},
                "blockers": blockers,
                "sample_size": len(facts),
                "profitable_outcomes": sum(1 for x in determinate if x > 0),
                "cumulative_profit": None if cumulative is None else {"amount": cumulative, "currency": next(iter(currencies)) if currencies else None},
                "same_channel": len(channels) <= 1 and not any("CHANNEL" in b for b in blockers),
                "same_monetization_path": len(paths) <= 1 and "MIXED_MONETIZATION_PATHS" not in blockers,
                "viral_performance_alone_has_no_scale_authority": True,
                "rationale": rationale or {},
            },
            natural_key=f"c1-c6:{':'.join(ids)}:min{policy.min_repeatable_outcomes}",
            subject_identity_id=subject,
            record_state=decision,
            upstream_states=[(sid, "C1_C6_REALIZED_OUTCOME_INPUT") for sid in ids],
        )

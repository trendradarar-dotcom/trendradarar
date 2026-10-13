from __future__ import annotations

from typing import Any

from .ledger import GovernanceLedger, ArtifactRef, LedgerError
from .db import tx
from .util import json_dumps


class ExecutionService:
    def __init__(self, ledger: GovernanceLedger):
        self.ledger = ledger

    def _assert_current_live_channel_binding(self, state_id: str) -> dict[str, Any]:
        state = self.ledger.get_state(state_id)
        if state["state_type"] != "LIVE_CHANNEL_BINDING" or state["payload"].get("status") != "ACTIVE":
            raise LedgerError("live_channel_binding_state_id must reference an ACTIVE LIVE_CHANNEL_BINDING")
        from .db import connect
        with connect(self.ledger.db_path) as conn:
            row = conn.execute(
                """SELECT s.id FROM artifact_state s
                   JOIN domain_record d ON d.artifact_state_id=s.id
                   WHERE s.identity_id=? AND d.stage='LIVE_CHANNEL_BINDING'
                   ORDER BY s.version DESC LIMIT 1""",
                (state["identity_id"],),
            ).fetchone()
        if not row or row["id"] != state_id:
            raise LedgerError("live_channel_binding_state_id is stale/superseded; define a new ExecutionConfiguration")
        return state

    def define_configuration(
        self,
        opportunity_state_id: str,
        eligibility_state_id: str,
        *,
        platform: str,
        channel: str | None,
        content_form: str,
        production_route: str,
        actionable_from: str | None,
        actionable_to: str | None,
        required_resources: dict[str, Any],
        capital_assumption: dict[str, Any],
        operational_mode: str,
        monetization_scenario: dict[str, Any] | None = None,
        live_channel_binding_state_id: str | None = None,
        require_live_channel_binding: bool = False,
    ) -> ArtifactRef:
        opp = self.ledger.get_state(opportunity_state_id)
        elig = self.ledger.get_state(eligibility_state_id)
        if opp["state_type"] != "OPPORTUNITY":
            raise LedgerError("opportunity_state_id must be OPPORTUNITY")
        if elig["state_type"] != "ELIGIBILITY_ASSESSMENT":
            raise LedgerError("eligibility_state_id must be ELIGIBILITY_ASSESSMENT")
        if elig["payload"].get("outcome") != "ELIGIBLE":
            raise LedgerError("ExecutionConfiguration may only be defined after an ELIGIBLE governing eligibility state")
        opportunity_subject = self.ledger.subject_identity_for_state(opportunity_state_id)
        eligibility_subject = self.ledger.subject_identity_for_state(eligibility_state_id)
        if opportunity_subject != eligibility_subject:
            raise LedgerError("eligibility state belongs to a different governed opportunity subject")

        platform_norm = platform.strip().lower()
        channel_binding = None
        if require_live_channel_binding and not live_channel_binding_state_id:
            raise LedgerError("Operational ExecutionConfiguration requires an exact LIVE_CHANNEL_BINDING state")
        if live_channel_binding_state_id:
            channel_binding = self._assert_current_live_channel_binding(live_channel_binding_state_id)
            if str(channel_binding["payload"].get("platform") or "").lower() != platform_norm:
                raise LedgerError("ExecutionConfiguration platform does not match exact live channel binding")
            bound_channel = str(channel_binding["payload"].get("channel_ref") or "")
            if channel is not None and channel != bound_channel:
                raise LedgerError("ExecutionConfiguration channel string does not match exact live channel binding")
            channel = bound_channel

        reassess = self.ledger.get_dependency_policy("UPSTREAM_REQUIRES_REASSESSMENT", 1)
        invalidate = self.ledger.get_dependency_policy("MATERIAL_UPSTREAM_INVALIDATES", 1)

        iid = self.ledger.get_or_create_identity(
            "EXECUTION_CONFIGURATION",
            f"exec:{opportunity_state_id}:{eligibility_state_id}:{platform_norm}:{live_channel_binding_state_id or channel}:{content_form}:{production_route}",
        )
        payload = {
            "opportunity_state_id": opportunity_state_id,
            "eligibility_state_id": eligibility_state_id,
            "platform": platform_norm,
            "channel": channel,
            "live_channel_binding_state_id": live_channel_binding_state_id,
            "content_form": content_form,
            "production_route": production_route,
            "actionable_from": actionable_from,
            "actionable_to": actionable_to,
            "required_resources": required_resources,
            "capital_assumption": capital_assumption,
            "operational_mode": operational_mode,
            "monetization_scenario": monetization_scenario,
            "exact_channel_state_required_for_operational_publication": bool(require_live_channel_binding),
        }
        state = self.ledger.create_state(iid, "EXECUTION_CONFIGURATION", payload, effective_from=actionable_from, effective_to=actionable_to)
        subject = opportunity_subject
        with tx(self.ledger.db_path) as conn:
            conn.execute(
                """INSERT INTO execution_configuration(
                  artifact_state_id,opportunity_identity_id,platform,channel,live_channel_binding_state_id,content_form,production_route,actionable_from,actionable_to,
                  required_resources_json,capital_assumption_json,operational_mode,monetization_configuration_state_id
                ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,NULL)""",
                (
                    state.state_id,
                    subject,
                    platform_norm,
                    channel,
                    live_channel_binding_state_id,
                    content_form,
                    production_route,
                    actionable_from,
                    actionable_to,
                    json_dumps(required_resources),
                    json_dumps(capital_assumption),
                    operational_mode,
                ),
            )
            conn.execute(
                "INSERT INTO domain_record(artifact_state_id,stage,owner_authority,subject_identity_id,scope_json,record_state) VALUES(?,?,?,?,?,?)",
                (state.state_id, "EXECUTION_CONFIGURATION", "Execution Feasibility Authority", subject, json_dumps({"platform": platform_norm, "channel": channel, "live_channel_binding_state_id": live_channel_binding_state_id}), "DEFINED"),
            )
        self.ledger.add_provenance(opportunity_state_id, state.state_id, "EXECUTION_CONFIGURATION_FOR")
        self.ledger.add_provenance(eligibility_state_id, state.state_id, "EXECUTION_CONFIGURATION_ELIGIBILITY_GATE")
        if live_channel_binding_state_id:
            self.ledger.add_provenance(live_channel_binding_state_id, state.state_id, "EXECUTION_CONFIGURATION_CHANNEL_BINDING")
        self.ledger.bind_dependency(state.state_id, opportunity_state_id, "EXECUTION_CONFIGURATION_FOR", reassess, {"materiality": "opportunity semantic/config change"})
        self.ledger.bind_dependency(state.state_id, eligibility_state_id, "EXECUTION_CONFIGURATION_ELIGIBILITY_GATE", invalidate, {"materiality": "eligibility/currentness/policy change"})
        if live_channel_binding_state_id:
            self.ledger.bind_dependency(state.state_id, live_channel_binding_state_id, "EXECUTION_CONFIGURATION_CHANNEL_BINDING", invalidate, {"materiality": "channel/account/platform binding change requires new execution configuration and reauthorization"})
        return ArtifactRef(iid, state.state_id, state.version, state.raw_hash, state.canonical_hash)

    def assess_feasibility(self, execution_configuration_state_id: str, *, constraints: dict[str, Any], outcome: str, rationale: dict[str, Any]) -> ArtifactRef:
        if outcome not in {"FEASIBLE", "FEASIBLE_WITH_CONSTRAINTS", "NOT_FEASIBLE", "UNRESOLVED"}:
            raise LedgerError("invalid feasibility outcome")
        cfg = self.ledger.get_state(execution_configuration_state_id)
        policy = self.ledger.get_dependency_policy("UPSTREAM_REQUIRES_REASSESSMENT", 1)
        if cfg["state_type"] != "EXECUTION_CONFIGURATION":
            raise LedgerError("requires EXECUTION_CONFIGURATION")
        result = self.ledger.record_domain(
            "FEASIBILITY_ASSESSMENT",
            "Execution Feasibility Authority",
            {"execution_configuration_state_id": execution_configuration_state_id, "constraints": constraints, "outcome": outcome, "rationale": rationale},
            natural_key=f"feas:{execution_configuration_state_id}:{outcome}",
            subject_identity_id=self.ledger.subject_identity_for_state(execution_configuration_state_id),
            record_state=outcome,
            upstream_states=[(execution_configuration_state_id, "FEASIBILITY_CONFIGURATION")],
        )
        self.ledger.bind_dependency(result.state_id, execution_configuration_state_id, "FEASIBILITY_CONFIGURATION", policy, {"materiality": "execution scenario change"})
        return result

from __future__ import annotations

import math
from typing import Any

from .ledger import GovernanceLedger, LedgerError
from .db import connect, tx
from .util import json_dumps, utcnow


class OperationsService:
    def __init__(self, ledger: GovernanceLedger):
        self.ledger = ledger

    def _domain_row(self, state_id: str):
        with connect(self.ledger.db_path) as conn:
            return conn.execute("SELECT * FROM domain_record WHERE artifact_state_id=?", (state_id,)).fetchone()

    def _assert_current_channel_binding(self, channel_binding_state_id: str) -> dict[str, Any]:
        state = self.ledger.get_state(channel_binding_state_id)
        if state["state_type"] != "LIVE_CHANNEL_BINDING" or state["payload"].get("status") != "ACTIVE":
            raise LedgerError("Exact live channel binding is not ACTIVE")
        with connect(self.ledger.db_path) as conn:
            latest = conn.execute(
                """SELECT s.id FROM artifact_state s
                   JOIN domain_record d ON d.artifact_state_id=s.id
                   WHERE s.identity_id=? AND d.stage='LIVE_CHANNEL_BINDING'
                   ORDER BY s.version DESC LIMIT 1""",
                (state["identity_id"],),
            ).fetchone()
        if not latest or latest["id"] != channel_binding_state_id:
            raise LedgerError("Exact live channel binding is stale/superseded; reauthorization required")
        return state

    @staticmethod
    def _payload_value(payload: dict[str, Any], path: str | None):
        if not path:
            return payload
        cur: Any = payload
        for part in path.split("."):
            if not isinstance(cur, dict) or part not in cur:
                return None
            cur = cur[part]
        return cur

    def _assert_current_domain_state(self, state_id: str, *, expected_stage: str | None = None) -> dict[str, Any]:
        state = self.ledger.get_state(state_id)
        with connect(self.ledger.db_path) as conn:
            if expected_stage:
                dr = conn.execute("SELECT stage FROM domain_record WHERE artifact_state_id=?", (state_id,)).fetchone()
                if not dr or dr["stage"] != expected_stage:
                    raise LedgerError(f"State is not expected governed stage: {expected_stage}")
            latest = conn.execute(
                "SELECT id FROM artifact_state WHERE identity_id=? ORDER BY version DESC LIMIT 1",
                (state["identity_id"],),
            ).fetchone()
        if not latest or latest["id"] != state_id:
            raise LedgerError("Governed state is stale/superseded; fresh review/authorization required")
        return state

    def _assert_authorized_recommendation_chain(self, recommendation_state_id: str, creative_state_id: str) -> dict[str, Any]:
        rec = self._assert_current_domain_state(recommendation_state_id, expected_stage="PUBLICATION_RECOMMENDATION")
        payload = rec.get("payload") or {}
        if payload.get("fixture") is True and payload.get("recommendation") == "RECOMMEND_PUBLISH_FIXTURE_ONLY":
            # Backward-compatible structural fixture path. It is never a real C1 recommendation.
            return rec
        if payload.get("recommendation") != "RECOMMEND_PUBLISH":
            raise LedgerError("Human AUTHORIZED decision is only valid for RECOMMEND_PUBLISH")
        if payload.get("creative_state_id") != creative_state_id:
            raise LedgerError("Recommendation is not bound to the exact creative state")
        comp_id = str(payload.get("compliance_state_id") or "")
        elig_id = str(payload.get("eligibility_state_id") or "")
        if not comp_id or not elig_id:
            raise LedgerError("Recommendation lacks exact compliance/eligibility bindings")
        comp = self._assert_current_domain_state(comp_id, expected_stage="COMPLIANCE_ASSESSMENT")
        elig = self._assert_current_domain_state(elig_id, expected_stage="ELIGIBILITY_ASSESSMENT")
        if comp["payload"].get("creative_state_id") != creative_state_id or comp["payload"].get("eligibility_state_id") != elig_id:
            raise LedgerError("Recommendation compliance chain does not match exact creative/eligibility states")
        if comp["payload"].get("gate_decision") != "PASS" or elig["payload"].get("outcome") != "ELIGIBLE":
            raise LedgerError("Recommendation chain is no longer publishable")
        subject = self.ledger.subject_identity_for_state(creative_state_id)
        if self.ledger.subject_identity_for_state(comp_id) != subject or self.ledger.subject_identity_for_state(elig_id) != subject:
            raise LedgerError("Recommendation chain crosses governed subjects")
        return rec

    def _authorization_covers_creative(self, authorization_state_id: str, creative_state_id: str) -> bool:
        auth = self.ledger.get_state(authorization_state_id)
        if auth["state_type"] != "HUMAN_AUTHORIZATION":
            return False
        if auth["payload"].get("creative_state_id") == creative_state_id:
            return True
        with connect(self.ledger.db_path) as conn:
            row = conn.execute(
                """SELECT 1
                   FROM provenance_edge auth_edge
                   JOIN provenance_edge content_edge ON content_edge.to_state_id=auth_edge.from_state_id
                   WHERE auth_edge.to_state_id=?
                     AND auth_edge.edge_type='HUMAN_AUTHORIZATION_TARGET'
                     AND content_edge.from_state_id=?
                     AND content_edge.edge_type='RECOMMENDATION_CONTENT'
                   LIMIT 1""",
                (authorization_state_id, creative_state_id),
            ).fetchone()
            return bool(row)

    def _append_operator_provenance(self, result_state_id: str, auth_context: dict[str, Any] | None, edge_type: str = "AUTHORIZED_OPERATOR_BINDING") -> None:
        if not auth_context:
            return
        binding_state_id = auth_context.get("governed_operator_binding_state_id")
        if binding_state_id:
            self.ledger.get_state(str(binding_state_id))
            self.ledger.add_provenance(str(binding_state_id), result_state_id, edge_type)

    def _validate_authenticated_auth_context(
        self,
        auth_context: dict[str, Any] | None,
        *,
        required_role: str,
        required_scope: str,
    ) -> dict[str, Any] | None:
        """Validate material-action authorization provenance at the service boundary.

        API middleware already resolves a signed token against the current governed operator binding,
        but material services must not blindly trust a caller-supplied auth_context.  When an
        authenticated context is supplied, the exact bound state, subject, role, scope, currentness,
        and token supersession boundary are revalidated before a governed action is recorded.
        Structural/local calls may omit auth_context entirely; operational API paths do not.
        """
        if not auth_context:
            return None
        if not auth_context.get("authenticated"):
            raise LedgerError("Authenticated execution context is malformed")
        binding_state_id = str(auth_context.get("governed_operator_binding_state_id") or "")
        subject = str(auth_context.get("subject") or "").strip()
        if not binding_state_id or not subject:
            raise LedgerError("Authenticated execution context lacks exact governed operator binding/subject")
        if auth_context.get("authorized_role") != required_role:
            raise LedgerError(f"Authenticated execution context does not authorize required role: {required_role}")
        if auth_context.get("authorized_scope") != required_scope:
            raise LedgerError(f"Authenticated execution context does not authorize required scope: {required_scope}")

        binding = self.ledger.get_state(binding_state_id)
        if binding["state_type"] != "OPERATOR_IDENTITY_BINDING":
            raise LedgerError("Execution authorization provenance does not reference OPERATOR_IDENTITY_BINDING")
        payload = binding["payload"]
        if payload.get("status") != "ACTIVE" or str(payload.get("subject") or "") != subject:
            raise LedgerError("Execution authorization provenance does not match an ACTIVE governed subject binding")

        # Exact-state currentness: a superseded binding may not authorize a new material action.
        with connect(self.ledger.db_path) as conn:
            latest = conn.execute(
                """SELECT s.id FROM artifact_state s
                   JOIN artifact_identity i ON i.id=s.identity_id
                   JOIN domain_record d ON d.artifact_state_id=s.id
                   WHERE i.id=? AND d.stage='OPERATOR_IDENTITY_BINDING'
                   ORDER BY s.version DESC LIMIT 1""",
                (binding["identity_id"],),
            ).fetchone()
        if not latest or latest["id"] != binding_state_id:
            raise LedgerError("Execution authorization provenance references a stale/superseded operator binding")

        roles = {str(x) for x in payload.get("roles") or []}
        scopes = {str(x) for x in payload.get("scopes") or []}
        if required_role not in roles and "admin" not in roles:
            raise LedgerError(f"Governed operator binding does not authorize required role: {required_role}")
        if required_scope not in scopes and "*" not in scopes:
            raise LedgerError(f"Governed operator binding does not authorize required scope: {required_scope}")

        issued_at = int(auth_context.get("issued_at") or 0)
        token_not_before = int(payload.get("token_not_before_epoch") or 0)
        if issued_at and issued_at < token_not_before:
            raise LedgerError("Authenticated execution context predates the current operator-binding token boundary")
        return auth_context

    def record_human_authorization(
        self,
        recommendation_state_id: str,
        authorizer: str,
        decision: str,
        *,
        notes: str = "",
        auth_context: dict[str, Any] | None = None,
        execution_configuration_state_id: str | None = None,
        channel_binding_state_id: str | None = None,
        media_descriptor_state_id: str | None = None,
        require_exact_channel: bool = False,
        require_exact_media: bool = False,
    ):
        if auth_context is not None:
            self._validate_authenticated_auth_context(auth_context, required_role="publisher_authorizer", required_scope="publication:authorize")
            if str(auth_context.get("subject") or "").strip() != str(authorizer or "").strip():
                raise LedgerError("Human authorization authorizer must match the authenticated governed subject")
        if decision not in {"AUTHORIZED", "REJECTED", "REVISE"}:
            raise LedgerError("Invalid human authorization decision")
        rec = self.ledger.get_state(recommendation_state_id)
        dr = self._domain_row(recommendation_state_id)
        if not dr or dr["stage"] != "PUBLICATION_RECOMMENDATION":
            raise LedgerError("Target is not a publication recommendation")
        subject_id = dr["subject_identity_id"]
        creative_state_id = rec["payload"].get("creative_state_id")
        if not creative_state_id:
            with connect(self.ledger.db_path) as conn:
                edge = conn.execute(
                    "SELECT from_state_id FROM provenance_edge WHERE to_state_id=? AND edge_type='RECOMMENDATION_CONTENT' ORDER BY created_at DESC LIMIT 1",
                    (recommendation_state_id,),
                ).fetchone()
            creative_state_id = edge["from_state_id"] if edge else None
        if not creative_state_id:
            raise LedgerError("Publication recommendation does not bind an exact creative state")
        if decision == "AUTHORIZED":
            self._assert_authorized_recommendation_chain(recommendation_state_id, creative_state_id)

        channel_state = None
        if require_exact_channel and (not execution_configuration_state_id or not channel_binding_state_id):
            raise LedgerError("Operational human publication authorization requires exact ExecutionConfiguration and LIVE_CHANNEL_BINDING states")
        if require_exact_media and not media_descriptor_state_id:
            raise LedgerError("C1 publication authorization requires an exact publication media descriptor")
        if execution_configuration_state_id:
            cfg = self.ledger.get_state(execution_configuration_state_id)
            if cfg["state_type"] != "EXECUTION_CONFIGURATION":
                raise LedgerError("execution_configuration_state_id is not EXECUTION_CONFIGURATION")
            if self.ledger.subject_identity_for_state(execution_configuration_state_id) != subject_id:
                raise LedgerError("Human authorization execution configuration belongs to a different governed subject")
            cfg_channel_binding = cfg["payload"].get("live_channel_binding_state_id")
            if channel_binding_state_id and cfg_channel_binding != channel_binding_state_id:
                raise LedgerError("Human authorization channel binding does not match exact ExecutionConfiguration channel state")
        if channel_binding_state_id:
            channel_state = self._assert_current_channel_binding(channel_binding_state_id)

        media_state = None
        if media_descriptor_state_id:
            media_state = self.ledger.get_state(media_descriptor_state_id)
            if media_state["state_type"] != "PUBLICATION_MEDIA_DESCRIPTOR":
                raise LedgerError("media_descriptor_state_id is not PUBLICATION_MEDIA_DESCRIPTOR")
            if media_state["payload"].get("creative_state_id") != creative_state_id:
                raise LedgerError("Human authorization media descriptor does not bind the exact creative state")
            if self.ledger.subject_identity_for_state(media_descriptor_state_id) != subject_id:
                raise LedgerError("Human authorization media descriptor belongs to a different governed subject")

        upstream = [(recommendation_state_id, "HUMAN_AUTHORIZATION_TARGET"), (creative_state_id, "HUMAN_AUTHORIZATION_EXACT_CONTENT")]
        if execution_configuration_state_id:
            upstream.append((execution_configuration_state_id, "HUMAN_AUTHORIZATION_EXECUTION_CONFIGURATION"))
        if channel_binding_state_id:
            upstream.append((channel_binding_state_id, "HUMAN_AUTHORIZATION_EXACT_CHANNEL_BINDING"))
        if media_descriptor_state_id:
            upstream.append((media_descriptor_state_id, "HUMAN_AUTHORIZATION_EXACT_MEDIA"))

        auth = self.ledger.record_domain(
            "HUMAN_AUTHORIZATION",
            "Human Final Publication Authority",
            {
                "recommendation_state_id": recommendation_state_id,
                "creative_state_id": creative_state_id,
                "execution_configuration_state_id": execution_configuration_state_id,
                "channel_binding_state_id": channel_binding_state_id,
                "channel_ref": channel_state["payload"].get("channel_ref") if channel_state else None,
                "platform": channel_state["payload"].get("platform") if channel_state else None,
                "media_descriptor_state_id": media_descriptor_state_id,
                "media_sha256": media_state["payload"].get("sha256") if media_state else None,
                "publication_metadata_sha256": media_state["payload"].get("publication_metadata_sha256") if media_state else None,
                "intended_privacy_status": media_state["payload"].get("intended_privacy_status") if media_state else None,
                "decision": decision,
                "authorizer": authorizer,
                "identity_assurance": auth_context or {"authenticated": False, "mode": "STRUCTURAL_ONLY"},
                "notes": notes,
                "recorded_at": utcnow(),
                "exact_recommendation_version_bound": True,
                "exact_content_version_bound": True,
                "exact_channel_state_bound": bool(channel_binding_state_id),
                "exact_media_state_bound": bool(media_descriptor_state_id),
            },
            natural_key=f"human-auth:{recommendation_state_id}:{utcnow()}",
            subject_identity_id=subject_id,
            record_state=decision,
            upstream_states=upstream,
        )
        self._append_operator_provenance(auth.state_id, auth_context)
        return auth

    def record_commercial_authorization(
        self,
        monetization_configuration_state_id: str,
        authorizer: str,
        decision: str,
        *,
        notes: str = "",
        auth_context: dict[str, Any] | None = None,
    ):
        if auth_context is not None:
            self._validate_authenticated_auth_context(auth_context, required_role="commercial_authorizer", required_scope="commercial:authorize")
        if decision not in {"AUTHORIZED", "REJECTED"}:
            raise LedgerError("Invalid commercial authorization decision")
        cfg = self.ledger.get_state(monetization_configuration_state_id)
        if cfg["state_type"] != "MONETIZATION_CONFIGURATION":
            raise LedgerError("Target is not a monetization configuration")
        with connect(self.ledger.db_path) as conn:
            row = conn.execute("SELECT opportunity_identity_id FROM monetization_configuration WHERE artifact_state_id=?", (monetization_configuration_state_id,)).fetchone()
        auth = self.ledger.record_domain(
            "HUMAN_COMMERCIAL_AUTHORIZATION",
            "Human Commercial Authority",
            {
                "monetization_configuration_state_id": monetization_configuration_state_id,
                "decision": decision,
                "authorizer": authorizer,
                "identity_assurance": auth_context or {"authenticated": False, "mode": "STRUCTURAL_ONLY"},
                "notes": notes,
                "exact_configuration_state_bound": True,
            },
            natural_key=f"commercial-auth:{monetization_configuration_state_id}:{utcnow()}",
            subject_identity_id=row["opportunity_identity_id"] if row else cfg["identity_id"],
            record_state=decision,
            upstream_states=[(monetization_configuration_state_id, "COMMERCIAL_AUTHORIZATION_TARGET")],
        )
        self._append_operator_provenance(auth.state_id, auth_context)
        return auth

    def activate_monetization(
        self,
        monetization_configuration_state_id: str,
        *,
        dependency_state_ids: list[str],
        provider_result_ref: str | None = None,
        auth_context: dict[str, Any] | None = None,
    ):
        if auth_context is not None:
            self._validate_authenticated_auth_context(auth_context, required_role="commercial_operator", required_scope="monetization:activate")
        self.ledger.get_state(monetization_configuration_state_id)
        with connect(self.ledger.db_path) as conn:
            row = conn.execute("SELECT * FROM monetization_configuration WHERE artifact_state_id=?", (monetization_configuration_state_id,)).fetchone()
            requirements = conn.execute(
                "SELECT * FROM monetization_activation_requirement WHERE monetization_configuration_state_id=? ORDER BY requirement_key",
                (monetization_configuration_state_id,),
            ).fetchall()
        if not row:
            raise LedgerError("Unknown monetization configuration")
        if row["lifecycle_state"] != "READY_FOR_ACTIVATION":
            raise LedgerError("Monetization configuration is not READY_FOR_ACTIVATION")
        dep_states = {sid: self.ledger.get_state(sid) for sid in dependency_state_ids}

        satisfied_by: dict[str, str] = {}
        for req in requirements:
            if not req["required"]:
                continue
            accepted = set(__import__("json").loads(req["accepted_values_json"]))
            matched = None
            for sid, state in dep_states.items():
                if state["state_type"] != req["required_state_type"]:
                    continue
                value = self._payload_value(state["payload"], req["payload_path"])
                expected = {monetization_configuration_state_id if x == "__CONFIG_STATE_ID__" else x for x in accepted}
                if not expected or value in expected:
                    matched = sid
                    break
            if matched is None:
                raise LedgerError(f"Required activation dependency not satisfied: {req['requirement_key']}")
            satisfied_by[req["requirement_key"]] = matched

        creative_sid = satisfied_by.get("EXACT_CREATIVE_BINDING")
        human_sid = satisfied_by.get("HUMAN_PUBLICATION_AUTHORIZATION")
        if creative_sid and human_sid and not self._authorization_covers_creative(human_sid, creative_sid):
            raise LedgerError("Human publication authorization is not bound to the exact creative artifact used for activation")
        if human_sid:
            human = self.ledger.get_state(human_sid)
            if human["payload"].get("channel_binding_state_id"):
                self._assert_current_channel_binding(human["payload"]["channel_binding_state_id"])

        with connect(self.ledger.db_path) as conn:
            for key, sid in satisfied_by.items():
                dr = conn.execute("SELECT subject_identity_id FROM domain_record WHERE artifact_state_id=?", (sid,)).fetchone()
                if dr and dr["subject_identity_id"] and dr["subject_identity_id"] != row["opportunity_identity_id"]:
                    raise LedgerError(f"Activation dependency {key} belongs to a different governed subject")

        identity = self.ledger.get_or_create_identity("MONETIZATION_ACTIVATION", f"activation:{monetization_configuration_state_id}")
        payload = {
            "monetization_configuration_state_id": monetization_configuration_state_id,
            "activation_state": "ACTIVE",
            "activated_at": utcnow(),
            "provider_result_ref": provider_result_ref,
            "dependency_state_ids": dependency_state_ids,
            "requirements_satisfied_by": satisfied_by,
            "execution_actor_authorization": auth_context or {"authenticated": False, "mode": "STRUCTURAL_ONLY"},
        }
        state = self.ledger.create_state(identity, "MONETIZATION_ACTIVATION", payload, effective_from=payload["activated_at"])
        with tx(self.ledger.db_path) as conn:
            conn.execute(
                "INSERT INTO monetization_activation_record(artifact_state_id,monetization_configuration_state_id,activation_state,activated_at,provider_result_ref,dependency_snapshot_json) VALUES(?,?,?,?,?,?)",
                (state.state_id, monetization_configuration_state_id, "ACTIVE", payload["activated_at"], provider_result_ref, json_dumps(payload["requirements_satisfied_by"])),
            )
            conn.execute(
                "INSERT INTO domain_record(artifact_state_id,stage,owner_authority,subject_identity_id,scope_json,record_state) VALUES(?,?,?,?,?,?)",
                (state.state_id, "MONETIZATION_ACTIVATION", "MCAA", row["opportunity_identity_id"], "{}", "ACTIVE"),
            )
        self.ledger.add_provenance(monetization_configuration_state_id, state.state_id, "ACTIVATES_CONFIGURATION")
        self._append_operator_provenance(state.state_id, auth_context)
        reconcile_policy = self.ledger.get_dependency_policy("UPSTREAM_REQUIRES_RECONCILIATION", 1)
        for key, sid in satisfied_by.items():
            self.ledger.add_provenance(sid, state.state_id, f"ACTIVATION_DEPENDENCY:{key}")
            self.ledger.bind_dependency(state.state_id, sid, f"ACTIVATION_DEPENDENCY:{key}", reconcile_policy, {"requirement_key": key})
        return state

    def _assert_latest_human_authorization(self, authorization_state_id: str, recommendation_state_id: str) -> dict[str, Any]:
        auth = self.ledger.get_state(authorization_state_id)
        with connect(self.ledger.db_path) as conn:
            latest = conn.execute(
                """SELECT s.id FROM provenance_edge p
                   JOIN artifact_state s ON s.id=p.to_state_id
                   JOIN domain_record d ON d.artifact_state_id=s.id
                   WHERE p.from_state_id=?
                     AND p.edge_type='HUMAN_AUTHORIZATION_TARGET'
                     AND d.stage='HUMAN_AUTHORIZATION'
                   ORDER BY s.recorded_at DESC, s.version DESC LIMIT 1""",
                (recommendation_state_id,),
            ).fetchone()
        if not latest or latest["id"] != authorization_state_id:
            raise LedgerError("Human authorization is stale/superseded by a newer decision")
        if auth["payload"].get("decision") != "AUTHORIZED":
            raise LedgerError("Latest human publication decision is not AUTHORIZED")
        return auth

    def validate_publication_execution_gate(
        self,
        creative_state_id: str,
        authorization_state_id: str,
        *,
        channel_binding_state_id: str | None = None,
        monetization_activation_state_id: str | None = None,
        require_bound_channel: bool = False,
        auth_context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Side-effect-free revalidation immediately before an external publication attempt.

        The definitive record_publication_execution call repeats these checks after provider response;
        this preflight exists to avoid performing a provider side effect when a gate is already stale.
        """
        if auth_context is not None:
            self._validate_authenticated_auth_context(auth_context, required_role="publication_operator", required_scope="publication:execute")
        creative = self.ledger.get_state(creative_state_id)
        auth = self.ledger.get_state(authorization_state_id)
        if creative["state_type"] != "CREATIVE_ARTIFACT":
            raise LedgerError("creative_state_id is not a creative artifact")
        if auth["state_type"] != "HUMAN_AUTHORIZATION" or auth["payload"].get("decision") != "AUTHORIZED":
            raise LedgerError("Valid human authorization required")
        if not self._authorization_covers_creative(authorization_state_id, creative_state_id):
            raise LedgerError("Human authorization is not bound to this exact creative artifact")
        recommendation_state_id = str(auth["payload"].get("recommendation_state_id") or "")
        if not recommendation_state_id:
            raise LedgerError("Human authorization lacks exact recommendation binding")
        self._assert_latest_human_authorization(authorization_state_id, recommendation_state_id)
        self._assert_authorized_recommendation_chain(recommendation_state_id, creative_state_id)
        auth_channel_state_id = auth["payload"].get("channel_binding_state_id")
        channel_state = None
        if require_bound_channel and not channel_binding_state_id:
            raise LedgerError("Operational publication requires exact channel_binding_state_id")
        if channel_binding_state_id:
            if auth_channel_state_id != channel_binding_state_id:
                raise LedgerError("Publication channel binding does not match exact human-authorized channel binding")
            channel_state = self._assert_current_channel_binding(channel_binding_state_id)
            exec_cfg_id = auth["payload"].get("execution_configuration_state_id")
            if exec_cfg_id:
                cfg = self.ledger.get_state(exec_cfg_id)
                if cfg["payload"].get("live_channel_binding_state_id") != channel_binding_state_id:
                    raise LedgerError("Publication channel binding does not match exact ExecutionConfiguration channel binding")
        elif require_bound_channel:
            raise LedgerError("Publication channel binding is required")
        if monetization_activation_state_id:
            act = self.ledger.get_state(monetization_activation_state_id)
            if act["state_type"] != "MONETIZATION_ACTIVATION" or act["payload"].get("activation_state") != "ACTIVE":
                raise LedgerError("Provided monetization activation is not ACTIVE")
            creative_cfg = creative["payload"].get("monetization_configuration_state_id")
            if creative_cfg and act["payload"].get("monetization_configuration_state_id") != creative_cfg:
                raise LedgerError("Monetization activation is not bound to the creative artifact's exact configuration")
        return {
            "creative": creative,
            "authorization": auth,
            "recommendation_state_id": recommendation_state_id,
            "channel_state": channel_state,
            "execution_configuration_state_id": auth["payload"].get("execution_configuration_state_id"),
        }

    def record_publication_execution(
        self,
        creative_state_id: str,
        authorization_state_id: str,
        *,
        channel: str | None = None,
        channel_binding_state_id: str | None = None,
        external_result_ref: str,
        monetization_activation_state_id: str | None = None,
        require_bound_channel: bool = False,
        auth_context: dict[str, Any] | None = None,
    ):
        if auth_context is not None:
            self._validate_authenticated_auth_context(auth_context, required_role="publication_operator", required_scope="publication:execute")
        creative = self.ledger.get_state(creative_state_id)
        auth = self.ledger.get_state(authorization_state_id)
        if creative["state_type"] != "CREATIVE_ARTIFACT":
            raise LedgerError("creative_state_id is not a creative artifact")
        if auth["state_type"] != "HUMAN_AUTHORIZATION" or auth["payload"].get("decision") != "AUTHORIZED":
            raise LedgerError("Valid human authorization required")
        if not self._authorization_covers_creative(authorization_state_id, creative_state_id):
            raise LedgerError("Human authorization is not bound to this exact creative artifact")
        recommendation_state_id = str(auth["payload"].get("recommendation_state_id") or "")
        if not recommendation_state_id:
            raise LedgerError("Human authorization lacks exact recommendation binding")
        self._assert_latest_human_authorization(authorization_state_id, recommendation_state_id)
        self._assert_authorized_recommendation_chain(recommendation_state_id, creative_state_id)

        channel_state = None
        auth_channel_state_id = auth["payload"].get("channel_binding_state_id")
        if require_bound_channel and not channel_binding_state_id:
            raise LedgerError("Operational publication requires exact channel_binding_state_id")
        if channel_binding_state_id:
            if auth_channel_state_id != channel_binding_state_id:
                raise LedgerError("Publication channel binding does not match exact human-authorized channel binding")
            channel_state = self._assert_current_channel_binding(channel_binding_state_id)
            channel = channel_state["payload"].get("channel_ref")
            exec_cfg_id = auth["payload"].get("execution_configuration_state_id")
            if exec_cfg_id:
                cfg = self.ledger.get_state(exec_cfg_id)
                if cfg["payload"].get("live_channel_binding_state_id") != channel_binding_state_id:
                    raise LedgerError("Publication channel binding does not match exact ExecutionConfiguration channel binding")
        elif require_bound_channel:
            raise LedgerError("Publication channel binding is required")

        if monetization_activation_state_id:
            act = self.ledger.get_state(monetization_activation_state_id)
            if act["state_type"] != "MONETIZATION_ACTIVATION" or act["payload"].get("activation_state") != "ACTIVE":
                raise LedgerError("Provided monetization activation is not ACTIVE")
            creative_cfg = creative["payload"].get("monetization_configuration_state_id")
            if creative_cfg and act["payload"].get("monetization_configuration_state_id") != creative_cfg:
                raise LedgerError("Monetization activation is not bound to the creative artifact's exact configuration")
        with connect(self.ledger.db_path) as conn:
            dr = conn.execute("SELECT * FROM domain_record WHERE artifact_state_id=?", (creative_state_id,)).fetchone()
        upstream = [(creative_state_id, "EXECUTED_CONTENT"), (authorization_state_id, "EXECUTION_AUTHORIZATION")]
        if channel_binding_state_id:
            upstream.append((channel_binding_state_id, "EXECUTION_EXACT_CHANNEL_BINDING"))
        exec_cfg_id = auth["payload"].get("execution_configuration_state_id")
        if exec_cfg_id:
            upstream.append((exec_cfg_id, "EXECUTION_CONFIGURATION_AUTHORIZED"))
        if monetization_activation_state_id:
            upstream.append((monetization_activation_state_id, "EXECUTION_MONETIZATION_ACTIVATION"))
        execution = self.ledger.record_domain(
            "PUBLICATION_EXECUTION",
            "Execution / Publication Records",
            {
                "creative_state_id": creative_state_id,
                "authorization_state_id": authorization_state_id,
                "execution_configuration_state_id": exec_cfg_id,
                "channel_binding_state_id": channel_binding_state_id,
                "channel": channel,
                "platform": channel_state["payload"].get("platform") if channel_state else None,
                "external_result_ref": external_result_ref,
                "monetization_activation_state_id": monetization_activation_state_id,
                "executed_at": utcnow(),
                "execution_actor_authorization": auth_context or {"authenticated": False, "mode": "STRUCTURAL_ONLY"},
            },
            natural_key=f"publication:{external_result_ref}",
            subject_identity_id=dr["subject_identity_id"] if dr else None,
            record_state="EXECUTED",
            upstream_states=upstream,
        )
        self._append_operator_provenance(execution.state_id, auth_context)
        return execution

    def bind_economic_evidence_source(
        self,
        *,
        connector: str,
        source_name: str,
        allowed_roles: list[str],
        allowed_currencies: list[str] | None = None,
        status: str = "ACTIVE",
        auth_context: dict[str, Any] | None = None,
    ):
        """Bind an external source class to a narrowly governed economic-evidence authority.

        A non-manual connector name is not, by itself, financial authority.  This binding is
        intentionally separate from SOURCE_RECORD ingestion so that an observed source cannot
        self-promote into proof of revenue/cost merely by choosing a plausible connector name.
        """
        if auth_context is not None:
            self._validate_authenticated_auth_context(
                auth_context,
                required_role="finance_operator",
                required_scope="economics:bind_source",
            )
        connector_norm = str(connector or "").strip().lower()
        source_name_norm = str(source_name or "").strip()
        if not connector_norm or not source_name_norm:
            raise LedgerError("Economic evidence source binding requires connector and source_name")
        if connector_norm in {"manual", "manual_api", "manual_json", "synthetic"}:
            raise LedgerError("Manual/synthetic connectors cannot be granted economic evidence authority")

        roles = sorted({str(x or "").strip().upper() for x in allowed_roles if str(x or "").strip()})
        if not roles or any(role not in {"REVENUE", "COST"} for role in roles):
            raise LedgerError("Economic evidence source binding roles must be a non-empty subset of REVENUE/COST")

        currencies = sorted({str(x or "").strip().upper() for x in (allowed_currencies or []) if str(x or "").strip()})
        if any(len(code) != 3 or not code.isalpha() or not code.isascii() for code in currencies):
            raise LedgerError("Economic evidence source binding currencies must use 3-letter alphabetic codes")
        status_norm = str(status or "").strip().upper()
        if status_norm not in {"ACTIVE", "REVOKED"}:
            raise LedgerError("Economic evidence source binding status must be ACTIVE or REVOKED")

        binding = self.ledger.record_domain(
            "ECONOMIC_EVIDENCE_SOURCE_BINDING",
            "Economic Evidence Source Authority",
            {
                "binding_contract": "C1_ECONOMIC_EVIDENCE_SOURCE_BINDING@V1",
                "connector": connector_norm,
                "source_name": source_name_norm,
                "allowed_roles": roles,
                "allowed_currencies": currencies,
                "currency_scope": "ANY_EXPLICIT_CURRENCY" if not currencies else "EXACT_ALLOWLIST",
                "status": status_norm,
                "generic_nonmanual_source_is_not_authority": True,
                "synthetic_or_manual_source_forbidden": True,
            },
            natural_key=f"economic-evidence-source:{connector_norm}:{source_name_norm}",
            record_state=status_norm,
        )
        self._append_operator_provenance(binding.state_id, auth_context)
        return binding

    def record_economic_outcome(
        self,
        publication_state_id: str,
        *,
        performance: dict[str, Any],
        revenue: dict[str, Any],
        costs: list[dict[str, Any]],
        attribution: dict[str, Any],
        evidence_state_ids: list[str] | None = None,
        auth_context: dict[str, Any] | None = None,
    ):
        if auth_context is not None:
            self._validate_authenticated_auth_context(auth_context, required_role="finance_operator", required_scope="economics:record")
        pub = self.ledger.get_state(publication_state_id)
        if pub["state_type"] != "PUBLICATION_EXECUTION":
            raise LedgerError("Outcome target must be publication execution")

        def finite_amount(value: Any, label: str) -> float:
            try:
                amount = float(value)
            except (TypeError, ValueError) as exc:
                raise LedgerError(f"{label} amount must be numeric") from exc
            if not math.isfinite(amount):
                raise LedgerError(f"{label} amount must be finite")
            return amount

        rev_amount = finite_amount(revenue.get("amount"), "revenue")
        revenue_currency = str(revenue.get("currency") or "").strip().upper() or None
        normalized_costs: list[dict[str, Any]] = []
        totals_by_currency: dict[str, float] = {}
        missing_cost_currency = False
        for i, item in enumerate(costs):
            amount = finite_amount(item.get("amount"), f"cost[{i}]")
            currency = str(item.get("currency") or "").strip().upper() or None
            if currency is None:
                missing_cost_currency = True
            else:
                totals_by_currency[currency] = totals_by_currency.get(currency, 0.0) + amount
            normalized_costs.append({**item, "amount": amount, "currency": currency})

        evidence_state_ids = list(dict.fromkeys(evidence_state_ids or []))
        evidence_details: list[dict[str, Any]] = []
        evidence_blockers: list[str] = []
        verified_revenue_evidence: list[tuple[float, str]] = []
        verified_cost_evidence: list[tuple[float, str]] = []

        def is_synthetic_payload(payload: dict[str, Any]) -> bool:
            nested = payload.get("payload")
            return payload.get("fixture") is True or (isinstance(nested, dict) and nested.get("fixture") is True)

        for sid in evidence_state_ids:
            try:
                st = self.ledger.get_state(sid)
            except LedgerError:
                evidence_details.append({"state_id": sid, "verified": False, "reason": "ECONOMIC_EVIDENCE_MISSING_OR_STALE"})
                evidence_blockers.append("INSUFFICIENT_STALE_EVIDENCE")
                continue
            payload = st.get("payload") or {}
            detail: dict[str, Any] = {"state_id": sid, "state_type": st["state_type"]}
            if st["state_type"] != "EVIDENCE":
                detail.update({"verified": False, "reason": "ECONOMIC_EVIDENCE_MUST_BE_TYPED_EVIDENCE"})
                evidence_details.append(detail)
                evidence_blockers.append("INSUFFICIENT_UNTYPED_EVIDENCE")
                continue
            if is_synthetic_payload(payload):
                detail.update({"verified": False, "reason": "SYNTHETIC_EVIDENCE"})
                evidence_details.append(detail)
                evidence_blockers.append("SYNTHETIC_CONTAMINATION")
                continue
            try:
                self._assert_current_domain_state(sid, expected_stage="EVIDENCE")
            except LedgerError:
                detail.update({"verified": False, "reason": "ECONOMIC_EVIDENCE_MISSING_OR_STALE"})
                evidence_details.append(detail)
                evidence_blockers.append("INSUFFICIENT_STALE_EVIDENCE")
                continue
            evidence_row = self._domain_row(sid)
            if not evidence_row or evidence_row["record_state"] != "VERIFIED":
                detail.update({"verified": False, "reason": "ECONOMIC_EVIDENCE_RECORD_NOT_VERIFIED"})
                evidence_details.append(detail)
                evidence_blockers.append("INSUFFICIENT_UNVERIFIED_EVIDENCE_STATE")
                continue

            source_state_id = str(payload.get("source_state_id") or "").strip()
            source_binding_state_id = str(payload.get("economic_source_binding_state_id") or "").strip()
            role = str(payload.get("economic_role") or "").strip().upper()
            verification_status = str(payload.get("verification_status") or "").strip().upper()
            bound_publication = str(payload.get("publication_state_id") or "").strip()
            if not source_state_id or not source_binding_state_id or role not in {"REVENUE", "COST"} or verification_status != "EXTERNAL_SOURCE_BOUND" or bound_publication != publication_state_id:
                detail.update({"verified": False, "reason": "ECONOMIC_EVIDENCE_CONTRACT_INCOMPLETE_OR_WRONG_PUBLICATION"})
                evidence_details.append(detail)
                evidence_blockers.append("INSUFFICIENT_EVIDENCE_CONTRACT")
                continue

            try:
                source = self.ledger.get_state(source_state_id)
            except LedgerError:
                detail.update({"verified": False, "reason": "ECONOMIC_EVIDENCE_SOURCE_MISSING_OR_STALE"})
                evidence_details.append(detail)
                evidence_blockers.append("INSUFFICIENT_EVIDENCE_SOURCE")
                continue
            source_payload = source.get("payload") or {}
            connector = str(source_payload.get("connector") or "").strip().lower()
            source_name = str(source_payload.get("source_name") or "").strip()
            if source["state_type"] != "SOURCE_RECORD" or is_synthetic_payload(source_payload) or connector in {"", "manual", "manual_api", "manual_json", "synthetic"}:
                detail.update({"verified": False, "reason": "ECONOMIC_EVIDENCE_SOURCE_NOT_INDEPENDENT", "connector": connector})
                evidence_details.append(detail)
                evidence_blockers.append("INSUFFICIENT_UNVERIFIED_SOURCE")
                continue
            try:
                self._assert_current_domain_state(source_state_id, expected_stage="SOURCE_RECORD")
            except LedgerError:
                detail.update({"verified": False, "reason": "ECONOMIC_EVIDENCE_SOURCE_MISSING_OR_STALE", "connector": connector})
                evidence_details.append(detail)
                evidence_blockers.append("INSUFFICIENT_EVIDENCE_SOURCE")
                continue

            try:
                binding = self._assert_current_domain_state(source_binding_state_id, expected_stage="ECONOMIC_EVIDENCE_SOURCE_BINDING")
            except LedgerError:
                detail.update({"verified": False, "reason": "ECONOMIC_EVIDENCE_SOURCE_BINDING_MISSING_OR_STALE", "connector": connector})
                evidence_details.append(detail)
                evidence_blockers.append("INSUFFICIENT_SOURCE_AUTHORITY")
                continue
            binding_payload = binding.get("payload") or {}
            if (
                binding_payload.get("binding_contract") != "C1_ECONOMIC_EVIDENCE_SOURCE_BINDING@V1"
                or binding_payload.get("status") != "ACTIVE"
                or str(binding_payload.get("connector") or "").strip().lower() != connector
                or str(binding_payload.get("source_name") or "").strip() != source_name
                or role not in {str(x).upper() for x in (binding_payload.get("allowed_roles") or [])}
            ):
                detail.update({"verified": False, "reason": "ECONOMIC_EVIDENCE_SOURCE_OUTSIDE_GOVERNED_AUTHORITY", "connector": connector, "source_binding_state_id": source_binding_state_id})
                evidence_details.append(detail)
                evidence_blockers.append("INSUFFICIENT_SOURCE_AUTHORITY")
                continue
            with connect(self.ledger.db_path) as conn:
                linked = conn.execute(
                    "SELECT 1 FROM provenance_edge WHERE from_state_id=? AND to_state_id=? AND edge_type='ECONOMIC_EVIDENCE_SOURCE'",
                    (source_state_id, sid),
                ).fetchone() is not None
                authority_linked = conn.execute(
                    "SELECT 1 FROM provenance_edge WHERE from_state_id=? AND to_state_id=? AND edge_type='ECONOMIC_EVIDENCE_SOURCE_AUTHORITY'",
                    (source_binding_state_id, sid),
                ).fetchone() is not None
            if not linked:
                detail.update({"verified": False, "reason": "ECONOMIC_EVIDENCE_SOURCE_LINK_MISSING", "connector": connector})
                evidence_details.append(detail)
                evidence_blockers.append("INSUFFICIENT_EVIDENCE_LINKAGE")
                continue
            if not authority_linked:
                detail.update({"verified": False, "reason": "ECONOMIC_EVIDENCE_SOURCE_AUTHORITY_LINK_MISSING", "connector": connector})
                evidence_details.append(detail)
                evidence_blockers.append("INSUFFICIENT_SOURCE_AUTHORITY")
                continue
            try:
                evidence_amount = finite_amount(payload.get("amount"), f"evidence[{sid}]")
            except LedgerError:
                detail.update({"verified": False, "reason": "ECONOMIC_EVIDENCE_AMOUNT_INVALID", "connector": connector})
                evidence_details.append(detail)
                evidence_blockers.append("INSUFFICIENT_EVIDENCE_VALUE")
                continue
            evidence_currency = str(payload.get("currency") or "").strip().upper()
            if not evidence_currency:
                detail.update({"verified": False, "reason": "ECONOMIC_EVIDENCE_CURRENCY_MISSING", "connector": connector})
                evidence_details.append(detail)
                evidence_blockers.append("INSUFFICIENT_EVIDENCE_VALUE")
                continue
            allowed_currencies = {str(x).upper() for x in (binding_payload.get("allowed_currencies") or [])}
            if allowed_currencies and evidence_currency not in allowed_currencies:
                detail.update({"verified": False, "reason": "ECONOMIC_EVIDENCE_CURRENCY_OUTSIDE_GOVERNED_AUTHORITY", "connector": connector, "currency": evidence_currency})
                evidence_details.append(detail)
                evidence_blockers.append("INSUFFICIENT_SOURCE_AUTHORITY")
                continue
            detail.update({"verified": True, "source_state_id": source_state_id, "source_binding_state_id": source_binding_state_id, "connector": connector, "economic_role": role, "amount": evidence_amount, "currency": evidence_currency})
            evidence_details.append(detail)
            (verified_revenue_evidence if role == "REVENUE" else verified_cost_evidence).append((evidence_amount, evidence_currency))

        expected_revenue_evidence = [(rev_amount, revenue_currency)] if revenue_currency else []
        expected_cost_evidence = sorted((item["amount"], item["currency"]) for item in normalized_costs if item["currency"] is not None)
        if not normalized_costs and revenue_currency:
            expected_cost_evidence = [(0.0, revenue_currency)]
        if sorted(verified_revenue_evidence) != sorted(expected_revenue_evidence):
            evidence_blockers.append("REVENUE_EVIDENCE_MISMATCH")
        if sorted(verified_cost_evidence) != expected_cost_evidence:
            evidence_blockers.append("COST_EVIDENCE_MISMATCH")

        evidence_blockers = list(dict.fromkeys(evidence_blockers))
        if not evidence_state_ids:
            evidence_status = "INSUFFICIENT_NO_EVIDENCE"
        elif "SYNTHETIC_CONTAMINATION" in evidence_blockers:
            evidence_status = "SYNTHETIC_CONTAMINATION"
        elif evidence_blockers:
            evidence_status = "INSUFFICIENT_OR_UNVERIFIED_EVIDENCE"
        else:
            evidence_status = "SYSTEM_EVIDENCE_BOUND"

        blockers: list[str] = []
        if evidence_status != "SYSTEM_EVIDENCE_BOUND":
            blockers.append(evidence_status)
            blockers.extend(evidence_blockers)
        if revenue_currency is None:
            blockers.append("REVENUE_CURRENCY_MISSING")
        if missing_cost_currency:
            blockers.append("COST_CURRENCY_MISSING")
        if len(totals_by_currency) > 1:
            blockers.append("MIXED_COST_CURRENCIES")
        if len(totals_by_currency) == 1 and revenue_currency and next(iter(totals_by_currency)) != revenue_currency:
            blockers.append("REVENUE_COST_CURRENCY_MISMATCH")

        comparable_cost_total = 0.0 if not costs else (next(iter(totals_by_currency.values())) if len(totals_by_currency) == 1 and not missing_cost_currency else None)
        profit = rev_amount - comparable_cost_total if not blockers and comparable_cost_total is not None else None
        realized_state = "DETERMINATE_EVIDENCE_BOUND" if profit is not None else "NOT_EVALUABLE"

        with connect(self.ledger.db_path) as conn:
            dr = conn.execute("SELECT * FROM domain_record WHERE artifact_state_id=?", (publication_state_id,)).fetchone()
        subject = dr["subject_identity_id"] if dr else None
        actor = auth_context or {"authenticated": False, "mode": "STRUCTURAL_ONLY"}
        evidence_upstream = [(sid, "ECONOMIC_EVIDENCE") for sid in evidence_state_ids]
        perf = self.ledger.record_domain(
            "PERFORMANCE_OBSERVATION", "Economic Outcome & Learning Authority",
            {"publication_state_id": publication_state_id, "performance": performance, "observed_at": utcnow(), "execution_actor_authorization": actor, "evidence_state_ids": evidence_state_ids},
            natural_key=f"performance:{publication_state_id}:{utcnow()}", subject_identity_id=subject, record_state="OBSERVED",
            upstream_states=[(publication_state_id, "PERFORMANCE_OF"), *evidence_upstream],
        )
        rev = self.ledger.record_domain(
            "REVENUE_OBSERVATION", "Economic Outcome & Learning Authority",
            {"publication_state_id": publication_state_id, "revenue": {**revenue, "amount": rev_amount, "currency": revenue_currency}, "attribution": attribution, "observed_at": utcnow(), "execution_actor_authorization": actor, "evidence_state_ids": evidence_state_ids},
            natural_key=f"revenue:{publication_state_id}:{utcnow()}", subject_identity_id=subject, record_state="OBSERVED",
            upstream_states=[(publication_state_id, "REVENUE_FROM"), *evidence_upstream],
        )
        cost = self.ledger.record_domain(
            "COST_OBSERVATION", "Economic Outcome & Learning Authority",
            {
                "publication_state_id": publication_state_id,
                "costs": normalized_costs,
                "totals_by_currency": totals_by_currency,
                "comparable_total": None if comparable_cost_total is None else {"amount": comparable_cost_total, "currency": revenue_currency if not costs else next(iter(totals_by_currency), revenue_currency)},
                "observed_at": utcnow(),
                "execution_actor_authorization": actor,
                "evidence_state_ids": evidence_state_ids,
            },
            natural_key=f"cost:{publication_state_id}:{utcnow()}", subject_identity_id=subject, record_state="OBSERVED",
            upstream_states=[(publication_state_id, "COST_OF"), *evidence_upstream],
        )
        outcome = self.ledger.record_domain(
            "REALIZED_ECONOMIC_OUTCOME", "Economic Outcome & Learning Authority",
            {
                "publication_state_id": publication_state_id,
                "revenue": {**revenue, "amount": rev_amount, "currency": revenue_currency},
                "cost_totals_by_currency": totals_by_currency,
                "profit": None if profit is None else {"amount": profit, "currency": revenue_currency},
                "profit_semantics": "SYSTEM_CALCULATED_REALIZED_NET_RESULT_FROM_EXACT_EVIDENCE_BOUND_INPUTS__NOT_AUDITED_OR_STATUTORY_PROFIT",
                "profit_verification": {
                    "status": "SYSTEM_EVIDENCE_BOUND" if profit is not None else "NOT_VERIFIED",
                    "evidence_status": evidence_status,
                    "evidence_state_ids": evidence_state_ids,
                    "evidence_details": evidence_details,
                    "audited_profit": False,
                    "statutory_profit": False,
                    "investment_return_guarantee": False,
                },
                "evaluation_blockers": blockers,
                "attribution": attribution,
                "prediction_not_rewritten": True,
                "execution_actor_authorization": actor,
            },
            natural_key=f"outcome:{publication_state_id}:{utcnow()}", subject_identity_id=subject, record_state=realized_state,
            upstream_states=[(perf.state_id, "OUTCOME_PERFORMANCE_INPUT"), (rev.state_id, "OUTCOME_REVENUE_INPUT"), (cost.state_id, "OUTCOME_COST_INPUT"), *evidence_upstream],
        )
        for state_id in (perf.state_id, rev.state_id, cost.state_id, outcome.state_id):
            self._append_operator_provenance(state_id, auth_context)
        return {"performance": perf, "revenue": rev, "cost": cost, "outcome": outcome}

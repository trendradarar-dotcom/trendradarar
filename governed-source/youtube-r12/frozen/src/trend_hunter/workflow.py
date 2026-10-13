from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from .db import connect, tx
from .ledger import GovernanceLedger, LedgerError, ArtifactRef
from .util import json_dumps, new_id, utcnow


BLOCKING_STATES = {"INELIGIBLE", "BLOCK", "DO_NOT_RECOMMEND", "REJECTED", "NOT_FEASIBLE"}


@dataclass(frozen=True)
class DependencyEffect:
    binding_id: str
    effect: str
    downstream_state_id: str
    event_id: str


class GovernedWorkflow:
    """Cross-authority execution helpers.

    The workflow never treats downstream PASS as permission to ignore an exact
    upstream blocking state. All dependencies are exact state references.
    """

    def __init__(self, ledger: GovernanceLedger):
        self.ledger = ledger

    def assert_no_gate_laundering(self, upstream_state_ids: list[str]) -> None:
        for sid in upstream_state_ids:
            st = self.ledger.get_state(sid)
            payload = st["payload"]
            candidates = {
                st.get("status"),
                payload.get("outcome"),
                payload.get("gate_decision"),
                payload.get("decision"),
                payload.get("recommendation"),
            }
            if any(x in BLOCKING_STATES for x in candidates if x is not None):
                raise LedgerError(f"Upstream governing block cannot be laundered: {sid}")

    def apply_upstream_change(self, old_state_id: str, new_state_id: str | None) -> list[DependencyEffect]:
        effects: list[DependencyEffect] = []
        with tx(self.ledger.db_path) as conn:
            rows = conn.execute(
                """SELECT b.*,p.effect,p.materiality_rule_json,p.affected_semantics_json
                   FROM dependency_binding b JOIN dependency_change_policy p ON p.id=b.change_policy_id
                   WHERE b.upstream_state_id=?""",
                (old_state_id,),
            ).fetchall()
            for r in rows:
                mapping = {
                    "INVALIDATE": "INVALIDATED",
                    "RECONCILE": "RECONCILIATION_REQUIRED",
                    "REASSESS": "REASSESSMENT_REQUIRED",
                    "NO_EFFECT": "NO_EFFECT_CONFIRMED",
                }
                event_id = new_id("dre")
                conn.execute(
                    """INSERT INTO invalidation_reconciliation_event(
                        id,dependency_binding_id,event_type,upstream_old_state_id,upstream_new_state_id,
                        affected_downstream_state_id,payload_json,recorded_at,committed_at
                    ) VALUES(?,?,?,?,?,?,?,?,?)""",
                    (event_id, r["id"], mapping[r["effect"]], old_state_id, new_state_id, r["downstream_state_id"],
                     json_dumps({"policy_effect":r["effect"],"materiality_rule":json.loads(r["materiality_rule_json"]),"affected_semantics":json.loads(r["affected_semantics_json"])}),
                     utcnow(), utcnow()),
                )
                effects.append(DependencyEffect(r["id"], r["effect"], r["downstream_state_id"], event_id))
        return effects

    def bind_exact_dependencies(self, downstream_state_id: str, bindings: list[tuple[str, str, str]]) -> list[str]:
        """bindings: [(upstream_state_id, dependency_type, change_policy_id)]"""
        out=[]
        for upstream, dep_type, policy_id in bindings:
            self.ledger.get_state(upstream)
            out.append(self.ledger.bind_dependency(downstream_state_id, upstream, dep_type, policy_id))
        return out

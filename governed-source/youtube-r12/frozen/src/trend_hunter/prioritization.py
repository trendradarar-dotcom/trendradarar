from __future__ import annotations

from typing import Any

from .ledger import GovernanceLedger, ArtifactRef, LedgerError


class PrioritizationService:
    def __init__(self,ledger:GovernanceLedger): self.ledger=ledger

    def decide(self, economic_state_id: str, feasibility_state_id: str, *, policy_key: str, policy_version: int, decision: str, rationale: dict[str,Any]) -> ArtifactRef:
        econ=self.ledger.get_state(economic_state_id); feas=self.ledger.get_state(feasibility_state_id)
        policy=self.ledger.get_dependency_policy('UPSTREAM_REQUIRES_REASSESSMENT',1)
        if econ['state_type']!='ECONOMIC_EXPECTATION' or feas['state_type']!='FEASIBILITY_ASSESSMENT': raise LedgerError('wrong inputs')
        e_cfg=econ['payload'].get('execution_configuration_state_id'); f_cfg=feas['payload'].get('execution_configuration_state_id')
        if e_cfg!=f_cfg: raise LedgerError('economic and feasibility assessments must share the same exact ExecutionConfiguration')
        if feas['payload'].get('outcome')=='NOT_FEASIBLE' and decision in {'SELECT','ALLOCATE','PROCEED'}:
            raise LedgerError('cannot select NOT_FEASIBLE scenario without explicit override contract')
        cfg=self.ledger.get_state(e_cfg)
        result=self.ledger.record_domain('PRIORITY_DECISION','Prioritization & Resource Allocation Authority',{
            'execution_configuration_state_id':e_cfg,'policy_key':policy_key,'policy_version':policy_version,'decision':decision,'rationale':rationale,'universal_score':None
        },natural_key=f"priority:{e_cfg}:{policy_key}:{policy_version}:{decision}",subject_identity_id=self.ledger.subject_identity_for_state(e_cfg),record_state=decision,
        upstream_states=[(economic_state_id,'PRIORITY_ECONOMIC_INPUT'),(feasibility_state_id,'PRIORITY_FEASIBILITY_INPUT')])
        self.ledger.bind_dependency(result.state_id,economic_state_id,'PRIORITY_ECONOMIC_INPUT',policy,{'materiality':'economic expectation change'})
        self.ledger.bind_dependency(result.state_id,feasibility_state_id,'PRIORITY_FEASIBILITY_INPUT',policy,{'materiality':'feasibility change'})
        return result

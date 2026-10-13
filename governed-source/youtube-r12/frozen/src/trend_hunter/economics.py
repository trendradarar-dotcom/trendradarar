from __future__ import annotations

from typing import Any

from .ledger import GovernanceLedger, ArtifactRef, LedgerError


class EconomicExpectationService:
    def __init__(self,ledger:GovernanceLedger): self.ledger=ledger

    def estimate(self, execution_configuration_state_id: str, *, mechanism: str, horizon: str, scenarios: list[dict[str,Any]], coverage: str, uncertainty: dict[str,Any]) -> ArtifactRef:
        cfg=self.ledger.get_state(execution_configuration_state_id)
        if cfg['state_type']!='EXECUTION_CONFIGURATION': raise LedgerError('requires prior EXECUTION_CONFIGURATION')
        if not mechanism: raise LedgerError('monetization mechanism/scenario required')
        policy=self.ledger.get_dependency_policy('UPSTREAM_REQUIRES_REASSESSMENT',1)
        # Values are explicit caller-supplied assumptions/scenarios; service does not fabricate them.
        normalized=[]
        for i,s in enumerate(scenarios):
            if 'expected_revenue' not in s or 'incremental_cost' not in s:
                raise LedgerError(f'scenario {i} must provide expected_revenue and incremental_cost')
            rev=s['expected_revenue']; cost=s['incremental_cost']
            if rev.get('currency') != cost.get('currency'):
                contribution=None; state='NOT_COMPARABLE_CURRENCY'
            else:
                contribution={'amount':float(rev['amount'])-float(cost['amount']),'currency':rev.get('currency')}; state='DETERMINATE'
            normalized.append({**s,'expected_contribution':contribution,'calculation_state':state})
        result=self.ledger.record_domain('ECONOMIC_EXPECTATION','Economic Expectation Authority',{
            'execution_configuration_state_id':execution_configuration_state_id,'mechanism':mechanism,'horizon':horizon,
            'scenarios':normalized,'coverage':coverage,'uncertainty':uncertainty,'prediction_not_realized_outcome':True,'opaque_score':None
        },natural_key=f"econ:{execution_configuration_state_id}:{mechanism}:{horizon}",subject_identity_id=self.ledger.subject_identity_for_state(execution_configuration_state_id),record_state='ESTIMATED',
        upstream_states=[(execution_configuration_state_id,'ECONOMIC_SCENARIO_CONFIGURATION')])
        self.ledger.bind_dependency(result.state_id,execution_configuration_state_id,'ECONOMIC_SCENARIO_CONFIGURATION',policy,{'materiality':'execution scenario or monetization assumption change'})
        return result

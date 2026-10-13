from __future__ import annotations

from typing import Any

from .ledger import GovernanceLedger, ArtifactRef, LedgerError


class SaturationCharacterizationService:
    """SRCA first realization: supply occupancy relative to a pinned baseline."""
    FORBIDDEN_COMPETITION_TOKENS = {
        'competition','competitive','competitor','competitive_population','competitive_arena',
        'contestability','contestable','substitutability','substitute','demand_serving_suitability',
    }

    def __init__(self,ledger:GovernanceLedger): self.ledger=ledger

    @classmethod
    def _contains_forbidden_semantics(cls, value: Any) -> bool:
        if isinstance(value, dict):
            for k,v in value.items():
                key=str(k).strip().lower().replace('-','_').replace(' ','_')
                if any(tok in key for tok in cls.FORBIDDEN_COMPETITION_TOKENS):
                    return True
                if cls._contains_forbidden_semantics(v):
                    return True
            return False
        if isinstance(value, (list,tuple,set)):
            return any(cls._contains_forbidden_semantics(v) for v in value)
        if isinstance(value, str):
            text=value.strip().lower().replace('-','_').replace(' ','_')
            return any(tok in text for tok in cls.FORBIDDEN_COMPETITION_TOKENS)
        return False

    def content_supply_occupancy(self, trend_state_id: str, *, eligible_supply_value: float | None, baseline_value: float | None, baseline_contract: dict[str,Any], coverage: str, uncertainty: dict[str,Any] | str) -> ArtifactRef:
        trend=self.ledger.get_state(trend_state_id)
        policy=self.ledger.get_dependency_policy('UPSTREAM_REQUIRES_REASSESSMENT',1)
        if trend['state_type']!='TREND_MEASUREMENT': raise LedgerError('trend_state_id must be TREND_MEASUREMENT')
        selection_basis=baseline_contract.get('selection_basis')
        if selection_basis not in {'PRECOMMITTED_EXACT','VERSIONED_OUTCOME_INDEPENDENT_RULE'}:
            raise LedgerError('baseline selection must be precommitted or governed by an outcome-independent versioned rule')
        if not baseline_contract.get('id'):
            raise LedgerError('baseline contract must identify the exact governed reference basis')
        if selection_basis=='VERSIONED_OUTCOME_INDEPENDENT_RULE' and not (
            baseline_contract.get('selection_rule_contract_id') or
            (baseline_contract.get('selection_rule_key') and baseline_contract.get('selection_rule_version') is not None)
        ):
            raise LedgerError('versioned baseline selection requires an exact version-pinned selection rule reference')
        if self._contains_forbidden_semantics(baseline_contract):
            raise LedgerError('competition/demand semantics hidden in R_supply baseline are forbidden')
        if eligible_supply_value is None or baseline_value is None or baseline_value <= 0:
            state='NOT_EVALUABLE'; ratio=None
        else:
            state='DETERMINATE'; ratio=float(eligible_supply_value)/float(baseline_value)
        payload={
            'realization_contract':'CONTENT_SUPPLY_OCCUPANCY_RELATIVE_TO_SCOPE_BASELINE@V1',
            'trend_state_id':trend_state_id,
            'eligible_supply_value':eligible_supply_value,
            'reference_basis':baseline_contract,
            'baseline_value':baseline_value,
            'occupancy_ratio':ratio,
            'orientation':'higher_ratio_means_greater_supply_occupation_relative_to_pinned_baseline',
            'coverage':coverage,
            'uncertainty':uncertainty,
            'competition_semantics_used':False,
            'demand_semantics_used':False,
            'opportunity_value_not_asserted':True,
            'reference_selection_outcome_independent':True,
        }
        result=self.ledger.record_domain(
            'SATURATION_CHARACTERIZATION','SRCA',payload,
            natural_key=f"sat:{trend_state_id}:{baseline_contract['id']}",
            subject_identity_id=self.ledger.subject_identity_for_state(trend_state_id),scope=trend['payload'].get('scope',{}),record_state=state,
            upstream_states=[(trend_state_id,'CHARACTERIZES_TREND_MEASUREMENT')],
        )
        self.ledger.bind_dependency(result.state_id,trend_state_id,'CHARACTERIZES_TREND_MEASUREMENT',policy,{'materiality':'trend measurement/reference input change'})
        return result

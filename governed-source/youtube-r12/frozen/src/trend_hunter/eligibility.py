from __future__ import annotations

from typing import Any

from .ledger import GovernanceLedger, ArtifactRef, LedgerError


class EligibilityService:
    """Conservative eligibility gate. No political keyword guessing as truth.

    If a governed classifier/reviewer has not supplied a risk determination,
    the service returns HUMAN_REVIEW_REQUIRED rather than silently ELIGIBLE.
    """
    def __init__(self,ledger:GovernanceLedger): self.ledger=ledger

    def assess(self, opportunity_state_id: str, *, target: dict[str,Any], political_risk_determination: str | None, other_findings: list[dict[str,Any]] | None=None) -> ArtifactRef:
        opp=self.ledger.get_state(opportunity_state_id)
        if opp['state_type']!='OPPORTUNITY': raise LedgerError('target must be OPPORTUNITY')
        policy=self.ledger.get_dependency_policy('UPSTREAM_REQUIRES_REASSESSMENT',1)
        if political_risk_determination in {'POLITICAL_OPPOSITION','POLITICAL_ACTIVISM','POLITICAL_MOBILIZATION'}:
            outcome='INELIGIBLE'
        elif political_risk_determination in {'STATE_SENSITIVE','UNRESOLVED',None}:
            outcome='HUMAN_REVIEW_REQUIRED'
        elif political_risk_determination=='NON_POLITICAL':
            outcome='ELIGIBLE'
        else:
            outcome='NOT_EVALUABLE'
        result = self.ledger.record_domain(
            'ELIGIBILITY_ASSESSMENT','Opportunity Eligibility & Jurisdictional Risk Authority',{
                'opportunity_state_id':opportunity_state_id,
                'target':target,
                'political_risk_determination':political_risk_determination,
                'other_findings':other_findings or [],
                'outcome':outcome,
                'truth_independent':True,
            },natural_key=f"elig:{opportunity_state_id}:{target}",subject_identity_id=self.ledger.subject_identity_for_state(opportunity_state_id),scope=target,record_state=outcome,
            upstream_states=[(opportunity_state_id,'ELIGIBILITY_TARGET')],
        )
        self.ledger.bind_dependency(result.state_id,opportunity_state_id,'ELIGIBILITY_TARGET',policy,{'materiality':'opportunity semantic or target-relevant change'})
        return result

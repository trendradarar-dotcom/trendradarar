from __future__ import annotations

from typing import Any

from .ledger import GovernanceLedger, ArtifactRef, LedgerError


class OpportunityService:
    """Candidate/thesis/factor records only; never creates an opaque score."""
    def __init__(self,ledger:GovernanceLedger): self.ledger=ledger

    def create_candidate(self, candidate_key: str, *, story_state_id: str, role_bound_scope: dict[str,Any], thesis: str, factor_state_ids: list[str], factor_assertions: dict[str,Any]) -> ArtifactRef:
        story=self.ledger.get_state(story_state_id)
        reassess=self.ledger.get_dependency_policy('UPSTREAM_REQUIRES_REASSESSMENT',1)
        if story['state_type']!='STORY': raise LedgerError('story_state_id must be STORY')
        for sid in factor_state_ids: self.ledger.get_state(sid)
        oid=self.ledger.get_or_create_identity('OPPORTUNITY',candidate_key)
        result=self.ledger.record_domain(
            'OPPORTUNITY','Opportunity Authority',{
                'candidate_key':candidate_key,
                'story_state_id':story_state_id,
                'role_bound_scope':role_bound_scope,
                'thesis':thesis,
                'factor_assertions':factor_assertions,
                'profile_semantics':'non_synthetic_factor_profile',
                'opportunity_score':None,
                'eligibility_not_asserted':True,
                'profitability_not_asserted':True,
            },
            natural_key=f'candidate:{candidate_key}',subject_identity_id=oid,scope=role_bound_scope,record_state='CANDIDATE',
            upstream_states=[(story_state_id,'OPPORTUNITY_STORY_BASIS')]+[(sid,'OPPORTUNITY_FACTOR_INPUT') for sid in factor_state_ids],
        )
        self.ledger.bind_dependency(result.state_id,story_state_id,'OPPORTUNITY_STORY_BASIS',reassess,{'materiality':'story identity/basis change'})
        for sid in factor_state_ids:
            self.ledger.bind_dependency(result.state_id,sid,'OPPORTUNITY_FACTOR_INPUT',reassess,{'materiality':'factor assertion/input change'})
        return result

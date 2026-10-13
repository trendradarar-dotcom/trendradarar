from __future__ import annotations

from .ledger import GovernanceLedger, ArtifactRef, LedgerError


class PublicationRecommendationService:
    def __init__(self,ledger:GovernanceLedger): self.ledger=ledger

    def recommend(self, creative_state_id: str, eligibility_state_id: str, compliance_state_id: str) -> ArtifactRef:
        creative=self.ledger.get_state(creative_state_id); elig=self.ledger.get_state(eligibility_state_id); comp=self.ledger.get_state(compliance_state_id)
        if creative['state_type']!='CREATIVE_ARTIFACT' or elig['state_type']!='ELIGIBILITY_ASSESSMENT' or comp['state_type']!='COMPLIANCE_ASSESSMENT': raise LedgerError('invalid inputs')
        subject = self.ledger.subject_identity_for_state(creative_state_id)
        if self.ledger.subject_identity_for_state(eligibility_state_id) != subject or self.ledger.subject_identity_for_state(compliance_state_id) != subject:
            raise LedgerError('recommendation inputs belong to different governed subjects')
        if creative['payload'].get('eligibility_state_id') != eligibility_state_id:
            raise LedgerError('recommendation eligibility is not the exact creative eligibility state')
        if comp['payload'].get('creative_state_id') != creative_state_id:
            raise LedgerError('compliance assessment is not bound to the exact creative state')
        if comp['payload'].get('eligibility_state_id') != eligibility_state_id:
            raise LedgerError('compliance assessment is not bound to the exact eligibility state')
        if comp['payload'].get('target') != creative['payload'].get('target'):
            raise LedgerError('compliance target differs from creative target')
        invalidate=self.ledger.get_dependency_policy('MATERIAL_UPSTREAM_INVALIDATES',1)
        reassess=self.ledger.get_dependency_policy('UPSTREAM_REQUIRES_REASSESSMENT',1)
        eo=elig['payload'].get('outcome'); cd=comp['payload'].get('gate_decision')
        if eo=='INELIGIBLE' or cd=='BLOCK': rec='DO_NOT_RECOMMEND'
        elif eo!='ELIGIBLE' or cd=='HUMAN_REVIEW': rec='RECOMMEND_HOLD'
        elif cd=='WARNING': rec='RECOMMEND_REVISE'
        elif cd=='PASS': rec='RECOMMEND_PUBLISH'
        else: rec='RECOMMEND_HOLD'
        result=self.ledger.record_domain('PUBLICATION_RECOMMENDATION','Publication Recommendation Authority',{
            'creative_state_id':creative_state_id,'eligibility_state_id':eligibility_state_id,'compliance_state_id':compliance_state_id,
            'recommendation':rec,'human_final_authorization_required':True,
            'exact_chain_validated': True,
        },natural_key=f"recommend:{creative_state_id}:{compliance_state_id}",subject_identity_id=subject,record_state=rec,
        upstream_states=[(creative_state_id,'RECOMMENDATION_CONTENT'),(eligibility_state_id,'RECOMMENDATION_ELIGIBILITY'),(compliance_state_id,'RECOMMENDATION_COMPLIANCE')])
        self.ledger.bind_dependency(result.state_id,creative_state_id,'RECOMMENDATION_CONTENT',invalidate,{'materiality':'content version change'})
        self.ledger.bind_dependency(result.state_id,eligibility_state_id,'RECOMMENDATION_ELIGIBILITY',invalidate,{'materiality':'eligibility change'})
        self.ledger.bind_dependency(result.state_id,compliance_state_id,'RECOMMENDATION_COMPLIANCE',reassess,{'materiality':'compliance finding/gate change'})
        return result

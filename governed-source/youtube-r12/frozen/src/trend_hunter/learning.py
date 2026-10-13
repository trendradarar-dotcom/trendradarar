from __future__ import annotations

from typing import Any
from .ledger import GovernanceLedger, ArtifactRef, LedgerError


class LearningService:
    def __init__(self,ledger:GovernanceLedger): self.ledger=ledger

    def propose_update(self, realized_outcome_state_id: str, *, target_contract_or_model: str, proposal: dict[str,Any], rationale: dict[str,Any]) -> ArtifactRef:
        out=self.ledger.get_state(realized_outcome_state_id)
        if out['state_type']!='REALIZED_ECONOMIC_OUTCOME': raise LedgerError('learning input must be REALIZED_ECONOMIC_OUTCOME')
        verification=(out.get('payload') or {}).get('profit_verification') or {}
        if verification.get('status') != 'SYSTEM_EVIDENCE_BOUND':
            raise LedgerError('learning from realized economics requires a SYSTEM_EVIDENCE_BOUND outcome; synthetic/insufficient evidence cannot train learning')
        return self.ledger.record_domain('LEARNING_UPDATE_PROPOSAL','Economic Outcome & Learning Authority',{
            'realized_outcome_state_id':realized_outcome_state_id,'target_contract_or_model':target_contract_or_model,
            'proposal':proposal,'rationale':rationale,'forward_version_only':True,'historical_prediction_not_rewritten':True,
        },natural_key=f"learning:{realized_outcome_state_id}:{target_contract_or_model}",subject_identity_id=out['identity_id'],record_state='PROPOSED',
        upstream_states=[(realized_outcome_state_id,'LEARNING_FROM_REALIZED_OUTCOME')])

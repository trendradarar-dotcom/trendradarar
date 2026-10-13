from __future__ import annotations

from typing import Any

from .ledger import GovernanceLedger, ArtifactRef, LedgerError
from .c1_policy import normalize_market_language
from .publishing_target import normalize_publication_target


class ComplianceService:
    def __init__(self,ledger:GovernanceLedger): self.ledger=ledger

    @staticmethod
    def _synthetic(payload: dict[str, Any]) -> bool:
        nested = payload.get('payload')
        return payload.get('fixture') is True or (isinstance(nested, dict) and nested.get('fixture') is True)

    def _validate_finding(self, finding: dict[str, Any], *, dimension: str, strict_c1: bool, creative_state_id: str) -> dict[str, Any]:
        if not isinstance(finding, dict):
            raise LedgerError(f'{dimension} finding must be a structured object')
        status = str(finding.get('status') or '').strip().upper()
        if strict_c1 and status not in {'PASS','WARNING','BLOCK','UNRESOLVED','NOT_APPLICABLE'}:
            raise LedgerError(f'{dimension} finding has invalid status')
        if strict_c1 and status in {'UNRESOLVED','NOT_APPLICABLE'} and not str(finding.get('reason') or '').strip():
            raise LedgerError(f'{dimension} {status} finding requires an explicit reason')
        evidence_ids = list(dict.fromkeys(finding.get('evidence_state_ids') or []))
        verified_ids: list[str] = []
        for sid in evidence_ids:
            st = self.ledger.get_state(str(sid))
            payload = st.get('payload') or {}
            if st['state_type'] != 'EVIDENCE':
                raise LedgerError(f'{dimension} finding evidence must be typed EVIDENCE')
            if self._synthetic(payload):
                raise LedgerError(f'{dimension} finding cannot rely on synthetic/fixture evidence')
            if strict_c1:
                if str(payload.get('creative_state_id') or '') != creative_state_id:
                    raise LedgerError(f'{dimension} evidence is not bound to the exact creative state')
                if str(payload.get('review_scope') or '').strip().lower() != dimension:
                    raise LedgerError(f'{dimension} evidence has the wrong specialized review scope')
                if str(payload.get('verification_status') or '').strip().upper() not in {'HUMAN_REVIEWED','EXTERNAL_SOURCE_BOUND','GOVERNED_POLICY_CHECK'}:
                    raise LedgerError(f'{dimension} evidence lacks governed verification status')
            verified_ids.append(str(sid))
        if strict_c1 and status in {'PASS','WARNING','BLOCK','NOT_APPLICABLE'} and not verified_ids:
            raise LedgerError(f'{dimension} material finding requires typed non-synthetic evidence')
        return {**finding, 'status': status, 'evidence_state_ids': verified_ids}

    def assess(
        self,
        creative_state_id: str,
        eligibility_state_id: str,
        *,
        target: dict[str,Any],
        legal_findings: list[dict[str,Any]],
        platform_findings: list[dict[str,Any]],
        coverage_state: str,
        gate_decision: str,
        strict_c1: bool = False,
    ) -> ArtifactRef:
        target = normalize_publication_target(target)
        if coverage_state not in {'SUFFICIENT','PARTIAL','UNKNOWN'}: raise LedgerError('invalid coverage state')
        if gate_decision not in {'PASS','WARNING','HUMAN_REVIEW','BLOCK'}: raise LedgerError('invalid gate decision')
        creative=self.ledger.get_state(creative_state_id); elig=self.ledger.get_state(eligibility_state_id)
        if creative['state_type']!='CREATIVE_ARTIFACT' or elig['state_type']!='ELIGIBILITY_ASSESSMENT': raise LedgerError('invalid inputs')

        creative_subject = self.ledger.subject_identity_for_state(creative_state_id)
        eligibility_subject = self.ledger.subject_identity_for_state(eligibility_state_id)
        if creative_subject != eligibility_subject:
            raise LedgerError('creative and eligibility belong to different governed subjects')
        if creative['payload'].get('eligibility_state_id') != eligibility_state_id:
            raise LedgerError('compliance eligibility must be the exact eligibility state consumed by the creative')
        if creative['payload'].get('target') != target:
            raise LedgerError('compliance target must exactly match the creative target')

        legal = [self._validate_finding(f, dimension='legal', strict_c1=strict_c1, creative_state_id=creative_state_id) for f in legal_findings]
        platform = [self._validate_finding(f, dimension='platform', strict_c1=strict_c1, creative_state_id=creative_state_id) for f in platform_findings]
        if strict_c1:
            normalize_market_language(target.get('publication_language') or target.get('language'))
            if not str(target.get('target_market') or target.get('region') or '').strip():
                raise LedgerError('C1 compliance target requires an explicit target_market/region')
            if not legal or not platform:
                raise LedgerError('C1 compliance requires explicit legal and platform review findings')
            all_statuses = [f['status'] for f in legal + platform]
            if gate_decision == 'PASS' and any(s not in {'PASS','NOT_APPLICABLE'} for s in all_statuses):
                raise LedgerError('C1 PASS cannot be asserted while legal/platform findings are unresolved, warning, or blocked')
            if gate_decision == 'WARNING' and any(s in {'BLOCK','UNRESOLVED'} for s in all_statuses):
                raise LedgerError('C1 WARNING cannot launder BLOCK/UNRESOLVED findings')
            if any(s == 'BLOCK' for s in all_statuses) and gate_decision != 'BLOCK':
                raise LedgerError('C1 BLOCK finding requires BLOCK gate decision')
            if any(s == 'UNRESOLVED' for s in all_statuses) and gate_decision not in {'HUMAN_REVIEW','BLOCK'}:
                raise LedgerError('C1 UNRESOLVED finding requires HUMAN_REVIEW or BLOCK')

        if elig['payload'].get('outcome')=='INELIGIBLE' and gate_decision in {'PASS','WARNING'}:
            gate_decision='BLOCK'
        if coverage_state in {'PARTIAL','UNKNOWN'} and gate_decision=='PASS':
            raise LedgerError('PASS cannot be asserted with PARTIAL/UNKNOWN coverage without a separately governed exception')
        reassess=self.ledger.get_dependency_policy('UPSTREAM_REQUIRES_REASSESSMENT',1)
        invalidate=self.ledger.get_dependency_policy('MATERIAL_UPSTREAM_INVALIDATES',1)
        evidence_ids = list(dict.fromkeys(
            sid for f in legal + platform for sid in (f.get('evidence_state_ids') or [])
        ))
        upstream = [(creative_state_id,'COMPLIANCE_CONTENT_TARGET'),(eligibility_state_id,'COMPLIANCE_UPSTREAM_ELIGIBILITY')]
        upstream.extend((sid, 'COMPLIANCE_TYPED_EVIDENCE') for sid in evidence_ids)
        result=self.ledger.record_domain('COMPLIANCE_ASSESSMENT','Distribution Compliance Authority',{
            'creative_state_id':creative_state_id,'eligibility_state_id':eligibility_state_id,'target':target,
            'legal_findings':legal,'platform_findings':platform,'coverage_state':coverage_state,'gate_decision':gate_decision,
            'legal_rules_distinct_from_platform_policy':True,'compliance_not_truth':True,
            'c1_strict_review': bool(strict_c1), 'evidence_state_ids': evidence_ids,
        },natural_key=f"compliance:{creative_state_id}:{target}",subject_identity_id=creative_subject,scope=target,record_state=gate_decision,
        upstream_states=upstream)
        self.ledger.bind_dependency(result.state_id,creative_state_id,'COMPLIANCE_CONTENT_TARGET',reassess,{'materiality':'content/target change'})
        self.ledger.bind_dependency(result.state_id,eligibility_state_id,'COMPLIANCE_UPSTREAM_ELIGIBILITY',invalidate,{'materiality':'upstream ineligibility cannot be laundered'})
        for sid in evidence_ids:
            self.ledger.bind_dependency(result.state_id, sid, 'COMPLIANCE_TYPED_EVIDENCE', reassess, {'materiality':'legal/platform evidence change'})
        return result

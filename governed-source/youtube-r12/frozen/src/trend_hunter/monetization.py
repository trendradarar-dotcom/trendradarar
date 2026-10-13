from __future__ import annotations

from typing import Any

from .ledger import GovernanceLedger, ArtifactRef, LedgerError
from .db import tx, connect
from .util import json_dumps


class MonetizationService:
    def __init__(self,ledger:GovernanceLedger): self.ledger=ledger

    @staticmethod
    def _commercial_path(*, mechanism, provider, account_ref, offer_or_product_ref, campaign_ref, tracked_destination):
        if not str(mechanism or "").strip():
            raise LedgerError("monetization mechanism is required")
        def norm(v): return None if v is None else str(v).strip()
        return {
            "mechanism": str(mechanism).strip(),
            "provider": norm(provider),
            "account_ref": norm(account_ref),
            "offer_or_product_ref": norm(offer_or_product_ref),
            "campaign_ref": norm(campaign_ref),
            "tracked_destination": norm(tracked_destination),
        }

    def _current_commercial_channel_decision_for_subject(self, subject_identity_id: str):
        # Commercial-channel decisions use a natural key that includes the target/path,
        # so an older decision can remain the latest version of *its own* identity after
        # a newer decision is recorded under a different identity. Authority is therefore
        # subject-global: only the newest decision for this governed subject may control
        # subsequent monetization configuration.
        with connect(self.ledger.db_path) as conn:
            row = conn.execute(
                """SELECT d.artifact_state_id FROM domain_record d
                   JOIN artifact_state s ON s.id=d.artifact_state_id
                   WHERE d.stage='COMMERCIAL_CHANNEL_DECISION' AND d.subject_identity_id=?
                   ORDER BY s.recorded_at DESC, s.rowid DESC
                   LIMIT 1""",
                (subject_identity_id,),
            ).fetchone()
        if row is None:
            return None
        st = self.ledger.get_state(row["artifact_state_id"])
        with connect(self.ledger.db_path) as conn:
            latest = conn.execute(
                "SELECT id FROM artifact_state WHERE identity_id=? ORDER BY version DESC LIMIT 1",
                (st["identity_id"],),
            ).fetchone()
        if not latest or latest["id"] != st["id"]:
            raise LedgerError('latest commercial channel decision is stale/superseded; re-evaluation is required')
        return st

    def configure(self, priority_state_id: str, *, mechanism: str, provider: str | None, account_ref: str | None, offer_or_product_ref: str | None, campaign_ref: str | None, tracked_destination: str | None, attribution: dict[str,Any], payout_terms: dict[str,Any], currency: str | None, commercial_authorization_ref: str | None=None, requires_commercial_authorization: bool=False, activation_requirements: list[dict[str,Any]] | None=None) -> ArtifactRef:
        pr=self.ledger.get_state(priority_state_id)
        if pr['state_type']!='PRIORITY_DECISION': raise LedgerError('priority_state_id must be PRIORITY_DECISION')
        if pr['payload'].get('decision') in {'REJECT','HOLD','DO_NOT_ALLOCATE'}: raise LedgerError('priority decision does not permit configuration')
        subject=self.ledger.subject_identity_for_state(priority_state_id)
        commercial_decision=self._current_commercial_channel_decision_for_subject(subject)
        if commercial_decision is not None:
            cp=commercial_decision.get('payload') or {}
            if cp.get('decision') == 'HOLD':
                raise LedgerError('current commercial channel decision is HOLD; monetization configuration is blocked')
            expected=self._commercial_path(**{
                'mechanism': (cp.get('evaluated_monetization_path') or {}).get('mechanism'),
                'provider': (cp.get('evaluated_monetization_path') or {}).get('provider'),
                'account_ref': (cp.get('evaluated_monetization_path') or {}).get('account_ref'),
                'offer_or_product_ref': (cp.get('evaluated_monetization_path') or {}).get('offer_or_product_ref'),
                'campaign_ref': (cp.get('evaluated_monetization_path') or {}).get('campaign_ref'),
                'tracked_destination': (cp.get('evaluated_monetization_path') or {}).get('tracked_destination'),
            })
            actual=self._commercial_path(mechanism=mechanism,provider=provider,account_ref=account_ref,offer_or_product_ref=offer_or_product_ref,campaign_ref=campaign_ref,tracked_destination=tracked_destination)
            if actual != expected:
                raise LedgerError('monetization configuration differs from the current evaluated commercial channel monetization path')
        policy=self.ledger.get_dependency_policy('UPSTREAM_REQUIRES_REASSESSMENT',1)
        iid=self.ledger.get_or_create_identity('MONETIZATION_CONFIGURATION',f"mon:{priority_state_id}:{mechanism}:{provider}:{offer_or_product_ref}:{campaign_ref}")
        lifecycle='READY_FOR_ACTIVATION' if mechanism and (provider or tracked_destination or offer_or_product_ref) else 'CONFIGURED'
        requirements = activation_requirements or [
            {'key':'ELIGIBILITY','required_state_type':'ELIGIBILITY_ASSESSMENT','payload_path':'outcome','accepted_values':['ELIGIBLE'],'required':True},
            {'key':'COMPLIANCE','required_state_type':'COMPLIANCE_ASSESSMENT','payload_path':'gate_decision','accepted_values':['PASS','WARNING'],'required':True},
            {'key':'HUMAN_PUBLICATION_AUTHORIZATION','required_state_type':'HUMAN_AUTHORIZATION','payload_path':'decision','accepted_values':['AUTHORIZED'],'required':True},
            {'key':'EXACT_CREATIVE_BINDING','required_state_type':'CREATIVE_ARTIFACT','payload_path':'monetization_configuration_state_id','accepted_values':['__CONFIG_STATE_ID__'],'required':True},
        ]
        if requires_commercial_authorization:
            requirements.append({'key':'HUMAN_COMMERCIAL_AUTHORIZATION','required_state_type':'HUMAN_COMMERCIAL_AUTHORIZATION','payload_path':'decision','accepted_values':['AUTHORIZED'],'required':True})
        payload={'priority_state_id':priority_state_id,'mechanism':mechanism,'provider':provider,'account_ref':account_ref,'offer_or_product_ref':offer_or_product_ref,
                 'campaign_ref':campaign_ref,'tracked_destination':tracked_destination,'attribution':attribution,'payout_terms':payout_terms,'currency':currency,
                 'lifecycle_state':lifecycle,'commercial_authorization_ref':commercial_authorization_ref,
                 'requires_commercial_authorization':requires_commercial_authorization,'activation_requirements':requirements,
                 'commercial_channel_decision_state_id': commercial_decision['id'] if commercial_decision is not None else None}
        st=self.ledger.create_state(iid,'MONETIZATION_CONFIGURATION',payload)
        with tx(self.ledger.db_path) as conn:
            dr=conn.execute('SELECT subject_identity_id FROM domain_record WHERE artifact_state_id=?',(priority_state_id,)).fetchone()
            subject=dr['subject_identity_id'] if dr and dr['subject_identity_id'] else subject
            conn.execute("""INSERT INTO monetization_configuration(
              artifact_state_id,opportunity_identity_id,mechanism,provider,account_ref,offer_or_product_ref,campaign_ref,tracked_destination,
              attribution_json,payout_terms_json,currency,lifecycle_state,commercial_authorization_ref
            ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (st.state_id,subject,mechanism,provider,account_ref,offer_or_product_ref,campaign_ref,tracked_destination,json_dumps(attribution),json_dumps(payout_terms),currency,lifecycle,commercial_authorization_ref))
            conn.execute('INSERT INTO domain_record(artifact_state_id,stage,owner_authority,subject_identity_id,scope_json,record_state) VALUES(?,?,?,?,?,?)',
                         (st.state_id,'MONETIZATION_CONFIGURATION','MCAA',subject,'{}',lifecycle))
            for req in requirements:
                conn.execute("""INSERT INTO monetization_activation_requirement(
                    monetization_configuration_state_id,requirement_key,required_state_type,accepted_values_json,payload_path,required,created_at
                ) VALUES(?,?,?,?,?,?,datetime('now'))""",
                (st.state_id,req['key'],req['required_state_type'],json_dumps(req.get('accepted_values',[])),req.get('payload_path'),int(req.get('required',True))))
        self.ledger.add_provenance(priority_state_id,st.state_id,'MONETIZATION_SELECTION_BASIS')
        self.ledger.bind_dependency(st.state_id,priority_state_id,'MONETIZATION_SELECTION_BASIS',policy,{'reason':'priority_or_resource_allocation_change_may_require_reassessment'})
        if commercial_decision is not None:
            self.ledger.add_provenance(commercial_decision['id'], st.state_id, 'EXACT_COMMERCIAL_CHANNEL_DECISION')
            self.ledger.bind_dependency(st.state_id, commercial_decision['id'], 'EXACT_COMMERCIAL_CHANNEL_DECISION', policy, {'reason':'commercial channel or evaluated monetization path change requires reassessment'})
        return ArtifactRef(iid,st.state_id,st.version,st.raw_hash,st.canonical_hash)


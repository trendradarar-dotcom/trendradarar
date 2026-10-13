from __future__ import annotations

from collections import defaultdict
from typing import Any

from .ledger import GovernanceLedger, ArtifactRef, LedgerError
from .db import connect


class TrendMeasurementService:
    """Produces scope/time measurements only from explicit Signal artifacts.

    The service preserves provider metric semantics and never collapses unlike
    metrics into a universal trend score.
    """
    def __init__(self,ledger:GovernanceLedger): self.ledger=ledger

    def measure(self, story_state_id: str, signal_state_ids: list[str], *, scope: dict[str,Any], window: dict[str,Any]) -> ArtifactRef:
        story=self.ledger.get_state(story_state_id)
        if story['state_type']!='STORY': raise LedgerError('story_state_id must be STORY')
        metrics=defaultdict(list)
        consumed=[]
        for sid in signal_state_ids:
            st=self.ledger.get_state(sid)
            if st['state_type']!='SIGNAL': raise LedgerError(f'{sid} is not SIGNAL')
            consumed.append((sid,'TREND_SIGNAL_INPUT'))
            for m in st['payload'].get('metrics',[]):
                metrics[m.get('metric')].append(m)
        payload={
            'story_state_id':story_state_id,
            'scope':scope,
            'window':window,
            'metric_groups':dict(metrics),
            'cross_metric_aggregation':None,
            'observed_activity_not_coverage':True,
            'missing_not_zero':True,
            'origin_not_asserted':True,
        }
        return self.ledger.record_domain(
            'TREND_MEASUREMENT','Trend Measurement Authority',payload,
            natural_key=f"trend:{story_state_id}:{scope}:{window}",
            subject_identity_id=self.ledger.subject_identity_for_state(story_state_id),scope=scope,record_state='MEASURED',
            upstream_states=[(story_state_id,'MEASURES_STORY')]+consumed,
        )

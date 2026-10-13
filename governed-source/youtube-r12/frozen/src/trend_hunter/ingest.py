from __future__ import annotations

from typing import Iterable

from .connectors.base import SourceItem
from .ledger import GovernanceLedger, ArtifactRef


class IngestionService:
    def __init__(self, ledger: GovernanceLedger):
        self.ledger=ledger

    def ingest(self, items: Iterable[SourceItem], connector_name: str) -> list[ArtifactRef]:
        out=[]
        for item in items:
            natural=f"{item.source_name}:{item.external_id}:{item.observed_at}"
            ref=self.ledger.record_domain(
                "SOURCE_RECORD", "Source Adapter Authority",
                {
                    "source_name": item.source_name,
                    "connector": connector_name,
                    "external_id": item.external_id,
                    "payload": item.payload,
                    "observed_at": item.observed_at,
                },
                natural_key=natural,
                scope={
                    k:item.payload.get(k) for k in ("language","region","platform") if item.payload.get(k) is not None
                },
                observed_at=item.observed_at,
                record_state="OBSERVED",
            )
            out.append(ref)
        return out

from __future__ import annotations
from .base import SourceItem
from ..util import utcnow

class SyntheticConnector:
    """Explicitly synthetic fixture source. Never presented as real-world evidence."""
    name = "synthetic_fixture"

    def fetch(self) -> list[SourceItem]:
        now = utcnow()
        return [
            SourceItem(
                source_name=self.name,
                external_id="story-demo-en",
                observed_at=now,
                payload={
                    "fixture": True,
                    "language": "en",
                    "region": "US",
                    "platform": "youtube",
                    "semantic_key": "demo_subject_alpha",
                    "attention_observed": 180,
                    "eligible_supply_observed": 75,
                    "supply_baseline": 50,
                    "political_sensitive": False,
                },
            ),
            SourceItem(
                source_name=self.name,
                external_id="story-demo-ar",
                observed_at=now,
                payload={
                    "fixture": True,
                    "language": "ar",
                    "region": "SA",
                    "platform": "youtube",
                    "semantic_key": "demo_subject_alpha",
                    "attention_observed": 55,
                    "eligible_supply_observed": 8,
                    "supply_baseline": 40,
                    "political_sensitive": False,
                },
            ),
        ]

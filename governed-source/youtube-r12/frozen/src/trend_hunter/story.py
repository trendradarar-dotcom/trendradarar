from __future__ import annotations

from .ledger import GovernanceLedger, ArtifactRef, LedgerError


class StoryService:
    def __init__(self,ledger:GovernanceLedger): self.ledger=ledger

    def bind_story(self, story_key: str, source_or_claim_state_ids: list[str], *, basis: str, human_reviewed: bool=False) -> ArtifactRef:
        if not source_or_claim_state_ids:
            raise LedgerError("story requires at least one input")
        for sid in source_or_claim_state_ids: self.ledger.get_state(sid)
        identity=self.ledger.get_or_create_identity("STORY",story_key)
        return self.ledger.record_domain(
            "STORY","Story Cluster Authority",
            {
                "story_key":story_key,
                "membership_basis":basis,
                "human_reviewed":human_reviewed,
                "truth_not_asserted":True,
                "topic_not_equated_to_story":True,
            },
            natural_key=f"story-binding:{story_key}:{len(source_or_claim_state_ids)}",
            subject_identity_id=identity,
            record_state="BOUND",
            upstream_states=[(sid,"STORY_MEMBERSHIP_INPUT") for sid in source_or_claim_state_ids],
        )

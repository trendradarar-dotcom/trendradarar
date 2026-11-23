"""Fail-closed local evidence source trust contract.

No external connector, credentials, or production trust authority. An asserted
source identity, access scope or digest never establishes source authenticity.
"""
from __future__ import annotations

import hashlib
import json
import os
import sys
from datetime import datetime, timezone

from .db import connect
from .ledger import GovernanceLedger, LedgerError
from .util import canonical_json_bytes

KIND = "EVIDENCE_SOURCE_TRUST"
STATES = frozenset({"SOURCE_UNVERIFIED", "EVIDENCE_PENDING",
                    "EVIDENCE_CONFLICT", "RECONCILIATION_REQUIRED"})
PLATFORMS = frozenset({"youtube", "tiktok", "instagram", "snapchat"})


def _time(value: str) -> datetime:
    if not isinstance(value, str) or not value:
        raise LedgerError("Timestamp required")
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise LedgerError("Invalid timestamp") from exc
    if dt.tzinfo is None:
        raise LedgerError("Timezone required")
    return dt.astimezone(timezone.utc)


def _synthetic(value) -> bool:
    if isinstance(value, dict):
        if value.get("synthetic_only") is True or value.get("test_authority") or value.get("fixture") is True:
            return True
        return any(_synthetic(k) or _synthetic(v) for k, v in value.items())
    if isinstance(value, (list, tuple)):
        return any(_synthetic(v) for v in value)
    return isinstance(value, str) and ("PUBLISHER_TEST_" in value or "TEST_ONLY" in value)


class EvidenceSourceTrustService:
    def __init__(self, ledger: GovernanceLedger):
        self.ledger = ledger

    def _lineage(self, state_id: str) -> None:
        pending, visited = [state_id], set()
        while pending:
            current = pending.pop()
            if current in visited:
                continue
            visited.add(current)
            state = self.ledger.get_state(current)
            if _synthetic({"state_type": state["state_type"], "payload": state["payload"]}):
                raise LedgerError("Synthetic lineage cannot establish production trust")
            with connect(self.ledger.db_path) as conn:
                rows = conn.execute("SELECT from_state_id FROM provenance_edge WHERE to_state_id=?",
                                    (current,)).fetchall()
            pending.extend(row["from_state_id"] for row in rows)

    def record(self, *, evidence_id: str, declared_source: str, platform: str,
               channel_ref: str, post_id: str, creative_state_id: str,
               content_version: str, access_scope: str, raw_response: bytes,
               claimed_sha256: str, acquired_at: str, valid_from: str,
               valid_until: str, state: str = "SOURCE_UNVERIFIED",
               related_state_id: str | None = None,
               isolated_test: bool = False) -> dict:
        if state not in STATES or platform not in PLATFORMS:
            raise LedgerError("Invalid evidence state or platform")
        if not all(isinstance(x, str) and x.strip() for x in
                   (evidence_id, declared_source, channel_ref, post_id,
                    creative_state_id, content_version, access_scope, claimed_sha256)):
            raise LedgerError("Complete source and publication identity required")
        if not isinstance(raw_response, bytes) or not raw_response:
            raise LedgerError("Raw response bytes required")
        actual_hash = hashlib.sha256(raw_response).hexdigest()
        if claimed_sha256 != actual_hash:
            raise LedgerError("Raw response hash mismatch")
        acquired = _time(acquired_at)
        start, end = _time(valid_from), _time(valid_until)
        if start >= end or not start <= acquired <= end:
            raise LedgerError("Invalid evidence validity window")
        if isolated_test:
            if os.environ.get("TREND_HUNTER_EVIDENCE_TEST_ONLY") != "1" or "pytest" not in sys.modules:
                raise LedgerError("Explicit isolated pytest runtime required")
        if related_state_id:
            related = self.ledger.get_state(related_state_id)
            rp = related["payload"]
            for key, value in (("platform", platform), ("channel_ref", channel_ref),
                               ("creative_state_id", creative_state_id),
                               ("content_version", content_version)):
                if rp.get(key) != value:
                    raise LedgerError("Evidence relationship mismatch: " + key)
            if rp.get("external_post_id", rp.get("post_id")) != post_id:
                raise LedgerError("Evidence post identity mismatch")
            if not isolated_test:
                self._lineage(related_state_id)
        # No production authenticity or access authorization verifier exists.
        # Even a non-synthetic record remains unverified, never production-eligible.
        payload = dict(evidence_id=evidence_id, declared_source=declared_source,
                       source_authenticated=False, access_authorized=False,
                       platform=platform, channel_ref=channel_ref, post_id=post_id,
                       creative_state_id=creative_state_id, content_version=content_version,
                       access_scope=access_scope, claimed_sha256=claimed_sha256,
                       acquired_at=acquired_at, valid_from=valid_from, valid_until=valid_until,
                       state=state, related_state_id=related_state_id,
                       synthetic_only=isolated_test or _synthetic(declared_source),
                       production_eligible=False, automatic_replay_allowed=False,
                       independent_verification="NOT_AVAILABLE")
        return self.ledger.record_evidence_claim_atomic(
            claim_key=evidence_id, payload=payload, raw_bytes=raw_response,
            upstream_state_id=related_state_id)

    def reconcile(self, *, evidence_id: str, decision: str,
                  reason: str, reviewer_ref: str) -> dict:
        return self.ledger.reconcile_evidence_claim(
            claim_key=evidence_id, decision=decision,
            reason=reason, reviewer_ref=reviewer_ref)

    def inspect(self, evidence_id: str) -> dict:
        state = self.ledger.get_latest_state_by_natural_key(
            KIND, "evidence-source:" + evidence_id)
        if not state:
            raise LedgerError("Evidence not found")
        payload = state["payload"]
        return dict(state_id=state["id"], state=payload["state"],
                    raw_hash=state["raw_hash"], source_authenticated=False,
                    access_authorized=False, production_eligible=False,
                    reconciliation_required=True, automatic_replay_allowed=False)

    def verify_production(self, evidence_id: str) -> None:
        raise LedgerError("Independent production source authority is on HOLD")

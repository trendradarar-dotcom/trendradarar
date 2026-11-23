"""Publication outcome evidence contract (local, fail-closed; no provider adapters).

Historical PUBLICATION_EXECUTION records retain their existing semantics.
A provider assertion, including a renamed synthetic record, is NOT verification.
No real verification authority is configured in this isolated slice.
"""
from __future__ import annotations

import hashlib
import json
import sqlite3
from typing import Any

from .db import connect, tx
from .ledger import GovernanceLedger, LedgerError
from .util import canonical_json_bytes, json_dumps, new_id, utcnow

SYNTHETIC_MARKERS = ("PUBLISHER_TEST_", "synthetic_only", "fixture", "test_authority")
STATES = frozenset({"SENT", "RECEIVED", "OUTCOME_UNKNOWN", "RECONCILIATION_REQUIRED",
                    "FAILED_FINAL", "HELD"})


def _reject_synthetic(value: Any) -> None:
    """Reject nested synthetic provenance, even when outer type was renamed."""
    if isinstance(value, dict):
        if value.get("synthetic_only") is True or value.get("fixture") is True:
            raise LedgerError("Synthetic evidence is ineligible for verified publication")
        for k, v in value.items():
            if any(marker in str(k) for marker in SYNTHETIC_MARKERS):
                raise LedgerError("Synthetic evidence marker is forbidden")
            _reject_synthetic(v)
    elif isinstance(value, (list, tuple)):
        for v in value:
            _reject_synthetic(v)
    elif isinstance(value, str) and "PUBLISHER_TEST_" in value:
        raise LedgerError("Synthetic evidence provenance is forbidden")


class PublicationOutcomeService:
    def __init__(self, ledger: GovernanceLedger):
        self.ledger = ledger

    def record_attempt(self, *, command_id: str, idempotency_key: str,
                       creative_state_id: str, authorization_state_id: str,
                       platform: str, target: str, content_version: str,
                       status: str, evidence: dict[str, Any]):
        """Record attempts and unknown outcomes; never assert successful publication."""
        if status not in STATES:
            raise LedgerError("Attempt status cannot assert verified publication")
        if not all([command_id, idempotency_key, creative_state_id,
                    authorization_state_id, platform, target, content_version]):
            raise LedgerError("Exact command, approval, platform, target and version required")
        _reject_synthetic(evidence)
        payload = dict(command_id=command_id, idempotency_key=idempotency_key,
                       creative_state_id=creative_state_id,
                       authorization_state_id=authorization_state_id,
                       platform=platform, target=target, content_version=content_version,
                       status=status, evidence=evidence, verified=False)
        digest = hashlib.sha256(canonical_json_bytes(payload)).hexdigest()
        with tx(self.ledger.db_path) as conn:
            row = conn.execute(
                "SELECT metadata_json FROM artifact_identity WHERE kind=? AND natural_key=?",
                ("PUBLICATION_OUTCOME_ATTEMPT_KEY", idempotency_key)).fetchone()
            if row:
                old = json.loads(row["metadata_json"])
                if old != {"command_id": command_id, "digest": digest}:
                    raise LedgerError("Conflicting publication attempt idempotency key")
            else:
                conn.execute(
                    "INSERT INTO artifact_identity(id,kind,natural_key,metadata_json,created_at) VALUES(?,?,?,?,?)",
                    (new_id("aid"), "PUBLICATION_OUTCOME_ATTEMPT_KEY", idempotency_key,
                     json_dumps({"command_id": command_id, "digest": digest}), utcnow()))
        if row:
            with connect(self.ledger.db_path) as conn:
                existing = conn.execute(
                    """SELECT s.id FROM artifact_state s JOIN artifact_identity i
                       ON s.identity_id=i.id WHERE i.kind='PUBLICATION_OUTCOME_ATTEMPT'
                       AND i.natural_key=? ORDER BY s.version DESC LIMIT 1""",
                    (command_id,)).fetchone()
            if not existing:
                raise LedgerError("Interrupted attempt claim: reconcile; never replay")
            return existing["id"]
        result = self.ledger.record_domain(
            "PUBLICATION_OUTCOME_ATTEMPT", "Publication Outcome Attempts",
            payload, natural_key=command_id, record_state=status)
        return result.state_id

    def inspect(self, command_id: str) -> dict[str, Any]:
        with connect(self.ledger.db_path) as conn:
            row = conn.execute(
                """SELECT s.id,s.payload_json FROM artifact_state s JOIN artifact_identity i
                   ON s.identity_id=i.id WHERE i.kind='PUBLICATION_OUTCOME_ATTEMPT'
                   AND i.natural_key=? ORDER BY s.version DESC LIMIT 1""",
                (command_id,)).fetchone()
        if row is None:
            raise LedgerError("No publication attempt; reconciliation required")
        payload = json.loads(row["payload_json"])
        return {"state_id": row["id"], "status": payload["status"],
                "verified": False, "automatic_resend_allowed": False,
                "reconciliation_required": payload["status"] in
                    {"OUTCOME_UNKNOWN", "RECONCILIATION_REQUIRED", "HELD"}}

    def verify(self, *, attempt_state_id: str, evidence: dict[str, Any]):
        """Fail closed until independent provider evidence trust is authorized.

        The isolated slice has no approved verifier or real provider credentials.
        Even apparently plausible provider IDs are never accepted as proof.
        """
        state = self.ledger.get_state(attempt_state_id)
        if state["state_type"] != "PUBLICATION_OUTCOME_ATTEMPT":
            raise LedgerError("Verified outcome requires a governed publication attempt")
        _reject_synthetic(state.get("payload") or {})
        _reject_synthetic(evidence)
        for key in ("platform", "target", "creative_state_id", "content_version"):
            if evidence.get(key) != state["payload"].get(key):
                raise LedgerError(f"Publication evidence mismatch: {key}")
        if not evidence.get("external_post_id") or not evidence.get("source_ref"):
            raise LedgerError("Independent publication evidence reference required")
        raise LedgerError("Independent provider evidence verifier not authorized; verified publication HOLD")

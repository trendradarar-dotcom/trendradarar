"""Isolated, fail-closed publication performance measurement contract.

No provider client, production verifier, or automatic economic/learning writes.
A positive test may use an explicitly injected verifier, never production authority.
"""
from __future__ import annotations

import hashlib
import os
import sys
import json
from datetime import datetime, timezone
from typing import Any, Callable

from .ledger import GovernanceLedger, LedgerError
from .db import connect, tx
from .util import canonical_json_bytes, json_dumps, new_id, utcnow

PROOF_KIND = "VERIFIED_PUBLICATION_OUTCOME"
MEASUREMENT_KIND = "PUBLICATION_PERFORMANCE_MEASUREMENT"
CLAIM_KIND = "PUBLICATION_PERFORMANCE_CLAIM"


def _synthetic(value: Any) -> bool:
    if isinstance(value, dict):
        if value.get("synthetic_only") is True or value.get("fixture") is True or value.get("test_authority"):
            return True
        return any(_synthetic(k) or _synthetic(v) for k, v in value.items())
    if isinstance(value, (list, tuple)):
        return any(_synthetic(v) for v in value)
    return isinstance(value, str) and ("PUBLISHER_TEST_" in value or "TEST_ONLY" in value)


def _timestamp(value: str) -> datetime:
    if not isinstance(value, str) or not value:
        raise LedgerError("Timestamp is required")
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise LedgerError("Invalid ISO8601 timestamp") from exc
    if dt.tzinfo is None:
        raise LedgerError("Timestamp must include timezone")
    return dt.astimezone(timezone.utc)


class PublicationPerformanceService:
    def __init__(self, ledger: GovernanceLedger, *,
                 isolated_test_verifier: Callable[[dict], bool] | None = None):
        self.ledger = ledger
        self._test_verifier = isolated_test_verifier

    def _publication(self, publication_state_id: str, *, test_only: bool) -> dict:
        pub = self.ledger.get_state(publication_state_id)
        payload = pub.get("payload") or {}
        if pub["state_type"] != PROOF_KIND:
            raise LedgerError("Independently verified publication outcome required")
        if payload.get("verification_status") != "INDEPENDENTLY_VERIFIED":
            raise LedgerError("Independent publication verification missing")
        if test_only:
            if os.environ.get('TREND_HUNTER_PERFORMANCE_TEST_ONLY') != '1' or 'pytest' not in sys.modules:
                raise LedgerError('Isolated performance proof requires explicit pytest runtime')
            if not self._test_verifier or not self._test_verifier(pub):
                raise LedgerError("Isolated test proof verifier rejected publication")
        else:
            # There is no approved production verifier in this isolated slice.
            raise LedgerError("Production publication proof authority is on HOLD")
        return pub

    def record(self, *, publication_state_id: str, platform: str, channel_ref: str,
               external_post_id: str, creative_state_id: str, content_version: str,
               source_ref: str, source_digest: str, observed_at: str,
               window_start: str, window_end: str, metrics: list[dict],
               idempotency_key: str, status: str = "OBSERVED",
               isolated_test: bool = False) -> str:
        if status not in {"OBSERVED", "OUTCOME_UNKNOWN", "RECONCILIATION_REQUIRED"}:
            raise LedgerError("Unsupported performance state")
        if not all(isinstance(v, str) and v.strip() for v in
                   (publication_state_id, platform, channel_ref, external_post_id,
                    creative_state_id, content_version, source_ref, source_digest, idempotency_key)):
            raise LedgerError("Complete publication and evidence identity required")
        if isolated_test is not True and _synthetic((source_ref, metrics)):
            raise LedgerError("Synthetic evidence cannot enter production performance")
        pub = self._publication(publication_state_id, test_only=isolated_test)
        pp = pub["payload"]
        binding = {"platform": platform, "channel_ref": channel_ref,
                   "external_post_id": external_post_id, "creative_state_id": creative_state_id,
                   "content_version": content_version}
        for key, val in binding.items():
            if pp.get(key) != val:
                raise LedgerError("Verified publication binding mismatch: " + key)
        if _timestamp(window_start) >= _timestamp(window_end):
            raise LedgerError("Invalid measurement window")
        if _timestamp(observed_at) < _timestamp(window_start):
            raise LedgerError("Observation predates measurement window")
        if status == "OBSERVED" and not metrics:
            raise LedgerError("Observed performance requires metrics")
        if status != "OBSERVED" and metrics:
            raise LedgerError("Unresolved measurement must not invent metrics")
        names = set()
        for m in metrics:
            if not isinstance(m, dict) or not all(isinstance(m.get(k), str) and m[k].strip()
                                                 for k in ("name", "unit", "definition", "platform")):
                raise LedgerError("Metric definition, unit and platform required")
            if m["platform"] != platform or m["name"] in names:
                raise LedgerError("Metric platform mismatch or duplicate metric")
            names.add(m["name"])
            value = m.get("value")
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not __import__("math").isfinite(value) or value < 0:
                raise LedgerError("Metric value must be finite and nonnegative")
        payload = dict(publication_state_id=publication_state_id, **binding,
                       source_ref=source_ref, source_digest=source_digest,
                       observed_at=observed_at, window_start=window_start,
                       window_end=window_end, metrics=metrics, status=status,
                       synthetic_only=isolated_test, production_eligible=False)
        digest = hashlib.sha256(canonical_json_bytes(payload)).hexdigest()
        claim_key = "performance:" + idempotency_key
        with tx(self.ledger.db_path) as conn:
            prior = conn.execute(
                "SELECT metadata_json FROM artifact_identity WHERE kind=? AND natural_key=?",
                (CLAIM_KIND, claim_key)).fetchone()
            if prior:
                old = json.loads(prior["metadata_json"])
                if old["digest"] != digest:
                    raise LedgerError("Conflicting performance idempotency key; reconcile")
            else:
                conn.execute(
                    "INSERT INTO artifact_identity(id,kind,natural_key,metadata_json,created_at) VALUES(?,?,?,?,?)",
                    (new_id("aid"), CLAIM_KIND, claim_key, json_dumps({"digest": digest}), utcnow()))
        if prior:
            with connect(self.ledger.db_path) as conn:
                row = conn.execute(
                    """SELECT s.id FROM artifact_state s JOIN artifact_identity i ON s.identity_id=i.id
                       WHERE i.kind=? AND i.natural_key=? ORDER BY s.version DESC LIMIT 1""",
                    (MEASUREMENT_KIND, claim_key)).fetchone()
            if not row:
                raise LedgerError("Interrupted performance claim; manual reconciliation required")
            return row["id"]
        result = self.ledger.record_domain(
            MEASUREMENT_KIND, "Publication Performance Measurement",
            payload, natural_key=claim_key, record_state=status,
            upstream_states=[(publication_state_id, "MEASURES_VERIFIED_PUBLICATION")])
        return result.state_id

    def inspect(self, idempotency_key: str) -> dict:
        key = "performance:" + idempotency_key
        with connect(self.ledger.db_path) as conn:
            row = conn.execute(
                """SELECT s.id,s.payload_json FROM artifact_state s JOIN artifact_identity i ON s.identity_id=i.id
                   WHERE i.kind=? AND i.natural_key=? ORDER BY s.version DESC LIMIT 1""",
                (MEASUREMENT_KIND, key)).fetchone()
        if not row:
            raise LedgerError("Measurement missing; manual reconciliation required")
        payload = json.loads(row["payload_json"])
        return {"state_id": row["id"], "status": payload["status"],
                "production_eligible": False, "automatic_replay_allowed": False,
                "reconciliation_required": payload["status"] != "OBSERVED"}

"""Durable local publisher-command journal. No network or real publisher adapters.

SQLite artifact_identity UNIQUE(kind,natural_key) claims are committed before
recording transitions. An interrupted claim fails closed; it never resends.
"""
from __future__ import annotations
import json
import sqlite3
from .db import tx, connect
from .ledger import GovernanceLedger
from .util import new_id, utcnow
from .publisher_contract import ContractError, TEST_AUTHORITY, content_digest, validate_transition

class PublisherCommandJournal:
    def __init__(self, ledger: GovernanceLedger):
        self.ledger = ledger

    def _latest(self, command_id: str):
        with connect(self.ledger.db_path) as conn:
            row = conn.execute(
                """SELECT s.id,s.payload_json FROM artifact_state s
                   JOIN artifact_identity i ON i.id=s.identity_id
                   WHERE i.kind='PUBLISHER_TEST_COMMAND'
                     AND i.natural_key=?
                     AND s.state_type='PUBLISHER_TEST_COMMAND'
                   ORDER BY s.version DESC LIMIT 1""", (command_id,)
            ).fetchone()
        if row is None:
            raise ContractError("Missing command or interrupted claim: manual reconciliation required")
        return row["id"], json.loads(row["payload_json"])

    def create(self, command_id: str, idempotency_key: str, platform: str,
               target: str, content: dict):
        if not command_id or not idempotency_key:
            raise ContractError("Command and idempotency identifiers required")
        digest = content_digest(platform, target, content)
        with tx(self.ledger.db_path) as conn:
            existing = conn.execute(
                "SELECT metadata_json FROM artifact_identity WHERE kind=? AND natural_key=?",
                ("PUBLISHER_TEST_IDEMPOTENCY", idempotency_key)
            ).fetchone()
            if existing:
                meta = json.loads(existing["metadata_json"])
                if meta != {"command_id": command_id, "digest": digest}:
                    raise ContractError("Idempotency key reused with different command/content")
            else:
                conn.execute(
                    "INSERT INTO artifact_identity(id,kind,natural_key,metadata_json,created_at) VALUES(?,?,?,?,?)",
                    (new_id("aid"), "PUBLISHER_TEST_IDEMPOTENCY", idempotency_key,
                     json.dumps({"command_id": command_id, "digest": digest}), utcnow())
                )
        if existing:
            return self._latest(command_id)
        # A crash after the atomic claim fails closed on replay, never dispatches.
        ref = self.ledger.record_domain(
            "PUBLISHER_TEST_COMMAND", "Synthetic Publisher Command Authority",
            {"command_id": command_id, "idempotency_key": idempotency_key,
             "digest": digest, "platform": platform, "target": target,
             "state": "CREATED", "synthetic_only": True, "evidence": "local-create"},
            natural_key=command_id, record_state="CREATED")
        return ref.state_id, self.ledger.get_state(ref.state_id)["payload"]

    def advance(self, command_id: str, expected_state_id: str, next_state: str,
                evidence: str, *, test_authority: str = ""):
        # Atomic arbitration on the exact predecessor. No external side effect.
        with tx(self.ledger.db_path) as conn:
            row = conn.execute(
                """SELECT s.id,s.payload_json FROM artifact_state s
                   JOIN artifact_identity i ON i.id=s.identity_id
                   WHERE i.kind='PUBLISHER_TEST_COMMAND' AND i.natural_key=?
                   ORDER BY s.version DESC LIMIT 1""", (command_id,)
            ).fetchone()
            if not row or row["id"] != expected_state_id:
                raise ContractError("Stale or missing predecessor; no automatic replay")
            payload = json.loads(row["payload_json"])
            validate_transition(payload["state"], next_state, evidence=evidence,
                                test_authority=test_authority)
            try:
                conn.execute(
                    "INSERT INTO artifact_identity(id,kind,natural_key,metadata_json,created_at) VALUES(?,?,?,?,?)",
                    (new_id("aid"), "PUBLISHER_TEST_TRANSITION_CLAIM",
                     expected_state_id, json.dumps({"next": next_state}), utcnow())
                )
            except sqlite3.IntegrityError as exc:
                raise ContractError("Transition already claimed; reconciliation required") from exc
        # Failure after the durable claim remains a HOLD; no retry side effect.
        next_payload = dict(payload, state=next_state, evidence=evidence,
                            previous_state_id=expected_state_id)
        ref = self.ledger.record_domain(
            "PUBLISHER_TEST_COMMAND", "Synthetic Publisher Command Authority",
            next_payload, natural_key=command_id, record_state=next_state,
            upstream_states=[(expected_state_id, "PUBLISHER_TEST_PREDECESSOR")])
        return ref.state_id, next_payload

    def dispatch_to_synthetic(self, command_id: str, expected_state_id: str,
                              evidence: str):
        # Not an adapter: only writes a synthetic state. No HTTP or provider calls.
        return self.advance(command_id, expected_state_id, "DISPATCHED",
                            evidence, test_authority=TEST_AUTHORITY)

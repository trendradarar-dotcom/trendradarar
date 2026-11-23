"""Offline-only governed publisher command contract; no platform credentials or clients."""
from __future__ import annotations
from dataclasses import dataclass
from hashlib import sha256
import json

class ContractError(ValueError):
    pass

STATES = frozenset({
    "CREATED", "AUTHORIZED_FOR_TEST", "DISPATCHED", "RECEIVED",
    "EXECUTING", "RESULT_REPORTED", "RESULT_VERIFIED", "RECONCILED",
    "HELD", "FAILED_RETRYABLE", "FAILED_FINAL", "OUTCOME_UNKNOWN",
    "RECONCILIATION_REQUIRED", "CANCELLED",
})
TRANSITIONS = {
    "CREATED": {"AUTHORIZED_FOR_TEST", "HELD", "CANCELLED"},
    "AUTHORIZED_FOR_TEST": {"DISPATCHED", "HELD", "CANCELLED"},
    "DISPATCHED": {"RECEIVED", "FAILED_RETRYABLE", "FAILED_FINAL", "OUTCOME_UNKNOWN"},
    "RECEIVED": {"EXECUTING", "OUTCOME_UNKNOWN", "FAILED_FINAL"},
    "EXECUTING": {"RESULT_REPORTED", "FAILED_FINAL", "OUTCOME_UNKNOWN"},
    "RESULT_REPORTED": {"RESULT_VERIFIED", "RECONCILIATION_REQUIRED"},
    "RESULT_VERIFIED": {"RECONCILED", "RECONCILIATION_REQUIRED"},
    "FAILED_RETRYABLE": {"DISPATCHED", "HELD", "CANCELLED"},
    "OUTCOME_UNKNOWN": {"RECONCILIATION_REQUIRED"},
    "RECONCILIATION_REQUIRED": {"RESULT_VERIFIED", "FAILED_FINAL", "HELD"},
    "HELD": {"CANCELLED"},
    "FAILED_FINAL": set(),
    "CANCELLED": set(),
    "RECONCILED": set(),
}
# This is a structural test authority, never a real publication authorization.
TEST_AUTHORITY = "SYNTHETIC_TEST_ONLY"

def content_digest(platform: str, target: str, content: dict) -> str:
    if platform not in {"youtube", "tiktok", "instagram", "snapchat"}:
        raise ContractError("Unsupported publisher target")
    if not target or not isinstance(content, dict):
        raise ContractError("Invalid target/content")
    raw = json.dumps({"platform": platform, "target": target, "content": content},
                     sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return sha256(raw.encode("utf-8")).hexdigest()

def validate_transition(current: str, next_state: str, *, evidence: str,
                        test_authority: str = "") -> None:
    if current not in STATES or next_state not in TRANSITIONS[current]:
        raise ContractError(f"Illegal transition: {current} -> {next_state}")
    if not isinstance(evidence, str) or not evidence.strip():
        raise ContractError("Auditable transition evidence required")
    if next_state == "AUTHORIZED_FOR_TEST" and test_authority != TEST_AUTHORITY:
        raise ContractError("Only explicit synthetic-test authority is allowed")
    if next_state == "DISPATCHED" and test_authority != TEST_AUTHORITY:
        raise ContractError("No real publisher dispatch authority")
    if current == "OUTCOME_UNKNOWN" and next_state != "RECONCILIATION_REQUIRED":
        raise ContractError("Unknown outcome cannot be retried automatically")

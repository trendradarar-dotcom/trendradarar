"""Test-only bridge: governed recommendation -> synthetic publisher journal.

No provider adapters, HTTP clients, revenue, measurement, or learning writes.
"""
from __future__ import annotations
import os
import sys
from .ledger import GovernanceLedger, LedgerError
from .operations import OperationsService
from .publisher_dispatch import PublisherCommandJournal
from .publisher_contract import ContractError, TEST_AUTHORITY

def assert_test_runtime() -> None:
    # Both conditions are required; setting an environment variable in production
    # cannot independently activate the bridge.
    if os.environ.get("TREND_HUNTER_PUBLISHER_BRIDGE_TEST_ONLY") != "1" or "pytest" not in sys.modules:
        raise ContractError("Publisher bridge is restricted to explicit pytest runtime")

class PublisherEngineBridge:
    def __init__(self, ledger: GovernanceLedger):
        self.ledger = ledger
        self.operations = OperationsService(ledger)
        self.journal = PublisherCommandJournal(ledger)

    def create(self, *, creative_state_id: str, authorization_state_id: str,
               channel_binding_state_id: str, platform: str, target: str,
               command_id: str, idempotency_key: str):
        assert_test_runtime()
        # Reuse the existing governed execution gate. No new authorization.
        gate = self.operations.validate_publication_execution_gate(
            creative_state_id, authorization_state_id,
            channel_binding_state_id=channel_binding_state_id,
            require_bound_channel=True)
        auth = gate["authorization"]["payload"]
        channel = gate["channel_state"]["payload"]
        if auth.get("platform") != platform or channel.get("platform") != platform:
            raise ContractError("Platform does not match exact authorization and binding")
        if str(channel.get("channel_ref") or "") != target or auth.get("channel_ref") != target:
            raise ContractError("Destination does not match exact authorization and binding")
        if not auth.get("exact_content_version_bound") or not auth.get("exact_channel_state_bound"):
            raise ContractError("Authorization lacks exact content/channel version")
        creative = gate["creative"]
        # Immutable state id and canonical digest bind the command to content version.
        content = {"creative_state_id": creative_state_id,
                   "canonical_hash": creative["canonical_hash"],
                   "authorization_state_id": authorization_state_id,
                   "recommendation_state_id": gate["recommendation_state_id"],
                   "synthetic_only": True}
        return self.journal.create(command_id, idempotency_key, platform, target, content)

    def authorize_test(self, command_id: str, expected_state_id: str):
        assert_test_runtime()
        return self.journal.advance(command_id, expected_state_id,
                                    "AUTHORIZED_FOR_TEST", "synthetic-test-only",
                                    test_authority=TEST_AUTHORITY)

    def dispatch(self, command_id: str, expected_state_id: str):
        assert_test_runtime()
        return self.journal.dispatch_to_synthetic(command_id, expected_state_id,
                                                   "synthetic-no-provider-call")

    def reconcile(self, command_id: str, expected_state_id: str,
                  next_state: str, evidence: str):
        assert_test_runtime()
        # Reconciliation never invokes dispatch; no automatic retry from UNKNOWN.
        if next_state not in {"RECONCILIATION_REQUIRED", "RESULT_VERIFIED",
                              "FAILED_FINAL", "HELD", "RECONCILED"}:
            raise ContractError("Reconciliation cannot dispatch or retry")
        return self.journal.advance(command_id, expected_state_id,
                                    next_state, evidence)

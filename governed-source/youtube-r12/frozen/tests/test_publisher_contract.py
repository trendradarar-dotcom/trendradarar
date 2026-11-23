import pytest
from trend_hunter.publisher_contract import (
    ContractError, TEST_AUTHORITY, content_digest, validate_transition,
)

def test_content_digest_deterministic_and_target_bound():
    a = content_digest("youtube", "test-channel", {"x": 1, "y": 2})
    assert a == content_digest("youtube", "test-channel", {"y": 2, "x": 1})
    assert a != content_digest("youtube", "other-channel", {"x": 1, "y": 2})
    assert a != content_digest("youtube", "test-channel", {"x": 3, "y": 2})

@pytest.mark.parametrize("current,next_state", [
    ("CREATED", "RECEIVED"), ("RECEIVED", "RESULT_VERIFIED"),
    ("OUTCOME_UNKNOWN", "DISPATCHED"), ("RECONCILED", "DISPATCHED"),
    ("FAILED_FINAL", "DISPATCHED"), ("RESULT_REPORTED", "RECONCILED"),
])
def test_illegal_transitions(current, next_state):
    with pytest.raises(ContractError):
        validate_transition(current, next_state, evidence="synthetic")

def test_authorized_for_test_is_not_real_publication_authority():
    with pytest.raises(ContractError):
        validate_transition("CREATED", "AUTHORIZED_FOR_TEST", evidence="e")
    with pytest.raises(ContractError):
        validate_transition("AUTHORIZED_FOR_TEST", "DISPATCHED", evidence="e")
    validate_transition("CREATED", "AUTHORIZED_FOR_TEST", evidence="e",
                        test_authority=TEST_AUTHORITY)

def test_evidence_is_required():
    with pytest.raises(ContractError):
        validate_transition("DISPATCHED", "RECEIVED", evidence="")

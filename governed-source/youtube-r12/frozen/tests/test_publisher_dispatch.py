from concurrent.futures import ThreadPoolExecutor
import pytest
from trend_hunter.db import init_db
from trend_hunter.ledger import GovernanceLedger
from trend_hunter.publisher_contract import ContractError, TEST_AUTHORITY
from trend_hunter.publisher_dispatch import PublisherCommandJournal

@pytest.fixture
def journal(tmp_path):
    db = str(tmp_path / "publisher.sqlite")
    init_db(db)
    return PublisherCommandJournal(GovernanceLedger(db, str(tmp_path / "objects")))

def test_restart_and_key_collision(journal):
    state, data = journal.create("cmd-1", "key-1", "youtube", "test", {"text": "a"})
    restarted = PublisherCommandJournal(GovernanceLedger(journal.ledger.db_path,
                                                         journal.ledger.storage_dir))
    again, payload = restarted.create("cmd-1", "key-1", "youtube", "test", {"text": "a"})
    assert state == again and payload["state"] == "CREATED"
    with pytest.raises(ContractError):
        restarted.create("cmd-2", "key-1", "youtube", "test", {"text": "different"})

def test_receipt_is_not_publication_and_reconciliation(journal):
    sid, _ = journal.create("cmd-2", "key-2", "youtube", "test", {"text": "a"})
    sid, _ = journal.advance("cmd-2", sid, "AUTHORIZED_FOR_TEST", "synthetic approval",
                             test_authority=TEST_AUTHORITY)
    sid, _ = journal.dispatch_to_synthetic("cmd-2", sid, "synthetic send")
    sid, received = journal.advance("cmd-2", sid, "RECEIVED", "synthetic receipt")
    assert received["state"] == "RECEIVED" and received["synthetic_only"]
    with pytest.raises(ContractError):
        journal.advance("cmd-2", sid, "RESULT_VERIFIED", "no result")
    sid, _ = journal.advance("cmd-2", sid, "OUTCOME_UNKNOWN", "timeout")
    with pytest.raises(ContractError):
        journal.dispatch_to_synthetic("cmd-2", sid, "unsafe replay")
    sid, _ = journal.advance("cmd-2", sid, "RECONCILIATION_REQUIRED", "reconcile")
    sid, _ = journal.advance("cmd-2", sid, "RESULT_VERIFIED", "synthetic result proof")
    sid, done = journal.advance("cmd-2", sid, "RECONCILED", "synthetic audit proof")
    assert done["state"] == "RECONCILED"

def test_concurrent_same_predecessor_only_one_wins(journal):
    sid, _ = journal.create("cmd-3", "key-3", "youtube", "test", {"text": "a"})
    def attempt(_):
        try:
            return journal.advance("cmd-3", sid, "AUTHORIZED_FOR_TEST", "test",
                                   test_authority=TEST_AUTHORITY)[0]
        except ContractError:
            return None
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(attempt, range(2)))
    assert sum(x is not None for x in results) == 1

def test_unknown_outcome_never_retries(journal):
    sid, _ = journal.create("cmd-4", "key-4", "tiktok", "test", {"text": "a"})
    sid, _ = journal.advance("cmd-4", sid, "AUTHORIZED_FOR_TEST", "test",
                             test_authority=TEST_AUTHORITY)
    sid, _ = journal.dispatch_to_synthetic("cmd-4", sid, "synthetic")
    sid, _ = journal.advance("cmd-4", sid, "OUTCOME_UNKNOWN", "synthetic timeout")
    with pytest.raises(ContractError):
        journal.dispatch_to_synthetic("cmd-4", sid, "retry")

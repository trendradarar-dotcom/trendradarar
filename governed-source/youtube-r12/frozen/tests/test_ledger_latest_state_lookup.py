from trend_hunter.db import init_db
from trend_hunter.ledger import GovernanceLedger


def test_get_latest_state_by_natural_key_returns_newest_version(tmp_path):
    db_path = str(tmp_path / "ledger.db")
    init_db(db_path)
    ledger = GovernanceLedger(db_path)

    first = ledger.record_domain(
        "EVIDENCE",
        "Test Review Authority",
        {"value": 1},
        natural_key="test-review:creative-1",
    )
    second = ledger.record_domain(
        "EVIDENCE",
        "Test Review Authority",
        {"value": 2},
        natural_key="test-review:creative-1",
    )

    assert first.state_id != second.state_id

    latest = ledger.get_latest_state_by_natural_key(
        "EVIDENCE",
        "test-review:creative-1",
    )

    assert latest is not None
    assert latest["id"] == second.state_id
    assert latest["state_type"] == "EVIDENCE"
    assert latest["payload"]["value"] == 2

    assert (
        ledger.get_latest_state_by_natural_key(
            "EVIDENCE",
            "test-review:missing",
        )
        is None
    )
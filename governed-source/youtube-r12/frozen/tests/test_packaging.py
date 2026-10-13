from __future__ import annotations

import shutil
import sys
from pathlib import Path

from trend_hunter.db import init_db
from trend_hunter.ledger import GovernanceLedger


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import verify_delivery  # noqa: E402


def test_content_descriptors_use_logical_content_addressed_refs(tmp_path: Path):
    db = tmp_path / "trend_hunter.db"
    init_db(str(db))
    ledger = GovernanceLedger(str(db))
    iid = ledger.get_or_create_identity("TEST", "logical-object-ref")
    state = ledger.create_state(iid, "TEST_STATE", {"x": 1}, raw_bytes=b"raw bytes")
    loaded = ledger.get_state(state.state_id)
    assert loaded["raw_storage_ref"] == f"object://sha256/{loaded['raw_hash']}"
    assert loaded["canonical_storage_ref"] == f"object://sha256/{loaded['canonical_hash']}"
    assert ledger.resolve_storage_ref(loaded["raw_storage_ref"]).is_file()
    assert ledger.integrity_check()["ok"] is True


def test_delivery_state_is_relocatable_after_original_root_removed(tmp_path: Path):
    build_root = tmp_path / "build_A"
    extract_root = tmp_path / "extract_B"
    build_root.mkdir()
    extract_root.mkdir()

    db_a = build_root / "trend_hunter.db"
    init_db(str(db_a))
    ledger_a = GovernanceLedger(str(db_a))
    iid = ledger_a.get_or_create_identity("TEST", "relocation")
    st = ledger_a.create_state(iid, "TEST_STATE", {"relocatable": True}, raw_bytes=b"portable")
    assert ledger_a.integrity_check()["ok"] is True
    # Packaging must checkpoint WAL state into the portable main DB before copying/zipping.
    from trend_hunter.db import connect
    with connect(str(db_a)) as conn:
        conn.execute("PRAGMA wal_checkpoint(TRUNCATE)").fetchall()

    shutil.copy2(db_a, extract_root / "trend_hunter.db")
    shutil.copytree(build_root / "trend_hunter_objects", extract_root / "trend_hunter_objects")
    shutil.rmtree(build_root)
    assert not build_root.exists()

    ledger_b = GovernanceLedger(str(extract_root / "trend_hunter.db"))
    loaded = ledger_b.get_state(st.state_id)
    assert loaded["raw_storage_ref"].startswith("object://sha256/")
    assert ledger_b.resolve_storage_ref(loaded["raw_storage_ref"]).is_file()
    assert ledger_b.integrity_check()["ok"] is True


def test_full_verification_cannot_pass_when_tests_are_skipped():
    skipped = verify_delivery.test_execution_plan("FULL_DELIVERY_VERIFICATION", True)
    assert skipped is not None
    assert skipped["executed"] is False
    assert skipped["ok"] is False
    assert verify_delivery.derive_engineering_package_verified(True, "FULL_DELIVERY_VERIFICATION", skipped) is False


def test_integrity_only_scope_never_claims_full_engineering_verification():
    skipped = verify_delivery.test_execution_plan("INTEGRITY_ONLY_VERIFICATION", True)
    assert skipped is not None
    assert skipped["ok"] is True
    assert verify_delivery.derive_engineering_package_verified(True, "INTEGRITY_ONLY_VERIFICATION", skipped) is False


def test_snapshot_manifest_uses_relocatable_delivery_path():
    import json
    meta = json.loads((ROOT / "data" / "snapshot_manifest.json").read_text(encoding="utf-8"))
    declared = Path(meta["path"])
    assert not declared.is_absolute()
    assert ".." not in declared.parts
    assert declared.as_posix() == "data/ledger_snapshot.json"


def test_packaged_backup_smoke_report_redacts_builder_temporary_paths():
    import json
    meta = json.loads((ROOT / "data" / "backup_restore_smoke.json").read_text(encoding="utf-8"))
    assert meta["builder_temporary_paths_redacted"] is True
    assert meta["backup"]["backup"] == "BUILD_TEMPORARY_BACKUP_ARCHIVE__NOT_PACKAGED"
    assert meta["restore"]["destination"] == "BUILD_TEMPORARY_RESTORE_DIRECTORY__NOT_PACKAGED"


def test_run_checks_executes_one_inprocess_full_pytest_run(monkeypatch):
    import pytest
    import run_checks

    seen = {}

    def fake_pytest_main(args):
        seen["args"] = list(args)
        return 7

    class ExitObserved(BaseException):
        pass

    def fake_exit(code):
        seen["exit_code"] = code
        raise ExitObserved()

    monkeypatch.delenv("PYTEST_DISABLE_PLUGIN_AUTOLOAD", raising=False)
    monkeypatch.setattr("pytest.main", fake_pytest_main)
    monkeypatch.setattr(run_checks.os, "_exit", fake_exit)
    with pytest.raises(ExitObserved):
        run_checks.main()

    assert seen["args"] == ["-q", "-p", "no:cacheprovider"]
    assert run_checks.os.environ["PYTEST_DISABLE_PLUGIN_AUTOLOAD"] == "1"
    assert seen["exit_code"] == 7

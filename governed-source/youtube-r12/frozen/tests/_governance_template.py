from __future__ import annotations

import atexit
import shutil
import tempfile
from pathlib import Path

from trend_hunter.bootstrap import bootstrap_governance
from trend_hunter.db import init_db
from trend_hunter.ledger import GovernanceLedger

_TEMPLATE_ROOT = Path(tempfile.mkdtemp(prefix='trend-hunter-test-governance-'))
_TEMPLATE_DB = _TEMPLATE_ROOT / 'template.db'
_TEMPLATE_OBJ = _TEMPLATE_ROOT / 'objects'
_READY = False
_ACTIVE_CLONES: set[Path] = set()


def _cleanup() -> None:
    shutil.rmtree(_TEMPLATE_ROOT, ignore_errors=True)


atexit.register(_cleanup)


def _ensure_template() -> None:
    global _READY
    if _READY:
        return
    init_db(str(_TEMPLATE_DB))
    ledger = GovernanceLedger(str(_TEMPLATE_DB), str(_TEMPLATE_OBJ))
    bootstrap_governance(ledger)
    assert ledger.integrity_check()['ok'] is True
    _READY = True


def cleanup_isolated_governance_ledgers() -> None:
    """Remove per-test writable clones while preserving the pristine process template."""
    for root in tuple(_ACTIVE_CLONES):
        shutil.rmtree(root, ignore_errors=True)
        _ACTIVE_CLONES.discard(root)


def isolated_governance_ledger(tmp_path: Path, name: str) -> GovernanceLedger:
    """Clone a pristine governed baseline into a private writable test store."""
    _ensure_template()
    root = tmp_path / f'governed-{name}'
    root.mkdir(parents=True)
    db = root / 'ledger.db'
    obj = root / 'objects'
    shutil.copy2(_TEMPLATE_DB, db)
    shutil.copytree(_TEMPLATE_OBJ, obj)
    _ACTIVE_CLONES.add(root)
    return GovernanceLedger(str(db), str(obj))

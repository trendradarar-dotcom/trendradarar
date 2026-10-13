from __future__ import annotations

import hashlib
import json
import shutil
import sqlite3
import tempfile
import zipfile
from pathlib import Path

from .ledger import GovernanceLedger, LedgerError


class BackupError(RuntimeError):
    pass


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def create_backup(db_path: str, output_zip: str) -> dict:
    db = Path(db_path).resolve()
    if not db.is_file():
        raise BackupError(f"Database not found: {db}")
    ledger = GovernanceLedger(str(db))
    integrity = ledger.integrity_check()
    if not integrity.get("ok"):
        raise BackupError(f"Refusing to back up an integrity-failing ledger: {integrity['issues']}")

    objects = Path(ledger.storage_dir).resolve()
    output = Path(output_zip).resolve()
    output.parent.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory(prefix="trend-hunter-backup-") as td:
        root = Path(td)
        portable_db = root / "trend_hunter.db"
        src = sqlite3.connect(str(db))
        dst = sqlite3.connect(str(portable_db))
        try:
            src.backup(dst)
        finally:
            dst.close(); src.close()

        copied_objects = root / "trend_hunter_objects"
        shutil.copytree(objects, copied_objects)

        files = []
        for p in sorted(root.rglob("*")):
            if p.is_file():
                files.append({"path": p.relative_to(root).as_posix(), "sha256": _sha256(p), "size": p.stat().st_size})
        manifest = {
            "backup_format": "trend-hunter-operational-backup-v1",
            "source_integrity": integrity,
            "files": files,
        }
        (root / "BACKUP_MANIFEST.json").write_text(json.dumps(manifest, sort_keys=True, indent=2), encoding="utf-8")
        with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as z:
            for p in sorted(root.rglob("*")):
                if p.is_file():
                    z.write(p, p.relative_to(root).as_posix())

    return {"ok": True, "backup": str(output), "sha256": _sha256(output), "file_count": len(files) + 1}


def restore_backup(backup_zip: str, destination_dir: str) -> dict:
    backup = Path(backup_zip).resolve()
    dest = Path(destination_dir).resolve()
    if dest.exists() and any(dest.iterdir()):
        raise BackupError("Restore destination must be empty")
    dest.mkdir(parents=True, exist_ok=True)

    with zipfile.ZipFile(backup) as z:
        for info in z.infolist():
            target = (dest / info.filename).resolve()
            try:
                target.relative_to(dest)
            except ValueError as exc:
                raise BackupError("Backup contains path traversal") from exc
        z.extractall(dest)

    manifest_path = dest / "BACKUP_MANIFEST.json"
    if not manifest_path.is_file():
        raise BackupError("Backup manifest missing")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    mismatches = []
    for item in manifest.get("files", []):
        p = dest / item["path"]
        if not p.is_file() or _sha256(p) != item["sha256"] or p.stat().st_size != item["size"]:
            mismatches.append(item["path"])
    if mismatches:
        raise BackupError(f"Backup hash verification failed: {mismatches}")

    db = dest / "trend_hunter.db"
    ledger = GovernanceLedger(str(db), str(dest / "trend_hunter_objects"))
    integrity = ledger.integrity_check()
    if not integrity.get("ok"):
        raise BackupError(f"Restored ledger integrity failed: {integrity['issues']}")
    return {"ok": True, "destination": str(dest), "integrity": integrity, "verified_files": len(manifest.get("files", []))}

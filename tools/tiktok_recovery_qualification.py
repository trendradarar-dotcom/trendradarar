import argparse
import hashlib
import json
import os
import secrets
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SERVICE_DIR = ROOT / "tiktok_oauth_service"
if str(SERVICE_DIR) not in sys.path:
    sys.path.insert(0, str(SERVICE_DIR))

from durable_state import DurableState, DurableStateError  # noqa: E402


DEFAULT_MARKER_KEY = "production-recovery-qualification"


def _keys_from_env():
    raw = os.environ.get("TIKTOK_STATE_ENCRYPTION_KEYS", "").strip()
    if not raw:
        raw = os.environ.get("TIKTOK_STATE_ENCRYPTION_KEY", "").strip()
    keys = [x.strip() for x in raw.split(",") if x.strip()]
    if not keys:
        raise DurableStateError("state encryption key is required")
    return keys


def _store():
    return DurableState.from_env()


def _sha(value):
    return hashlib.sha256(str(value).encode("utf-8")).hexdigest()


def _emit(payload):
    print(json.dumps(payload, sort_keys=True, separators=(",", ":")))


def cmd_write_marker(args):
    store = _store()
    value = secrets.token_urlsafe(32)
    store.set_recovery_marker(args.marker_key, value)
    marker = store.get_recovery_marker(args.marker_key)
    if not marker or marker["value"] != value:
        raise DurableStateError("recovery marker write verification failed")
    _emit({
        "ok": True,
        "action": "write-marker",
        "marker_key": args.marker_key,
        "marker_sha256": _sha(value),
        "database_health": store.health(),
    })


def cmd_verify_marker(args):
    store = _store()
    marker = store.get_recovery_marker(args.marker_key)
    if not marker:
        raise DurableStateError("recovery marker missing")
    actual = _sha(marker["value"])
    if actual != args.expected_sha256.lower():
        raise DurableStateError("recovery marker hash mismatch")
    _emit({
        "ok": True,
        "action": "verify-marker",
        "marker_key": args.marker_key,
        "marker_sha256": actual,
        "database_health": store.health(),
    })


def cmd_backup(args):
    store = _store()
    result = store.backup_to(args.destination)
    marker = store.get_recovery_marker(args.marker_key)
    _emit({
        "ok": True,
        "action": "backup",
        "backup_path": result["path"],
        "backup_sha256": result["sha256"],
        "marker_present": bool(marker),
        "marker_sha256": _sha(marker["value"]) if marker else None,
    })


def cmd_restore_verify(args):
    restored = DurableState.restore_backup(
        args.backup,
        args.target,
        _keys_from_env(),
    )
    marker = restored.get_recovery_marker(args.marker_key)
    if not marker:
        raise DurableStateError("recovery marker missing after restore")
    actual = _sha(marker["value"])
    if actual != args.expected_sha256.lower():
        raise DurableStateError("restored recovery marker hash mismatch")
    backend = os.environ.get("TIKTOK_STATE_BACKEND", "sqlite").strip().lower()
    restored_target = (
        "postgresql-target"
        if backend in ("postgres", "postgresql")
        else str(Path(args.target).resolve())
    )
    _emit({
        "ok": True,
        "action": "restore-verify",
        "marker_key": args.marker_key,
        "marker_sha256": actual,
        "restored_health": restored.health(),
        "restored_target": restored_target,
    })


def cmd_cleanup(args):
    store = _store()
    deleted = store.delete_recovery_marker(args.marker_key)
    _emit({
        "ok": True,
        "action": "cleanup-marker",
        "marker_key": args.marker_key,
        "deleted": bool(deleted),
    })


def build_parser():
    parser = argparse.ArgumentParser(
        description="TikTok production persistence / backup / restore qualification helper"
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("write-marker")
    p.add_argument("--marker-key", default=DEFAULT_MARKER_KEY)
    p.set_defaults(func=cmd_write_marker)

    p = sub.add_parser("verify-marker")
    p.add_argument("--marker-key", default=DEFAULT_MARKER_KEY)
    p.add_argument("--expected-sha256", required=True)
    p.set_defaults(func=cmd_verify_marker)

    p = sub.add_parser("backup")
    p.add_argument("--marker-key", default=DEFAULT_MARKER_KEY)
    p.add_argument("--destination", required=True)
    p.set_defaults(func=cmd_backup)

    p = sub.add_parser("restore-verify")
    p.add_argument("--marker-key", default=DEFAULT_MARKER_KEY)
    p.add_argument("--backup", required=True)
    p.add_argument(
        "--target",
        required=True,
        help="SQLite absolute target path or PostgreSQL target URL; never logged for PostgreSQL",
    )
    p.add_argument("--expected-sha256", required=True)
    p.set_defaults(func=cmd_restore_verify)

    p = sub.add_parser("cleanup-marker")
    p.add_argument("--marker-key", default=DEFAULT_MARKER_KEY)
    p.set_defaults(func=cmd_cleanup)
    return parser


def main():
    args = build_parser().parse_args()
    try:
        args.func(args)
    except DurableStateError as exc:
        _emit({"ok": False, "error": str(exc), "action": args.command})
        raise SystemExit(2)


if __name__ == "__main__":
    main()

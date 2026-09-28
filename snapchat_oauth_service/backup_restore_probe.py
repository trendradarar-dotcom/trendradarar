import os
import sys

from state_store import DurableStateStore


PROFILE_ID = "backup-restore-profile"
PUBLICATION_ID = "backup-restore-publication-20260928"
REMOTE_ID = "backup_restore_spotlight_12345678"


def seed(url: str) -> None:
    store = DurableStateStore(url)
    store.init_schema()
    admission = store.begin_publication(
        profile_id=PROFILE_ID,
        publication_id=PUBLICATION_ID,
        correlation_id="backup-restore-correlation-0001",
        description="backup-restore-evidence",
        media_sha256="b" * 64,
        duration=35.0,
        width=1080,
        height=1920,
        max_hour=100,
        max_day=100,
        max_concurrent=10,
        max_attempts=2,
        retry_horizon_seconds=1800,
    )
    if not admission["created"]:
        raise RuntimeError("backup_fixture_was_not_created")
    for before, after in (
        ("RECEIVED", "VALIDATED"),
        ("VALIDATED", "MEDIA_CREATING"),
        ("MEDIA_CREATING", "MEDIA_UPLOADING"),
    ):
        store.transition(
            profile_id=PROFILE_ID,
            publication_id=PUBLICATION_ID,
            allowed_from=(before,),
            new_state=after,
        )
    store.transition(
        profile_id=PROFILE_ID,
        publication_id=PUBLICATION_ID,
        allowed_from=("MEDIA_UPLOADING",),
        new_state="SUBMITTING",
        remote_media_id="backup_restore_media_12345678",
        mark_submit_started=True,
    )
    store.transition(
        profile_id=PROFILE_ID,
        publication_id=PUBLICATION_ID,
        allowed_from=("SUBMITTING",),
        new_state="SUBMITTED",
        remote_media_id="backup_restore_media_12345678",
        remote_spotlight_id=REMOTE_ID,
    )
    print("backup fixture seeded")


def verify(url: str) -> None:
    store = DurableStateStore(url)
    row = store.get_publication(PROFILE_ID, PUBLICATION_ID)
    if not row:
        raise RuntimeError("restored_publication_missing")
    if row["state"] != "SUBMITTED":
        raise RuntimeError(f"restored_state_mismatch:{row['state']}")
    if row.get("remote_spotlight_id") != REMOTE_ID:
        raise RuntimeError("restored_remote_id_mismatch")

    duplicate = store.begin_publication(
        profile_id=PROFILE_ID,
        publication_id=PUBLICATION_ID,
        correlation_id="backup-restore-correlation-0002",
        description="backup-restore-evidence",
        media_sha256="b" * 64,
        duration=35.0,
        width=1080,
        height=1920,
        max_hour=100,
        max_day=100,
        max_concurrent=10,
        max_attempts=2,
        retry_horizon_seconds=1800,
    )
    if duplicate["created"] or duplicate["retry_admitted"]:
        raise RuntimeError("restore_allowed_duplicate_publication")
    if duplicate["row"]["state"] != "SUBMITTED":
        raise RuntimeError("restored_duplicate_guard_state_mismatch")
    print("backup/restore duplicate-prevention verification passed")


def main() -> int:
    if len(sys.argv) != 3 or sys.argv[1] not in {"seed", "verify"}:
        print("usage: backup_restore_probe.py <seed|verify> <postgres_url>", file=sys.stderr)
        return 2
    mode, url = sys.argv[1], sys.argv[2]
    if not url.startswith("postgres"):
        raise RuntimeError("postgres_url_required")
    if mode == "seed":
        seed(url)
    else:
        verify(url)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

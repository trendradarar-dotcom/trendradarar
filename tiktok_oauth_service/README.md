# Trend Radar TikTok OAuth service

Isolated TikTok OAuth / upload / Direct Post service for Trend Radar / TrendHunter.

## Safety posture

- No public publication authority is implied by this branch.
- Mutations fail closed unless explicitly enabled.
- Kill switch overrides mutation enablement.
- OAuth state is random, durable, one-time, expires, and is bound to the initiating browser session.
- Client secret, access token, and refresh token remain server-side only.
- Session/token payloads are encrypted at rest in the configured durable state database.
- Publication state, idempotency, hard limits, audit events, UNKNOWN handling, and reconciliation are persisted.
- Media admission is MP4/H.264-only and requires full H.264 stream decode before provider mutation.
- Automatic mutation retries are disabled.

## Production persistence

The DurableState semantics are preserved behind two backends:

- `SQLite` — test/development only.
- `PostgreSQL` — required production backend.

Production selection is explicit and fail-closed:

```text
TIKTOK_RUNTIME_MODE=production
TIKTOK_STATE_BACKEND=postgresql
TIKTOK_POSTGRES_URL=<TikTok-dedicated PostgreSQL URL>
```

If production selects SQLite, PostgreSQL is unavailable, the PostgreSQL URL is missing/invalid, or the driver cannot load, durable state initialization fails. There is **no silent fallback to SQLite**.

Sensitive session/OAuth/recovery-marker payloads remain encrypted with:

- `TIKTOK_STATE_ENCRYPTION_KEY`
- or `TIKTOK_STATE_ENCRYPTION_KEYS`

The PostgreSQL backend preserves:

- persistent unique idempotency;
- transactional publication admission;
- atomic state transitions;
- cross-instance concurrency safety;
- provider publication ID uniqueness;
- UNKNOWN-state safety;
- persistent hard limits and mutation events;
- durable audit continuity;
- encrypted logical backup / isolated restore;
- duplicate prevention after restart, redelivery, and restore.

PostgreSQL code-level support does not itself establish production admission. Final R5 still requires independently verified production persistence, backup/restore, external alert delivery, cold takeover, and final architecture acceptance.

## Python / dependencies

CI target: Python 3.12.

Canonical reproducible dependency input:
- `tiktok_oauth_service/requirements.lock`

Install with:

```bash
python -m pip install --require-hashes -r tiktok_oauth_service/requirements.lock
```

`requirements.txt` is a readable version-pin list; `requirements.lock` is the hash-locked installation authority used by CI.

The runtime media validator depends on PyAV/FFmpeg through the pinned `av` wheel. The production state backend uses hash-locked Psycopg 3 packages.

## Test command

```bash
cd tiktok_oauth_service
python -m unittest -v \
  test_durable_state.py \
  test_app_safety.py \
  test_recovery.py \
  test_reconciliation.py \
  test_media_validation.py \
  test_atomicity.py \
  test_backend_selection.py
```

## Runtime start

```bash
python tiktok_oauth_service/app.py
```

## Required / security-relevant environment names

- `TIKTOK_CLIENT_KEY`
- `TIKTOK_CLIENT_SECRET`
- `TIKTOK_REDIRECT_URI`
- `TIKTOK_SCOPES`
- `PUBLIC_BASE_URL`
- `TIKTOK_RUNTIME_MODE`
- `TIKTOK_STATE_BACKEND`
- `TIKTOK_STATE_DB_PATH` — SQLite test/dev only
- `TIKTOK_POSTGRES_URL` — PostgreSQL production backend
- `TIKTOK_STATE_ENCRYPTION_KEY` or `TIKTOK_STATE_ENCRYPTION_KEYS`
- `TIKTOK_MUTATIONS_ENABLED`
- `TIKTOK_KILL_SWITCH`
- `TIKTOK_AUDIT_APPROVED`
- `TIKTOK_MAX_MUTATIONS_PER_HOUR`
- `TIKTOK_MAX_MUTATIONS_PER_DAY`
- `TIKTOK_MAX_ACTIVE_MUTATIONS_PER_ACCOUNT`
- `TIKTOK_MAX_ACTIVE_MUTATIONS_GLOBAL`
- `PORT`

Default code scopes on the remediation branch:
- `video.publish`
- `video.upload`

Do not change the already-submitted TikTok Developer review configuration merely to align it with remediation code while that review remains pending.

## Recovery

See:
- `review/tiktok/TIKTOK_INCIDENT_RECOVERY_RUNBOOK_20260928.md`
- `review/tiktok/TIKTOK_OWNER_RECOVERY_PACKAGE_20260928.md`

The exact independently accepted commit, not this moving remediation branch, must become the eventual Golden Recovery baseline.

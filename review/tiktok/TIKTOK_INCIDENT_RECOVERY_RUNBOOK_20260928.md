# TikTok Incident Recovery Runbook

Date: 2026-09-28
Scope: Trend Radar TikTok integration only
Recovery branch: tiktok-runtime-reliability-remediation-20260928
Verified live-runtime baseline before remediation: a421e755c31bf8e00a2cffc047db2c7d9e70bcbe
Public posting authority: NOT GRANTED
TIKTOK_AUDIT_APPROVED: false/unset
Golden Release: NOT YET FROZEN — requires independent retest first

## Emergency objective

Stop every TikTok mutation before attempting repair, preserve durable evidence, determine the local/remote state of every in-flight publication, rotate or revoke affected credentials, and only resume after exact-target verification.

## Immediate containment

1. Set `TIKTOK_KILL_SWITCH=true`.
2. Set `TIKTOK_MUTATIONS_ENABLED=false`.
3. Do not clear the durable state database.
4. Do not retry UNKNOWN, PROCESSING, UPLOAD_STARTED or UPLOADED records.
5. Preserve service logs and a verified database backup before repair.
6. If credential compromise is suspected, revoke TikTok authorization and rotate client/runtime secrets through the owner-controlled providers.
7. Keep `TIKTOK_AUDIT_APPROVED=false/unset` unless separate documented approval exists.

The code gate rejects Direct Post, private-test mutation and draft-upload mutation with HTTP 423 while the kill switch is active or mutations are not explicitly enabled.

## Evidence capture

Capture without secret values:
- current Git commit and branch;
- runtime service identity;
- UTC incident start/end;
- correlation/request identifiers where available;
- publication ledger rows: idempotency_key, content_sha256, account_hash, operation, state, provider_publish_id, attempt_count, timestamps and error code;
- TikTok provider status response for each provider_publish_id;
- deployment/event logs;
- SHA-256 of the database backup.

Never export plaintext access token, refresh token, client secret or authorization code into the incident report.

## Reconciliation procedure

For every non-terminal publication record:
1. Locate the durable publication row.
2. Verify the record belongs to the connected account hash.
3. If `provider_publish_id` exists, query TikTok publish status using the currently authorized account.
4. Map confirmed provider completion:
   - DIRECT_POST -> PUBLISHED
   - DRAFT_UPLOAD -> READY
5. Map explicit provider failure -> FAILED.
6. Network/5xx/ambiguous response -> UNKNOWN.
7. UNKNOWN stays UNKNOWN until a later provider query resolves it.
8. Never create a new publication intent for the same account + operation + content hash merely because the prior result is unknown.

## Backup

Use only an isolated destination that does not already exist.

The durable-state module uses SQLite online backup and `PRAGMA quick_check`, then returns the backup SHA-256. The backup must be stored outside the failing instance before destructive recovery work.

Minimum backup evidence:
- backup file SHA-256;
- source commit;
- schema/code version;
- timestamp;
- count of publication records by state.

## Restore

Restore only into a clean, isolated target path first.

The restore procedure:
1. verify source backup with `PRAGMA quick_check`;
2. restore with the SQLite backup API;
3. verify the restored database again;
4. start code in NO-PUBLISH mode;
5. inspect terminal and non-terminal publication states;
6. prove the idempotency barrier still rejects an already-published content intent;
7. reconcile unresolved provider IDs;
8. do not enable mutations until recovery evidence is accepted.

The tested restore implementation refuses to overwrite an existing target database.

## Credential compromise

1. Keep the kill switch active.
2. Revoke the TikTok user authorization via the official revoke flow where applicable.
3. Remove the local durable session.
4. Rotate `TIKTOK_CLIENT_SECRET` if client credentials may be affected.
5. Rotate `TIKTOK_STATE_ENCRYPTION_KEY(S)`; retain the prior key temporarily only if needed to decrypt and migrate legitimate stored state.
6. Re-authorize the intended TikTok account through a fresh OAuth flow.
7. Verify the returned `open_id` is the intended account before any mutation.
8. Reconcile the incident window before resuming service.

## Rebuild From Trusted Source

Rebuild from:
- repository: trendradarar-dotcom/trendradarar;
- exact independently accepted Golden Release commit (once frozen);
- pinned Python dependency file;
- clean runtime;
- new/rotated secrets;
- restored verified publication database;
- documented environment configuration.

Do not rebuild from a developer laptop, chat transcript, unverified ZIP, or mutable working directory as the sole source of truth.

## Rollback

Until independent retest closes the remediation package, there is no accepted Golden Release for public-production TikTok publishing.

The currently live review runtime commit `a421e755c31bf8e00a2cffc047db2c7d9e70bcbe` may be used only as the known pre-remediation review baseline; it is not a security/recoverability PASS and must not be relabeled as one.

## Controlled return to service

Required order:
1. exact code/DB version verified;
2. durable state healthy;
3. kill switch remains active;
4. OAuth account binding verified;
5. scope verification PASS;
6. unresolved ledger entries reconciled;
7. independent security retest PASS for the recovery target;
8. only then explicitly set `TIKTOK_MUTATIONS_ENABLED=true`;
9. keep public posting disabled unless TikTok approval and all internal gates independently permit it;
10. remove `TIKTOK_KILL_SWITCH` only after the preceding gates are evidenced.

## Human takeover

A replacement engineer needs no original chat to execute this runbook. The required source, configuration names, state model, backup/restore procedure, kill switch and reconciliation rules are recorded in the repository. Secret values remain owner/runtime controlled and are intentionally absent from documentation.

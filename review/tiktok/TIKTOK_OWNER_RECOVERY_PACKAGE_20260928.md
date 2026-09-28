# TikTok Owner Recovery Package

Date: 2026-09-28
Scope: TikTok integration only
Repository: trendradarar-dotcom/trendradarar
Verified live service branch before remediation: tiktok-oauth-service
Verified live service commit before remediation: a421e755c31bf8e00a2cffc047db2c7d9e70bcbe
Remediation branch: tiktok-runtime-reliability-remediation-20260928
Status: REMEDIATION / INDEPENDENT RETEST NOT YET COMPLETE

## 1. Ownership map

Owner-controlled assets that must remain recoverable:
- GitHub repository: trendradarar-dotcom/trendradarar
- TikTok Developer App: Trend Radar AR
- TikTok Developer App ID: 7687950912619218965
- Review/runtime domain: share.trendradar.com.co
- Render TikTok service: trendradar-tiktok-oauth
- TikTok account binding: authoritative identity is the OAuth `open_id`, not username/display name
- Recovery email / Developer account ownership remains external to source code and must be maintained by the owner

No developer or AI model is required to possess the secret values for recovery.

## 2. Runtime architecture

Browser / creator
  -> Trend Radar TikTok web service
     -> OAuth state/session durable store
     -> Creator Info query
     -> Internal mutation gate
        -> Kill switch
        -> required scope check
        -> account binding
        -> media validation
        -> hard-limit admission
        -> durable publication intent / idempotency
     -> TikTok Content Posting API
        -> Direct Post init OR Upload-to-Inbox init
        -> provider upload URL
        -> publish-status reconciliation
     -> durable publication ledger

The durable ledger is the recovery authority for local publication intent. TikTok provider state is the remote authority. An ambiguous difference remains UNKNOWN until reconciled.

## 3. Trust boundaries

Boundary A — Browser -> Trend Radar service:
- browser cookie is HttpOnly/Secure/SameSite=Lax;
- mutation requests require session authorization and CSRF protection;
- consent is explicit.

Boundary B — Trend Radar -> TikTok OAuth/API:
- client secret and user tokens remain server side;
- required scopes are checked before mutation;
- refreshed `open_id` must match the bound account.

Boundary C — Runtime -> durable state:
- session payloads are encrypted;
- raw OAuth state/handoff/session identifiers are not stored in plaintext;
- publication content is represented by hashes/IDs, not by embedding media in the ledger.

Boundary D — Control plane:
- `TIKTOK_KILL_SWITCH` and `TIKTOK_MUTATIONS_ENABLED` control whether TikTok mutations can occur.
- public/audit authorization remains a separate gate.

## 4. TikTok endpoints used

OAuth:
- authorization: https://www.tiktok.com/v2/auth/authorize/
- token / refresh: https://open.tiktokapis.com/v2/oauth/token/
- revoke: https://open.tiktokapis.com/v2/oauth/revoke/

Content Posting:
- creator info: https://open.tiktokapis.com/v2/post/publish/creator_info/query/
- Direct Post init: https://open.tiktokapis.com/v2/post/publish/video/init/
- Upload-to-Inbox init: https://open.tiktokapis.com/v2/post/publish/inbox/video/init/
- status: https://open.tiktokapis.com/v2/post/publish/status/fetch/

## 5. Scopes

Remediation code requires:
- `video.publish` for Direct Post and its status path
- `video.upload` for Upload-to-Inbox / draft and its status path

The remediation branch no longer includes `user.info.basic` in its default scope set because the reviewed runtime does not presently demonstrate a separate User Info API dependency. Do not change the already-submitted TikTok review configuration while that review remains in progress. Scope minimization for deployment is a separate post-review admission step.

## 6. Configuration names — no secret values

Required or security-relevant:
- `TIKTOK_CLIENT_KEY`
- `TIKTOK_CLIENT_SECRET`
- `TIKTOK_REDIRECT_URI`
- `TIKTOK_SCOPES`
- `PUBLIC_BASE_URL`
- `TIKTOK_STATE_DB_PATH`
- `TIKTOK_STATE_ENCRYPTION_KEY` or `TIKTOK_STATE_ENCRYPTION_KEYS`
- `TIKTOK_MUTATIONS_ENABLED`
- `TIKTOK_KILL_SWITCH`
- `TIKTOK_AUDIT_APPROVED`
- `TIKTOK_MAX_MUTATIONS_PER_HOUR`
- `TIKTOK_MAX_MUTATIONS_PER_DAY`
- `TIKTOK_MAX_ACTIVE_MUTATIONS_PER_ACCOUNT`
- `TIKTOK_MAX_ACTIVE_MUTATIONS_GLOBAL`
- `PORT`

Default safety posture in remediation code:
- mutations are disabled unless `TIKTOK_MUTATIONS_ENABLED=true`;
- kill switch overrides mutation enablement;
- automatic mutation retries = 0;
- retry horizon = 0;
- public/audit approval is not inferred.

## 7. Durable state schema

Tables:
- `oauth_states`: one-time hashed OAuth state plus encrypted session binding
- `sessions`: encrypted server-side OAuth/session payload
- `handoffs`: one-time hashed handoff plus encrypted session binding
- `publications`: idempotency, content identity, account identity, operation, provider ID, state, attempts and error
- `mutation_events`: persistent hard-limit admission events

Publication states:
`RECEIVED -> VALIDATED -> SAFETY_APPROVED -> PUBLISH_REQUESTED -> UPLOAD_STARTED -> UPLOADED -> PROCESSING -> PUBLISHED/READY`

Holding/error states:
- `UNKNOWN`
- `FAILED`

UNKNOWN is never considered safe to republish.

## 8. Idempotency identity

Stable mutation identity is derived from:
- bound account hash
- operation type
- source media content SHA-256

Filename or transient job ID does not create a new content identity.

## 9. Build and test

Python target used by CI: 3.12

Reproducible dependency authority:
- `tiktok_oauth_service/requirements.lock`
- install with `python -m pip install --require-hashes -r tiktok_oauth_service/requirements.lock`

Pinned direct runtime packages include:
- `av==18.1.0`
- `cryptography==46.0.1`
- `cffi==2.1.1`
- `pycparser==3.0`

The media validator uses PyAV/FFmpeg and decodes the entire H.264 video stream before provider mutation; first-frame-only validation is not the intended acceptance rule.

CI:
- compile app/state/tests/SBOM generator
- install hash-locked dependencies
- run durable-state tests
- safety-gate tests
- backup/restore tests
- reconciliation tests
- media validation tests
- concurrency tests
- generate exact-commit CycloneDX SBOM
- reject mutable GitHub Action version tags
- reject legacy in-memory OAuth stores
- preserve audit-approval gate

No deployment is required to execute these internal tests.

## 10. Runtime start

Current application start command:
`python tiktok_oauth_service/app.py`

The remediation runtime additionally requires a production-persistent `TIKTOK_STATE_DB_PATH` and encryption key configuration. If the database path is not configured or state initialization fails, OAuth/mutation paths fail closed.

## 11. Important infrastructure blocker

The currently verified Render TikTok service is on the pre-remediation branch and no production-persistent TikTok state volume/database has yet been evidenced for this remediation target.

Therefore:
- the remediation branch MUST NOT be represented as production-persistence PASS;
- it MUST NOT be deployed during the pending TikTok App Review merely to obtain evidence;
- final production admission requires a durable production state backend/volume, backup location and restore evidence bound to the deployed target.

No paid infrastructure is authorized by this package.

## 12. Kill switch

Emergency stop:
- set `TIKTOK_KILL_SWITCH=true`;
- ensure `TIKTOK_MUTATIONS_ENABLED=false`.

Expected effect:
- Direct Post blocked;
- Upload-to-Inbox blocked;
- private diagnostic posting blocked;
- no automatic retries exist;
- durable ledger remains readable for reconciliation.

## 13. Disconnect / revocation

POST `/auth/tiktok/disconnect`:
- verifies CSRF;
- requests TikTok token revocation;
- removes the local durable session;
- reports whether remote revocation was confirmed.

A new OAuth authorization is required to reconnect.

## 14. Backup / restore

Implementation:
- SQLite online backup API
- source/destination `PRAGMA quick_check`
- SHA-256 of backup
- restore refuses to overwrite an existing target

Tests prove a restored database retains a PUBLISHED record and continues to reject a duplicate intent for the same idempotency key.

## 15. Reconciliation

For known `provider_publish_id`:
- verify account binding;
- query TikTok status;
- Direct Post + PUBLISH_COMPLETE -> PUBLISHED;
- Draft + PUBLISH_COMPLETE -> READY;
- Draft + SEND_TO_USER_INBOX -> READY;
- explicit provider publication failure -> FAILED;
- status-read/network/429/5xx ambiguity -> UNKNOWN;
- later successful reconciliation may resolve UNKNOWN to PUBLISHED/READY.

## 16. Golden Release

Current status:
`GOLDEN_RELEASE = NOT YET ACCEPTED`

R2 was independently exact-target verified but final acceptance remained FAIL-CLOSED because required adversarial evidence and production recovery gates were incomplete. Any later remediation candidate must receive a new exact commit/tree and independent retest.

The independently accepted exact remediation commit will become the Golden Release only after:
- all critical tests close;
- production-persistent state infrastructure is proven;
- independent security/reliability retest passes;
- recovery package is verified.

The pre-remediation live commit `a421e755c31bf8e00a2cffc047db2c7d9e70bcbe` is a historical operational baseline, not a final security acceptance target.

## 17. Rollback / rebuild

Rollback or rebuild must use:
- exact accepted commit;
- pinned dependencies;
- clean runtime;
- new/rotated secrets where relevant;
- verified state backup;
- explicit NO-PUBLISH startup;
- reconciliation before mutation enablement.

See:
`review/tiktok/TIKTOK_INCIDENT_RECOVERY_RUNBOOK_20260928.md`

## 18. Human takeover checklist

A cold engineer must be able to:
1. identify the repository and exact target;
2. build and run tests;
3. configure state without receiving secret values in documentation;
4. keep mutation disabled;
5. inspect publication ledger/state;
6. operate kill switch;
7. revoke/reconnect OAuth;
8. make and verify a backup;
9. restore in isolation;
10. reconcile provider status;
11. rebuild and redeploy only after authorization;
12. demonstrate no duplicate post after restore.

If these actions require the original developer/chat/AI beyond documented credentials held by the owner, maintainability/recoverability remains NOT VERIFIED.

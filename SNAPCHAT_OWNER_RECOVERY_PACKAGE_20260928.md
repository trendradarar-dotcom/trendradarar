# SNAPCHAT OWNER RECOVERY PACKAGE — 2026-09-28

PROJECT: Trend Radar / TrendHunter  
SCOPE: Snapchat only  
STATUS: REMEDIATION CANDIDATE — NOT PRODUCTION ACCEPTANCE  
SUPERSEDES FOR THIS CANDIDATE: SNAPCHAT_OWNER_RECOVERY_PACKAGE_20260925.md

## 1. Purpose

This package is intended to let the owner or a new qualified engineer understand, stop, rebuild, recover, and independently retest the Snapchat subsystem without the original AI conversation or original developer.

It does not authorize public publishing.

## 2. Source ownership and isolation

Repository:
- trendradarar-dotcom/trendradarar

Remediation branch:
- snapchat-production-remediation-20260928

Original production-review branch remains separate:
- snapchat-production-review-20260925

Snapchat implementation:
- snapchat_oauth_service/app.py
- snapchat_oauth_service/state_store.py
- snapchat_oauth_service/media_probe.py
- snapchat_oauth_service/audit.py
- snapchat_oauth_service/requirements.txt
- snapchat_oauth_service/migrations/001_snapchat_durable_state.sql
- snapchat_oauth_service/test_app.py
- snapchat_oauth_service/test_postgres_integration.py
- snapchat_oauth_service/backup_restore_probe.py

Legacy provider-neutral publisher remains in:
- snapchat_publisher_service/

CI:
- .github/workflows/snapchat-publisher-ci.yml
- .github/scripts/snapchat_secret_scan.py

Do not use databases, credentials, queues, services, or secrets from Instagram, TikTok, YouTube, TCC, Tanoub Travel, or any other project.

## 3. Exact Snapchat identity

Expected owned account:
- username: trendradarar
- brand: Trend Radar

Expected Public Profile ID:
- 3f5d8925-0da7-4da6-9b87-d8aa326026a0

Snapchat Business Organization ID:
- 0cf1ddf6-1ede-41af-bfd7-4d959ca89b1e

OAuth application:
- Trend Radar Snapchat API

OAuth client ID is operational metadata and must be verified against the owner-controlled Snapchat Business account before production. Client secret values are never stored in this document.

Exact binding is code-enforced against both:
- Public Profile ID
- username trendradarar

A display name alone is not sufficient.

## 4. Render inventory

Existing production-review services were not modified by this remediation:
- trendradar-snapchat-publisher — srv-dar6s0vavr4c7380epmg
- trendradar-snapchat-oauth — srv-daqvhinavr4c73f6r9sg

Isolated remediation candidate service:
- trendradar-snapchat-remediation-candidate
- service ID: srv-dasrgsm0tbcc738nkhg0
- branch: snapchat-production-remediation-20260928
- auto deploy: disabled
- region: Frankfurt
- public publishing: disabled
- kill switch: active
- emergency read-only: active
- no production Snapchat credentials installed
- no shared project database installed

A dedicated free Render PostgreSQL could not be created because the workspace already has another active free-tier database. That existing database belongs to another project and MUST NOT be reused. No paid database was authorized or created.

## 5. Required configuration names

Connection / identity:
- SNAPCHAT_DIRECT_API_ENABLED
- SNAPCHAT_CLIENT_ID
- SNAPCHAT_CLIENT_SECRET
- SNAPCHAT_REDIRECT_URI
- SNAPCHAT_STATE_SECRET
- SNAPCHAT_TOKEN_ENCRYPTION_KEY
- SNAPCHAT_PUBLIC_PROFILE_ID
- SNAPCHAT_EXPECTED_USERNAME
- SNAPCHAT_OWNER_KEY
- SNAPCHAT_DATABASE_URL

Publication control:
- SNAPCHAT_PUBLICATION_ENABLED
- SNAPCHAT_KILL_SWITCH
- SNAPCHAT_EMERGENCY_READ_ONLY
- SNAPCHAT_TARGET_ACCOUNT_VERIFIED
- SNAPCHAT_DURABLE_RECONCILIATION_READY
- SNAPCHAT_ALERTING_READY
- SNAPCHAT_PRODUCTION_ASSURANCE_READY
- SNAPCHAT_HARD_LIMITS_VERIFIED

Hard limits:
- SNAPCHAT_MAX_POSTS_PER_HOUR
- SNAPCHAT_MAX_POSTS_PER_DAY
- SNAPCHAT_MAX_CONCURRENT_PUBLISHES
- SNAPCHAT_MAX_ATTEMPTS_PER_PUBLICATION
- SNAPCHAT_RETRY_HORIZON_SECONDS

Secret values are intentionally excluded.

## 6. Safe default / candidate control state

Production opening requires every production gate to pass simultaneously.

Until then:
- SNAPCHAT_PUBLICATION_ENABLED=false
- SNAPCHAT_KILL_SWITCH=true
- SNAPCHAT_EMERGENCY_READ_ONLY=true
- SNAPCHAT_TARGET_ACCOUNT_VERIFIED=false
- SNAPCHAT_DURABLE_RECONCILIATION_READY=false
- SNAPCHAT_ALERTING_READY=false
- SNAPCHAT_PRODUCTION_ASSURANCE_READY=false
- SNAPCHAT_HARD_LIMITS_VERIFIED=false

Expected authorized public publication blast radius:
- 0

## 7. Durable state model

Production acceptance requires PostgreSQL.

SQLite support exists only for isolated development/unit tests and is deliberately rejected as production-durable.

Schema migration:
- snapchat_oauth_service/migrations/001_snapchat_durable_state.sql

Durable tables:
- snapchat_oauth_intents
- snapchat_oauth_states
- snapchat_oauth_tokens
- snapchat_publications

Publication records bind:
- Public Profile ID
- publication_id
- content_id
- job_id
- content description hash
- media SHA-256
- actual media duration
- actual media width/height
- attempt count
- correlation ID
- remote media ID
- remote Spotlight ID
- local state
- timestamps
- last error

The same publication_id may not silently refer to different content/job/media.

## 8. Publication state semantics

Current direct-path states include:
- RECEIVED
- VALIDATED
- MEDIA_CREATING
- MEDIA_UPLOADING
- SUBMITTING
- SUBMITTED
- LIVE
- REJECTED
- FAILED_PRE_SUBMIT
- UNKNOWN

Rules:
- UNKNOWN is not success.
- UNKNOWN is not safe to republish.
- SUBMITTING/UNKNOWN survive process restart in durable state.
- a failed pre-submit attempt may retry only under the configured attempt/horizon limits and only if the immutable publication payload matches.
- a remote-side uncertainty must be reconciled before any retry.

## 9. OAuth durability and recovery

OAuth initiation requires:
1. owner-authorized creation of a one-time OAuth intent;
2. one-time consumption of that intent;
3. signed state;
4. browser-bound nonce cookie;
5. durable one-time state consumption;
6. exact Public Profile ID + username validation;
7. read-only authorized-access verification;
8. only then encrypted durable token storage.

Persisted OAuth credentials are encrypted with SNAPCHAT_TOKEN_ENCRYPTION_KEY.

A restart must not depend on process memory for the refresh credential.

Local disconnect:
- POST /admin/disconnect with owner authorization
- clears persisted OAuth credentials
- clears runtime token cache
- blocks silent reuse of the old local connection

External Snapchat app/account revocation remains a separate owner-controlled external action when required.

## 10. Hard-limit baseline

Current conservative code defaults:
- max posts/hour: 2
- max posts/day: 10
- max concurrent publishes/profile: 1
- max attempts/publication: 2
- retry horizon: 1800 seconds

These limits are implementation defaults only. Production must keep SNAPCHAT_HARD_LIMITS_VERIFIED=false until the final production configuration is independently checked.

## 11. Media handling

The direct path receives an uploaded MP4; it does not fetch an arbitrary user-supplied media URL.

Actual video metadata is probed server-side before admission:
- duration
- width
- height

Current internal production contract:
- MP4
- 30–60 seconds
- minimum 540x960
- portrait 9:16 target
- description <=160 characters

Provider-returned media upload paths are restricted to the Snapchat Business API host.

## 12. Backup / restore

Required production asset:
- PostgreSQL database containing OAuth and publication state.

Backup must include the durable Snapchat database and be associated with:
- exact source commit/freeze;
- schema migration version;
- UTC timestamp.

Validated CI recovery method uses PostgreSQL pg_dump/pg_restore and verifies that a restored SUBMITTED publication remains non-republishable.

Production backup retention and scheduling remain an infrastructure decision and must be configured on the final dedicated Snapchat database.

Never restore a Snapchat database over another project database.

## 13. Credential rotation

SNAPCHAT_OWNER_KEY:
- rotate in the runtime secret manager;
- verify old value fails;
- preserve audit evidence.

SNAPCHAT_TOKEN_ENCRYPTION_KEY:
- do not replace while encrypted credentials remain unreadable under the new key;
- safest recovery procedure is: close publication -> disconnect local OAuth -> replace encryption key -> perform a fresh owner-authorized OAuth connection -> verify exact binding.

SNAPCHAT_CLIENT_SECRET:
- close publication first;
- rotate at Snapchat;
- update runtime secret;
- invalidate/revoke superseded authorization where applicable;
- re-run OAuth/profile binding verification.

Refresh/access credentials:
- never copy into repository, reports, logs, or chat;
- use disconnect/re-consent/refresh lifecycle as appropriate.

## 14. Build from trusted source

1. obtain the owner-controlled repository;
2. identify the exact frozen Snapchat candidate SHA;
3. verify it against the independent review handoff;
4. create a clean isolated Python environment;
5. install exact pinned requirements;
6. apply the documented database migration to a dedicated Snapchat database;
7. run compile, dependency audit, Bandit, unit/adversarial tests, PostgreSQL integration tests, backup/restore probe, and secret scans;
8. deploy with publication disabled, kill switch active, and emergency read-only active;
9. verify /health;
10. only then configure credentials;
11. perform owner-authorized OAuth connection;
12. verify exact profile binding in read-only mode;
13. do not open publication until all independent acceptance gates are closed.

## 15. Recovery evidence to preserve

- frozen Git commit SHA;
- branch/tag/freeze reference;
- CI run ID and job logs;
- Render service/deploy IDs;
- database backup identity and timestamp;
- correlation IDs;
- publication IDs;
- content IDs;
- job IDs;
- remote media IDs;
- remote Spotlight IDs;
- control-state snapshot without secrets;
- Snapchat remote state evidence;
- incident time window.

## 16. Owner control requirements

Owner must retain recoverable control of:
- Snapchat account trendradarar;
- Snapchat Business Organization;
- OAuth App;
- project recovery email;
- GitHub repository;
- Render workspace;
- dedicated Snapchat database;
- all secret-manager values;
- ability to disable the Render service or close publication externally.

No recovery-critical value may exist only in an AI chat, original developer machine, or undocumented manual step.

## 17. Remaining acceptance gates

The remediation implementation does NOT close by itself:
- Snapchat Public Profile API allowlist external approval;
- verified external alert delivery;
- independent penetration test;
- independent final code/architecture retest;
- practical independent kill-switch/service-stop drill;
- cold-engineer handover;
- final dedicated production database provisioning and backup schedule;
- final production secret rotation/revocation drill;
- final production freeze and exact deployed-target verification.

Therefore:
- PUBLICATION_AUTHORITY = ZERO
- SECURITY_RELIABILITY_RECOVERABILITY_ACCEPTANCE = NOT YET PASS

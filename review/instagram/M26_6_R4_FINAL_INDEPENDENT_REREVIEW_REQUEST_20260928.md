# Independent Re-Review Request — Instagram M26.6 / R4 FINAL

PROJECT: TrendHunter / Trend Radar
SCOPE: Instagram only
MODE: Fresh / Independent / Adversarial / Read-Only First / Exact-Target-Bound / Exact-Evidence-Bound / No Producer Trust / Fail-Closed

## Exact code target

Repository: trendradarar-dotcom/trendradarar
Remediation branch: instagram-production-remediation-r4-20260928

EXACT CODE TARGET: 7055c33042b4e46b150315067c08dbda728974e7
EXACT CODE TREE: a3feac56d118266fcaf28eff577642e04252f4e3
EXACT-TARGET CI RUN: 36378357445
CI RESULT: SUCCESS

LIVE SYNC COMMIT: 1a4f99a089d928c45319cde26a5ca71ff32a796c
LIVE SYNC TREE: a3feac56d118266fcaf28eff577642e04252f4e3

Render backend deploy:
dep-dasuuo7pn0mc73a6pv3g

Render gateway deploy:
dep-dasuuoojo6nc73diatqg

Both deploys were observed LIVE on the live sync commit.

The commit containing this request must be documentation-only and a direct child of the exact target. Verify that independently from the supplied Git bundle.

## Previous independent findings requiring fresh retest

Do not trust remediation claims. Reproduce independently:

1. CRITICAL — Live candidate equivalence previously failed.
2. CRITICAL — Alternate backend OAuth routes bypassed gateway hard-disable.
3. HIGH — Machine publisher account binding was not immutable inside PublisherRuntime.
4. HIGH — Restart/crash recovery stalled NEW and could orphan container creation.
5. MEDIUM — Publication state transition and audit event were not atomic.
6. NOT VERIFIED — Race/concurrency had not been exercised against real PostgreSQL multi-worker execution.
7. NOT VERIFIED — Supply-chain reproducibility lacked immutable package bytes/hashes.

## Mandatory exact-target gate

Before reviewing findings, independently verify:

- commit 7055c33042b4e46b150315067c08dbda728974e7 exists in the Git bundle;
- its tree is exactly a3feac56d118266fcaf28eff577642e04252f4e3;
- the final review-request commit is its direct child;
- the target-to-review delta is documentation only;
- CI run 36378357445 has head_sha equal to the exact target and completed SUCCESS;
- the live sync commit has exactly the same tree as the exact target;
- runtime wheelhouse hashes and SHA256SUMS match.

## Findings to retest independently

### A. All OAuth linking routes fail closed

Verify both gateway and backend routes, including:
- /oauth/browser/start
- /oauth/browser/callback
- /oauth/start
- /oauth/callback
- /api/public-oauth/start
- /api/public-oauth/callback
- /auth/instagram/start
- /auth/instagram/callback

Confirm no alternate linking/re-link route remains open in this candidate.

### B. Immutable governed account binding

Probe PublisherRuntime directly with alternate username and professional user ID values.

Required governed identity:
- username: trendradarar
- account type: BUSINESS
- professional user ID: 17841428134382903

A retargeted PublisherRuntime must not be configured and must fail the credential gate.

### C. Crash-safe container admission

Verify:
NEW -> CONTAINER_CREATE_REQUESTED -> CONTAINER_CREATED

Required behavior:
- a true NEW job can resume after restart because no provider create call started;
- CONTAINER_CREATE_REQUESTED after restart becomes UNKNOWN;
- no blind provider container-create retry occurs after ambiguity;
- PUBLISH_REQUESTED remains fail-closed after restart.

### D. Atomic state + audit

Using real PostgreSQL failure injection, verify that failure to insert STATE_TRANSITION audit evidence rolls back the job state update in the same transaction.

### E. PostgreSQL concurrency

Independently inspect and preferably rerun the exact PostgreSQL 18 CI tests:
- concurrent duplicate reservation;
- advisory-lock serialization between independent workers/connections;
- daily blast-radius enforcement under concurrent publish workers;
- crash/restart states;
- state/audit atomic rollback.

### F. Supply-chain reproducibility

Verify:
- exact pinned requirements;
- pip-audit PASS;
- Actions pinned to commit SHAs;
- exact CI wheelhouse artifact;
- SHA256SUMS for every downloaded wheel;
- whether the captured wheel bytes satisfy the requested reproducibility standard.

### G. Live candidate equivalence

Independently verify:
- live backend and gateway deploys point to live sync commit 1a4f99a089d928c45319cde26a5ca71ff32a796c;
- that commit tree equals the exact candidate tree;
- backend live health exposes build_revision M26.6-R4-PRODUCTION-ADMISSION-20260928;
- public_publish_authorized=false;
- instagram_publish_enabled=false;
- exact_account_binding_configured=true;
- oauth_relink_hard_disabled=true;
- fresh browser /share remains 403;
- unauthenticated machine status remains 403;
- OAuth linking start routes remain fail-closed.

Do not publish a Reel and do not enable either publication gate.

## Existing previously-PASS controls that must not be assumed

Reconfirm as needed:
- M2M authorization;
- content-level duplicate prevention;
- UNKNOWN handling;
- ambiguous media_publish recovery;
- maximum blast radius;
- kill switch/no-publish;
- byte-level media preflight;
- durable media and publication state.

## Operational evidence boundary

Do not promote the following to PASS without actual independent execution evidence:
- Monitoring / Alerting acceptance;
- Backup / Restore drill;
- Disaster Recovery drill;
- Golden / LKG promotion;
- Owner Recovery Package execution;
- Rebuild From Trusted Source drill;
- Human Takeover exercise;
- Cold Engineer Handover;
- Independent Penetration Test.

A runbook or implementation is not a drill.

## Safety constraints

No remediation during the independent review.
No public Reel.
No enabling publication gates.
No production-state mutation beyond read-only verification.

Required:
INSTAGRAM_PUBLIC_PUBLISH_AUTHORIZED=false
INSTAGRAM_PUBLISH_ENABLED=false

## Required output

CRITICAL_OPEN =
HIGH_OPEN =
MEDIUM_OPEN =
CRITICAL_NOT_VERIFIED =

EXACT_TARGET_VERIFIED =
EXACT_TREE_VERIFIED =
EXACT_TARGET_CI =
DOCUMENTATION_ONLY_DELTA_VERIFIED =
LIVE_TREE_EQUIVALENCE =

OAUTH_ALL_ROUTES_FAIL_CLOSED =
IMMUTABLE_ACCOUNT_BINDING =
RESTART_CRASH_RECOVERY =
AUDIT_STATE_ATOMICITY =
RACE_CONCURRENCY =
SUPPLY_CHAIN_REPRODUCIBILITY =

ARCHITECTURE_AND_TRUST_BOUNDARIES =
TOKEN_SECRET_SECURITY =
AUTHORIZATION_BOUNDARY =
M2M =
DUPLICATE_PREVENTION =
UNKNOWN_HANDLING =
AMBIGUOUS_PUBLISH_RECOVERY =
MAXIMUM_BLAST_RADIUS =
KILL_SWITCH_NO_PUBLISH =
MEDIA_BYTE_PREFLIGHT =
DURABLE_STATE =
LOGGING_AUDIT =

MONITORING_ALERTING =
BACKUP_RESTORE =
DISASTER_RECOVERY =
GOLDEN_BASELINE =
RECOVERY_RUNBOOK =
OWNER_RECOVERY_PACKAGE =
REBUILD_FROM_TRUSTED_SOURCE =
HUMAN_TAKEOVER =
COLD_ENGINEER_HANDOVER =
PENETRATION_TEST =
LIVE_CANDIDATE_EQUIVALENCE =

FIRST_PUBLIC_ACTIVATION_ELIGIBLE =
INDEPENDENT_FINAL_VERDICT = PASS / FAIL-CLOSED

Any critical missing evidence => FAIL-CLOSED.

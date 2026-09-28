# Independent Re-Review Request — Instagram M26.6 / R4

PROJECT: TrendHunter / Trend Radar
SCOPE: Instagram only
MODE: Fresh / Independent / Adversarial / Read-Only First / Exact-Target-Bound / Exact-Evidence-Bound / No Producer Trust / Fail-Closed

## Exact code target

Repository: trendradarar-dotcom/trendradarar
Branch: instagram-production-remediation-r4-20260928

EXACT CODE TARGET: 19e147a86f3a1cffae466a13e0c9c0eb0561d38f
EXACT CODE TREE: 72f0df3eb6447c62c1f9fdb686dc9f8a47546b2b
EXACT-TARGET CI RUN: 36378244057
CI RESULT: SUCCESS

The commit containing this request is documentation-only and is not the code target.

## Previous independent findings requiring fresh retest

Do not trust remediation claims. Reproduce independently:

1. CRITICAL — Alternate backend OAuth routes bypassed the gateway hard-disable.
2. HIGH — Machine publisher account binding was not immutable inside PublisherRuntime.
3. HIGH — Restart/crash recovery stalled jobs left in NEW and could orphan container creation.
4. MEDIUM — Publication state transition and audit event were not atomic.
5. NOT VERIFIED — Race/concurrency behavior had not been exercised against real PostgreSQL multi-worker execution.
6. NOT VERIFIED — Supply-chain reproducibility lacked immutable runtime package bytes/hashes.
7. CRITICAL — Live candidate equivalence previously failed because Render was running older commits.

## Remediation areas to verify independently

### OAuth closure
Verify all relevant backend and gateway OAuth start/callback routes fail closed in this candidate and that no alternate route permits public re-link.

### Immutable account binding
Probe PublisherRuntime directly with alternate username / professional user ID values.
Expected: configured() must be false and all governed runtime identity remains bound to:
- username: trendradarar
- account type: BUSINESS
- professional user ID: 17841428134382903

### Crash-safe container admission
Verify the state machine:
NEW -> CONTAINER_CREATE_REQUESTED -> CONTAINER_CREATED

Required behavior:
- NEW can resume safely after restart.
- CONTAINER_CREATE_REQUESTED becomes UNKNOWN after restart.
- No blind re-send of the provider container mutation after an ambiguous create request.

### Atomic state + audit
Use a real PostgreSQL failure injection.
A failed STATE_TRANSITION audit insert must roll back the state update in the same transaction.

### PostgreSQL concurrency
Independently inspect and, where practical, rerun the exact CI tests using PostgreSQL 18.
Verify:
- concurrent duplicate reservation;
- advisory-lock serialization between independent workers/connections;
- daily blast-radius enforcement with concurrent publish workers;
- crash/restart states.

### Supply chain
Verify:
- exact pinned dependencies;
- pip-audit result;
- GitHub Actions pinned to commit SHAs;
- the exact CI-generated wheelhouse artifact and SHA256SUMS;
- whether this is sufficient for the requested reproducibility standard.

## Safety constraints

Do not remediate during this review.
Do not enable public publishing.
Do not publish a real Reel.
Do not alter Render or PostgreSQL production state.

Required safety state remains:
INSTAGRAM_PUBLIC_PUBLISH_AUTHORIZED=false
INSTAGRAM_PUBLISH_ENABLED=false

## Important operational boundary

This candidate has NOT yet been promoted to the live Render services.

Therefore LIVE_CANDIDATE_EQUIVALENCE must remain FAIL / NOT VERIFIED until the exact reviewed SHA is deliberately deployed with both publish gates false and rechecked independently.

Likewise do not promote the following to PASS without actual drill evidence:
- Monitoring / Alerting
- Backup / Restore
- Disaster Recovery
- Golden / LKG
- Owner Recovery Package execution
- Rebuild From Trusted Source
- Human Takeover
- Cold Engineer Handover
- Independent Penetration Test

## Required output

CRITICAL_OPEN =
HIGH_OPEN =
MEDIUM_OPEN =
CRITICAL_NOT_VERIFIED =

EXACT_TARGET_VERIFIED =
EXACT_TREE_VERIFIED =
EXACT_TARGET_CI =
DOCUMENTATION_ONLY_DELTA_VERIFIED =

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

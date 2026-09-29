# TikTok R5 — Directed Independent PostgreSQL Backend Retest

Date: 2026-09-29
Project: TrendHunter / Trend Radar
Scope: TikTok ONLY

## Review mode

Fresh / Independent / Adversarial / Read-Only First / Exact-Target-Bound / Exact-Evidence-Bound / No Producer Trust / Fail-Closed

This review is a directed retest of the NEW PostgreSQL DurableState architecture only, plus focused no-regression checks for previously closed controls that depend on persistence/state semantics.

It does NOT authorize production cutover or public posting.

## Exact candidate

Repository:
`trendradarar-dotcom/trendradarar`

Frozen branch:
`tiktok-r5-postgres-independent-retest-candidate-20260929`

EXACT COMMIT:
`d98ee71e110118dc9fff4710dca6bf61381eeefc`

EXACT TREE:
`4e1f7a6240b15f6c7d80a994efe0331e0dfce912`

Base held runtime / R4.2 accepted exact target:
`ece8039623ee82176d756591af9495414a80d3d6`

## Mandatory Exact Target gate

Before evaluating code or tests:
1. verify package manifest;
2. verify Git bundle;
3. clone bundle independently;
4. verify HEAD equals exact commit;
5. verify HEAD^{tree} equals exact tree;
6. reconstruct root tree from full-repository-snapshot.tar;
7. verify reconstructed tree equals exact tree.

Any mismatch:
`EXACT TARGET = NOT VERIFIED`
and stop Fail-Closed.

## PG-01 — Backend Selection / No Fallback

Independently verify and execute:
- SQLite remains available only for test/dev/local;
- production requires `TIKTOK_RUNTIME_MODE=production`;
- production requires `TIKTOK_STATE_BACKEND=postgresql`;
- missing backend fails closed;
- missing/unsupported runtime mode fails closed;
- production + SQLite fails closed;
- missing PostgreSQL URL fails closed;
- invalid PostgreSQL URL fails closed;
- unavailable PostgreSQL fails closed;
- PostgreSQL driver/load failure cannot silently select SQLite;
- no implicit environment/config path can bypass the production PostgreSQL requirement.

Required verdict:
`PG-01 Backend Selection / Fail-Closed`

## PG-02 — Encryption / Sensitive State

Using reviewer-controlled synthetic secrets:
- session access/refresh token values must not be stored plaintext in PostgreSQL;
- OAuth browser/session binding ciphertext must remain encrypted;
- handoff session binding must remain encrypted;
- recovery marker value must remain encrypted;
- correct configured keys decrypt;
- corrupted ciphertext fails closed;
- rotation semantics remain compatible with MultiFernet key sets;
- audit detail must reject secret field names as before.

Required verdict:
`PG-02 Encrypted Sensitive State`

## PG-03 — Persistent Idempotency / Admission / Concurrency

Run on a REAL PostgreSQL instance, not a mock.

Required adversarial/concurrency probes:
1. multiple independent store instances concurrently create the same idempotency key;
   - exactly one creator;
   - all others receive existing record;
   - one publication intent only.
2. concurrent admissions for the same account under active-account limit;
   - limit cannot be bypassed.
3. concurrent accounts under global limits;
   - global hard limits remain enforceable.
4. mutation-event history remains persistent across new connections/store instances.
5. redelivery after restart returns existing publication record and cannot create a new mutation intent.

Required verdict:
`PG-03 Idempotency / Transactional Admission / Concurrency`

## PG-04 — State Machine / Provider Binding / UNKNOWN

Required:
- state transitions remain identical to accepted semantics;
- invalid transitions fail closed;
- concurrent terminal-transition race cannot produce an invalid/intermediate final state;
- provider_publish_id is uniquely bound;
- duplicate provider ID across publications is rejected;
- attempt count remains durable;
- UNKNOWN survives new process/connection;
- UNKNOWN cannot restart upload/publication;
- later reconciliation may resolve UNKNOWN only through allowed transitions;
- provider ID/state/audit updates stay transactionally coherent.

Required verdict:
`PG-04 State / Provider Binding / UNKNOWN Safety`

## PG-05 — Backup / Restore / Audit / Duplicate Barrier

Use source PostgreSQL DB and a CLEAN second PostgreSQL DB.

Required:
- consistent source snapshot;
- backup artifact is encrypted;
- backup plaintext must not expose synthetic marker/token/provider values;
- SHA-256 is produced and independently verified;
- corrupted/wrong-key backup fails closed;
- incomplete/malformed backup fails closed;
- restore refuses non-empty target;
- recovery marker survives;
- PUBLISHED record survives;
- UNKNOWN record survives;
- provider_publish_id survives;
- mutation-event history survives;
- audit history survives;
- event ID sequences continue safely after restore;
- same idempotency key remains blocked after restore/redelivery;
- UNKNOWN remains unsafe to republish after restore.

Required verdict:
`PG-05 Backup / Restore / Audit / Duplicate Barrier`

## PG-06 — Supply Chain

Independently verify:
- Psycopg packages are version-pinned and hash-locked;
- all transitive requirements used by hash-locked install are pinned/hashes present;
- installation succeeds with `--require-hashes` on Python 3.12;
- SBOM binds to exact candidate commit;
- SBOM includes PostgreSQL driver components and requirement-lock hash;
- GitHub Actions use immutable full SHA refs;
- no new mutable dependency path is introduced.

Required verdict:
`PG-06 Supply Chain`

## Focused no-regression

Do NOT reopen previously closed findings without contradictory evidence.

Recheck only persistence/state-related dependencies:
- F-01 OAuth state/browser binding;
- F-02 429 -> UNKNOWN -> later success;
- F-03 Draft terminal READY mapping;
- F-04 media validator code identity against accepted R3 path, or equivalent focused regression;
- F-05 immutable supply chain;
- R4.2 watchdog behavior/code identity;
- kill switch/no-publish default;
- zero automatic mutation retries;
- idempotency/duplicate barrier;
- audit secret exclusion.

Required verdict:
`FOCUSED NO-REGRESSION = PASS/FAIL/NOT VERIFIED`

## Production gates explicitly OUTSIDE this closure

Even if PG-01..PG-06 all PASS, do NOT grant final production auto-publish acceptance.

Still separate and later:
- isolated TikTok production PostgreSQL resource;
- runtime equivalence of deployed successor;
- production persistence/restart evidence;
- off-runtime backup / production restore;
- external alert delivery;
- cold-engineer / owner takeover;
- Golden Recovery;
- controlled cutover;
- observation period;
- final architecture/security acceptance.

## Non-mutation rules

Reviewer MUST NOT:
- deploy;
- merge;
- change Render;
- create/use any non-TikTok database/resource;
- delete or replace the held runtime;
- Recall/Resubmit TikTok App Review;
- enable public posting;
- set `TIKTOK_AUDIT_APPROVED=true`.

## Required verdict vocabulary

Use only:
`PASS / FAIL / NOT VERIFIED / N/A`

Required final table:
- EXACT TARGET
- PG-01
- PG-02
- PG-03
- PG-04
- PG-05
- PG-06
- FOCUSED NO-REGRESSION
- POSTGRESQL DIRECTED RETEST
- FINAL PRODUCTION AUTO-PUBLISH ACCEPTANCE

Expected production verdict remains:
`NOT VERIFIED / NOT AUTHORIZED`

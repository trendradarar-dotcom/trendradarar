# TikTok R5 — Fresh Independent PostgreSQL Execution Only

No product remediation is requested.

Exact candidate remains:
- COMMIT `d98ee71e110118dc9fff4710dca6bf61381eeefc`
- TREE `4e1f7a6240b15f6c7d80a994efe0331e0dfce912`

A real PostgreSQL 16 review database now exists solely for independent execution.

The reviewer should rerun only the previously NOT VERIFIED areas:

## PG-02
- write synthetic access/refresh tokens and inspect raw PostgreSQL storage;
- prove plaintext absence;
- correct/wrong/corrupt key probes;
- MultiFernet rotation;
- OAuth/handoff/recovery-marker encryption;
- audit secret-name rejection.

## PG-03
- simultaneous same-idempotency creation from independent connections;
- active-account race;
- global-limit race;
- mutation-history persistence;
- redelivery after new connections/restart.

## PG-04
- invalid transition rejection;
- concurrent terminal-transition race;
- duplicate provider ID;
- durable attempt counter;
- UNKNOWN reopen/restart behavior;
- UNKNOWN reconciliation through allowed transition only;
- state/provider/audit transactional coherence.

## PG-05
Use source DB plus a second clean database/schema/isolated target:
- encrypted backup artifact;
- independent SHA-256;
- wrong-key backup;
- corrupted backup;
- malformed/incomplete backup;
- non-empty restore target rejection;
- PUBLISHED + UNKNOWN + provider ID + mutation events + audit continuity;
- event sequence continuation;
- duplicate barrier after restore;
- UNKNOWN remains unsafe to republish after restore.

Then repeat focused persistence/state no-regression only.

Do not:
- change candidate code;
- deploy candidate;
- cut over production;
- enable public posting;
- use production TikTok secrets;
- use any non-TikTok resource.

Required verdicts:
- PG-02
- PG-03
- PG-04
- PG-05
- Focused No-Regression
- PostgreSQL Directed Retest

Final production acceptance remains NOT AUTHORIZED even if these become PASS.

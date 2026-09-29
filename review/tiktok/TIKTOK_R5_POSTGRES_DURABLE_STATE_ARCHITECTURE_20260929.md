# TikTok R5 — PostgreSQL DurableState Architecture

Date: 2026-09-29
Scope: TikTok only
Isolation: strict

## Governing anchor

Current held runtime:
- service: `trendradar-tiktok-r5-admission`
- service ID: `srv-datgpumk1f9s7387ai70`
- branch: `tiktok-production-prequal-r4-2-retest-candidate-20260929`
- live commit: `ece8039623ee82176d756591af9495414a80d3d6`

That runtime is preserved. This PostgreSQL work is not a cutover.

## Architecture

```text
DurableState.from_env()
  -> explicit backend selection
      -> SQLite backend       [test/dev only]
      -> PostgreSQL backend   [required production]
```

Production requires:

```text
TIKTOK_RUNTIME_MODE=production
TIKTOK_STATE_BACKEND=postgresql
TIKTOK_POSTGRES_URL=<TikTok-dedicated PostgreSQL URL>
TIKTOK_STATE_ENCRYPTION_KEY(S)=<owner-controlled key material>
```

Fail-closed rules:
- missing backend => fail;
- missing runtime mode => fail;
- unsupported backend/mode => fail;
- production + SQLite => fail;
- production PostgreSQL URL missing/invalid => fail;
- PostgreSQL driver unavailable => fail;
- PostgreSQL connection unavailable => fail;
- no fallback to SQLite.

## Preserved semantics

The PostgreSQL backend preserves the existing R5 state model:

Tables / logical authorities:
- OAuth states;
- sessions;
- handoffs;
- publications;
- mutation events / hard-limit admission;
- audit events;
- recovery markers.

Preserved safety properties:
- sensitive session/OAuth payload encryption before persistence;
- one-time OAuth state;
- browser/session state binding;
- one-time handoffs;
- persistent unique idempotency;
- duplicate prevention after restart/redelivery;
- provider publication ID uniqueness;
- state-machine transition validation;
- UNKNOWN remains non-terminal/unsafe to republish;
- attempt count durability;
- audit continuity;
- hard-limit persistence;
- recovery marker persistence.

## Transaction and concurrency model

PostgreSQL publication intent:
- atomic `INSERT ... ON CONFLICT DO NOTHING RETURNING`;
- exactly one creator for a shared idempotency key.

Publication admission:
- explicit SQL transaction;
- PostgreSQL transaction-scoped advisory lock serializes admission decisions;
- publication row is locked `FOR UPDATE`;
- account/global historical and active-operation limits are evaluated inside the same transaction;
- mutation-event insertion + state transition + audit record commit atomically.

Publication state transitions:
- publication row locked `FOR UPDATE`;
- transition validated against the existing state machine;
- provider publication ID remains uniquely constrained;
- transition + audit entry commit atomically.

OAuth/handoff consumption:
- row locked `FOR UPDATE`;
- mismatch does not consume legitimate OAuth state;
- replay remains rejected.

This is intentionally conservative: admission serialization favors safety over maximum throughput.

## Encryption

Application-sensitive payloads remain encrypted with Fernet/MultiFernet before entering PostgreSQL:
- session payload;
- OAuth session binding;
- handoff session binding;
- recovery marker value.

Database compromise alone must not expose plaintext access/refresh tokens from those fields.

Key rotation semantics remain:
- first key writes;
- configured key set can read previous ciphertext during rotation.

## Backup / restore

PostgreSQL backend adds an application-level encrypted logical backup:
- consistent `REPEATABLE READ READ ONLY` snapshot;
- deterministic table export;
- binary fields base64-wrapped inside the logical payload;
- entire logical payload Fernet/MultiFernet encrypted;
- SHA-256 returned for backup artifact;
- restore refuses a non-empty target;
- event sequences reset after restore;
- restored publication/idempotency/provider/audit/recovery-marker state is retained.

This portable backup is a code-level recovery mechanism. R5 production closure still requires:
- backup destination outside the live failure domain;
- production-bound restore exercise;
- provider/platform backup evidence where applicable.

## Dependency / supply chain

Python target remains 3.12.

PostgreSQL driver:
- `psycopg==3.3.6`
- `psycopg-binary==3.3.6`
- `typing-extensions==4.16.0`

All are pinned in `requirements.lock` with SHA-256 hashes and covered by the existing CycloneDX SBOM generator.

## Internal verification

Producer CI uses a real PostgreSQL 16 service container.

Current producer tests include:
- existing SQLite/R3/R4 regression suite;
- explicit production-backend fail-closed selection;
- PostgreSQL unavailable => fail closed;
- encrypted session persistence;
- OAuth state one-time/browser-binding;
- handoff one-time;
- concurrent idempotency exactly-one creation;
- concurrent hard-limit admission;
- atomic terminal transition;
- provider publication ID uniqueness;
- UNKNOWN restart safety;
- encrypted logical backup/restore;
- duplicate barrier after restore;
- audit continuity after restore.

Producer CI is not independent closure evidence.

## Cutover status

`PRODUCTION CUTOVER = HOLD`

Forbidden until directed independent retest:
- replacing the held runtime;
- deleting the old resource;
- granting R5 final production PASS;
- treating SQLite/Persistent Disk as final production state;
- using any non-TikTok database or secret.

## Next gate

Freeze a new exact candidate after internal CI is green.

Then perform a directed independent retest focused on:
- backend selection / no fallback;
- PostgreSQL semantic equivalence;
- concurrency/idempotency/state transitions;
- encryption;
- restart/redelivery/UNKNOWN safety;
- backup/restore + duplicate barrier;
- audit continuity;
- related no-regression probes for previously closed findings.

Only after that may an isolated TikTok PostgreSQL production runtime be created for runtime-equivalence and production persistence/recovery evidence.

# TikTok Production Admission Gate — Post-R3

Date: 2026-09-29
Scope: TrendHunter / Trend Radar — TikTok only

## Governing state

Independent R3 result:
- Exact Target = PASS
- F-01 = CLOSED / PASS
- F-02 = PASS
- F-03 = PASS
- F-04 = CLOSED / PASS
- F-05 = PASS
- R3 Independent Adversarial Retest = PASS

This does NOT authorize production auto-publish.

## Production environment observation

Read-only Render inspection shows:
- TikTok service: `trendradar-tiktok-oauth`
- live branch remains: `tiktok-oauth-service`
- live service plan remains: `free`
- hardened R3 target is not deployed by this work
- no dedicated TikTok Postgres instance is currently evidenced

Any existing non-TikTok database/store is OUT OF SCOPE and MUST NOT be reused for TikTok. Project isolation is mandatory.

## Remaining blocking gates

### G-PERSIST — production-persistent state

Required evidence:
1. hardened exact candidate deployed to an explicitly authorized controlled environment;
2. `TIKTOK_STATE_DB_PATH` points to a truly persistent backend/volume, not ephemeral instance filesystem;
3. recovery marker written;
4. process/service restart or replacement occurs;
5. the same marker is independently verified after restart/replacement;
6. UNKNOWN/PUBLISHED publication records persist;
7. duplicate barriers remain intact.

Current state:
`NOT VERIFIED`

### G-BACKUP — production backup + restore

Required evidence:
1. backup destination is separate from the live runtime failure domain;
2. backup integrity SHA-256 recorded;
3. backup source passes integrity check;
4. isolated restore succeeds;
5. recovery marker survives;
6. PUBLISHED/UNKNOWN state survives;
7. restored state still blocks duplicate publication;
8. restore does not overwrite live state.

Current state:
`NOT VERIFIED`

### G-ALERT — external alert delivery

Internal preparation includes:
- secret-free `/ops/health`;
- signed webhook watchdog tooling.

Independent R4 pre-qualification found the first watchdog version could miss UNKNOWN/stale conditions when source flags were inconsistent and could miss HTTP 404/429 responses. R4.1 independently confirmed those original cases were fixed, but found a narrower type-validation defect: fractional counters such as `0.5` and `-0.5` were coerced with `int(value)` and could become `0`. The post-R4.1 remediation now accepts only real non-negative JSON integers and rejects floats/fractions, numeric strings, booleans, negatives, missing counts, malformed schema, and every non-2xx response fail-closed. This remediation is NOT independently closed yet.

Required external evidence:
1. UNKNOWN/stale/degraded health causes alert;
2. alert leaves the TikTok runtime failure domain;
3. alert reaches an owner-approved operational destination;
4. no token/client secret is included;
5. delivery failure itself is visible.

Current state:
`NOT VERIFIED`

### G-COLD — cold engineer takeover

Required:
- independent engineer receives only source, docs, recovery package and runbooks;
- no original chat/AI/developer help;
- builds and tests;
- starts in NO-PUBLISH mode;
- verifies exact target;
- operates kill switch;
- performs local recovery marker/backup/restore drill;
- diagnoses simulated UNKNOWN;
- demonstrates revoke/reconnect procedure without receiving secret values in documentation;
- records blockers.

Current state:
`NOT VERIFIED`

### G-ARCH — final independent architecture/security acceptance

Required independent review of:
- architecture and trust boundaries;
- production state failure domain;
- backup failure domain;
- alerting failure domain;
- owner control/recovery;
- no hidden dependency on original developer/AI;
- final exact deployed target.

Current state:
`NOT VERIFIED`

## Financial / external infrastructure boundary

The currently observed TikTok Render service is free and does not evidence a persistent TikTok state volume/database.

No paid infrastructure is authorized by this document.
Do not:
- attach a paid disk;
- create a paid database;
- upgrade Render plan;
- deploy the hardened candidate;
until the owner explicitly authorizes that external/financial production-admission step.

## Prepared qualification tools

- `tools/tiktok_recovery_qualification.py`
  - write encrypted recovery marker
  - verify marker after restart
  - create integrity-checked backup
  - isolated restore + marker verification
  - cleanup marker

- `tools/tiktok_ops_watchdog.py`
  - reads secret-free `/ops/health`
  - fail-closes on every non-2xx or malformed/incomplete health response
  - independently evaluates UNKNOWN and stale counts even if source flags are inconsistent
  - accepts those counts only as actual non-negative JSON integers; floats/fractions and coercible strings are rejected
  - sends HMAC-SHA256 signed JSON to an HTTPS webhook
  - does not send OAuth tokens/secrets
  - remains pending independent post-R4 retest

These tools are producer preparation only. Their existence does not close production gates.

## Admission rule

Production Auto-Publish stays:

`NOT AUTHORIZED`

until all blocking gates above have independent closure evidence and a final exact deployed target is reviewed.

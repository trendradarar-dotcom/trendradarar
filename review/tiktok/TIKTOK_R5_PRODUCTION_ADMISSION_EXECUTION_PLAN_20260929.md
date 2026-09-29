# TikTok R5 — Production Admission Execution Plan

Date: 2026-09-29
Project: TrendHunter / Trend Radar
Scope: TikTok ONLY

## Starting anchor

Accepted local/pre-production anchors:
- R3 Independent Adversarial Retest = PASS
- F-01..F-05 = CLOSED / PASS
- R4-01 Recovery Qualification Tooling = PASS
- R4-02 Alert Watchdog Tooling = PASS / CLOSED by R4.2
- R4-03 Documentation Completeness = PASS / CLOSED by R4.2
- Focused Regression = PASS

Exact R4.2 accepted commit:
`ece8039623ee82176d756591af9495414a80d3d6`

Exact R4.2 tree:
`f4fbd1ab5273c0e66decca5b68674e2a1d2ed532`

## R5 objective

Close only the remaining production-bound gates, while keeping public posting disabled.

R5 is NOT public-launch authorization.

## Gate P1 — Production Persistent State

Required:
1. create/attach a TikTok-dedicated persistent state backend or volume;
2. deploy the hardened candidate in NO-PUBLISH posture;
3. set `TIKTOK_MUTATIONS_ENABLED=false`;
4. set `TIKTOK_KILL_SWITCH=true`;
5. keep `TIKTOK_AUDIT_APPROVED=false/unset`;
6. write recovery marker;
7. restart/redeploy/replace the runtime instance;
8. verify the same marker after restart/replacement;
9. verify durable publication records persist;
10. verify duplicate barriers still work.

Pass condition:
`PRODUCTION PERSISTENCE = PASS`

## Gate P2 — Production Backup / Restore

Required:
1. backup destination must be outside the live runtime failure domain;
2. record backup SHA-256;
3. verify source integrity;
4. restore to an isolated target;
5. verify recovery marker survives;
6. verify PUBLISHED/UNKNOWN state survives;
7. verify duplicate barrier survives restore;
8. verify restore never overwrites live state.

Pass condition:
`PRODUCTION BACKUP / RESTORE = PASS`

## Gate P3 — External Alert Delivery

Required:
1. run watchdog outside or independently from the TikTok runtime failure domain;
2. use an owner-approved external alert destination;
3. trigger UNKNOWN/stale/degraded/unreachable conditions;
4. verify alert delivery;
5. verify HMAC;
6. verify no secret leakage;
7. verify delivery failure itself is visible.

Pass condition:
`EXTERNAL ALERT DELIVERY = PASS`

## Gate P4 — Cold Engineer / Owner Takeover

Required:
- a genuinely independent operator receives only exact source/docs/runbooks/recovery package;
- no original chat or undocumented developer/AI knowledge;
- builds/tests;
- starts NO-PUBLISH;
- operates kill switch;
- performs recovery-marker/backup/restore drill;
- diagnoses UNKNOWN;
- demonstrates revoke/reconnect procedure;
- records blockers.

Pass condition:
`COLD ENGINEER HANDOVER = PASS`

## Gate P5 — Golden Recovery Baseline

Required:
- exact deployed commit/tree fixed;
- exact dependency lock/SBOM fixed;
- production state architecture recorded;
- backup destination recorded;
- restore runbook tested;
- alert path tested;
- owner recovery package validated;
- rollback target and procedure verified.

Pass condition:
`GOLDEN RECOVERY BASELINE = PASS`

## Gate P6 — Final Independent Architecture / Security Acceptance

Reviewer must evaluate the ACTUAL deployed architecture:
- runtime;
- persistent state failure domain;
- backup failure domain;
- external alert failure domain;
- owner control;
- secret lifecycle;
- no-publish safety;
- no dependency on original developer/AI;
- exact deployed target.

Only after all production gates pass may the reviewer evaluate:
`SECURITY, RELIABILITY & RECOVERABILITY ACCEPTANCE`

## Current hard stop

At preparation time the observed TikTok Render service remains on a free plan and no dedicated TikTok persistent state database/volume has been independently evidenced.

Therefore R5 cannot begin its production-bound execution until the owner explicitly authorizes the external/financial infrastructure and controlled deployment step.

## Owner authorization required before execution

Explicit authorization is required for any action that may:
- create paid persistent storage/database;
- upgrade the Render service plan;
- attach a persistent disk/volume;
- deploy the hardened candidate to Render;
- configure a real external alert destination.

No such action is authorized by this document.

## Safety posture during R5

Even after owner authorization:
- no public posting;
- no TikTok Recall/Resubmit;
- no `TIKTOK_AUDIT_APPROVED=true`;
- mutations disabled;
- kill switch enabled;
- evidence collection first;
- independent retest before any later launch decision.

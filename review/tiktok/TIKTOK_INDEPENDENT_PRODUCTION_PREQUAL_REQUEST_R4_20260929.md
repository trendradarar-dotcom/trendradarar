# TikTok R4 — Independent Production-Admission Pre-Qualification Request

Date: 2026-09-29
Project: TrendHunter / Trend Radar
Scope: TikTok ONLY

## Review type

Fresh / Independent / Read-Only First / Exact-Target-Bound / Exact-Evidence-Bound / No Producer Trust / Fail-Closed

R4 is NOT a request to deploy or authorize public posting.

Its purpose is to independently review the post-R3 production-admission preparation before any paid infrastructure or deployment is authorized.

## Exact R4 candidate

Repository:
`trendradarar-dotcom/trendradarar`

Frozen branch:
`tiktok-production-admission-candidate-20260929-r4`

EXACT COMMIT:
`dd8e9bac48c8208f3f51bcc83b916db402050d42`

EXACT TREE:
`3beafc241aa5e54f933b4ec4f2a49b8c424c2c2f`

Base independently accepted R3 target:
`47be83f732e63ffc04362f19820c9818e3d574a9`

## Mandatory first gate

Independently verify:
- Git bundle;
- exact commit;
- exact tree;
- full repository snapshot reconstructed root tree;
- package manifest.

Any mismatch:
`EXACT TARGET = NOT VERIFIED`
and stop Fail-Closed.

## R3 closure preservation

R3 independently closed:
- F-01
- F-02
- F-03
- F-04
- F-05

R4 must run focused regression checks for those safety properties but must not silently reinterpret R3 as production acceptance.

## New R4 changes requiring independent review

### R4-01 — recovery qualification markers

Review:
- new `recovery_markers` table;
- marker value encrypted at rest;
- marker key/value validation;
- marker survives database reopen;
- marker survives backup/restore;
- cleanup works;
- no OAuth/token secret is written into marker data.

Run:
`tools/tiktok_recovery_qualification.py`

Required local sequence:
1. write marker;
2. start a fresh process / reopen DB;
3. verify marker hash;
4. create backup;
5. restore to isolated target;
6. verify same marker hash;
7. cleanup.

This is LOCAL/TOOLING evidence only and MUST NOT be called production persistence.

### R4-02 — external alert watchdog

Review:
`tools/tiktok_ops_watchdog.py`

Verify:
- only HTTPS external endpoints are accepted;
- localhost HTTP exists only for test use;
- degraded/unreachable/UNKNOWN/stale health requires attention;
- healthy state sends no alert;
- alert body contains no OAuth/client secrets;
- HMAC-SHA256 signature covers exact JSON body;
- delivery failure returns a failing exit condition;
- no TikTok publication mutation is performed by the watchdog.

Use a reviewer-owned local/mock webhook. Do not contact a real production destination unless separately authorized.

### R4-03 — recovery/cold-handover documentation

Review:
- `review/tiktok/TIKTOK_PRODUCTION_ADMISSION_GATE_20260929.md`
- `review/tiktok/TIKTOK_COLD_ENGINEER_HANDOVER_QUALIFICATION_20260929.md`
- `review/tiktok/TIKTOK_OWNER_RECOVERY_PACKAGE_20260928.md`
- updated evidence matrix.

Determine whether a genuinely cold engineer can execute the documented local build/test/recovery procedure using repository documentation only.

If the reviewer performing R4 is also the same reviewer who already knows the project deeply, report:
`COLD ENGINEER HANDOVER = NOT VERIFIED`
unless a genuinely cold independent operator performs it.

### R4-04 — architecture pre-review

Independently review:
- runtime -> durable state trust boundary;
- local SQLite failure domain;
- proposed production persistence qualification;
- backup failure-domain requirement;
- alert failure-domain requirement;
- owner-control assumptions;
- kill-switch/no-publish posture;
- dependencies on external infrastructure.

Do NOT mark production architecture PASS merely because the tooling is sound.

Final deployed architecture cannot be accepted before the actual persistent state/backup/alert infrastructure exists and is tested.

## Production environment facts to verify read-only if access is available

At preparation time, producer observed:
- Render TikTok service name: `trendradar-tiktok-oauth`
- live branch: `tiktok-oauth-service`
- live plan: free
- hardened R3/R4 target not deployed
- no dedicated TikTok Postgres instance evidenced

Any non-TikTok database/store is OUT OF SCOPE and must not be reused.

If independently verified, record these only as current-environment facts, not PASS for production persistence.

## Required verdicts

Use:
- PASS
- FAIL
- NOT VERIFIED
- N/A

Required R4 verdicts:
- EXACT TARGET
- R3 REGRESSION
- R4-01 Recovery Qualification Tooling
- R4-02 Alert Watchdog Tooling
- R4-03 Documentation Completeness
- Independent Architecture Pre-Review
- Cold Engineer Handover
- Production Persistence
- Production Backup / Restore
- External Alert Delivery
- Owner Recovery
- FINAL PRODUCTION AUTO-PUBLISH ACCEPTANCE

## Expected fail-closed production result

Unless actual authorized production infrastructure is present and independently exercised, these must remain:
- Production Persistence = NOT VERIFIED
- Production Backup / Restore = NOT VERIFIED
- External Alert Delivery = NOT VERIFIED
- Cold Engineer Handover = NOT VERIFIED unless actually performed
- FINAL PRODUCTION AUTO-PUBLISH ACCEPTANCE = NOT VERIFIED / NOT AUTHORIZED

## Non-mutation rules

Do not:
- Deploy;
- Merge;
- change Render configuration;
- create/attach paid infrastructure;
- Recall/Resubmit TikTok App Review;
- enable public posting;
- set `TIKTOK_AUDIT_APPROVED=true`.

## Closure chain

`Evidence -> Remediation -> Independent Retest -> Closure Evidence`

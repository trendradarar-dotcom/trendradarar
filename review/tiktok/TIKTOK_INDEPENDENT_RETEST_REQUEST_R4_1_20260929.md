# TikTok R4.1 — Independent Retest Request

Date: 2026-09-29
Project: TrendHunter / Trend Radar
Scope: TikTok only

## Review mode

Fresh / Independent / Adversarial / Read-Only First / Exact-Target-Bound / Exact-Evidence-Bound / No Producer Trust / Fail-Closed

This is a focused retest of the R4 local failures only.

## Exact R4.1 candidate

Repository:
`trendradarar-dotcom/trendradarar`

Frozen branch:
`tiktok-production-prequal-r4-retest-candidate-20260929-r4-1`

EXACT COMMIT:
`168642cf54a25edf0949f2e61ede457a3ec19f18`

EXACT TREE:
`7b5102b6e71fe788cd220db26bc3afb3c1097ce4`

Previous R4 failed candidate:
`dd8e9bac48c8208f3f51bcc83b916db402050d42`

Base independently accepted R3:
`47be83f732e63ffc04362f19820c9818e3d574a9`

## Mandatory first gate

Independently verify:
- package manifest;
- Git bundle;
- exact commit;
- exact tree;
- full repository snapshot root tree.

Any mismatch => `EXACT TARGET = NOT VERIFIED` and stop Fail-Closed.

## R4-02 — Alert Watchdog Tooling Retest

The prior R4 independently proved false negatives.

R4.1 remediation must be attacked independently.

Required probes:

1. HTTP 200 + `unknown_count=1` + `ok=true` + `attention_required=false`
   - expected: attention required / alert path engaged.

2. HTTP 200 + `stale_nonterminal_count>0` + healthy source flags
   - expected: attention required / alert path engaged.

3. HTTP 404 + valid JSON
   - expected: attention required.

4. HTTP 429 + valid JSON
   - expected: attention required.

5. HTTP 429 + `{}`
   - expected: fail closed / attention required.

6. HTTP 200 + incomplete required health schema
   - expected: fail closed / attention required.

7. invalid/negative UNKNOWN or stale count
   - expected: fail closed / attention required.

8. healthy complete 2xx response with zero UNKNOWN/stale
   - expected: no alert.

9. unreachable endpoint
   - expected: attention required.

10. webhook delivery failure
   - expected: failing exit condition.

11. HMAC-SHA256
   - independently verify signature covers exact emitted JSON body.

12. secret exclusion
   - emitted alert must not contain OAuth access/refresh tokens or client secret.

13. watchdog must not perform any TikTok provider publication mutation.

Use local/mock endpoints only. Do not contact TikTok production.

R4-02 = PASS only if all mandatory fail-closed cases are reproduced independently.

## R4-03 — Documentation Completeness Retest

Independently review current exact candidate documentation.

Verify:
- R3 is correctly recorded as independently PASS within its reviewed scope;
- R4 failure is explicitly recorded;
- watchdog documentation matches actual remediated behavior;
- production persistence/backup/external alert/cold takeover remain NOT VERIFIED;
- no text implies production admission or public posting authorization;
- no stale R2 baseline is presented as current governing state;
- owner recovery package and evidence matrix are mutually consistent.

R4-03 = PASS only if no material state/behavior contradiction remains.

## Focused regression

Do NOT reopen R3 findings without new evidence.

Run a focused regression sufficient to show R4.1 changes did not break:
- recovery qualification tooling;
- OAuth browser/session binding;
- 429 -> UNKNOWN -> later success;
- draft READY mapping;
- media validator code identity relative to accepted R3 path or equivalent regression;
- supply-chain lock/SBOM checks;
- kill switch/no-publish.

## Architecture pre-review

Re-evaluate the pre-review only to the extent affected by R4-02/R4-03.

It is acceptable for architecture pre-review to remain NOT VERIFIED/FAIL-CLOSED for actual production topology because:
- production persistence;
- off-runtime backup failure domain;
- real external alert destination;
- production restore path;
- cold-engineer handover
still do not exist as independently proven production evidence.

Do not convert local tooling success into production architecture acceptance.

## Non-mutation rules

Do not:
- deploy;
- merge;
- change Render;
- create/attach paid infrastructure;
- Recall/Resubmit TikTok App Review;
- enable public posting;
- set `TIKTOK_AUDIT_APPROVED=true`.

## Verdict vocabulary

Use only:
- PASS
- FAIL
- NOT VERIFIED
- N/A

Required verdicts:
- EXACT TARGET
- R4-02 Alert Watchdog Tooling
- R4-03 Documentation Completeness
- Focused R3/R4 Regression
- Architecture Pre-Review
- FINAL PRODUCTION AUTO-PUBLISH ACCEPTANCE

Expected final production result remains:
`NOT VERIFIED / NOT AUTHORIZED`
until real production persistence/recovery/alert/cold-takeover gates are independently closed.

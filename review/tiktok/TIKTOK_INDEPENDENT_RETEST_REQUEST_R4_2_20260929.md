# TikTok R4.2 — Focused Independent Retest Request

Project: TrendHunter / Trend Radar
Scope: TikTok only
Review mode: Fresh / Independent / Adversarial / Exact-Target-Bound / Exact-Evidence-Bound / No Producer Trust / Fail-Closed

## Exact R4.2 candidate

Repository:
`trendradarar-dotcom/trendradarar`

Frozen branch:
`tiktok-production-prequal-r4-2-retest-candidate-20260929`

EXACT COMMIT:
`ece8039623ee82176d756591af9495414a80d3d6`

EXACT TREE:
`f4fbd1ab5273c0e66decca5b68674e2a1d2ed532`

Previous failed R4.1:
`168642cf54a25edf0949f2e61ede457a3ec19f18`

Base accepted R3:
`47be83f732e63ffc04362f19820c9818e3d574a9`

## Mandatory first gate

Verify independently:
- manifest;
- Git bundle;
- commit;
- tree;
- full snapshot root tree.

Mismatch => EXACT TARGET = NOT VERIFIED and stop.

## R4-02 focused retest

Retest the watchdog only, especially strict counter typing.

Required invalid-count probes:
- `unknown_count = 0.5`
- `unknown_count = -0.5`
- `stale_nonterminal_count = 0.5`
- `stale_nonterminal_count = -0.5`
- `unknown_count = 1.0`
- `unknown_count = "1"`
- booleans
- negative integers
- nonnumeric strings
- missing counts

Every invalid value must fail closed / require attention.

Also recheck prior R4 cases:
- UNKNOWN>0 with healthy source flags;
- stale>0 with healthy source flags;
- HTTP 404;
- HTTP 429;
- 429 + {};
- incomplete 200 schema;
- healthy complete 2xx;
- unreachable endpoint;
- webhook delivery failure;
- HMAC-SHA256 exact-body verification;
- secret exclusion;
- no TikTok publication mutation.

## R4-03 documentation retest

Verify documentation now states precisely:
- only real non-negative JSON integer counters are accepted;
- fractional/coercible values are rejected;
- R3 remains PASS;
- R4 and R4.1 failures are recorded;
- production persistence/backup/external alert/cold takeover remain NOT VERIFIED;
- no production/public-posting authorization is implied.

## Focused regression

Do not reopen F-01..F-05 without new contradictory evidence.
Run only enough focused regression to ensure the watchdog/doc changes did not break R3/R4-01 controls.

## Non-mutation rules

No Deploy.
No Merge.
No Render changes.
No paid infrastructure.
No TikTok Recall/Resubmit.
No Public Posting.
No `TIKTOK_AUDIT_APPROVED=true`.

## Required verdicts

- EXACT TARGET
- R4-02 Alert Watchdog Tooling
- R4-03 Documentation Completeness
- Focused Regression
- FINAL PRODUCTION AUTO-PUBLISH ACCEPTANCE

Even if R4-02/R4-03 PASS:
`FINAL PRODUCTION AUTO-PUBLISH ACCEPTANCE = NOT VERIFIED / NOT AUTHORIZED`
until production persistence/recovery/alert/cold-takeover gates are independently closed.

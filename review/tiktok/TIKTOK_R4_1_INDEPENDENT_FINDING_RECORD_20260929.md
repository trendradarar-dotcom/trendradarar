# TikTok R4.1 Independent Finding Record

Date: 2026-09-29
Scope: TikTok only

Exact R4.1 target:
- commit: `168642cf54a25edf0949f2e61ede457a3ec19f18`
- tree: `7b5102b6e71fe788cd220db26bc3afb3c1097ce4`

Independent R4.1 verdict:
- Exact Target = PASS
- R4-02 Alert Watchdog Tooling = FAIL
- R4-03 Documentation Completeness = FAIL
- Focused R3/R4 Regression = PASS
- Architecture Pre-Review = FAIL
- R3 remains PASS; F-01..F-05 remain closed
- Final Production Auto-Publish = NOT VERIFIED / NOT AUTHORIZED

New R4.1 defect:
`_nonnegative_int()` used `int(value)`, so fractional JSON numbers such as `0.5` and `-0.5` could be truncated to `0` and incorrectly treated as healthy.

Required remediation:
- accept only actual non-negative JSON integer values;
- reject all floats/fractions, numeric strings, booleans, negatives, missing/invalid counts;
- keep all prior R4 fail-closed behavior.

Closure requires independent focused retest.

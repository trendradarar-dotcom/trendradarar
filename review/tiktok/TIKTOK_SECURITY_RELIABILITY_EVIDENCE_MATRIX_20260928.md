# TikTok Security / Reliability / Recoverability — Evidence Matrix

Updated: 2026-09-29
Scope: TikTok only

## Independent closure anchors

R3 exact target independently verified:
- commit: `47be83f732e63ffc04362f19820c9818e3d574a9`
- tree: `cf4f045ed253318726ec0aad4b88f7cdac358998`

Independent R3 result:
- F-01 OAuth browser/session binding = PASS / CLOSED
- F-02 429 reconciliation = PASS
- F-03 draft terminal consistency = PASS
- F-04 full H.264 validation = PASS / CLOSED
- F-05 supply-chain hardening = PASS
- R3 Independent Adversarial Retest = PASS

R3 did NOT authorize production auto-publish.

Status vocabulary:
- INDEPENDENT PASS — independently reproduced on the exact reviewed candidate.
- INTERNAL PASS — producer implementation/tests pass but do not replace required independent verification.
- PARTIAL — substantial evidence exists but one or more production/live/independent conditions remain.
- NOT VERIFIED — required evidence remains unavailable.
- N/A — not applicable to the actual design.

## 47-item acceptance matrix

| # | Requirement | Status | Evidence / remaining gap |
|---|---|---|---|
| 1 | Exact Target | INDEPENDENT PASS | R3 commit/tree and full snapshot reconstruction independently matched. |
| 2 | Independent Code Review | PARTIAL | Independent review/retests covered the TikTok implementation and findings, but final post-production-admission candidate review is still required. |
| 3 | Independent Architecture Review | NOT VERIFIED | Final architecture verdict must include the actual production state/backup/alert failure domains. |
| 4 | TikTok Account Binding | INDEPENDENT PASS | R3 two-session adversarial OAuth test proved no state/session/account cross-binding. |
| 5 | OAuth Security | INDEPENDENT PASS | One-time state/replay, browser binding, scope/refresh/open_id regressions independently exercised in the reviewed scope. |
| 6 | Scope Verification | INDEPENDENT PASS | Missing-scope fail-closed regression passed; Direct Post/draft scope separation retained. |
| 7 | Least Privilege | PARTIAL | Code defaults are minimized; production portal/deployed exact-scope admission remains a production-bound check. |
| 8 | Internal Authorization | PARTIAL | Session/CSRF/consent/mutation/kill-switch gates exist; final deployed-target bypass review remains. |
| 9 | Token / Secret Security | PARTIAL | Encrypted state, hashed identifiers, secret exclusions and prior history scanning exist; final deployed-secret operational review remains. |
| 10 | Disconnect Behavior | INTERNAL PASS | Revoke + durable local session removal are covered; production/live provider drill remains controlled. |
| 11 | Upload Path | PARTIAL | Historical provider draft upload worked; hardened exact target is not production deployed. |
| 12 | Direct Post Path | PARTIAL | Historical SELF_ONLY Direct Post worked; hardened exact target is not production deployed. |
| 13 | Direct Post Safety Gate | PARTIAL | Media/account/scope/idempotency/hard-limit gates precede provider mutation; final deployed-target review remains. |
| 14 | Idempotency | INDEPENDENT PASS | Duplicate/idempotency regressions independently passed. |
| 15 | Duplicate Upload Prevention | INDEPENDENT PASS | Independently reproduced duplicate suppression. |
| 16 | Duplicate Publish Prevention | INDEPENDENT PASS | Independently reproduced duplicate barrier/UNKNOWN safety semantics. |
| 17 | Persistent Publication State | PARTIAL | Local durability/restart/restore behavior is proven; production-persistent backend/volume is NOT VERIFIED. |
| 18 | Retry Policy | INDEPENDENT PASS | Zero blind mutation retry policy and reconciliation behavior independently regressed. |
| 19 | Timeout Handling | PARTIAL | UNKNOWN semantics are proven for ambiguous outcomes; final production/provider fault matrix remains. |
| 20 | Fail-Closed | INDEPENDENT PASS | OAuth/session/media/scope/kill-switch and ambiguity gates have independent adversarial/regression evidence. |
| 21 | Unknown-State Handling | INDEPENDENT PASS | UNKNOWN semantics and health signal regressions independently passed. |
| 22 | Negative / Adversarial Tests | INDEPENDENT PASS | R3 completed two-session OAuth and adversarial media corpus required for the outstanding findings. |
| 23 | Race / Concurrency Tests | INTERNAL PASS | Atomic duplicate/admission race tests pass; independent large-stress race evidence is not a current production blocker unless final reviewer requires it. |
| 24 | Media Validation | INDEPENDENT PASS | R3 adversarial corpus proved full-stream H.264 validation and zero provider mutation for rejected media. |
| 25 | SSRF Controls | N/A | Mutation path does not fetch user media URLs. |
| 26 | Metadata Integrity | PARTIAL | Existing validation exists; final deployed-target malformed metadata regression remains advisable. |
| 27 | Rate-Limit Handling | INDEPENDENT PASS | 429 -> UNKNOWN -> later terminal success independently reproduced. |
| 28 | Hard Limits | INTERNAL PASS | Durable transactional account/global limits remain implemented. |
| 29 | Maximum Blast Radius | INTERNAL PASS | Conservative per-account/global limits and active-operation caps remain configured in code. |
| 30 | Monitoring | PARTIAL | `/ops/health` is independently proven to flag UNKNOWN/stale. R4 found a false-negative in the first external watchdog; post-R4 remediation now fail-closes on non-2xx, malformed schema, UNKNOWN>0 and stale>0, but independent retest and real external delivery remain NOT VERIFIED. |
| 31 | Audit Trail | PARTIAL | Durable audit and secret-field rejection exist; final production retention/availability still depends on persistent state. |
| 32 | Kill Switch | INDEPENDENT PASS | Kill-switch regression independently passed. |
| 33 | Read-Only / No-Publish Mode | PARTIAL | Fail-closed posture is implemented; production admission must prove deployed startup/no-publish behavior. |
| 34 | Secret Rotation / Revocation | PARTIAL | Token/key rotation mechanisms exist; owner operational drill remains. |
| 35 | Restart / Crash Recovery | PARTIAL | Local restart/backup/UNKNOWN behavior works; production-bound restart/replacement drill is NOT VERIFIED. |
| 36 | Remote/Local Reconciliation | INDEPENDENT PASS | 429/UNKNOWN/later completion and draft terminal mappings independently reproduced. |
| 37 | Backup / Restore | PARTIAL | Local integrity-checked backup/restore works; off-instance production destination and production restore drill are NOT VERIFIED. |
| 38 | Restore Does Not Duplicate Publishing | INDEPENDENT PASS | Backup/restore duplicate barrier regression independently passed. |
| 39 | Supply Chain Review | INDEPENDENT PASS | R3 independently verified immutable Action SHAs, hash-locked dependencies and exact-commit SBOM binding. |
| 40 | Golden Recovery Baseline | NOT VERIFIED | R3 is independently accepted for its review scope but is not yet the final production Golden Release. |
| 41 | Recovery Runbook | PARTIAL | Runbook exists; R4 documentation review found status inconsistencies which are corrected on the post-R4 remediation branch, pending independent retest; production-bound recovery drill remains. |
| 42 | Owner Recovery Package | INTERNAL PASS | Owner package is documented and updated with production qualification tooling. |
| 43 | Rebuild From Trusted Source | PARTIAL | Procedure/tooling exists; cold independent rebuild has not yet been completed. |
| 44 | Human Takeover | PARTIAL | Takeover procedure exists; independent execution remains. |
| 45 | Cold Engineer Handover | NOT VERIFIED | Must be executed independently using source/docs/runbooks only. |
| 46 | All Blocking Findings Closed | NOT VERIFIED | R3 code findings are closed; production persistence, backup/restore, alert delivery, cold takeover and final architecture acceptance remain open. |
| 47 | No Critical NOT VERIFIED | NOT VERIFIED | Production recovery and ownership gates remain NOT VERIFIED. |

## Current verdict

`R3 INDEPENDENT ADVERSARIAL RETEST = PASS`

Independent R4 pre-qualification:
- Recovery Qualification Tooling = PASS
- Alert Watchdog Tooling = FAIL
- Documentation Completeness = FAIL
- Architecture Pre-Review = FAIL
- production/cold-recovery gates = NOT VERIFIED

Post-R4 local remediation exists but is NOT independently closed yet.

Therefore:

`FINAL PRODUCTION AUTO-PUBLISH ACCEPTANCE = NOT VERIFIED / NOT AUTHORIZED`

## Next admissible sequence

1. prepare production qualification tooling without touching live production;
2. independently review the post-R3 production-admission candidate;
3. obtain explicit owner authorization before any paid persistent infrastructure or deployment;
4. deploy only in NO-PUBLISH / kill-switch posture;
5. prove production persistence across restart/replacement;
6. prove off-instance backup + isolated restore + duplicate barrier;
7. prove external alert delivery;
8. complete cold-engineer handover/recovery;
9. perform final independent architecture/security acceptance on the exact deployed target;
10. only then reconsider public auto-publish authorization.

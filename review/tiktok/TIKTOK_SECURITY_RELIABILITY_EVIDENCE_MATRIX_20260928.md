# TikTok Security / Reliability / Recoverability — Evidence Matrix

Date: 2026-09-28
Scope: TikTok only
Verified pre-remediation live target: `a421e755c31bf8e00a2cffc047db2c7d9e70bcbe`
Current remediation branch: `tiktok-runtime-reliability-remediation-20260928`
Matrix snapshot head: `24f01de955902a3dc2e93917bf2649b93613f4b6`

Status vocabulary:
- INTERNAL PASS — implemented and covered by exact-branch automated evidence, but not a substitute for required independent verification.
- PARTIAL — meaningful evidence exists but at least one required production/independent/live condition remains open.
- NOT VERIFIED — required evidence is not yet available.
- N/A — not applicable to the actual design.

## 47-item acceptance matrix

| # | Requirement | Current status | Exact evidence / remaining gap |
|---|---|---|---|
| 1 | Exact Target | INTERNAL PASS | Render verified the live TikTok service branch and live commit as `tiktok-oauth-service@a421...`; remediation was rebased from that exact runtime. |
| 2 | Independent Code Review | NOT VERIFIED | Current remediation and tests were produced/reviewed by the same remediation agent. Independent reviewer still required. |
| 3 | Independent Architecture Review | NOT VERIFIED | Architecture is documented; independent architecture verdict still required. |
| 4 | TikTok Account Binding | PARTIAL | OAuth `open_id` is persisted, refresh rejects `open_id` drift, publication ledger is account-hash bound, reconciliation rejects account mismatch. Independent/live adversarial confirmation remains. |
| 5 | OAuth Security | PARTIAL | Durable one-time state, expiry, encrypted server-side tokens, refresh, revoke, fail-closed tests. Full independent OAuth attack review remains. |
| 6 | Scope Verification | PARTIAL | Direct Post requires `video.publish`; draft requires `video.upload`; missing-scope test passes. Current already-submitted TikTok review configuration is intentionally untouched while In review. |
| 7 | Least Privilege | PARTIAL | Remediation default removes unproven `user.info.basic`; portal/live scope minimization is deferred until review-safe admission. |
| 8 | Internal Authorization | PARTIAL | Session + CSRF + explicit consent + mutation-enable + kill-switch + safety/hard-limit gates exist. Independent direct-backend/forged-request testing remains. |
| 9 | Token / Secret Security | PARTIAL | Durable session is encrypted, identifiers hashed, secret-like audit details rejected. 19 TikTok-service historical commits were scanned for obvious literal TikTok token/client-secret assignments with no findings. Full independent secret/supply-chain scan remains. |
| 10 | Disconnect Behavior | INTERNAL PASS | Revocation path + durable local session removal + test evidence. Live provider disconnect test is deferred to a controlled authorized phase. |
| 11 | Upload Path | PARTIAL | Existing provider demo proved draft upload; hardened path is internally validated but deliberately not deployed during App Review. |
| 12 | Direct Post Path | PARTIAL | Existing provider demo proved SELF_ONLY Direct Post/PUBLISH_COMPLETE; hardened branch is not deployed. |
| 13 | Direct Post Safety Gate | PARTIAL | Validation, account/scope gate, audit/public gate, idempotency and hard-limit admission precede provider mutation. Independent bypass testing remains. |
| 14 | Idempotency | INTERNAL PASS | Durable primary-key publication intent derived from account + operation + source-content hash; duplicate intent returns existing record. |
| 15 | Duplicate Upload Prevention | INTERNAL PASS | Duplicate content intent for same account/operation is blocked before provider mutation. |
| 16 | Duplicate Publish Prevention | INTERNAL PASS | Same durable idempotency barrier; UNKNOWN records cannot transition back to upload-started. |
| 17 | Persistent Publication State | PARTIAL | SQLite durable ledger + restart/restore tests pass. Production-persistent Render volume/database is not yet evidenced. |
| 18 | Retry Policy | INTERNAL PASS | Automated mutation retries = 0; retry horizon = 0. Ambiguous outcomes require reconciliation rather than blind retry. |
| 19 | Timeout Handling | PARTIAL | Provider/network ambiguity maps to UNKNOWN. Broader live timeout matrix remains for independent retest. |
| 20 | Fail-Closed | PARTIAL | Missing durable state, missing scope, account mismatch, kill switch, malformed/ambiguous provider outcomes fail closed in covered paths. Independent negative matrix remains. |
| 21 | Unknown-State Handling | INTERNAL PASS | UNKNOWN is durable, survives restart, is not PUBLISHED and cannot restart upload by state transition. |
| 22 | Negative / Adversarial Tests | PARTIAL | Scope, token refresh, account mismatch, tamper, duplicate, provider 5xx, restore/restart and kill-switch tests exist. Full requested matrix remains. |
| 23 | Race / Concurrency Tests | PARTIAL | SQLite `BEGIN IMMEDIATE` gives atomic idempotency/admission; explicit parallel-worker stress test still required. |
| 24 | Media Validation | PARTIAL | Type, maximum bytes, complete body and parseable duration are checked. Full codec/resolution/aspect-ratio/integrity matrix is not yet implemented/evidenced. |
| 25 | SSRF Controls | N/A | TikTok mutation paths accept uploaded video bytes; they do not fetch user-supplied media URLs. Reassess if URL ingestion is added. |
| 26 | Metadata Integrity | PARTIAL | Caption length, privacy, creator interaction restrictions and operation-bound metadata hash are present. Broader malformed/encoding/injection tests remain. |
| 27 | Rate-Limit Handling | PARTIAL | Conservative internal hard limits and zero automatic retries reduce storm risk. Live TikTok 429 behavior still requires controlled evidence. |
| 28 | Hard Limits | INTERNAL PASS | Per-account/hour/day, global/hour/day and active-account/global limits are enforced transactionally. |
| 29 | Maximum Blast Radius | INTERNAL PASS | Defaults: 6/account/hour, 24/account/day, 12/global/hour, 48/global/day, 1 active/account, 2 active/global, duplicate publish=0. |
| 30 | Monitoring | NOT VERIFIED | No production alerting/monitoring acceptance evidence yet. |
| 31 | Audit Trail | INTERNAL PASS | Durable publication/admission/state/control audit events; secret field names are rejected from audit details. |
| 32 | Kill Switch | INTERNAL PASS | Mutations are disabled by default; explicit kill switch blocks Direct Post, draft and private test with HTTP 423. |
| 33 | Read-Only / No-Publish Mode | INTERNAL PASS | Default runtime posture blocks mutations while health/status/reconciliation paths remain available. |
| 34 | Secret Rotation / Revocation | PARTIAL | Token refresh rotation, TikTok revoke flow and MultiFernet key rotation support/tests exist. Operational owner rotation drill remains. |
| 35 | Restart / Crash Recovery | PARTIAL | PROCESSING/UNKNOWN persistence and backup/restore tests pass. Full crash-at-each-side-effect fault-injection matrix remains. |
| 36 | Remote/Local Reconciliation | INTERNAL PASS | Provider status updates DIRECT_POST to PUBLISHED, draft to READY, 5xx to UNKNOWN; account mismatch blocks provider query. |
| 37 | Backup / Restore | PARTIAL | Verified SQLite backup/quick-check/restore implementation and tests. Production backup destination/state persistence not yet proven. |
| 38 | Restore Does Not Duplicate Publishing | INTERNAL PASS | Restored PUBLISHED intent remains duplicate-blocking; UNKNOWN intent remains non-republishable. |
| 39 | Supply Chain Review | PARTIAL | `cryptography` is version-pinned; GitHub Actions are pinned by immutable commit SHA. Full dependency-hash/SBOM/independent review remains. |
| 40 | Golden Recovery Baseline | NOT VERIFIED | Golden Release is intentionally NOT frozen before independent retest and production persistence evidence. |
| 41 | Recovery Runbook | PARTIAL | Repository runbook exists. A controlled independent recovery drill is still required. |
| 42 | Owner Recovery Package | INTERNAL PASS | Owner package records source, architecture, trust boundaries, env names, state schema, build/run, revoke, backup/restore and rebuild flow. |
| 43 | Rebuild From Trusted Source | PARTIAL | Procedure is documented; clean-room rebuild execution is not yet independently proven. |
| 44 | Human Takeover | PARTIAL | Handover material exists; takeover by a new engineer has not yet been observed. |
| 45 | Cold Engineer Handover | NOT VERIFIED | Must be executed by a person/agent independent of development using only repository package/runbooks. |
| 46 | All Blocking Findings Closed | NOT VERIFIED | Production persistence, monitoring, media validation, independent pen/review, cold handover and remaining adversarial probes are open. |
| 47 | No Critical NOT VERIFIED | NOT VERIFIED | Independent verification and production-recovery evidence are intentionally still open. |

## Current verdict

`SECURITY, RELIABILITY & RECOVERABILITY ACCEPTANCE — PASS` = **FORBIDDEN AT THIS STAGE**

Reason:
- implementation/remediation evidence is materially stronger;
- but the requested gate explicitly requires independent verification and production recovery evidence;
- the hardened branch is deliberately not deployed while the TikTok Developer App Review remains In review.

## Next admissible sequence

1. close remaining internal testable gaps without touching the pending TikTok App Review;
2. freeze one exact remediation candidate;
3. produce independent-review handoff;
4. independent adversarial/security/recovery retest;
5. only after that, separately authorize a controlled production-persistence admission/deployment;
6. never infer public posting authority from generic App Review status.

# TikTok Security, Reliability & Recoverability — Remediation Gate

Date: 2026-09-28
Project: TrendHunter / Trend Radar — TikTok channel only
Base exact target: a421e755c31bf8e00a2cffc047db2c7d9e70bcbe
Remediation branch: tiktok-runtime-reliability-remediation-20260928
Governance: ALI-PROGRAMMER-GOVERNANCE-GENERAL-1.5.0 + ALI_PRO
Isolation: TikTok only. No YouTube/Snapchat/Instagram/Tanoub/TCC mutation.
Main mutation: FORBIDDEN.
TikTok Developer review mutation/recall/resubmit: FORBIDDEN.
Public publication: FORBIDDEN.
TIKTOK_AUDIT_APPROVED: must remain false/unset.

## Exact-target correction

Fresh Render verification established that the live TikTok service `trendradar-tiktok-oauth` is bound to branch `tiktok-oauth-service` and its current LIVE deploy is commit `a421e755c31bf8e00a2cffc047db2c7d9e70bcbe`.

The earlier documentation-review commit `f54e2ab4655fe8799865666a5b588fadfd795d19` is NOT the live runtime target and MUST NOT be used as the production-readiness acceptance target.

The prior branch `tiktok-reliability-remediation-20260928` is therefore superseded and must not be merged or deployed.

## Discovery verdict

FINAL_ACCEPTANCE = NOT_YET_ELIGIBLE

Confirmed strengths at the exact target:
- OAuth state is random, one-time and TTL-bound.
- TikTok access/refresh tokens are kept server-side.
- Creator Info is queried before Direct Post.
- Pre-audit flow restricts Direct Post to SELF_ONLY and private-account guard.
- Existing evidence proves OAuth, Creator Info, Direct Post init, binary upload and PUBLISH_COMPLETE for SELF_ONLY.

Confirmed production-readiness blockers:
1. OAuth/session/state storage is process-memory ephemeral.
2. No durable publication ledger is proven.
3. No durable idempotency key/uniqueness barrier is proven.
4. No durable publication state machine with UNKNOWN semantics is proven.
5. No restart/retry/duplicate-worker reconciliation proof is present.
6. No independent TikTok publication kill switch with closure test is proven.
7. No bounded retry policy with durable retry counters/horizon is proven.
8. No production backup/restore evidence for publication state is proven.
9. No Golden Release + rollback/recovery evidence is proven.
10. No cold-engineer recovery handover evidence is proven.

## Required remediation order

R1 — Durable state foundation
- Move security/session/publication state required for recovery out of process memory.
- Store only the minimum required sensitive material, encrypted/protected by the runtime secret boundary.
- Define retention and revocation behavior.

R2 — Publication ledger + state machine
- Create a durable publication record before any TikTok upload/init.
- Minimum states:
  RECEIVED -> VALIDATED -> SAFETY_APPROVED -> UPLOAD_STARTED -> UPLOADED -> PUBLISH_REQUESTED -> PROCESSING -> PUBLISHED
  with FAILED and UNKNOWN terminal/holding semantics.
- UNKNOWN must never be treated as PUBLISHED or automatically retried as a new publication.

R3 — Idempotency / duplicate suppression
- Bind each publication intent to a stable idempotency key.
- Enforce uniqueness atomically in the durable store.
- Same intent after timeout/restart/duplicate worker must converge on the same record/provider publication rather than create a second post.

R4 — Reconciliation and recovery
- Persist TikTok publish_id/provider identifiers immediately when received.
- On timeout/restart, query provider status before any retry.
- Ambiguous provider outcome -> UNKNOWN -> reconciliation; never blind repost.

R5 — Retry hard limits
- Explicit retryable vs non-retryable taxonomy.
- Persist attempt count and retry horizon.
- Exponential/backoff policy with hard maximum attempts and hard maximum horizon.
- Exhaustion -> FAILED or UNKNOWN; no infinite loop.

R6 — Independent kill switch
- Add a fail-closed TikTok publication switch independent of TIKTOK_AUDIT_APPROVED.
- It must block Direct Post, draft upload, queued retries and workers before external side effects.
- Preserve ledger/evidence while disabled.
- Test enable -> block -> verify no provider call -> re-enable.

R7 — Backup / restore / golden release
- Define backup target for durable publication/security state.
- Prove restore into isolated environment.
- Freeze a known-good Golden Release with exact commit/config schema and rollback procedure.

R8 — Independent adversarial retest
Mandatory probes:
- duplicate same request
- concurrent duplicate workers
- crash after provider init
- crash after binary upload
- timeout after publish request
- provider 429/5xx
- malformed/expired OAuth state
- expired token / revoked authorization
- kill switch during queued retry
- restart with PROCESSING record
- UNKNOWN reconciliation
- backup restore
- rollback to Golden Release

## Closure rule

No item is PASS by implementation claim alone.

Required chain:
Evidence -> Remediation -> Independent Retest -> Closure Evidence.

Final PASS is forbidden until all blocking probes have exact-target evidence and no unresolved Critical/High finding remains.

## Current external TikTok review

The already-submitted TikTok Developer App Review is outside this remediation branch.
Do not Recall, resubmit, alter production review settings, or enable public posting while remediation is underway.

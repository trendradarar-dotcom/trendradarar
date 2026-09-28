# INDEPENDENT REVIEW REQUEST — Instagram M26.3

PROJECT: TrendHunter / Trend Radar
SCOPE: Instagram only
REVIEW MODE: Fresh / Independent / Adversarial / Read-Only / Exact-Target-Bound / Exact-Evidence-Bound / No Producer Trust / Fail-Closed

## Purpose

Issue an independent readiness verdict for the remediated Trend Radar Instagram publisher before any public-production authority is enabled.

The reviewer must not rely on producer/remediator verdicts as evidence of PASS.

## Exact product target

Repository:
trendradarar-dotcom/trendradarar

Remediation branch:
instagram-production-remediation-20260928

EXACT CODE TARGET:
8017927555ccceef8d0ab649a1a2b519f4d5efae

EXACT TREE:
0deaebe8a5c0f0a1ac357b8a88e5d8fc144f5efc

LIVE EQUIVALENT COMMIT:
72cbb290dd9c681966f2415947bb61de551dcac8

LIVE TREE:
0deaebe8a5c0f0a1ac357b8a88e5d8fc144f5efc

The commit hashes differ because the live review branch has synchronization/evidence lineage, but the exact deployed product tree is identical to the independently reviewable remediation target.

## Safety state during review

The reviewer must verify, not assume:

INSTAGRAM_PUBLIC_PUBLISH_AUTHORIZED=false
INSTAGRAM_PUBLISH_ENABLED=false
browser_public_publish_enabled=false

No real public Reel may be published by the review.

## Mandatory independent probes

### A. Target identity / provenance
- Resolve exact target commit and tree independently.
- Verify live Render product tree equivalence from code/deploy evidence.
- Verify no unreviewed code path can call media_publish.

### B. Browser-vs-machine separation
- Fresh unauthenticated /share must be denied.
- Fresh unauthenticated /api/reel must be denied.
- Browser review path must never call media_publish.
- GET /disconnect must not mutate authorization.
- Disconnect must require an owner-authorized session.

### C. Machine publisher authentication
- Machine media and publish endpoints must reject missing/wrong M2M authorization.
- Confirm durable machine token is unavailable to ordinary browser sessions.
- Confirm App Secret and OAuth token are not exposed by machine/browser responses.

### D. Publication contract / fail-closed gates
Independently verify that publication requires:
- exact account binding @trendradarar
- market SA
- language ar
- rights_status PASS
- policy_status PASS
- legal_status PASS
- commercial_status EDITORIAL_ORIGINAL
- admitted content_asset_id
- exact asset SHA-256
- idempotency_key
- correlation_id
- supported media metadata

UNKNOWN/non-PASS gates must HOLD, never publish.

### E. Idempotency / duplicate prevention
- Same idempotency key + same contract returns existing state.
- Same idempotency key + changed contract fails closed.
- State is persisted before provider publication side effects.
- UNKNOWN / ambiguous provider outcomes do not cause blind media_publish retry.
- PUBLISH_REQUESTED after restart/recovery must reconcile/fail closed rather than issue a second publish.

### F. Durable media staging
- Machine path must use the bounded durable spool, not tempfile.
- Verify content_asset_id + token + SHA-256 + expiry binding.
- Verify invalid/expired/mismatched media fails closed.
- Verify spool capacity/size limits.
- Confirm ephemeral /media review path cannot be admitted as production source.

### G. Provider controls
- Verify content_publishing_limit preflight.
- Verify daily publication cap.
- Verify max inflight.
- Verify unpublished queue cap.
- Verify recent-failure circuit breaker.
- Verify mutation-rate and per-job mutation caps.
- Verify processing reconciliation cadence is bounded.
- Verify post-publish provider-side media identity verification logic.

### H. TrendHunter bridge
- Verify governed manifest requirements.
- Verify cold-start retries are bounded.
- Verify retries do not create new publication intent/idempotency key.
- Verify reconciliation uses existing idempotency key.
- Verify terminal HOLD/UNKNOWN conditions stay fail-closed.

### I. Credential lifecycle / recovery
- Verify encrypted persistent token path.
- Verify restart reload.
- Verify refresh logic exact-account binding.
- Verify signed deauthorization/data deletion.
- Verify durable Disconnect semantics.
- Verify owner recovery/human takeover remains possible without weakening normal zero-human operation.

### J. Build / regression
- Independently inspect exact-pinned Python dependencies.
- Confirm Python 3.14.3 is the admitted runtime.
- Inspect current Instagram Publisher Admission CI.
- Re-run or independently inspect the exact-target adversarial tests.
- Do not accept an older PASS for a different tree.

### K. Live safe evidence
Review safe live self-test evidence:
INSTAGRAM_PUBLISHER_SELF_TEST
- ok=true
- m2m_auth=PASS
- media_spool=PASS
- idempotency=PASS
- publish_gate=HOLD_PUBLIC_DISABLED
- cleanup=PASS
- public_publish_authorized=false

Treat producer-generated self-test output as evidence to verify against code/runtime, not as a verdict.

## Known deliberately unexecuted event

A real hardened M2M media_publish call has NOT yet been executed, because owner public-publish authority remains false.

The reviewer must determine whether the exact target is:
- eligible for a governed first-public activation after independent PASS; or
- blocked by a concrete implementation/evidence gap that must be remediated first.

The reviewer must NOT perform the first public publication.

## Required verdict format

Return each mandatory area as:
PASS / FAIL / NOT VERIFIED

Then return:

CRITICAL_OPEN =
HIGH_OPEN =
MEDIUM_OPEN =
EXACT_TARGET_VERIFIED =
LIVE_TREE_EQUIVALENCE =
PUBLIC_GATES_CONFIRMED_FALSE =
OWNER_ONLY_STANDARD_ACCESS_CONSISTENT =
FIRST_PUBLIC_ACTIVATION_ELIGIBLE =
INDEPENDENT_FINAL_VERDICT = PASS / FAIL-CLOSED

If any mandatory evidence is missing or target identity is uncertain:
FAIL-CLOSED.

No remediation or mutation is allowed in this review.

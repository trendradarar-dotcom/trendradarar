# Instagram M26.2 — Readiness Verification — 2026-09-28

Project: TrendHunter / Trend Radar
Scope: Instagram public publishing admission
Mode: Fresh Verification / Read-Only / No Remediation / Exact-Target-Bound

## Product target under verification

Repository: trendradarar-dotcom/trendradarar
Branch at review start: instagram-production-review-20260924
Product HEAD: 6106fbb517cf41fa5d0f7d6e4e1ba1e7d76d650c
Product TREE: 10a37abbd151c104802d1d819ab6f6bf3516790d

Discovery evidence was recorded afterward in an evidence-only commit and does not alter the product target under judgment.

Live backend:
- trendradar-instagram-oauth
- deploy dep-daspnl0473hc739dntag
- commit 6106fbb517cf41fa5d0f7d6e4e1ba1e7d76d650c
- LIVE

Live gateway:
- trendradar-connect
- deployed commit 27f94fa1882b20218fe0ff52f7592019778ec552
- gateway app.py + requirements.txt are byte-identical to the same files at product HEAD

Discovery source:
review/instagram/M26_2_FRESH_DISCOVERY_REVIEW_20260928.md

## Verification matrix

| Requirement | Result | Evidence / reason |
|---|---|---|
| Exact backend product target live | PASS | Render live deploy is exact commit 6106fbb |
| Gateway code equivalence to target | PASS | app.py and requirements blobs byte-identical |
| Trusted custom OAuth domain | PASS | auth.trendradar.com.co recovered to configured=true after cold start |
| Instagram OAuth configuration | PASS | backend /health configured=true |
| Exact account binding @trendradarar | PASS | fresh live /share returns @trendradarar |
| Professional account type | PASS | BUSINESS |
| Professional user ID | PASS | 17841428134382903 |
| Required granted scopes | PASS | instagram_business_basic + instagram_business_content_publish |
| Owner-only Standard Access model | PASS | current Meta owner-managed/Instagram Login model does not require App Review |
| Encrypted durable token persistence | PASS | persistence_configured=true and prior restart reload evidence |
| Persistence fail-closed | PASS | persistence_required=true |
| Long-lived token refresh | PASS | prior REFRESHED_VERIFIED evidence for same account/id |
| Public-publish default currently closed | PASS | public_publish_authorized=false |
| Owner/publisher authorization on publish surface | FAIL | /share and /api/reel lack owner/M2M publish authorization; fresh anonymous session receives persisted account token context |
| Request-level publish authorization | FAIL | global env switch + consent field is not a caller authorization boundary |
| Idempotent/exactly-once publication | FAIL | no idempotency key or durable publish-intent/job ledger |
| Durable publication audit receipt | FAIL | no persistent container/media_id outcome ledger |
| Durable media hosting | FAIL | tempfile + in-memory MEDIA_STORE on web instance |
| Autonomous TrendHunter publisher binding | NOT VERIFIED | exact repo target contains review/browser flow; no proven engine worker/queue binding |
| Cold-start-safe unattended availability | FAIL | trusted gateway produced HTTP 503 on fresh cold-start probes |
| Durable retry/backoff around publish | FAIL | no exact-target durable publication queue/retry contract |
| Media format/provider preflight | FAIL | only .mp4 suffix + non-empty validation |
| Provider publishing-limit guard | FAIL | no /content_publishing_limit preflight |
| Provider-aligned processing poll strategy | FAIL | 3-second polling vs current Meta recommended ~1 minute cadence |
| True durable Disconnect behavior | FAIL | /disconnect clears only session/in-memory record |
| Fail-closed provider deauthorization | FAIL | invalid/missing signed_request still returns DEAUTHORIZED 200 without deleting durable token |
| Exact-target regression tests | FAIL | repository exact tree contains zero test files |
| Instagram CI admission workflow | FAIL | only Pages workflow exists |
| Reproducible Python runtime | FAIL | no Python version pin |
| Reproducible dependency set | FAIL | ranged requirements, no dependency lock |
| First real public media_publish outcome | NOT VERIFIED | intentionally not executed while public-publish gate is false |

## Critical readiness interpretation

The provider foundation itself is ready:
- Meta access model
- OAuth
- account identity
- permissions
- durable token storage
- refresh
- trusted domain

However, the current publication surface is not production-safe.

The most important blocker is authorization:
a fresh unauthenticated browser can load the persisted @trendradarar connection through /share. In the same build, /api/reel can proceed to media_publish whenever the global public-publish flag is true.

Therefore changing only:
INSTAGRAM_PUBLIC_PUBLISH_AUTHORIZED=true

would be unsafe and is explicitly NOT admitted.

## Final readiness verdict

PROVIDER_FOUNDATION = READY
TOKEN_RUNTIME = READY
OWNER_ONLY_STANDARD_ACCESS = READY
PUBLICATION_CONTROL_PLANE = NOT READY
AUTONOMOUS_PUBLISH_PATH = NOT READY
EXACT_TARGET_TEST_ADMISSION = NOT READY
REPRODUCIBLE_BUILD = NOT READY

**INSTAGRAM PUBLIC PUBLISH READINESS = NOT READY**

**ENABLE PUBLIC PUBLISH FLAG = PROHIBITED ON THIS TARGET**

This is an internal engineering readiness failure, not a Meta rejection and not an App Review blocker.

## Required remediation order before re-verification

1. Protect the publish plane with exact owner/M2M authentication and deny anonymous /share + /api/reel publication authority.
2. Introduce signed machine publish intent + idempotency key + durable publication job/receipt ledger.
3. Move provider-fetch media to durable object storage with bounded lifetime.
4. Bind the actual TrendHunter content pipeline to the protected publisher and prove zero-human execution.
5. Add retry/backoff/cold-start handling or an always-on runtime appropriate for unattended publication.
6. Add deterministic media preflight, provider publishing-limit guard, and provider-aligned status polling.
7. Correct Disconnect/deauthorization durable revocation semantics.
8. Add exact-target automated tests + Instagram CI admission.
9. Pin Python and dependency versions for reproducible builds.
10. Perform a fresh discovery review and then a fresh readiness verification on the remediated exact target.
11. Only after both pass may the owner decide whether to enable public publishing and execute the first governed public Reel.

NO REMEDIATION WAS PERFORMED BY THIS REVIEW.
PUBLIC_PUBLISH_AUTHORIZED remains false.

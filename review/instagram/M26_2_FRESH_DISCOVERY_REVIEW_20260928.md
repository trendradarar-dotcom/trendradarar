# Instagram M26.2 — Fresh Discovery Review — 2026-09-28

Project: TrendHunter / Trend Radar
Scope: Instagram only
Mode: Fresh / Adversarial / Read-Only / No Remediation / Exact-Target-Bound
Public publishing during review: DISABLED

## Exact target

Repository: trendradarar-dotcom/trendradarar
Branch: instagram-production-review-20260924
HEAD: 6106fbb517cf41fa5d0f7d6e4e1ba1e7d76d650c
TREE: 10a37abbd151c104802d1d819ab6f6bf3516790d

Backend live deploy:
- service: trendradar-instagram-oauth
- deploy: dep-daspnl0473hc739dntag
- commit: 6106fbb517cf41fa5d0f7d6e4e1ba1e7d76d650c
- status: LIVE

Gateway live deploy:
- service: trendradar-connect
- deploy: dep-das2n9p7lnhs73fc9f2g
- commit: 27f94fa1882b20218fe0ff52f7592019778ec552
- status: LIVE
- gateway app.py blob and requirements.txt blob are byte-identical to exact HEAD 6106fbb:
  - app.py blob: e46699edfae10801c6e4ae28f468be0475b5c6a2
  - requirements.txt blob: 0f0fe5bcd49afb2c4b1b4506ae9a9e1c30962bbb

## Fresh live probes

Backend /health:
- configured=true
- persistence_configured=true
- persistence_required=true
- public_publish_authorized=false
- API version=v26.0

Fresh unauthenticated browser request to backend /share:
- returned the connected account @trendradarar
- account type BUSINESS
- professional user ID 17841428134382903
- granted scopes:
  - instagram_business_basic
  - instagram_business_content_publish

Trusted gateway:
- first cold-start probes returned HTTP 503
- Render logs showed free-tier worker start
- subsequent probes to trendradar-connect.onrender.com/health and auth.trendradar.com.co/health returned configured=true / HTTP 200

## Provider reconciliation

Current Meta documentation reviewed:
- App Review for Instagram API, updated Jun 30 2026:
  https://developers.facebook.com/documentation/instagram-platform/app-review
- Content Publishing, updated Jun 30 2026:
  https://developers.facebook.com/documentation/instagram-platform/content-publishing

Current owner-only Standard Access model remains consistent with the live integration:
- one owner-managed account: @trendradarar
- Instagram Login
- Standard Access
- App Review not required for the current owner-only scenario
- content publishing guide supports Standard Access with Instagram Login
- live granted scopes match the working provider path

## Discovery findings

### D-01 — CRITICAL — publish operation lacks owner/publisher authorization

The public backend /share and POST /api/reel do not require an owner login, publish API secret, signed internal request, or other publisher authorization.

Source evidence:
- _token_record() falls back from the request session to the single persisted token for EXPECTED_USERNAME.
- /share calls _token_record() and renders the connected Trend Radar account.
- /api/reel calls _token_record() and then relies only on multipart input + consent=true.
- media_publish is executed whenever the global environment flag PUBLIC_PUBLISH_AUTHORIZED is true.

Fresh runtime proof:
A fresh browser with no prior owner session opened /share and received @trendradarar and its professional ID/scopes.

Impact:
If INSTAGRAM_PUBLIC_PUBLISH_AUTHORIZED is changed to true in the current build, any party able to reach the backend and submit the form/API can potentially publish to @trendradarar.

Verdict: BLOCKING.

### D-02 — HIGH — no idempotency / durable publication ledger

The publication path has no idempotency key, no durable job record, no unique publish-intent record, and no persistent media/container/media_id receipt ledger.

Impact:
Retries, browser resubmission, caller retries, ambiguous provider timeout, or automation retries can create duplicate public posts and leave no exact once-only audit trail.

Verdict: BLOCKING for autonomous production.

### D-03 — HIGH — production media source is ephemeral process-local storage

Uploaded video is saved under tempfile and indexed only in in-memory MEDIA_STORE.
The provider video_url points back to /media/<uuid>.mp4 on the same web instance.

Impact:
Restart, deploy, instance replacement, or process loss between upload and Meta fetch can invalidate the video URL. This is a review/demo architecture, not durable media delivery.

Verdict: BLOCKING for autonomous production.

### D-04 — HIGH — no proven TrendHunter-to-Instagram autonomous publish binding

The repository contains the isolated OAuth/Reels review service and gateway but no tested production worker/queue/job binding from the TrendHunter content factory into a protected Instagram publishing API.

The README explicitly names this component a Review Service.
The currently demonstrated path is a browser form upload with per-request checkbox consent.

Impact:
Provider connectivity is proven, but zero-human production publication from the engine is not proven on the exact live target.

Verdict: BLOCKING for zero-human production.

### D-05 — HIGH — free web services demonstrated cold-start unavailability

Both Render web services are on free plans.
Fresh probes to the trusted gateway returned HTTP 503 until Render started the worker; later probes recovered to HTTP 200.

Impact:
A scheduled autonomous publish can hit a transient 503. No durable publish queue/retry contract is present in this exact target.

Verdict: BLOCKING for unattended time-sensitive publication unless compensated by a durable retrying caller or always-on runtime.

### D-06 — MEDIUM — Disconnect does not disconnect durable authorization

GET /disconnect removes only TOKEN_STORE for the current sid and clears the Flask session.
It does not delete the encrypted Postgres token.

Because _token_record() reloads the persistent token, a later fresh session can reconnect automatically.

Impact:
The UI label “Disconnect” does not match actual durable authorization state.

Verdict: remediation required before production UI exposure.

### D-07 — MEDIUM — deauthorization callback is fail-open on invalid/missing signed request

/deauthorize deletes durable authorization only when a valid signed_request with user_id is present.
Otherwise it clears only the local session and still returns HTTP 200 DEAUTHORIZED.

Impact:
A malformed or unverifiable provider deauthorization can be acknowledged as success while the durable token remains.

Verdict: remediation required.

### D-08 — MEDIUM — media preflight is insufficient

Current validation is limited to:
- filename suffix .mp4
- non-empty file
- global 120 MiB request limit

No exact codec/container/duration/dimensions/frame-rate/audio/provider-eligibility preflight is present.

Impact:
Invalid media reaches Meta before deterministic local rejection, reducing zero-human reliability.

Verdict: remediation required for autonomous production.

### D-09 — MEDIUM — publishing rate-limit guard absent

The provider guide exposes /<IG_ID>/content_publishing_limit and documents an API publishing limit.
The exact target does not query or enforce this limit before publication.

Impact:
Autonomous publication has no fail-closed provider quota guard.

Verdict: remediation required.

### D-10 — MEDIUM — container polling cadence is aggressive

Current code polls every 3 seconds, up to 20 iterations.
Meta’s current Content Publishing troubleshooting guidance recommends polling approximately once per minute for no more than five minutes.

Impact:
Unnecessary request pressure and shorter processing tolerance.

Verdict: remediation required.

### D-11 — MEDIUM — current exact target has no Instagram regression tests or CI admission

Exact tree scan:
- test file count = 0
- GitHub workflows = only .github/workflows/pages.yml

Prior M26 test evidence predates the current gateway, encrypted persistence, deauthorization hardening, refresh path, and current production decision.

Impact:
No repeatable exact-target automated proof protects the current branch.

Verdict: BLOCKING under exact-target admission governance.

### D-12 — MEDIUM — runtime/dependency build is not reproducibly pinned

Instagram requirements use version ranges rather than exact locks.
No .python-version, runtime.txt, requirements lock, Poetry/Pipfile/uv lock exists.
Render logs show use of the current default Python runtime (3.14.3).

Impact:
A rebuild can produce different bytes/dependency behavior from the reviewed target.

Verdict: BLOCKING under exact-build reproducibility governance.

### D-13 — LOW/MEDIUM — backend operational surface is publicly exposed

Backend service IP allow list is 0.0.0.0/0 and /share exposes connected account identity/scopes.
The trusted gateway is hardened for browser OAuth, but publication UI remains directly on the backend.

Impact:
Unnecessary operational surface and metadata exposure.

Verdict: should be reduced as part of D-01 remediation.

### D-14 — NOTE — gateway deploy commit differs from branch HEAD, but relevant bytes match

The live gateway reports commit 27f94..., while branch HEAD is 6106....
Fresh blob comparison proves gateway app.py and requirements.txt are byte-identical between those commits.

Impact:
No functional gateway-code drift was found, but exact deployment provenance should be normalized for a final frozen production admission target.

Verdict: non-blocking if byte-equivalence receipt is retained; normalize before final freeze.

## Discovery conclusion

Provider/OAuth/token foundation is healthy, but enabling the global public-publish flag on the current target is unsafe.

DISCOVERY_REVIEW = FINDINGS_PRESENT
PUBLIC_PUBLISH_ENABLEMENT = DO NOT AUTHORIZE
NO REMEDIATION PERFORMED

# Instagram M26.3 — Post-Remediation Fresh Discovery — 2026-09-28

PROJECT: TrendHunter / Trend Radar
SCOPE: Instagram only
MODE: Fresh / Adversarial / Read-Only verification of remediated candidate
PUBLIC PUBLISHING DURING REVIEW: DISABLED

## Exact remediation candidate

Branch: instagram-production-remediation-20260928
HEAD: 8017927555ccceef8d0ab649a1a2b519f4d5efae
TREE: 0deaebe8a5c0f0a1ac357b8a88e5d8fc144f5efc

The live review branch contains byte-identical remediated app.py and tests after synchronization.

## Evidence reviewed

- Exact-target GitHub Actions run 36361758029: SUCCESS
  - checkout: PASS
  - Python 3.14.3 setup: PASS
  - exact dependency install: PASS
  - exact source compile: PASS
  - adversarial publisher tests: PASS
- Prior exact candidate run 36359891491: SUCCESS
- Live safe publisher self-test:
  - event=INSTAGRAM_PUBLISHER_SELF_TEST
  - ok=true
  - m2m_auth=PASS
  - media_spool=PASS
  - idempotency=PASS
  - publish_gate=HOLD_PUBLIC_DISABLED
  - cleanup=PASS
  - public_publish_authorized=false
- Live health after remediation:
  - configured=true
  - persistence_configured=true
  - persistence_required=true
  - publisher_m2m_configured=true
  - publisher_control_plane_configured=true
  - media_host_allowlist_configured=true
  - publisher_media_spool_configured=true
  - public_publish_authorized=false
  - instagram_publish_enabled=false
  - browser_public_publish_enabled=false
- Fresh anonymous /share probe: HTTP 403.
- Render Python runtime: 3.14.3 via PYTHON_VERSION.
- Requirements are exact-pinned.
- Latest disconnect hardening requires POST; GET is covered by adversarial test and returns 405 on the exact candidate.

## Closure of prior findings

D-01 anonymous publisher authority: CLOSED.
Browser sessions cannot inherit the persisted machine credential. /share and /api/reel require verified owner session. Browser review flow can never call media_publish. Production machine endpoints require M2M authorization.

D-02 idempotency / durable ledger: CLOSED.
Durable publication jobs/events are persisted before provider side effects; replay uses the same idempotency key and conflicting contracts fail closed.

D-03 ephemeral production media: CLOSED for current bounded owner-only operating envelope.
Production media uses a bounded PostgreSQL staging spool with SHA-256 binding, random public fetch token, expiry, capacity limits, and exact content_asset_id binding. Ephemeral tempfile remains only in the non-public browser review flow.

D-04 TrendHunter production binding: CLOSED at code/admission level.
trendhunter_instagram_publisher.py implements the governed manifest bridge, media admission, M2M publisher call, cold-start retry, reconciliation, and no blind duplicate retry.

D-05 cold start: MITIGATED.
Render free-tier cold start remains an availability characteristic, but the TrendHunter bridge retries bounded 502/503/504 responses and the publication contract is idempotent/fail-closed. Gateway cold start is OAuth-plane only; normal publishing uses the M2M backend.

D-06 disconnect durable revocation: CLOSED.
Owner disconnect deletes the durable credential and now requires POST.

D-07 deauthorization fail-open: CLOSED.
Missing/invalid signed request returns 400; durable deletion failure returns 503.

D-08 media preflight: CLOSED for current policy.
Machine path binds declared media metadata + SHA-256 to an admitted MP4 spool object and performs MP4/H.264/AAC signature checks plus bounded size/TTL/capacity checks.

D-09 publishing-limit guard: CLOSED.
Publisher checks provider content_publishing_limit and applies internal daily/inflight/queue/circuit/mutation limits.

D-10 polling cadence: CLOSED.
TrendHunter bridge uses governed reconciliation with a default 60-second interval and bounded polls.

D-11 tests/CI: CLOSED.
Dedicated Instagram Publisher Admission workflow exists and current exact candidate is green.

D-12 runtime/dependency reproducibility: CLOSED for current deployment model.
CI and Render use Python 3.14.3; Python package set is exact-pinned.

D-13 backend operational surface: MITIGATED.
Backend remains internet-reachable because Meta must fetch admitted media, but owner UI is session-protected and machine mutation endpoints require M2M authorization.

D-14 deploy provenance: candidate bytes are explicitly bound; final freeze should normalize branch/deploy identity after independent admission.

## New findings

No new CRITICAL or HIGH defect was discovered in this post-remediation read-only pass.

### R-01 — NOT VERIFIED — exact hardened machine path has not yet executed a real provider publication cycle

The new M2M production path has been live-tested only in fail-closed mode. It intentionally stopped at HOLD_PUBLIC_DISABLED and did not invoke provider publication.

Prior provider/OAuth/container evidence proves Meta connectivity, but it does not substitute for a real end-to-end run through this exact hardened machine control plane.

This is not a reason to bypass the gate. It is the purpose of the first governed activation after independent admission.

### R-02 — REQUIRED GOVERNANCE GATE — independent retest not yet completed

The same workstream that remediated findings must not self-assert independent assurance.
A separate fresh independent read-only reviewer must bind to the exact remediation target and evidence.

## Discovery verdict

POST_REMEDIATION_DISCOVERY = NO_NEW_BLOCKING_FINDINGS
CRITICAL_OPEN_TECHNICAL_FINDINGS = 0
HIGH_OPEN_TECHNICAL_FINDINGS = 0
EXACT_HARDENED_PROVIDER_ACTIVATION = NOT_YET_EXECUTED
INDEPENDENT_RETEST = REQUIRED
PUBLIC_PUBLISH_AUTHORIZED = FALSE
INSTAGRAM_PUBLISH_ENABLED = FALSE

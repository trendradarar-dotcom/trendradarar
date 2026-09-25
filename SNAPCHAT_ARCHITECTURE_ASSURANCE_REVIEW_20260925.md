# SNAPCHAT ARCHITECTURE ASSURANCE REVIEW — 2026-09-25

PROJECT: Trend Radar / TrendHunter
PLATFORM: Snapchat only
REVIEW MODE: Fresh Independent + Discovery + Directed + Creative/Adversarial + Verification
TARGET BRANCH: snapchat-production-review-20260925
PUBLICATION SIDE EFFECT: NONE
DECISION: HOLD FOR REMEDIATION BEFORE PROVIDER ONBOARDING / PUBLICATION

## Scope reviewed

- SNAPCHAT_AUTOMATION_ARCHITECTURE_GOVERNANCE_20260925.md
- SNAPCHAT_ACTIVATION_READINESS_20260925.md
- snapchat_publisher_service/publisher.py
- snapchat_publisher_service/app.py
- snapchat_publisher_service/test_publisher.py
- live Render deployment/readiness
- current Snapchat first-party monetization/authenticity rules
- current Ayrshare Snapchat linking/post/validation/status documentation and pricing

## Independent findings

### F1 — Ayrshare requires a Professional Profile, not merely a Public Profile
Severity: BLOCKING EXTERNAL LINK

Current Ayrshare Snapchat linking documentation requires the Snapchat Public Profile to be switched to a Professional Profile before linking. The existing governance treated this as optional/provider-dependent.

Required remediation:
- make Professional Profile verification an explicit pre-link gate;
- do not equate Professional Profile conversion with creating a separate legal business entity;
- no commercial-registry data may be invented.

### F2 — Provider-side no-side-effect validation is documented but not implemented
Severity: HIGH

Current /spotlight/validate only performs local validation and creates a payload preview.
Ayrshare provides POST /api/validate/post which performs provider-side validation without publishing.

Required remediation:
- implement provider validate(envelope) against /validate/post;
- production publication gate must require a successful provider validation after account connection/API-key configuration.

### F3 — Duplicate-publication protection is incomplete
Severity: HIGH

Ayrshare supports idempotencyKey for /post. Current adapter does not send one.

Required remediation:
- derive a deterministic idempotency key from the TrendHunter publication identity;
- preserve the same key across retries of the same intended publication;
- add internal serialization/dedup guard for simultaneous submissions because provider docs state concurrent duplicate calls may escape provider idempotency detection.

### F4 — Feedback loop is architectural text only
Severity: HIGH

The project intent requires performance/status feedback back into TrendHunter. Current service publishes but has no implemented post-status retrieval/webhook ingestion.

Required remediation:
- implement status read by Ayrshare post ID;
- persist provider post ID against trend_id/publication identity;
- add scheduled-post status/webhook path later if plan capability is available;
- provider result is not final TrendHunter success until platform status is reconciled.

### F5 — Boolean coercion is unsafe
Severity: HIGH

Current parsing uses bool(value). A JSON string such as "false" evaluates to True in Python, which can accidentally pass rights/originality/Saudi/global gates.

Required remediation:
- only native JSON true may satisfy a PASS gate;
- strings/numbers/null must fail closed.

### F6 — Snapchat 2026 authenticity change is not executable
Severity: HIGH FOR GROWTH/MONETIZATION

Snap announced in July 2026 that wholly AI-generated videos are no longer eligible for Spotlight recommendation. Current originality_passed does not prove the content is not wholly AI-generated.

Required remediation:
- add an explicit authenticity/human-origin gate;
- wholly AI-generated video must be blocked from the growth/monetization Spotlight lane;
- AI-assisted editing, localization, packaging and production may remain automated around human-origin/original source material.

### F7 — Unit tests exist but there is no execution evidence
Severity: MEDIUM

The Render build installs dependencies and starts the service; it does not execute the unit test suite.
A committed test file is not evidence of PASS.

Required remediation:
- run tests in CI/build or a separate exact-target verification job;
- block production enablement on test PASS.

### F8 — Provider cost is a material architecture dependency
Severity: BUSINESS GATE

Current Ayrshare public pricing shows Premium at $149/month for one social profile. Launch has a 28-day free trial without a card, but production use after evaluation is a financial commitment.

Required remediation:
- do not represent the provider route as cost-free;
- engineering may continue without payment;
- any paid subscription is owner-only;
- retain the direct Snapchat API path as a strategic fallback if provider economics are rejected later.

### F9 — Visual-board contract is documented but not machine-verified
Severity: MEDIUM

Country-specific board identity and GLOBAL_SELECTED are governance requirements, but the publisher only validates metadata, duration/resolution/ratio.

Required remediation:
- content-factory output manifest must assert the exact board/template ID, market label and global/local lane;
- publisher must reject missing/unknown template identity.

### F10 — Monetization eligibility is broader than the 30-second rule
Severity: BUSINESS/PRODUCT

Snapchat currently requires, among other conditions, original advertiser-friendly content, eligible-country residence, Snap Star status, 50,000 followers and 15,000 view-hours in 28 days including 3,000 Spotlight hours. Saudi Arabia is currently listed as payout-eligible.

Required remediation:
- keep the 30-second minimum as the content-production rule;
- track growth/eligibility metrics separately;
- do not treat technical publishing success as monetization eligibility.

## Review decision

The architecture direction remains viable, but it is NOT yet assurance-complete.

External provider onboarding/public publishing remains HOLD until F1-F7 and F9 are remediated or explicitly waived with evidence.
F8 is an owner-only financial decision and must not be auto-executed.
F10 is a growth/monetization operating constraint rather than a code-release blocker.

No live Snapchat post was created during this review.

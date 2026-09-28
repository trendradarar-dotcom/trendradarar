# INDEPENDENT REVIEW REQUEST — Instagram M26.5

PROJECT: TrendHunter / Trend Radar
SCOPE: Instagram only
REVIEW MODE: Fresh / Independent / Adversarial / Read-Only First / Exact-Target-Bound / Exact-Evidence-Bound / No Producer Trust / Fail-Closed

## Exact code target

Repository: trendradarar-dotcom/trendradarar
Branch: instagram-production-remediation-r3-20260928
EXACT CODE TARGET: 19221407a62969104aa386df64d5cc703d5f36b5
EXACT CODE TREE: 822407ac475d33b9e1a12919bf3367bd615c8ddf
Exact-target CI run: 36369036287
CI conclusion: SUCCESS

The commit containing this review request is documentation-only and is NOT the code target.

## Mandatory safety state

The reviewer must not enable public publishing or create a real public Reel.

Required state:
- INSTAGRAM_PUBLIC_PUBLISH_AUTHORIZED=false
- INSTAGRAM_PUBLISH_ENABLED=false
- browser public publishing disabled
- OAuth gateway hard-disabled fail-closed in this candidate

## Changes requiring independent verification

Do not trust the following claims. Reproduce them independently:

1. Byte-level media inspection now uses PyAV against the uploaded bytes, and the durable spool stores verified media metadata.
2. Publication intent is bound to the verified spool metadata and SHA-256.
3. Same content_asset_id or same asset SHA-256 cannot be bound to a new publication for the same account.
4. PUBLISH_REQUESTED and UNKNOWN consume blast-radius budget.
5. Unresolved UNKNOWN/PUBLISHED_UNVERIFIED/PUBLISH_REQUESTED ambiguity blocks new publication mutations.
6. Recovery of an ambiguous publication requires a candidate Media ID and provider-side verification before VERIFIED_RECOVERED.
7. Browser /api/reel cannot create an Instagram container while either publish gate is closed.
8. Exact account binding remains username trendradarar + BUSINESS + professional user id 17841428134382903.
9. cryptography is pinned at 50.0.0.
10. av is pinned at 18.1.0.
11. pip-audit 2.10.1 is run in CI against backend and gateway requirements.
12. OAuth gateway publication/linking routes are hard-disabled fail-closed in this candidate; verify there is no alternate active gateway route.

## Known review boundary

The candidate is not yet authorized for public activation.
Do not infer a Golden/LKG release from a green CI result.
Live deployment equivalence must be proven separately if the reviewer decides it is required for production acceptance.
Backup/restore, disaster recovery, penetration testing, monitoring/alerting, and cold-engineer handover must be marked PASS only if actual evidence exists.

## Mandatory probes

Return PASS / FAIL / NOT VERIFIED for at least:

A. Exact target identity and tree
B. Code architecture and trust boundaries
C. OAuth / account binding
D. Token and secret security
E. Browser vs machine authorization
F. M2M authentication
G. Persistent idempotency / duplicate prevention
H. Race / concurrency / atomic hard limits
I. Publication lifecycle / UNKNOWN handling
J. Maximum blast radius
K. Kill switch / emergency no-publish
L. Media preflight against current Meta requirements
M. Durable media and publication state
N. Logging / audit trail
O. Monitoring / alerting
P. Restart / crash recovery
Q. Ambiguous media_publish recovery
R. Backup / restore safety
S. Disaster recovery
T. Golden / LKG baseline
U. Recovery runbook / owner recovery package
V. Human takeover / cold-engineer handover
W. Penetration testing
X. Supply chain / known vulnerabilities
Y. Exact-target CI / reproducibility
Z. Live candidate equivalence if applicable

## Required final verdict

CRITICAL_OPEN =
HIGH_OPEN =
MEDIUM_OPEN =
CRITICAL_NOT_VERIFIED =
EXACT_TARGET_VERIFIED =
EXACT_TREE_VERIFIED =
DUPLICATE_PREVENTION =
AMBIGUOUS_PUBLISH_RECOVERY =
MAXIMUM_BLAST_RADIUS =
EXACT_ACCOUNT_BINDING =
OAUTH_GATEWAY_STATE =
MEDIA_BYTE_PREFLIGHT =
SUPPLY_CHAIN =
RECOVERABILITY =
FIRST_PUBLIC_ACTIVATION_ELIGIBLE =
INDEPENDENT_FINAL_VERDICT = PASS / FAIL-CLOSED

Any critical missing evidence => FAIL-CLOSED.
No remediation during this independent review.

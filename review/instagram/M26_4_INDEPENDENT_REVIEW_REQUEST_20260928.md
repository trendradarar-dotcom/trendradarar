# INDEPENDENT REVIEW REQUEST — Instagram M26.4

PROJECT: TrendHunter / Trend Radar
SCOPE: Instagram only
MODE: Fresh / Independent / Adversarial / Read-Only First / Exact-Target-Bound / Exact-Evidence-Bound / No Producer Trust / Fail-Closed

## Exact code target

Repository: trendradarar-dotcom/trendradarar
Remediation branch: instagram-production-remediation-r2-20260928
EXACT CODE TARGET: 13d71750f4deb45981020b3126b646f1cff13b95
EXACT CODE TREE: 7395993e01055ef536b2b31f83ae807b80af5dd0
Exact-target CI run: 36366855061
CI conclusion: SUCCESS

The review request commit that contains this document is metadata only and is not the code target.

## Public safety state

The reviewer must not enable public publishing.
Required safe state:
- INSTAGRAM_PUBLIC_PUBLISH_AUTHORIZED=false
- INSTAGRAM_PUBLISH_ENABLED=false
- browser_public_publish_enabled=false

No real public Reel is authorized by this review.

## Residual findings remediated in this target

Independently verify, do not trust these assertions:

1. Duplicate prevention is account + content bound:
   - same idempotency key / same contract replays safely;
   - same key / changed contract conflicts;
   - same content_asset_id with a new key is rejected;
   - same asset SHA-256 with a new content_asset_id is rejected;
   - database uniqueness is race-safe.

2. Maximum blast radius:
   - PUBLISH_REQUESTED and UNKNOWN count as potentially public exposure;
   - daily public exposure is rechecked immediately before media_publish;
   - UNKNOWN never creates a blind retry.

3. Concurrency:
   - provider mutation hard-limit decisions are serialized across workers;
   - irreversible media_publish decisions are serialized across workers.

4. Exact account binding:
   - username = trendradarar;
   - account type = BUSINESS;
   - professional user id = 17841428134382903;
   - any mismatch fails closed.

5. OAuth state:
   - signed state remains time-limited;
   - nonce is persisted as a hash;
   - nonce is one-time consumed;
   - replay fails closed.

6. Reel media contract:
   - minimum duration 3 seconds;
   - maximum duration 900 seconds;
   - frame rate 23-60;
   - horizontal width <= 1920;
   - governed H.264 MP4 profile;
   - video bitrate <= 25 Mbps;
   - AAC audio, when present, requires 48 kHz and <= 128 kbps.

7. Supply chain:
   - cryptography is upgraded to 48.0.1 or later-patched exact pin;
   - backend and gateway requirements are exact-pinned;
   - gateway is included in CI;
   - actions/checkout and actions/setup-python are pinned to commit SHAs;
   - pip check passes.

8. Recovery regression:
   - PUBLISH_REQUESTED after restart becomes UNKNOWN;
   - UNKNOWN content cannot be resubmitted under a new idempotency key.

## Mandatory independent areas

Return PASS / FAIL / NOT VERIFIED for:

A. Exact target identity and tree.
B. Architecture / trust boundaries.
C. OAuth / account binding.
D. Token and secret handling.
E. Browser vs machine authorization.
F. M2M publisher authentication.
G. Persistent idempotency and content-level duplicate prevention.
H. Race / concurrency / atomic hard limits.
I. Publication lifecycle and UNKNOWN handling.
J. Maximum blast radius.
K. Kill switch and no-publish mode.
L. Media preflight against current Meta requirements.
M. Logging / audit trail.
N. Monitoring / alerting.
O. Restart / crash recovery.
P. Backup / restore safety.
Q. Disaster recovery.
R. Golden/LKG baseline.
S. Recovery runbook / owner recovery package.
T. Human takeover / cold engineer handover.
U. Penetration testing.
V. Supply chain / dependency vulnerability review.
W. Exact-target CI / reproducibility.
X. Live safe runtime evidence, only if the exact candidate is deployed with publish gates false.

## Required verdict

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
OAUTH_STATE_REPLAY_PROTECTION =
SUPPLY_CHAIN =
RECOVERABILITY =
FIRST_PUBLIC_ACTIVATION_ELIGIBLE =
INDEPENDENT_FINAL_VERDICT = PASS / FAIL-CLOSED

Any critical missing evidence => FAIL-CLOSED.
Do not remediate during the independent review.

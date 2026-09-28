# Instagram M26.10 — Golden / Last-Known-Good Promotion Record

PROJECT: TrendHunter / Trend Radar
SCOPE: Instagram only
PROMOTION TYPE: Governance promotion record; no application-code change

## Promoted application baseline

R5_EXACT_TARGET_COMMIT:
d41c1c1cdaa7cf374989e2b059db6a640cb51eef

R5_EXACT_TARGET_TREE:
9b7d7c2ab974a55cc9073e24386f4cbe9de8437d

LIVE_DEPLOYMENT_BRANCH:
instagram-production-review-20260924

LIVE_SYNC_COMMIT:
d2477d9397643c789fa4b27dbcf669a83b1acd2a

LIVE_SYNC_TREE:
9b7d7c2ab974a55cc9073e24386f4cbe9de8437d

## Independent prerequisites already established

- HIGH-01 = CLOSED
- MEDIA_BYTE_PREFLIGHT = PASS
- LIVE_R5_EQUIVALENCE = PASS
- LIVE_REGRESSION_FOUND = NO
- M26.8 isolated trusted rebuild = PASS
- M26.8 isolated backup/restore = PASS
- M26.8 isolated DR = PASS
- M26.8 monitoring = PASS

## Promotion decision

GOLDEN_LKG_PROMOTION_RECORD = PROMOTED

The promoted recoverable application snapshot is the R5 exact target/tree above.
The live sync commit is an equivalent deployment wrapper whose tree is identical.

This promotion does NOT authorize public publication.

## Mandatory recovery posture

INSTAGRAM_PUBLIC_PUBLISH_AUTHORIZED=false
INSTAGRAM_PUBLISH_ENABLED=false

On recovery:
1. restore/build only from the exact target/tree and captured trusted artifacts;
2. keep both publication gates false;
3. preserve UNKNOWN and ambiguous-side-effect states;
4. never blindly repeat provider mutations after an ambiguous result;
5. verify exact account binding before any future activation;
6. require a new admission decision before public publishing.

## Explicit limits

This promotion record does not prove:
- production backup restoration;
- production DR/RTO/RPO;
- alert human acknowledgement;
- human takeover execution;
- cold engineer handover execution;
- token/secret rotation history;
- independent penetration testing.

Those remain separate gates.

# Instagram M26.8 — Golden / LKG Candidate Manifest

STATUS: CANDIDATE ONLY
PROMOTED: NO
PUBLIC ACTIVATION AUTHORIZED: NO

## Application candidate

R5 exact code target:
d41c1c1cdaa7cf374989e2b059db6a640cb51eef

R5 exact code tree:
9b7d7c2ab974a55cc9073e24386f4cbe9de8437d

R5 exact CI:
36422824796 = SUCCESS

Independent R5 result supplied by reviewer:
HIGH-01 = CLOSED
MEDIA_BYTE_PREFLIGHT = PASS
FIRST_PUBLIC_ACTIVATION_ELIGIBLE = NO

## Operations evidence candidate

Operations exact target:
0a68c4003261f1fe216140fb52665f1d91585d3f

Operations exact tree:
8561d105562ecf0d0ce8d3fa9f467bf7411af53d

Operations drill:
36442457664 = SUCCESS

## Captured immutable dependency evidence

R5 wheelhouse:
instagram-runtime-wheelhouse-d41c1c1cdaa7cf374989e2b059db6a640cb51eef

PostgreSQL image digest observed in operations drill:
postgres@sha256:5a5a84b19854a9ffaa54082c166ff4ec27473a361e496e5ea167f298f2da9722

## Promotion blockers

This candidate MUST NOT be promoted merely because producer drills passed.

At minimum, independent review must decide the outstanding production/human/security requirements, including:
- production backup/restore evidence;
- production DR evidence;
- alert delivery;
- full environment reproducibility;
- owner recovery execution;
- human takeover;
- cold-engineer handover;
- independent penetration test;
- token/secret security evidence where required.

## Live boundary

R5 is not deployed by this operations package.
The live Instagram service remains on the previously reviewed R4 fail-closed deployment.

## Governing result

GOLDEN_LKG_CANDIDATE = YES
GOLDEN_BASELINE_PROMOTED = NO
FIRST_PUBLIC_ACTIVATION_ELIGIBLE = NO

# تكليف المراجع المستقل — YouTube R1.1 / F-R1-01

PROJECT: TrendHunter / Trend Radar
SCOPE: YouTube only; external channel UCPm6nbktPc2Egr05AV-zPhA
PARENT GATE: TREND-R5-FOUR-INPUTS-GATE-20261004
REVIEW MODE: Fresh / Adversarial / Fake-only / Exact-artifact-bound / No producer trust / Fail-closed.

## Exact candidate
Local frozen ZIP and .sha256 located on the owner's Windows Desktop:
TrendHunter-YouTube-R11-Isolated-Candidate-20261004.zip
TrendHunter-YouTube-R11-Isolated-Candidate-20261004.zip.sha256
MANIFEST_SHA256.tsv is inside the ZIP. Recompute every file hash and ZIP CRC independently.
Compare against immutable R1 source hashes in the earlier independent adjudication.
Do NOT work from the mutable live TrendHunter production directory.

## Background
Prior independent finding F-R1-01: the same human authorization/request after a successful
private upload could cause another independent Fake upload-init and upload-bytes (R12).
Prior R1 adjudication: YOUTUBE_R1_LOCAL_EXACT_ENTRYPOINT=FAIL.
Candidate contains narrowly scoped changes to ledger.py, c1_youtube.py, api.py,
the existing two-scenario tests, and new tests/test_youtube_r11_claim.py.
The producer reports 45/45 local relevant tests PASS; that is NOT independent proof.

## Required fresh independent tests
A. First exact valid private request: success via Fake, one upload-init and one upload-bytes.
B. Identical sequential replay after success: reject before a second refresh; zero extra upload-init/bytes.
C. Two concurrent calls sharing the authorization on independently opened connections: at most one
   claim and one provider upload, including when both observe a valid preflight.
D. Two concurrent calls against the SAME READY attempt: only one provider upload effect.
E. Crash/restart after authorization reservation, before attempt creation: fail closed; no blind retry.
F. Crash/restart after provider reservation, before/after IN_FLIGHT or uncertain provider response:
   fail closed; preserve manual-reconciliation HOLD, never infer remote non-creation.
G. Legacy committed attempt/proof/execution using the authorization predating the new marker:
   refuse automatic replay.
H. Different newly approved authorization: do not accidentally prohibit an entirely separate
   legitimate approved workflow; still require full exact channel/media/privacy checks.
I. Retest malicious session URL, wrong channel, changed media, superseded binding,
   malformed provider result and production-default 423 lock. Fake/Stub only.
J. Inspect SQLite transaction and UNIQUE(kind,natural_key) arbitration directly;
   do not rely exclusively on producer's pytest results.

## Restrictions
No real YouTube API, OAuth live operation, DPAPI secret access, network publishing or uploads.
No production DB/code/flag changes; do not copy raw credential/token material.
Use temp isolated DB and synthetic media. No production remediation during independent review.
Keep public auto-publish disabled. Do not conflate R1.1 isolated success with Google API approval.

## Required verdict
F_R1_01_INDEPENDENT_RETEST = PASS / FAIL / NOT_VERIFIED
YOUTUBE_R11_LOCAL_EXACT_ENTRYPOINT = PASS / FAIL / NOT_VERIFIED
YOUTUBE_PRODUCTION_ADMISSION = HOLD
Provide independent commands, SHA references, test-level results and source locations.
If FAIL, identify narrow finding; do not auto-remediate.

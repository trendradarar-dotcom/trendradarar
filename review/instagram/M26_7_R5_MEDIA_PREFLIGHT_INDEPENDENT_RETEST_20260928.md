# Independent Adversarial Retest — Instagram M26.7 / R5 — HIGH-01 Only

PROJECT: TrendHunter / Trend Radar
SCOPE: Instagram only
RETEST SCOPE: HIGH-01 — Late media corruption / full byte-level decode only
MODE: Fresh / Independent / Adversarial / Read-Only First / Exact-Target-Bound / Exact-Evidence-Bound / No Producer Trust / Fail-Closed

## Governing boundary

This is a narrow successor retest. Do not reopen findings already independently closed in M26.6/R4 unless R5 itself introduces a directly evidenced regression.

Operational items previously left NOT VERIFIED (Monitoring, Backup/Restore, DR, Golden/LKG, Owner Recovery, Rebuild From Trusted Source, Human Takeover, Cold Engineer Handover, Penetration Test, full supply-chain environment reproducibility) remain separate. A PASS on HIGH-01 does not authorize first public activation.

Do not remediate during this review.
Do not deploy R5 to Render.
Do not publish a Reel.
Do not enable either publication gate.

## Exact target

R4 parent target:
7055c33042b4e46b150315067c08dbda728974e7

R5 EXACT CODE TARGET:
d41c1c1cdaa7cf374989e2b059db6a640cb51eef

R5 EXACT CODE TREE:
9b7d7c2ab974a55cc9073e24386f4cbe9de8437d

R5 EXACT-TARGET CI RUN:
36422824796

Expected CI result:
completed / success

The commit containing this request must be documentation-only and a direct child of the exact R5 target. Verify that from the supplied Git bundle.

## Previous independent finding

The prior independent R4 review established:

HIGH-01 — Late media corruption is not detected by current byte preflight.

The reproduced defect was that an MP4 could remain structurally demuxable and expose plausible stream metadata while corruption in later H.264 packets caused full PyAV frame decoding to fail after valid frames had already decoded. R4 used demux/packet inspection without requiring complete frame decoding to EOF.

The prior independent judgment was:
MEDIA_BYTE_PREFLIGHT = FAIL

## Mandatory Exact Target gate

Before retesting HIGH-01:

1. Verify the Git bundle.
2. Verify the exact R5 commit exists.
3. Verify its tree equals the exact R5 tree above.
4. Verify the review-request commit is a direct child of the R5 target.
5. Verify target-to-review delta is this documentation file only.
6. Verify CI run 36422824796 has head_sha equal to the exact R5 target.
7. Verify CI completed successfully.
8. Recompute supplied hashes / wheelhouse hashes where included.

If this gate fails: HIGH-01 remains NOT VERIFIED / FAIL-CLOSED.

## Code delta boundary

Independently compare R4 target to R5 target.

Expected R5 code/test delta is limited to:
- instagram_oauth_service/app.py
- tests/test_instagram_media_full_decode.py
- .github/workflows/instagram-publisher-ci.yml

Do not trust this list without comparing Git objects.

## Mandatory implementation review

Inspect the exact R5 implementation and verify that admission no longer relies only on:
- container open;
- stream metadata;
- packet demux;
- packet sizes/signatures.

Verify that before media is admitted the code performs full PyAV decoding through EOF for:
- the single video stream;
- the audio stream when present.

Verify that decoder exceptions fail closed and return a media decode error rather than verified media.

Confirm that a successful result records actual decoded frame counts or otherwise proves decode completion.

## Mandatory adversarial retest

Do not rely only on producer tests. Reproduce independently.

At minimum test:

A. Valid control
- MP4 container
- H.264 video
- AAC audio
- duration within allowed range
- FPS within allowed range
- valid dimensions
- 48 kHz audio
Expected: PASS and complete decode to EOF.

B. Early video corruption
Corrupt H.264 packet data near the beginning.
Expected: reject fail-closed.

C. Late video corruption after valid frames
Create an MP4 that:
- opens successfully;
- remains structurally demuxable;
- has plausible stream metadata;
- successfully decodes a meaningful number of initial video frames;
- then fails full video decode because a later packet is corrupt.
Expected: reject with no verified media.

This is the primary reproduction of HIGH-01.

D. Near-end video corruption
Corrupt a late video packet close to the end so most frames decode first.
Expected: reject.

E. Audio corruption with valid video
Corrupt a later AAC packet while the H.264 video still decodes completely.
Expected: reject due to audio decode failure.

F. Truncated tail
Remove required terminal media bytes / structure.
Expected: reject.

G. Independent mutation
Create at least one corruption variant not copied from the producer test implementation.
Expected: reject.

## Producer regression corpus to inspect

Exact CI includes tests intended to prove:
- valid H.264/AAC full decode;
- early video corruption rejection;
- late video corruption rejection after valid frames;
- near-end corruption rejection;
- late AAC corruption rejection while video remains valid;
- truncated-tail rejection.

Verify these tests actually ran in exact CI and did not skip.

Do not count producer tests as the independent adversarial retest; they are supporting evidence only.

## Regression guard

Because R5 is intentionally narrow, verify no direct regression in the existing Instagram admission suite:
- Publisher tests remain PASS.
- Gateway tests remain PASS.
- PostgreSQL integration tests remain PASS.
- PostgreSQL runtime/concurrency tests remain PASS.
- dependency audit remains PASS.

A newly evidenced R5 regression must be reported, but do not reopen unrelated previously-closed findings without evidence.

## Live boundary

R5 is intentionally NOT deployed during this retest.

The currently live R4 environment remains fail-closed.

Therefore:
LIVE_R5_EQUIVALENCE = NOT APPLICABLE / NOT VERIFIED for this narrow retest.

Do not modify Render to test R5.

## Safety state

The public publication gates must remain closed:

INSTAGRAM_PUBLIC_PUBLISH_AUTHORIZED=false
INSTAGRAM_PUBLISH_ENABLED=false

PUBLIC INSTAGRAM PUBLISHING = HOLD

## Required result

Return at least:

EXACT_TARGET_VERIFIED =
EXACT_TREE_VERIFIED =
EXACT_TARGET_CI =
DOCUMENTATION_ONLY_DELTA_VERIFIED =
R4_TO_R5_SCOPE_VERIFIED =

VALID_MEDIA_FULL_DECODE =
EARLY_VIDEO_CORRUPTION_REJECTED =
LATE_VIDEO_CORRUPTION_REJECTED =
NEAR_END_VIDEO_CORRUPTION_REJECTED =
LATE_AUDIO_CORRUPTION_REJECTED =
TRUNCATED_TAIL_REJECTED =
INDEPENDENT_CORRUPTION_VARIANT_REJECTED =
FULL_VIDEO_DECODE_TO_EOF =
FULL_AUDIO_DECODE_TO_EOF =

MEDIA_BYTE_PREFLIGHT =
HIGH_01_STATUS = CLOSED / OPEN / NOT VERIFIED
R5_REGRESSION_FOUND = YES / NO / NOT VERIFIED

LIVE_R5_EQUIVALENCE = NOT VERIFIED / N/A

FIRST_PUBLIC_ACTIVATION_ELIGIBLE = NO
INDEPENDENT_RETEST_VERDICT = PASS-HIGH-01-CLOSED / FAIL-CLOSED / NOT VERIFIED

A PASS here closes only HIGH-01. It does not convert the separately unverified operational requirements into PASS and does not authorize public activation.

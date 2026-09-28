# INDEPENDENT ADVERSARIAL RETEST REQUEST — TikTok R3

Date: 2026-09-28
Project: TrendHunter / Trend Radar
Scope: TikTok only

## Review mode

Fresh / Independent / Adversarial / Read-Only First / Exact-Target-Bound / Exact-Evidence-Bound / No Producer Trust / Fail-Closed

This R3 request exists because the previous R2 limited independent review:
- verified the exact R2 target;
- independently passed F-02, F-03 and F-05 within the documented local scope;
- left F-01 and F-04 NOT VERIFIED because the required adversarial probes were not executed;
- identified that the R2 media validator decoded only the first frame.

R3 changes the media validator to decode the entire H.264 stream before provider mutation and updates recovery/build documentation. F-01 remains open pending independent dynamic session-swapping evidence.

## Exact R3 candidate

Repository:
`trendradarar-dotcom/trendradarar`

Frozen branch:
`tiktok-independent-retest-candidate-20260928-r3`

EXACT COMMIT:
`47be83f732e63ffc04362f19820c9818e3d574a9`

EXACT TREE:
`cf4f045ed253318726ec0aad4b88f7cdac358998`

Previous R2 candidate:
`4b1c68a305b80738b0338b601e4cebd48ce1c0bb`

## Mandatory first gate

Before any retest:
1. verify the Git bundle independently;
2. clone it independently;
3. verify `HEAD` equals the exact R3 commit;
4. verify `HEAD^{tree}` equals the exact R3 tree;
5. reconstruct the full repository root tree from the supplied snapshot.

Any mismatch:
`EXACT TARGET = NOT VERIFIED`
and stop Fail-Closed.

## Findings already independently passed on R2

Do not reopen these without new contradictory evidence, but run regression checks for accidental breakage:

- F-02 — 429 reconciliation = PASS
- F-03 — Draft terminal consistency = PASS
- F-05 — immutable Actions / hash-locked dependencies / exact-commit SBOM = PASS

## F-01 — High — OAuth callback browser/session binding

Current producer implementation:
- callback requires an initiating `trsid` browser cookie before token exchange;
- OAuth state consumption requires the expected SID;
- wrong SID does not consume the legitimate state;
- state is one-time and expiring.

Static review is NOT closure.

### Mandatory independent dynamic probes

Use two logically separate browser/session clients against an isolated local test runtime with synthetic/mocked TikTok token exchange. Do not call TikTok production APIs.

1. Browser A starts OAuth and receives SID-A/state-A.
2. Browser B has no cookie and submits callback(state-A, valid mocked code).
   - expected: reject before provider token exchange;
   - no session/account binding created;
   - state-A remains usable by Browser A.
3. Browser B has SID-B and submits callback(state-A, valid mocked code).
   - expected: reject before provider token exchange;
   - no account/session swap;
   - state-A remains usable by Browser A.
4. Browser A submits callback(state-A, valid mocked code).
   - expected: one successful completion.
5. Replay the consumed callback.
   - expected: reject.
6. Attempt SID/account swapping with mocked provider returning a different account identity.
   - expected: no path may bind Browser B to Browser A's state/session.
7. Record whether token-exchange function was invoked for each rejected case.

Required independent evidence must include:
- request/cookie identity;
- state identity or safe hash;
- provider-exchange call count;
- resulting local session identity/state;
- replay result.

F-01 may become PASS only from reproduced dynamic evidence.

## F-04 — Medium — full H.264 media validation

R2 static review found first-frame-only decode was insufficient.

R3 remediation:
- structural MP4 checks remain fail-closed;
- PyAV/FFmpeg must open the MP4;
- selected codec must resolve to H.264;
- the validator decodes the ENTIRE video stream, not only the first frame;
- any decode exception rejects the media;
- every decoded frame must have valid/stable dimensions;
- decoded dimensions must match track dimensions;
- zero-frame media fails;
- validation completes before any Direct Post or Draft provider mutation.

### Mandatory independent adversarial media corpus

Run with locally generated or reviewer-owned synthetic files only; do not upload them to TikTok.

Required negative cases:
1. MP4 with `avc1` label + random/zero `mdat`.
2. Empty/truncated `mdat`.
3. H.264 stream corrupted after a valid first frame.
4. H.264 truncated after a valid first frame.
5. Broken AVC configuration/sample tables.
6. HEVC/H.265 file or misleading codec metadata.
7. Malformed MP4 boxes/trailing truncation.
8. Invalid or changing frame dimensions if a corpus case can express it.
9. Oversize/duration/aspect-policy violations.

Required positive control:
- a real decodable H.264 MP4 must pass.

Critical proof:
- a file whose first frame can decode but a later frame is corrupted must be rejected;
- provider mutation mocks/counters must remain zero for every rejected case.

F-04 may become PASS only with independent corpus execution evidence.

## Regression requirements

Re-run focused regressions for:
- F-02 429 -> UNKNOWN -> later success;
- F-03 SEND_TO_USER_INBOX/PUBLISH_COMPLETE -> READY;
- F-05 immutable Action refs, hash-locked install, SBOM exact-commit binding;
- OAuth state replay/expiry;
- scope checks;
- token refresh/open_id drift;
- idempotency/duplicate suppression;
- UNKNOWN semantics;
- kill switch/no-publish;
- backup/restore duplicate barrier;
- health UNKNOWN/stale signals.

## Remaining production gates

Even if F-01 and F-04 become PASS, do NOT grant Production Auto-Publish acceptance until independently proven:

- production-persistent state on the deployed hardened target;
- production backup destination and production-bound restore drill;
- external alert delivery;
- cold-engineer rebuild/handover;
- production-bound recovery exercise;
- owner recovery without original developer/AI session;
- final independent architecture/security acceptance.

## Non-mutation rules

The reviewer MUST NOT:
- deploy R3;
- merge to main;
- change Render;
- Recall or resubmit TikTok App Review;
- enable public posting;
- set `TIKTOK_AUDIT_APPROVED=true`.

## Verdict vocabulary

For every item:
`PASS / FAIL / NOT VERIFIED / N/A`

Final acceptance remains Fail-Closed while any High finding or critical recovery gate is open/NOT VERIFIED.

Closure chain:
`Evidence -> Remediation -> Independent Retest -> Closure Evidence`

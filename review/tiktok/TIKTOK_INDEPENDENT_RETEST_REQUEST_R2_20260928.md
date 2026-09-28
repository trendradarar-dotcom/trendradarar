# INDEPENDENT RETEST REQUEST — TikTok R2

Date: 2026-09-28
Project: TrendHunter / Trend Radar
Scope: TikTok integration ONLY

## Review mode

Fresh / Independent / Adversarial / Read-Only First / Exact-Target-Bound / Exact-Evidence-Bound / No Producer Trust / Fail-Closed

This is a NEW frozen remediation candidate created after the independent FAIL on candidate:
`acb5aff7a79de29f82c150428d29136148b51b36`.

The producer does NOT claim that F-01..F-05 are closed. They are only implemented and internally tested pending independent retest.

## Exact R2 candidate

Repository:
`trendradarar-dotcom/trendradarar`

Frozen review branch:
`tiktok-independent-retest-candidate-20260928-r2`

EXACT COMMIT:
`4b1c68a305b80738b0338b601e4cebd48ce1c0bb`

EXACT TREE:
`ce176732e850c3c229734f17ca1a929eedfa9cfc`

Previous failed candidate:
`acb5aff7a79de29f82c150428d29136148b51b36`

## Mandatory first gate

Before any finding retest:
1. independently verify the Git bundle;
2. independently clone the bundle;
3. verify `HEAD` equals the exact R2 commit;
4. verify `HEAD^{tree}` equals the exact R2 tree;
5. independently rebuild the full repository root tree from the supplied full snapshot.

If any binding fails:
`EXACT TARGET = NOT VERIFIED`
and stop Fail-Closed.

## Independent findings requiring retest

### F-01 — High — OAuth callback browser/session binding

Prior independent evidence:
- valid state could be accepted from a browser with no initiating cookie;
- callback then set the state-bound SID and created the session.

R2 remediation to independently attack:
- callback requires the initiating browser SID cookie before token exchange;
- durable OAuth state consumption requires the expected SID;
- SID mismatch does not consume the legitimate state.

Mandatory probes:
- callback with no cookie -> reject before provider token exchange;
- callback with wrong cookie -> reject before provider token exchange;
- wrong-cookie attempt must not consume legitimate state;
- legitimate browser/session can still complete one-time state consumption;
- replay remains rejected;
- test account/session swapping attempts.

Required closure:
`F-01 = PASS` only with independent reproducible evidence.

### F-02 — High — 429 reconciliation corruption

Prior independent evidence:
- PROCESSING + provider status HTTP 429 -> local FAILED;
- later provider PUBLISH_COMPLETE could not recover because FAILED was terminal.

R2 remediation to independently attack:
- status-read/API failure no longer proves publication failure;
- unsuccessful status reads become UNKNOWN;
- only explicit provider publication failure becomes FAILED;
- UNKNOWN can later reconcile to terminal success.

Mandatory probes:
- PROCESSING -> status 429 -> local UNKNOWN;
- later 200/PUBLISH_COMPLETE -> PUBLISHED for Direct Post;
- 5xx/network -> UNKNOWN;
- no second provider mutation;
- provider ID retained;
- explicit publication failure still -> FAILED.

### F-03 — Medium — Draft terminal taxonomy contradiction

Prior independent evidence:
- browser treated SEND_TO_USER_INBOX as terminal;
- backend kept the record PROCESSING.

R2 remediation:
- backend authoritative taxonomy:
  - DRAFT_UPLOAD + SEND_TO_USER_INBOX -> READY;
  - DRAFT_UPLOAD + PUBLISH_COMPLETE -> READY;
- status response exposes durable `local_state`;
- browser polling terminates on durable terminal local state.

Mandatory probes:
- SEND_TO_USER_INBOX -> READY;
- PUBLISH_COMPLETE -> READY;
- browser/backend terminal behavior no longer contradicts.

### F-04 — Medium — mislabeled H.264 accepted

Prior independent evidence:
- a tiny fake MP4 containing `avc1` labels and random/zero `mdat` passed validation.

R2 remediation:
- structural MP4 checks remain;
- PyAV/FFmpeg-backed MP4 open is required;
- codec must resolve to H.264;
- at least one real frame must decode;
- decoded dimensions must be valid and match track dimensions;
- decoder absence fails closed.

Mandatory probes:
- previous mislabeled/random-mdat corpus -> reject before provider mutation;
- non-MP4 -> reject;
- truncated MP4 -> reject;
- H.265/HEVC -> reject;
- decodable H.264 fixture -> pass;
- corrupt H.264 payload -> reject;
- duration/dimension/aspect/size rules still work;
- verify validation happens before any TikTok provider mutation.

### F-05 — Medium — supply-chain hardening

Prior independent evidence:
- repository Pages workflow used mutable `@vN` Action refs;
- dependencies were version-pinned but not hash-locked;
- no exact-build SBOM.

R2 remediation:
- every current workflow Action ref is a full immutable 40-hex commit SHA;
- `requirements.lock` has SHA-256 hashes and binary-only install;
- CI uses `pip --require-hashes`;
- exact-commit deterministic CycloneDX SBOM generator exists;
- package includes an SBOM generated for THIS exact R2 commit.

Mandatory probes:
- scan every file under `.github/workflows/` for mutable Action refs;
- independently run hash-locked install on supported Linux/Python 3.12 if network is available;
- verify lock hashes;
- verify generated SBOM exact commit == R2 commit;
- verify SBOM covers Python packages and GitHub Actions;
- identify any remaining supply-chain gap.

## Regression requirements

Do not limit the review to the five findings.

Re-run the previous critical acceptance probes for:
- OAuth state replay/expiration;
- scope enforcement;
- refresh-token rotation/open_id drift;
- disconnect/revoke;
- idempotency;
- duplicate Direct Post/Draft suppression;
- concurrency;
- UNKNOWN semantics;
- restart/backup/restore;
- kill switch/no-publish;
- hard limits/blast radius;
- audit secret exclusion;
- local/remote reconciliation;
- operations health.

Use only:
- PASS
- FAIL
- NOT VERIFIED
- N/A

## Known external gates that producer does NOT claim closed

Even if F-01..F-05 pass independently, final Production Auto-Publish acceptance is still forbidden unless independently proven:

- production-persistent state on the deployed hardened target;
- production-bound backup destination and restore drill;
- external monitoring/alert delivery;
- cold-engineer rebuild/handover;
- production-bound recovery drill;
- owner recovery without original developer/AI;
- final independent architecture/security acceptance.

## Non-mutation rules

The reviewer MUST NOT:
- Deploy R2;
- Merge to main;
- change Render branch/configuration;
- Recall or resubmit TikTok App Review;
- enable public posting;
- set `TIKTOK_AUDIT_APPROVED=true`.

## Verdict

For each finding:
`PASS / FAIL / NOT VERIFIED / N/A`

For overall:
`SECURITY, RELIABILITY & RECOVERABILITY ACCEPTANCE`

A final PASS is prohibited while any Critical/High finding remains open/NOT VERIFIED or production persistence/recovery/cold takeover remains unverified.

Closure chain remains:
`Evidence -> Remediation -> Independent Retest -> Closure Evidence`

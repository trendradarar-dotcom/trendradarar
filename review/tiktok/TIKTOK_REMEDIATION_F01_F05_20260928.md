# TikTok Independent Findings F-01..F-05 — Remediation Record

Date: 2026-09-28
Scope: TikTok only
Source verdict: independent review of exact candidate `acb5aff7a79de29f82c150428d29136148b51b36`
Source overall verdict: FAIL
Remediation rule: Evidence -> Remediation -> Independent Retest -> Closure Evidence

Nothing in this document closes an independent finding by producer assertion.

## F-01 — OAuth callback browser/session binding — High

Independent evidence:
- callback accepted a valid state without requiring the browser cookie/session that initiated OAuth;
- this permitted session/account swapping.

Remediation:
- `DurableState.consume_oauth_state` now requires the expected browser SID.
- state lookup compares the stored SID hash to the browser SID hash inside an immediate transaction.
- a mismatch does NOT consume the legitimate state.
- callback rejects missing browser cookie before token exchange.
- callback rejects mismatched browser/session binding before token exchange.

Producer-side tests:
- missing-cookie callback fails before provider exchange;
- wrong-cookie callback fails before provider exchange;
- wrong-cookie attempt does not burn the legitimate state;
- legitimate initiating SID can still consume state once.

Status:
`REMEDIATED — INDEPENDENT RETEST REQUIRED`

## F-02 — HTTP 429 reconciliation corruption — High

Independent evidence:
- status fetch 429 changed PROCESSING -> FAILED;
- later provider PUBLISH_COMPLETE could not recover because FAILED was terminal.

Remediation:
- a status-read/API error is no longer treated as publication failure.
- any unsuccessful status fetch transitions/preserves ambiguity as UNKNOWN.
- FAILED is reserved for explicit provider publication-failure status.
- UNKNOWN remains reconcilable to PUBLISHED/READY on a later successful provider status read.

Producer-side test:
- PROCESSING -> status 429 -> UNKNOWN;
- later status 200/PUBLISH_COMPLETE -> PUBLISHED.

Status:
`REMEDIATED — INDEPENDENT RETEST REQUIRED`

## F-03 — Draft terminal taxonomy contradiction — Medium

Independent evidence:
- browser polling treated SEND_TO_USER_INBOX as terminal;
- backend kept the durable record in PROCESSING.

Remediation:
- a single backend status taxonomy now maps:
  - DIRECT_POST + PUBLISH_COMPLETE -> PUBLISHED;
  - DRAFT_UPLOAD + PUBLISH_COMPLETE -> READY;
  - DRAFT_UPLOAD + SEND_TO_USER_INBOX -> READY;
  - explicit failure -> FAILED;
  - otherwise -> PROCESSING/UNKNOWN as appropriate.
- status API returns durable `local_state`.
- browser polling terminates according to durable local terminal state instead of maintaining a second provider-status taxonomy.

Producer-side test:
- DRAFT_UPLOAD + SEND_TO_USER_INBOX -> READY.

Status:
`REMEDIATED — INDEPENDENT RETEST REQUIRED`

## F-04 — mislabeled H.264 accepted without real payload proof — Medium

Independent evidence:
- a tiny synthetic MP4 containing an avc1 label and random/zero mdat passed the old validator.

Remediation:
- structural MP4 checks remain fail-closed.
- validation now additionally requires PyAV/FFmpeg-backed opening of the MP4.
- the selected video codec must resolve to H.264.
- at least one real video frame must decode successfully.
- decoded dimensions must be positive and match the track dimensions.
- if decoder dependency is unavailable, validation fails closed.
- a known decodable H.264 fixture is included for positive testing.
- a mislabeled avc1/random-mdat fixture is explicitly rejected.

Producer-side tests:
- real decodable H.264 fixture -> PASS;
- mislabeled avc1/random mdat -> rejected;
- truncated media -> rejected;
- non-MP4 -> rejected;
- oversize -> rejected;
- duration over policy -> rejected.

Status:
`REMEDIATED — INDEPENDENT RETEST REQUIRED`

## F-05 — repository-wide supply-chain hardening incomplete — Medium

Independent evidence:
- Pages workflow used mutable major-version tags;
- Python dependency file was version-pinned but not hash-locked;
- no exact-build SBOM evidence.

Remediation:
- every GitHub Action reference currently present under `.github/workflows/` is pinned to a full immutable commit SHA.
- TikTok Python dependencies are version-pinned.
- `requirements.lock` now uses SHA-256 hashes and binary-only installation.
- CI uses `pip --require-hashes`.
- deterministic CycloneDX SBOM generator binds the SBOM metadata to the exact full Git commit.
- CI fails if a mutable `@vN` GitHub Action reference reappears.
- CI generates and validates the exact-commit SBOM.

Producer-side evidence:
- Python 3.12 CI installs the hash-locked set;
- 46 tests PASS;
- exact-commit SBOM generation PASS;
- repository workflow mutable-tag scan PASS.

Status:
`REMEDIATED — INDEPENDENT RETEST REQUIRED`

## External / production gates intentionally still open

These findings are separate from the remaining acceptance gates. The following are NOT claimed closed by F-01..F-05 remediation:

- production-persistent state backend/volume for the hardened deployed target;
- production backup destination and production-bound restore drill;
- external monitoring/alert delivery;
- cold-engineer rebuild/handover;
- production-bound recovery exercise;
- final independent security/architecture acceptance.

Therefore:
`SECURITY, RELIABILITY & RECOVERABILITY ACCEPTANCE = NOT SELF-CLOSED`

A new exact candidate must be frozen and independently retested before any finding can be marked closed.

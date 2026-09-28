# INDEPENDENT REVIEW REQUEST — TikTok Security / Reliability / Recoverability

Date: 2026-09-28
Project: TrendHunter / Trend Radar
Scope: TikTok integration ONLY

## Review mode

Fresh / Independent / Adversarial / Read-Only First / Exact-Target-Bound / Exact-Evidence-Bound / No Producer Trust / Fail-Closed

The reviewer MUST NOT accept producer claims, prior PASS labels, CI success, documentation statements, or previous TikTok demo success as proof by themselves.

## Exact frozen candidate

Repository:
`trendradarar-dotcom/trendradarar`

Frozen review branch:
`tiktok-independent-review-candidate-20260928`

EXACT COMMIT:
`acb5aff7a79de29f82c150428d29136148b51b36`

EXACT TREE:
`56694a061bbd5ca09f1d8db8e014e04200258403`

Candidate source baseline:
`tiktok-oauth-service@a421e755c31bf8e00a2cffc047db2c7d9e70bcbe`

The reviewer must verify that the candidate branch still resolves to the exact commit above before reviewing findings.

Any branch movement or tree mismatch invalidates the review target.

## Live-service isolation / mandatory non-mutation rules

The current live Render TikTok service remains:
- service: `trendradar-tiktok-oauth`
- branch: `tiktok-oauth-service`
- live commit: `a421e755c31bf8e00a2cffc047db2c7d9e70bcbe`
- plan observed during remediation: free
- hardened independent-review candidate is NOT deployed

The reviewer must NOT:
- deploy the candidate;
- change the Render service branch;
- merge to `main`;
- modify the currently submitted TikTok Developer App Review;
- press Recall;
- resubmit the TikTok App Review;
- enable public publication;
- set `TIKTOK_AUDIT_APPROVED=true`;
- invent production persistence evidence.

## Why this independent review exists

The original runtime proved OAuth and creator-facing TikTok upload/post flows, but did not prove the production safety properties required for a self-operating publisher.

The remediation candidate adds or hardens:
- encrypted durable OAuth/session state;
- one-time persistent OAuth state and handoff;
- publication ledger and state machine;
- account-bound idempotency;
- duplicate suppression;
- UNKNOWN semantics and reconciliation;
- zero automatic mutation retries;
- hard per-account/global blast-radius limits;
- fail-closed mutation enablement;
- independent kill switch;
- strict MP4/H.264 media admission;
- refresh-token rotation and account-drift rejection;
- TikTok revocation/local disconnect;
- durable audit events;
- backup/restore helpers;
- restart/restore duplicate-safety tests;
- secret-free operational health signals;
- owner recovery / incident runbook;
- pinned Python dependencies;
- immutable-SHA GitHub Actions.

## Producer evidence that MUST be independently reproduced

Latest successful candidate-bound CI before freeze:
- workflow: `TikTok Runtime Remediation CI`
- candidate commit: `acb5aff7a79de29f82c150428d29136148b51b36`
- result observed by producer: SUCCESS

The reviewer must re-run or independently reproduce equivalent tests from the exact candidate. CI success alone is not acceptance.

Key test files:
- `tiktok_oauth_service/test_durable_state.py`
- `tiktok_oauth_service/test_app_safety.py`
- `tiktok_oauth_service/test_recovery.py`
- `tiktok_oauth_service/test_reconciliation.py`
- `tiktok_oauth_service/test_media_validation.py`
- `tiktok_oauth_service/test_atomicity.py`

Key implementation:
- `tiktok_oauth_service/app.py`
- `tiktok_oauth_service/durable_state.py`
- `tiktok_oauth_service/media_validation.py`
- `tiktok_oauth_service/requirements.txt`

Governance / recovery material:
- `review/tiktok/TIKTOK_SECURITY_RELIABILITY_REMEDIATION_PLAN_20260928.md`
- `review/tiktok/TIKTOK_SECURITY_RELIABILITY_EVIDENCE_MATRIX_20260928.md`
- `review/tiktok/TIKTOK_INCIDENT_RECOVERY_RUNBOOK_20260928.md`
- `review/tiktok/TIKTOK_OWNER_RECOVERY_PACKAGE_20260928.md`

## Mandatory independent probes

The reviewer must test or inspect at least the following, and must record exact evidence for every result.

### A. Exact-target integrity
1. Verify candidate branch -> exact commit.
2. Verify commit -> exact tree.
3. Verify no review is performed against another branch, ZIP, deploy or stale commit.

### B. OAuth / account / scope
4. State is random, one-time and expiring.
5. State replay fails closed.
6. Handoff replay fails closed.
7. Session/tokens are server-side and encrypted at rest in the durable state implementation.
8. Expired access token refreshes using refresh token.
9. Refresh-token rotation is persisted.
10. Refreshed `open_id` mismatch fails closed.
11. Direct Post without `video.publish` fails.
12. Draft upload without `video.upload` fails.
13. Disconnect performs provider revoke attempt and removes local durable session.
14. Confirm default code scope set is least-privilege relative to code paths, while NOT changing the already-submitted TikTok portal review.

### C. Publication safety / idempotency
15. Publication intent exists durably before provider mutation.
16. Same account + operation + same media content produces one stable idempotency identity.
17. Duplicate Direct Post intent cannot create a second provider mutation.
18. Duplicate draft intent cannot create a second provider mutation.
19. Concurrent duplicate workers have one winner.
20. Concurrent per-account admissions respect active-operation hard limit.
21. Filename/job-id change alone cannot bypass content identity.
22. UNKNOWN cannot be treated as PUBLISHED.
23. UNKNOWN cannot restart upload by blind retry.
24. Existing provider ID is reconciled before any new mutation.

### D. State machine / crash semantics
25. Invalid backward transitions fail.
26. Crash/restart with PROCESSING preserves provider ID/state.
27. Crash/restart with UNKNOWN preserves ambiguity.
28. Provider 5xx/network ambiguity maps to UNKNOWN.
29. Provider confirmed Direct Post completion maps to PUBLISHED.
30. Provider confirmed draft completion maps to READY, not PUBLISHED.
31. Explicit provider failure maps to FAILED.
32. Account mismatch blocks reconciliation before provider call.

### E. Retry / rate / blast radius
33. Automated mutation retry count is exactly zero unless independently re-authorized by future design.
34. Retry horizon is zero.
35. Per-account hourly/day limits are transactional and durable.
36. Global hourly/day limits are transactional and durable.
37. Active per-account/global limits are transactional.
38. 429/5xx cannot create retry storms or blind second posts.

### F. Kill switch / no-publish
39. Mutations are disabled by default unless explicitly enabled.
40. Kill switch overrides explicit mutation enablement.
41. Direct Post is blocked before provider mutation under kill switch.
42. Draft upload is blocked before provider mutation under kill switch.
43. Legacy private mutation diagnostic is unavailable.
44. Read-only health/reconciliation evidence remains available while mutations are blocked.
45. `TIKTOK_AUDIT_APPROVED` remains false/unset in acceptance evidence.

### G. Media
46. Non-MP4 fails.
47. Truncated/malformed ISO-BMFF fails.
48. Oversized body fails.
49. Incomplete request body fails.
50. Unsupported video codec fails.
51. Invalid dimensions/aspect policy fails.
52. Duration exceeding current creator limit fails.
53. No user-supplied media URL is fetched by the TikTok mutation path.
54. Confirm the legacy private diagnostic media is not used as a reason to weaken structural validation.

### H. Audit / secrets / supply chain
55. Audit trail records mutation intent/admission/state/control decisions.
56. Audit records do not contain access token, refresh token, client secret or auth code.
57. TikTok client secret/tokens are not hard-coded in the candidate.
58. Review git history independently for secret leakage; the producer's prior heuristic history scan is NOT sufficient proof.
59. Review pinned Python dependencies and immutable Action SHAs.
60. Identify dependency-integrity/SBOM gaps that remain.

### I. Backup / restore / recovery
61. Backup passes integrity check and has SHA-256.
62. Restore into clean target passes integrity check.
63. Restore refuses destructive overwrite.
64. Restored PUBLISHED intent still prevents duplicate mutation.
65. Restored UNKNOWN intent remains non-republishable.
66. Runbook can be followed without original developer/chat.
67. Recovery material contains no secret values.
68. Evaluate whether the implementation is usable with a truly persistent production state backend/volume.

### J. Monitoring / operations
69. `/ops/health` exposes only safe aggregate operational state.
70. UNKNOWN/stale non-terminal work degrades operational health.
71. Determine whether external alert routing is actually configured. Do NOT infer it from endpoint existence.

### K. Architecture / cold handover
72. Independent architecture review.
73. Identify single points of failure.
74. Identify hidden coupling to current developer/AI/chat.
75. Cold-engineer rebuild using repository/runbooks only.
76. Cold-engineer recovery drill from backup using repository/runbooks only.
77. Confirm owner can recover without original AI session.

## Known producer-declared open blockers — reviewer must not auto-close

At candidate freeze, these are intentionally NOT claimed as complete production evidence:
- a production-persistent state volume/database for the hardened candidate;
- a production backup destination and restore drill bound to the deployed hardened target;
- external monitoring/alert notification routing;
- live/provider fault injection for all failure boundaries;
- independent code/security/architecture review;
- cold-engineer handover/rebuild/recovery exercise;
- full SBOM/hash-locked Python supply-chain evidence.

The currently observed Render TikTok service is on a free plan and the hardened candidate is not deployed. The reviewer must not interpret local SQLite durability tests as proof of production persistence on the live service.

## Required verdict format

For every required item use only:
- PASS — independently evidenced on the exact target;
- FAIL — independently contradicted or vulnerability reproduced;
- NOT VERIFIED — evidence is missing/incomplete or external gate was not exercised;
- N/A — only when genuinely inapplicable, with reason.

Overall:
`SECURITY, RELIABILITY & RECOVERABILITY ACCEPTANCE — PASS`

is permitted only if:
- exact target is verified;
- no unresolved Critical/High finding remains;
- all mandatory critical items have independent evidence;
- production persistence/recovery is evidenced;
- no Critical item remains NOT VERIFIED.

Otherwise the overall result must remain FAIL-CLOSED / NOT AUTHORIZED FOR PRODUCTION AUTO-PUBLISH.

## Handoff rule after findings

Any newly confirmed finding must follow:

Evidence -> Remediation -> Independent Retest -> Closure Evidence

A producer fix is never self-closing.

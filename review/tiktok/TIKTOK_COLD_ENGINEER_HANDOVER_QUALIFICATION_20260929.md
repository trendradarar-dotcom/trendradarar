# TikTok Cold Engineer Handover Qualification

Date: 2026-09-29
Scope: TikTok only

## Independence rule

The cold engineer must not use:
- the original development conversation;
- the original developer's undocumented knowledge;
- the same remediation agent as the source of missing steps.

Allowed inputs only:
- exact repository candidate / bundle;
- documentation in `review/tiktok/`;
- source;
- runbooks;
- owner-provided credentials/secrets through normal secure channels, if a step legitimately requires them.

## Qualification sequence

1. Verify exact commit/tree from Git bundle.
2. Install Python 3.12 dependencies using:
   `python -m pip install --require-hashes -r tiktok_oauth_service/requirements.lock`
3. Run the full TikTok test suite.
4. Generate exact-commit SBOM.
5. Start the service with:
   - mutations disabled;
   - kill switch enabled;
   - no public posting authority.
6. Explain from documentation:
   - OAuth flow;
   - account binding;
   - required scopes;
   - publication state machine;
   - UNKNOWN semantics;
   - idempotency;
   - hard limits;
   - backup/restore;
   - kill switch;
   - revoke/reconnect.
7. Run local recovery qualification:
   - write recovery marker;
   - reopen/restart state;
   - verify marker;
   - create backup;
   - restore to isolated path;
   - verify marker after restore.
8. Inject or construct an UNKNOWN/stale state in the test environment and confirm `/ops/health` degrades.
9. Run the watchdog against an owner-approved test webhook and prove signed alert delivery.
10. Demonstrate that rejected media causes zero provider mutation.
11. Demonstrate duplicate intent remains blocked after restore.
12. Produce a written report of:
   - steps completed;
   - commands used;
   - independent evidence;
   - unclear/missing documentation;
   - any dependency on original developer/AI.

## Pass condition

`COLD ENGINEER HANDOVER = PASS`

only if the independent engineer completes the applicable procedure without needing undocumented help from the original developer/chat/AI.

If undocumented assistance is necessary:
`COLD ENGINEER HANDOVER = FAIL`

## Production caution

A local cold-engineer pass does NOT itself prove:
- Render production persistence;
- production backup destination;
- production alert delivery;
- production restore.

Those require separate production-bound evidence.

# Instagram Recovery Runbook — M26.5

PROJECT: TrendHunter / Trend Radar
SCOPE: Instagram only
MODE: Fail-Closed / Owner-Recovery / No secrets in repository

## Immediate containment

1. Set `INSTAGRAM_PUBLISH_ENABLED=false`.
2. Set `INSTAGRAM_PUBLIC_PUBLISH_AUTHORIZED=false`.
3. Confirm the live health endpoint reports both gates false.
4. Preserve logs, deploy identifiers, exact commit/tree, publication ledger, media spool evidence, and database evidence.
5. Do not retry jobs in `UNKNOWN`, `PUBLISH_REQUESTED`, or `PUBLISHED_UNVERIFIED`.
6. Any unresolved ambiguity blocks new publication mutations.

## Ambiguous publish recovery

If the `media_publish` response is lost, the job is quarantined as `UNKNOWN`. No blind retry is allowed.

An authorized recovery operator may identify a candidate Instagram Media ID from the governed account and submit it through the authenticated internal recovery endpoint. The system independently verifies that the candidate appears in the governed account media list, is a Reel, and has the exact governed final caption before moving the job to `VERIFIED_RECOVERED`.

If any check is inconclusive, the job remains `UNKNOWN` and publishing stays blocked.

## Credential incident

- Revoke the Instagram credential.
- Rotate Instagram/M2M/gateway/session secrets as applicable.
- Keep both public publishing gates false.
- Reconnect only username `trendradarar`, type `BUSINESS`, professional user id `17841428134382903`.
- Rerun the independent security/reliability/recoverability review.

## Backup / restore safety

A restored database can be older than Instagram's real state. After restore, every post-backup uncertain publication must be treated as `UNKNOWN` and reconciled before any new publication.

A backup restore does not authorize republishing.

## Rebuild from trusted source

Use only a frozen reviewed commit/tree, Python 3.14.3, exact requirements, fresh secrets, clean infrastructure, and public gates false. Run dependency audit and adversarial tests before reconnecting.

## Exit gate

Do not enable public Instagram publishing until an independent review passes and the owner explicitly authorizes activation.

This runbook documents the procedure. It is not evidence that a live backup/restore or disaster-recovery drill has already passed.

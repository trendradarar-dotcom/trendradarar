# Instagram M26.8 — Recovery Handover Candidate

STATUS: DOCUMENTATION CANDIDATE
EXECUTION DRILL: NOT VERIFIED
CONTAINS SECRET VALUES: NO

## Purpose

Provide enough non-secret anchors for an authorized owner or cold engineer to identify the governed build and recovery evidence without exposing credentials.

## Identity

Project:
TrendHunter / Trend Radar

Scope:
Instagram only

Governed Instagram identity:
username = trendradarar
account_type = BUSINESS
professional_user_id = 17841428134382903

## Application anchor

R5 exact target:
d41c1c1cdaa7cf374989e2b059db6a640cb51eef

R5 exact tree:
9b7d7c2ab974a55cc9073e24386f4cbe9de8437d

R5 exact CI:
36422824796

## Operations anchor

Operations target:
0a68c4003261f1fe216140fb52665f1d91585d3f

Operations tree:
8561d105562ecf0d0ce8d3fa9f467bf7411af53d

Operations drill:
36442457664

## Fail-closed rules

Before any recovery action:
1. Keep INSTAGRAM_PUBLIC_PUBLISH_AUTHORIZED=false.
2. Keep INSTAGRAM_PUBLISH_ENABLED=false.
3. Do not blindly retry UNKNOWN, PUBLISH_REQUESTED, or ambiguous container creation.
4. Preserve PostgreSQL publication state and audit events.
5. Verify exact account identity before any provider mutation.
6. Do not weaken the production database external network boundary.
7. Do not restore a backup unless its integrity and source are verified.

## Trusted rebuild

Use exact R5 source by commit SHA.
Use the captured R5 wheelhouse and verify every SHA-256 before installation.
Do not substitute newer dependency versions during recovery.
Use a verified PostgreSQL image/version compatible with the captured evidence.
Run the exact R5 acceptance suites before considering the rebuilt runtime usable.

## Data recovery

The isolated producer drill demonstrates a recovery method using pg_dump/pg_restore on PostgreSQL 18 with:
- canonical schema/data/constraint/index comparison;
- duplicate-prevention indexes checked;
- restored ambiguity semantics checked;
- corrupt backup rejection.

This does NOT prove that a current production backup has been successfully restored.

## Credential recovery boundary

No credential or secret value is stored in this document.
OAuth re-link remains hard-disabled in the reviewed candidate.
If credentials are lost or OAuth re-link is required, use a separately reviewed owner-controlled recovery design; do not bypass the hard-disable.

## Human/cold-engineer drill checklist

A real independent operator must be able to:
- identify exact R5 source and tree;
- verify evidence hashes;
- rebuild from captured dependencies;
- identify required environment variable names without seeing secret values in documentation;
- keep publish gates closed;
- recognize UNKNOWN/ambiguous states and avoid blind retry;
- validate a restore into an isolated environment;
- identify which steps require owner login/OAuth/2FA;
- state clearly that public activation remains unauthorized.

Until a real independent person completes this exercise:

OWNER_RECOVERY_PACKAGE = NOT VERIFIED
HUMAN_TAKEOVER = NOT VERIFIED
COLD_ENGINEER_HANDOVER = NOT VERIFIED

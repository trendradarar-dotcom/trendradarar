# SNAPCHAT REMEDIATION FINDINGS MATRIX — 2026-09-28

PROJECT: Trend Radar / TrendHunter  
SCOPE: Snapchat only  
STATUS: REMEDIATION IMPLEMENTED / INDEPENDENT RETEST PENDING  
FINAL ACCEPTANCE: HOLD

Vocabulary:
- IMPLEMENTED = remediation exists in candidate code.
- INTERNAL EVIDENCE = producer/remediation CI evidence exists.
- EXTERNAL OPEN = depends on Snapchat/production infrastructure/owner-controlled external action.
- INDEPENDENT OPEN = must not be closed by the same remediation process.
- NOT APPLICABLE = not present in the selected direct architecture.

| Finding | Remediation state | Evidence / remaining gate |
|---|---|---|
| F-01 Token persistence across restart | IMPLEMENTED + INTERNAL EVIDENCE | encrypted durable credential record in PostgreSQL; fresh-store tests PASS. Independent retest pending. |
| F-02 OAuth replay / login binding | IMPLEMENTED + INTERNAL EVIDENCE | one-time owner intent, signed state, browser nonce, durable one-time consumption, replay test. Independent retest pending. |
| F-03 Direct-path production-gate bypass | IMPLEMENTED + INTERNAL EVIDENCE | direct path now requires all production readiness gates + durable store/connection. Independent retest pending. |
| F-04 Persistent idempotency / duplicate prevention | IMPLEMENTED + INTERNAL EVIDENCE | PostgreSQL ledger, immutable publication/content/job/media binding, duplicate tests. Independent retest pending. |
| F-05 Crash / UNKNOWN / reconciliation | IMPLEMENTED + INTERNAL EVIDENCE | SUBMITTING persisted before remote POST; UNKNOWN blocks retry; reconciliation path exists; live provider reconciliation still depends on allowlist. |
| F-06 Exact target binding | IMPLEMENTED + INTERNAL EVIDENCE | exact Public Profile ID + username + authorized-access checks. Live read-only provider verification pending allowlist. |
| F-07 Disconnect / revocation | PARTIAL | local durable disconnect implemented. External Snapchat revocation/rotation practical drill remains EXTERNAL OPEN. |
| F-08 Hard limits / blast radius | IMPLEMENTED + INTERNAL EVIDENCE | hour/day/concurrency/attempt/horizon limits + PostgreSQL concurrency test. Final production values/verified flag remain open. |
| F-09 Actual media validation | IMPLEMENTED + INTERNAL EVIDENCE | server-side ffmpeg duration/resolution probe. Independent malformed-media campaign pending. |
| F-10 Deployment admission / exact deploy | PARTIAL | isolated candidate uses autoDeploy=no. Final frozen SHA/deploy verification pending. Original review branch protection is not claimed. |
| F-11 Independent kill switch | PARTIAL | app kill/read-only gates + hosting control-plane recovery procedure. Practical independent service-stop drill remains INDEPENDENT/EXTERNAL OPEN. |
| F-12 External alert delivery | EXTERNAL OPEN | no external alert sink has been selected and tested. SNAPCHAT_ALERTING_READY must remain false. |
| F-13 Secret history review | IMPLEMENTED + INTERNAL EVIDENCE | deterministic current-tree + Git-history scanner. Independent secret/provenance review remains open. |
| F-14 Penetration test / cold engineer | INDEPENDENT OPEN | automated CI is not a substitute for independent penetration test or cold handover. |

## Additional acceptance items

### SSRF

Direct selected path:
- uploaded media bytes are received directly;
- no arbitrary user-supplied media URL is fetched by the direct bridge;
- provider-returned upload URLs/paths are restricted to the Snapchat Business API host.

Therefore generic media-URL SSRF is NOT APPLICABLE to the selected direct upload path, subject to independent verification of the implementation.

### Queue / scheduler

The direct bridge currently does not implement its own queue or scheduler.

Queue-redelivery-specific controls are NOT APPLICABLE inside this isolated direct service today.

If a future worker/queue is added, queue durability, redelivery, backlog, scheduling, and kill-switch requirements become mandatory and require a new review.

### Database backup / restore

Now applicable because durable state was introduced.

Internal evidence:
- PostgreSQL pg_dump;
- clean restore database;
- restored SUBMITTED publication;
- duplicate admission denied after restore.

Production backup schedule/retention on a dedicated Snapchat database remains EXTERNAL OPEN.

## Current authorization

- PUBLICATION_AUTHORITY = ZERO
- SNAPCHAT_PUBLICATION_ENABLED must remain false
- SNAPCHAT_KILL_SWITCH must remain true
- SNAPCHAT_EMERGENCY_READ_ONLY must remain true
- SNAPCHAT_ALERTING_READY must remain false
- SNAPCHAT_PRODUCTION_ASSURANCE_READY must remain false

## Final acceptance

SECURITY_RELIABILITY_RECOVERABILITY_ACCEPTANCE = NOT YET PASS

Required next phase:
- freeze exact candidate;
- deploy exact frozen candidate fail-closed;
- prepare independent review handoff;
- independent retest / penetration / recovery / cold-handover evidence;
- external allowlist/read-only binding evidence;
- external alert delivery evidence;
- only then reconsider production opening.

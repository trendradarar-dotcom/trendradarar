# SNAPCHAT RECOVERY RUNBOOK — 2026-09-28

PROJECT: Trend Radar / TrendHunter  
SCOPE: Snapchat only  
STATUS: REMEDIATION CANDIDATE RUNBOOK  
SUPERSEDES FOR THIS CANDIDATE: SNAPCHAT_RECOVERY_RUNBOOK_20260925.md

## Trigger conditions

Activate this runbook when any of the following occurs:
- unauthorized/unexpected publication;
- suspected credential compromise;
- OAuth/account/profile mismatch;
- UNKNOWN state after a submit attempt;
- duplicate-publication suspicion;
- durable database outage/corruption;
- publisher/runtime integrity concern;
- deployed code not equal to the accepted frozen commit;
- abnormal retry/publication volume;
- loss of owner confidence in the subsystem.

## Phase 1 — Contain

Using the external hosting control plane, immediately enforce:
1. SNAPCHAT_PUBLICATION_ENABLED=false
2. SNAPCHAT_KILL_SWITCH=true
3. SNAPCHAT_EMERGENCY_READ_ONLY=true

Then:
4. do not clear logs;
5. do not retry UNKNOWN publications;
6. do not rotate/delete evidence before recording the current deploy;
7. if application-level control cannot be trusted, stop/suspend the Snapchat service from the hosting control plane.

The service-stop capability is the break-glass control when the publisher itself is untrusted.

## Phase 2 — Preserve

Record without exposing secrets:
- UTC incident time;
- exact repository commit;
- Render service and deploy IDs;
- current control-state flags;
- database identity;
- latest known backup identity;
- correlation IDs;
- publication IDs;
- content IDs;
- job IDs;
- remote media/Spotlight IDs;
- relevant safe logs;
- Snapchat-side status.

## Phase 3 — Freeze mutations

Do not:
- publish new content;
- retry UNKNOWN;
- consume scheduled work;
- reconnect silently;
- modify the database to make an uncertain record look successful.

Keep UNKNOWN as UNKNOWN until reconciled.

## Phase 4 — Determine external side effects

For each ambiguous publication:
1. load its durable publication record;
2. if remote_spotlight_id exists, query the exact Spotlight status;
3. verify remote profile ID equals the expected owned Public Profile;
4. map only documented states SUBMITTED/LIVE/REJECTED;
5. reject unexpected remote states as unverified;
6. if no remote ID exists after an ambiguous submit, use the reconciliation procedure;
7. accept a fallback match only when exactly one remote candidate matches the allowed evidence window;
8. if zero or multiple candidates exist, retain UNKNOWN.

Never convert UNKNOWN to success merely to clear an error.

## Phase 5 — Credential containment

If OAuth compromise is suspected:
1. keep publication closed;
2. execute local owner-authorized disconnect;
3. revoke/disable external Snapchat application/account authorization where required;
4. rotate SNAPCHAT_OWNER_KEY if affected;
5. rotate SNAPCHAT_CLIENT_SECRET if affected;
6. replace SNAPCHAT_TOKEN_ENCRYPTION_KEY only as part of a controlled disconnect/re-auth sequence;
7. perform fresh OAuth authorization after containment;
8. verify exact Public Profile ID and username before considering recovery.

## Phase 6 — Database containment

If database integrity is suspected:
1. stop publication;
2. take a forensic backup/snapshot if safe;
3. record schema and exact source commit;
4. never restore over another project database;
5. create a clean isolated Snapchat database;
6. apply the documented migration;
7. restore a trusted backup;
8. verify publication IDs/remote IDs;
9. run the restore duplicate-prevention probe;
10. keep all UNKNOWN records blocked.

## Phase 7 — Rebuild from trusted source

1. create clean runtime infrastructure;
2. deploy the exact independently accepted frozen Snapchat commit;
3. install pinned dependencies;
4. connect only the dedicated Snapchat database;
5. keep publication=false;
6. keep kill switch=true;
7. keep emergency read-only=true;
8. run CI-equivalent checks;
9. verify health;
10. configure secrets through the secret manager only;
11. reconnect OAuth through the one-time owner-authorized flow;
12. verify exact target binding read-only.

## Phase 8 — Backup/restore validation

Before production reopening after a restore:
- confirm restored publication state exists;
- confirm remote IDs survive;
- confirm duplicate admission for previously SUBMITTED/LIVE/UNKNOWN content is blocked;
- confirm content_id/job_id/media hash binding survives;
- confirm hard-limit counters derive from restored durable records;
- confirm OAuth durable record state is correct.

## Phase 9 — Independent re-verification

Required before reopening:
- exact-target verification;
- code/security retest independent from remediation;
- OAuth replay/login-CSRF probes;
- exact account/profile binding;
- durable idempotency/restart tests;
- UNKNOWN/reconciliation tests;
- race/concurrency tests;
- hard-limit tests;
- media validation tests;
- backup/restore test;
- secret/history scan;
- practical kill-switch/service-stop drill;
- alert delivery test;
- independent penetration test as applicable;
- cold-engineer handover when required by the governing acceptance gate.

## Phase 10 — Progressive recovery

Only after evidence exists:
1. set target_account_verified=true;
2. set durable_reconciliation_ready=true;
3. set alerting_ready=true only after external delivery evidence;
4. set production_assurance_ready=true only after independent acceptance;
5. set hard_limits_verified=true only after final production values are reviewed;
6. confirm dedicated PostgreSQL health/backup;
7. disable emergency read-only;
8. release kill switch;
9. set publication_enabled=true LAST.

Monitor the first governed production transaction.

## Phase 11 — Post-incident

- preserve closure evidence;
- document root cause;
- document affected publications;
- rotate any remaining affected credentials;
- add regression tests;
- perform independent retest;
- update owner recovery package;
- create a new frozen candidate;
- never reuse the old production acceptance after a security-relevant change.

## Owner emergency objective

A qualified engineer receiving only:
- frozen source;
- this runbook;
- owner recovery package;
- database backup/migration;
- access to owner-controlled external accounts;

must be able to stop, inspect, rebuild, restore, and independently validate the Snapchat subsystem without the original developer, original chat, or original AI model.

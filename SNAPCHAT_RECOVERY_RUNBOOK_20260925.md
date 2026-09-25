# SNAPCHAT RECOVERY RUNBOOK — 2026-09-25

PROJECT: Trend Radar / TrendHunter
SCOPE: Snapchat only

## Trigger conditions

Use this runbook if:
- unauthorized or unexpected Snapchat publication is suspected;
- a credential is suspected compromised;
- provider state is unknown after a failed request;
- the service is publishing duplicates;
- the deployed code does not match the accepted commit;
- the owner loses confidence in runtime integrity.

## Phase 1 — CONTAIN

1. Set SNAPCHAT_PUBLICATION_ENABLED=false.
2. Set SNAPCHAT_KILL_SWITCH=true.
3. Set SNAPCHAT_EMERGENCY_READ_ONLY=true.
4. Keep SNAPCHAT_PUBLISH_PROVIDER=disabled unless a selected provider must stay readable for reconciliation.
5. Confirm /health reports the closed control state.
6. Do not delete logs or redeploy over evidence before recording the current deploy and commit identifiers.

Expected result:
- no new publication request can be intentionally emitted.

## Phase 2 — PRESERVE

Record:
- UTC incident start time;
- Render service ID and deploy ID;
- deployed Git commit;
- relevant correlation IDs;
- publication IDs;
- provider post IDs;
- relevant safe log excerpts;
- exact external Snapchat/provider state.

Never paste credential values into the incident report.

## Phase 3 — REVOKE / ROTATE

If credential compromise is suspected:
- revoke the affected external authorization where supported;
- rotate SNAPCHAT_OWNER_KEY;
- rotate provider API credential if a provider exists;
- rotate Snapchat OAuth client/refresh credentials if the direct route is active;
- invalidate old values before reopening publication;
- verify account recovery email / 2FA remains owner-controlled.

## Phase 4 — DETERMINE EXTERNAL SIDE EFFECT

For every publication request with an ambiguous timeout or error:
- do not retry blindly;
- query provider/platform state by durable external identifier where available;
- classify each request as NOT_SENT / SENT_PENDING / LIVE / REJECTED / UNKNOWN;
- UNKNOWN remains blocked for retry until reconciled.

UNKNOWN != SUCCESS.

## Phase 5 — ERADICATE

If the runtime is suspected compromised:
- do not patch the compromised instance in place as the only recovery action;
- identify the last trusted source commit;
- review the exact diff after that commit;
- remove malicious/incorrect code from source;
- verify dependencies;
- prepare clean credentials.

## Phase 6 — REBUILD FROM TRUSTED SOURCE

1. create a clean runtime/service;
2. deploy from the exact verified repository commit;
3. install documented dependencies;
4. keep provider disabled;
5. keep publication disabled;
6. keep kill switch active;
7. keep emergency read-only active;
8. run compile/tests/security checks;
9. verify /health;
10. only then reconnect any external credential.

## Phase 7 — RE-VERIFY

Before production reopening:
- exact target account = trendradarar / Trend Radar;
- local gates PASS;
- Saudi gate PASS for SA content;
- country/global template identity PASS;
- authenticity/rights/originality PASS;
- durable reconciliation working;
- alerts working;
- current selected route still supported;
- no blocking security finding remains;
- independent verification requirements applicable to the final production route are completed.

## Phase 8 — RECOVER

Open production only through a deliberate change:
- select the accepted provider/first-party route;
- set emergency read-only false;
- release kill switch;
- set publication enabled true last.

Reopen progressively and monitor the first governed production transaction.

## Phase 9 — POST-INCIDENT

- preserve final evidence;
- document root cause;
- document affected publications;
- rotate any remaining exposed credentials;
- add a regression test for the incident;
- conduct an independent retest;
- update the recovery package and candidate baseline.

## Emergency owner objective

A qualified engineer receiving only:
- repository;
- this runbook;
- owner recovery package;
- current service access;
- owner-controlled external accounts;

must be able to stop the Snapchat subsystem without the original AI conversation.

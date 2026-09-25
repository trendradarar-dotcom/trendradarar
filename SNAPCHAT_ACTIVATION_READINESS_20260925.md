# SNAPCHAT ACTIVATION / ASSURANCE READINESS — 2026-09-25

PROJECT: Trend Radar / TrendHunter
PLATFORM: Snapchat only
MODE: strict isolation / exact evidence / fail-closed
AUTHORITATIVE GOVERNANCE: SNAPCHAT_AUTOMATION_GOVERNANCE_V2_20260925.md
ACCEPTANCE MATRIX: SNAPCHAT_ACCEPTANCE_MATRIX_20260925.md
PUBLICATION STATE: HOLD
PUBLICATION AUTHORITY: ZERO

## Frozen operating requirement

Normal runtime human actions target:
- 0

Accepted exception model:
- owner is disturbed only for a rare external legal/technical action that the automation cannot itself perform, such as external re-authentication/2FA/new legal consent.

Rejected:
- routine manual posting;
- unrelated commercial registry;
- misleading business identity;
- new paid publisher merely to solve Snapchat.

## Product identity

- username: trendradarar
- brand: Trend Radar / رادار الترند
- Public Profile: created
- master slogan: «اكتشف ما يصعد الآن في بلدك والعالم»
- local framing: «هذا ما يصعد الآن في بلدك»
- separate GLOBAL_SELECTED lane: «ترند عالمي»

## Geographic model

Arab-country lanes:
DZ, BH, KM, DJ, EG, IQ, JO, KW, LB, LY, MR, MA, OM, PS, QA, SA, SO, SD, SY, TN, AE, YE

Global:
- GLOBAL_SELECTED

Saudi:
- dedicated Saudi gate required.

## Current route feasibility

Direct Snapchat Public Profile API:
- official autonomous path exists technically;
- current official access model requires Business Account/Organization + OAuth App + allowlisting;
- under frozen owner constraints this route is externally blocked for the current setup;
- direct bridge retained dormant and fully disabled by default.

Ayrshare:
- adapter retained as evaluated contingency;
- not selected;
- no production subscription/trial/payment dependency.

Creative Kit / web upload:
- not accepted as normal runtime because user action is required to complete publication.

Current provider:
- disabled

## Publisher implementation

Service:
- trendradar-snapchat-publisher
- Render ID: srv-dar6s0vavr4c7380epmg
- URL: https://trendradar-snapchat-publisher.onrender.com
- latest verified deploy: dep-dar875nlot8c73equlng
- source code baseline in deploy: 7d98f9be995423ab9d2ef1ef2f612c23d049dd6e
- deploy state: LIVE

External /health verification:
- ok=true
- version=snapchat-publisher-service-20260925.3
- provider=disabled
- provider_configured=false
- publication_enabled=false
- kill_switch=true
- emergency_read_only=true
- normal_runtime_human_actions_target=0
- external_publication_side_effect=NONE

Implemented gates:
- exact 22 Arab markets + GLOBAL_SELECTED
- exact Arabic market labels
- exact local/global template IDs
- Arabic activation
- stable publication_id
- strict native-boolean PASS semantics
- rights gate
- originality gate
- human-origin gate
- wholly-AI-generated content blocked from growth lane
- Saudi gate
- HTTPS media URL
- 30–60 second internal target
- 9:16 target / minimum dimensions
- deterministic provider idempotency where supported
- in-process duplicate serialization
- generic provider validation/status adapter
- correlation IDs
- structured secret-safe audit events
- disabled provider default
- kill switch
- emergency read-only
- publication gate

## Dormant first-party bridge

Service:
- trendradar-snapchat-oauth
- Render ID: srv-daqvhinavr4c73f6r9sg
- URL: https://trendradar-snapchat-oauth.onrender.com
- latest verified deployment target: 9a55b44bb7e5bada1640c883086f1b57cc9c9df1
- deploy: dep-dar89a3ncjis73cgsn4g
- state: LIVE

External health:
- version=snapchat-oauth-service-20260925.2
- direct_api_enabled=false
- publication_enabled=false
- kill_switch=true
- emergency_read_only=true
- client_id=false
- client_secret=false
- profile_id=false
- refresh_token=false

External inertness verification:
- GET /auth/start returned direct_api_disabled
- external_side_effect=BLOCKED

Dormant bridge improvements:
- external API disabled by default;
- OAuth/read/publish/validation/token-status paths inert when disabled;
- error bodies/details reduced;
- current direct dependencies pinned;
- publication has independent publication/kill/read-only controls.

## CI / test / supply-chain evidence

Latest exact code CI:
- run ID: 36147465872
- head: 9a55b44bb7e5bada1640c883086f1b57cc9c9df1
- result: SUCCESS

Same run:
- publisher/API tests: 26 PASS
- dormant direct-bridge tests: 5 PASS
- Python compile both services: PASS
- pip dependency consistency: PASS
- pip-audit publisher requirements: NO KNOWN VULNERABILITIES FOUND
- pip-audit direct bridge requirements: NO KNOWN VULNERABILITIES FOUND
- basic committed credential-pattern scan: PASS

Publisher direct pins:
- Flask 3.1.3
- gunicorn 26.2.0
- requests 2.34.2

Direct bridge direct pins:
- Flask 3.1.3
- gunicorn 26.2.0
- requests 2.34.2
- cryptography 50.0.1

This is internal/automated evidence, not independent verification.

## Recovery assets created

- SNAPCHAT_OWNER_RECOVERY_PACKAGE_20260925.md
- SNAPCHAT_RECOVERY_RUNBOOK_20260925.md
- SNAPCHAT_SBOM_20260925.md
- SNAPCHAT_GOLDEN_BASELINE_CANDIDATE_20260925.md
- SNAPCHAT_ACCEPTANCE_MATRIX_20260925.md

Golden status:
- CANDIDATE ONLY
- not an independently verified GOLDEN RELEASE.

## Remaining production blockers

Blocking:
1. no currently accepted official publication route satisfies all frozen owner constraints;
2. durable cross-restart publication ledger/reconciliation is not implemented;
3. external alert delivery/retention is not verified;
4. independent code/architecture/security verification is not completed;
5. independent recovery/cold-engineer handover is not completed.

Not a blocker to internal preparation:
- content validation;
- Snapchat visual packaging;
- country/global routing;
- fail-closed service operation.

## Applicable acceptance state

Internal implementation / regression evidence:
- PASS for current fail-closed baseline.

Independent verification:
- NOT VERIFIED.

Autonomous public Spotlight:
- HOLD_EXTERNAL_ACCESS_MODEL.

Routine manual publishing:
- REJECTED.

Paid publishing intermediary:
- NOT SELECTED.

Unrelated commercial registry:
- NOT USED.

## Final current decision

SNAPCHAT_ENGINEERING_VIABILITY = YES
BUILD_AND_FORGET_NORMAL_RUNTIME_TARGET = VIABLE IN PRINCIPLE
CURRENT_PUBLIC_AUTONOMOUS_PUBLICATION = NOT YET VIABLE UNDER FROZEN ACCESS CONSTRAINTS
CURRENT_MAXIMUM_PUBLICATION_BLAST_RADIUS = 0
PUBLICATION_GATE = CLOSED

# SNAPCHAT OWNER RECOVERY PACKAGE — 2026-09-25

PROJECT: Trend Radar / TrendHunter
SCOPE: Snapchat only
PURPOSE: allow the owner or a new qualified engineer to understand, stop, rebuild and recover the Snapchat subsystem without the original chat or original AI model.

## 1. Source ownership

Repository:
- trendradarar-dotcom/trendradarar

Working branch:
- snapchat-production-review-20260925

Current governing file:
- SNAPCHAT_AUTOMATION_GOVERNANCE_V2_20260925.md

Current assurance file:
- SNAPCHAT_ARCHITECTURE_ASSURANCE_REVIEW_20260925.md

Publisher source:
- snapchat_publisher_service/app.py
- snapchat_publisher_service/publisher.py
- snapchat_publisher_service/audit.py
- snapchat_publisher_service/requirements.txt
- snapchat_publisher_service/test_publisher.py
- snapchat_publisher_service/test_app.py

Dormant first-party fallback:
- snapchat_oauth_service/app.py
- snapchat_oauth_service/requirements.txt
- snapchat_oauth_service/README.md

CI:
- .github/workflows/snapchat-publisher-ci.yml

## 2. Current external services

### Render publisher
Name:
- trendradar-snapchat-publisher

Service ID:
- srv-dar6s0vavr4c7380epmg

URL:
- https://trendradar-snapchat-publisher.onrender.com

Region:
- Frankfurt

Build:
- pip install -r snapchat_publisher_service/requirements.txt

Start:
- gunicorn --chdir snapchat_publisher_service app:app

### Render direct OAuth fallback
Name:
- trendradar-snapchat-oauth

Service ID:
- srv-daqvhinavr4c73f6r9sg

URL:
- https://trendradar-snapchat-oauth.onrender.com

Role:
- dormant first-party contingency only
- not current production publication authority

## 3. Snapchat ownership

Owned target account:
- username: trendradarar
- brand: Trend Radar
- Public Profile: created

Do not substitute:
- an unrelated commercial registry;
- a different Snapchat account;
- another platform account.

## 4. Required configuration names

Publisher controls:
- SNAPCHAT_PUBLISH_PROVIDER
- SNAPCHAT_PUBLICATION_ENABLED
- SNAPCHAT_KILL_SWITCH
- SNAPCHAT_EMERGENCY_READ_ONLY
- SNAPCHAT_OWNER_KEY
- SNAPCHAT_TARGET_ACCOUNT_VERIFIED
- SNAPCHAT_DURABLE_RECONCILIATION_READY
- SNAPCHAT_ALERTING_READY
- SNAPCHAT_PRODUCTION_ASSURANCE_READY

Optional dormant provider configuration:
- AYRSHARE_API_KEY
- AYRSHARE_BASE_URL

Direct first-party fallback variables:
- SNAPCHAT_CLIENT_ID
- SNAPCHAT_CLIENT_SECRET
- SNAPCHAT_REDIRECT_URI
- SNAPCHAT_STATE_SECRET
- SNAPCHAT_PUBLIC_PROFILE_ID
- SNAPCHAT_REFRESH_TOKEN
- SNAPCHAT_ACCESS_TOKEN
- SNAPCHAT_OWNER_KEY
- SNAPCHAT_PUBLICATION_ENABLED

Secret VALUES are intentionally excluded from this package.

## 5. Frozen safe configuration

Until the publication route is accepted:

- SNAPCHAT_PUBLISH_PROVIDER=disabled
- SNAPCHAT_PUBLICATION_ENABLED=false
- SNAPCHAT_KILL_SWITCH=true
- SNAPCHAT_EMERGENCY_READ_ONLY=true
- SNAPCHAT_TARGET_ACCOUNT_VERIFIED=false
- SNAPCHAT_DURABLE_RECONCILIATION_READY=false
- SNAPCHAT_ALERTING_READY=false
- SNAPCHAT_PRODUCTION_ASSURANCE_READY=false

Expected external publication blast radius:
- 0

## 6. Build from trusted source

A new engineer should:

1. obtain the repository from the owner-controlled GitHub account;
2. check out the exact accepted Snapchat branch/commit;
3. verify the commit against the recorded candidate baseline;
4. create a fresh isolated Python environment;
5. install the exact publisher requirements;
6. run compile + all Snapchat publisher tests;
7. run dependency/security checks required by the current CI;
8. deploy to a clean Render service with publication disabled, kill switch active and emergency read-only active;
9. verify /health before adding any external publication credential;
10. do not open production until the acceptance matrix is satisfied.

## 7. Routine health endpoints

Public read-only:
- GET /health
- GET /

Owner-protected read-only:
- GET /admin/control-state
- GET /spotlight/status/{provider_post_id} when a provider is selected

Validation:
- POST /spotlight/validate

Mutation:
- POST /spotlight/publish
- must remain blocked until all production controls are intentionally opened.

## 8. Recovery ownership

Owner must retain control of:
- GitHub repository account;
- Render workspace;
- Snapchat account trendradarar;
- project email accounts used for recovery;
- any future selected provider account;
- ability to revoke/replace every integration credential.

No recovery-critical credential should exist only in an AI chat or developer's personal machine.

## 9. Current persistence model

The current standalone publisher has no application database.

Therefore:
- there is no publisher database backup to restore today;
- source/config/service recovery is the immediate recovery concern;
- before production publication, a durable publication ledger/reconciliation store is still required.

Do not treat process memory as durable state.

## 10. External dependencies / replacement map

Snapchat:
- purpose: target publication network
- replaceable: no; it is the target platform
- emergency action: revoke integrations / stop publication

Render:
- purpose: runtime hosting
- replaceable: yes, because build/start/config are documented
- emergency action: disable publication controls / deploy clean service

Ayrshare:
- purpose: optional evaluated publisher adapter
- current state: NOT SELECTED
- replacement: direct first-party route or another future supported adapter

## 11. Incident evidence to preserve

On an incident preserve:
- exact deployed commit SHA;
- Render deploy ID;
- Render logs;
- correlation IDs;
- publication IDs;
- provider post IDs if any;
- time window;
- configuration names/state without exposing credential values;
- external Snapchat/provider status evidence.

Do not destroy logs before preservation.

## 12. Current recovery limitations

NOT YET VERIFIED:
- independent cold-engineer handover;
- independent penetration test;
- independent ASVS L3 assessment;
- durable publication ledger restore;
- automated external alert delivery;
- full disaster-recovery drill.

Therefore this package is a recovery asset, not proof that recovery acceptance has already passed.

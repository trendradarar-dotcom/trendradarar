# M26.0 — Fresh Meta Reconciliation — Instagram
Date: 2026-09-25
Project: TrendHunter / Trend Radar
Platform: Instagram
Mode: Fresh / Exact-Target-Bound / Fail-Closed / No New Workaround
Public Publishing: HOLD

## Scope
This gate reconciles the exact Meta/Instagram provider identity and OAuth configuration before any further production architecture freeze or publisher implementation.

## Fresh live target
Repository: trendradarar-dotcom/trendradarar
Branch: instagram-production-review-20260924

Instagram OAuth backend:
- Render service: trendradar-instagram-oauth
- Service ID: srv-daqed80u01pc73fs6rgg
- Branch: instagram-production-review-20260924
- Latest live code commit observed by Render: 2de9fc08e460b969e6e21957654656aa370f2987

Browser gateway:
- Render service: trendradar-connect
- Service ID: srv-dar4l3k9v7es739flr0g
- Branch: instagram-production-review-20260924
- Latest live code commit observed by Render: 2de9fc08e460b969e6e21957654656aa370f2987

Both Render services report latest deploy state LIVE.

## Exact provider error
Observed in owner browser:
Invalid Request: Invalid platform app

This occurs before successful Instagram authorization and therefore blocks OAuth acceptance.

## Finding M26.0-F1 — APP ID identity collision
Severity: BLOCKING
Status: OPEN / ROOT CAUSE BOUND

Repository evidence contains two conflicting labels for the same numeric identifier:

1. The live Meta app creation section records:
   META_APP_ID = 1584158563162593

2. A later Render readiness section records:
   INSTAGRAM_APP_ID = 1584158563162593

The same identifier was therefore promoted from a generic Meta App identity into the Instagram Login client-id slot without fresh provider evidence proving that it is the Instagram-specific App ID.

The live OAuth request used this value as client_id and Instagram rejected the request with:
Invalid platform app

## Provider model reconciliation
Target integration model:
Instagram API with Instagram Login

Required publication scopes:
- instagram_business_basic
- instagram_business_content_publish

Professional account target:
- @trendradarar
- Exact username binding required
- BUSINESS or MEDIA_CREATOR only

No Facebook Page requirement is assumed for this Instagram Login model.

## Exact provider fields that remain NOT VERIFIED
The following values MUST be read directly from the Meta Developer app's Instagram Login setup page and must not be inferred from Basic Settings, source code, old notes, URLs, or the generic Meta App header:

- Instagram App ID
- Instagram App Secret
- Instagram Business Login status/configuration
- Valid OAuth Redirect URI list
- Current permission/test readiness
- Exact Instagram Login product/use-case activation state

## Security handling
- Instagram App Secret must never be pasted into chat, GitHub, screenshots, review evidence, or public logs.
- Secret must be entered directly into the Render environment.
- Existing value must not be assumed correct merely because /health was previously configured=true.
- Public media_publish remains disabled.

## Mutation rule
Until M26.0-F1 is closed:
- NO new OAuth workaround.
- NO publisher implementation expansion.
- NO public publishing activation.
- NO architecture freeze based on the current App ID.
- NO use of 1584158563162593 as INSTAGRAM_APP_ID unless Meta's Instagram Login page independently proves it.

## M26.0 completion evidence required
PASS requires all of the following:

1. Direct visual/provider evidence of Instagram App ID from:
   Meta Developer App -> Instagram -> API setup with Instagram login
   (or the current equivalent Business Login settings page).

2. Confirmation that the Instagram App Secret shown on that same Instagram Login setup is the secret entered directly into Render.
   The secret value itself must not be recorded.

3. Exact Valid OAuth Redirect URI confirmed in Meta and matched byte-for-byte to the deployed callback.

4. OAuth start reaches Instagram authorization without Invalid platform app.

5. OAuth callback succeeds.

6. Returned provider identity verifies:
   username = trendradarar
   account type = BUSINESS or MEDIA_CREATOR
   professional user ID present.

7. Requested/granted scopes reconciled.

8. PUBLIC_INSTAGRAM_PUBLISH_AUTHORIZED remains false.

## Current gate result
M26.0 = HOLD
M26.0-F1 = OPEN
M26.1 ARCHITECTURE FREEZE = NOT AUTHORIZED

NEXT HUMAN EXCEPTION GATE:
Owner authenticates to the Meta Developer Console for the Trend Radar app. No secret is to be shared in chat.

NEXT MACHINE ACTION AFTER PROVIDER EVIDENCE:
- Replace only the incorrect Instagram-specific credential/config values.
- Redeploy.
- Fresh OAuth retest.
- Close M26.0-F1 only on provider evidence.
- Then proceed to M26.1 Architecture Freeze.


## Fresh provider evidence — 2026-09-26

OWNER_META_DEVELOPER_ACCESS = RESTORED
META_APP_NAME = Trend Radar
META_APP_ID = 1584158563162593

DIRECT_PROVIDER_PAGE:
Meta Developer App -> Instagram API -> API setup with Instagram login

INSTAGRAM_APP_NAME = Trend Radar-IG
INSTAGRAM_APP_ID = 1358113199729841
INSTAGRAM_APP_SECRET = PRESENT_ON_PROVIDER_PAGE_BUT_VALUE_NOT_RECORDED

FRESH_RENDER_UPDATE:
INSTAGRAM_APP_ID = 1358113199729841
Render deploy = LIVE
/health = configured=true
PUBLIC_INSTAGRAM_PUBLISH_AUTHORIZED = false

FRESH_OAUTH_START_RETEST:
RESULT = PASS
Observed provider gate = standard Instagram login page
Observed platform_app_id = 1358113199729841
Observed client_id = 1358113199729841
Previous provider error "Invalid platform app" = NOT PRESENT

M26.0-F1 APP_ID_IDENTITY_COLLISION:
ROOT_CAUSE = CONFIRMED
APP_ID_CORRECTION = PASS
FINDING_STATUS = PARTIALLY_CLOSED_PENDING_SECRET_AND_CALLBACK_VERIFICATION

Remaining completion evidence:
- Confirm the Instagram App Secret from the same Instagram Login setup is the value entered directly into Render; never record the secret value.
- Confirm exact OAuth redirect URI against provider configuration.
- Complete OAuth callback.
- Verify exact provider identity @trendradarar, BUSINESS/MEDIA_CREATOR, professional user ID.
- Reconcile requested and granted scopes.
- Keep PUBLIC_INSTAGRAM_PUBLISH_AUTHORIZED=false.


## Verification build live — 2026-09-26

CODE_COMMIT = ebbd052a2dedfa545b3839443438d26a4ebbb772
RENDER_DEPLOY = dep-dargl8t9fdbs739h5ujg
DEPLOY_STATUS = LIVE
HEALTH_OK = true
HEALTH_CONFIGURED = true
PUBLIC_INSTAGRAM_PUBLISH_AUTHORIZED = false

SAFE_CALLBACK_EVIDENCE_ADDED:
- username
- account_type
- professional_user_id
- permissions returned by short-token response when provider supplies them
- no access token or secret is displayed

CURRENT_EXACT_GATE:
INSTAGRAM_APP_SECRET must be replaced with the Instagram-specific secret displayed next to Instagram App ID 1358113199729841 on the provider page.
The prior secret was sourced before the App-ID collision was reconciled and is not accepted as Instagram-specific evidence.

AFTER_SECRET_REPLACEMENT:
1. Redeploy.
2. OAuth owner consent for @trendradarar.
3. Callback identity and permission verification.
4. Close M26.0 only if all provider evidence passes.

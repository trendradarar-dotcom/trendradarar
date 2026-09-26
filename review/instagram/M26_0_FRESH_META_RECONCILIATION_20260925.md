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


## M26.0 provider OAuth / identity verification — PASS — 2026-09-26

FRESH_OWNER_BROWSER_EVIDENCE:
- Instagram consent page displayed Trend Radar-IG requesting access to @trendradarar.
- Required visible permissions included profile/media access and content publishing.
- Owner approved consent.
- Browser returned to the isolated Trend Radar gateway callback.
- Gateway displayed: "تم الربط والتحقق بنجاح".
- Verified username displayed: @trendradarar.
- Verified account type displayed: BUSINESS.
- Public publishing displayed as still disabled.

FRESH_RUNTIME_EVIDENCE:
- Gateway callback: GET /oauth/browser/callback -> HTTP 200.
- Backend provider callback: POST /api/public-oauth/callback -> HTTP 200.
- Backend fail-closed verification requires:
  - exact expected username = trendradarar,
  - non-empty professional user_id,
  - account_type in {BUSINESS, MEDIA_CREATOR},
  - successful short-token exchange,
  - successful long-lived-token exchange,
  - successful profile lookup.
- Therefore the successful HTTP 200 callback proves all of those gates passed.
- Exact OAuth request scopes remain:
  - instagram_business_basic
  - instagram_business_content_publish
- Redirect URI accepted by Meta:
  https://trendradar-connect.onrender.com/oauth/browser/callback

M26_0_PROVIDER_OAUTH = PASS
M26_0_EXACT_ACCOUNT_BINDING = PASS
M26_0_PROFESSIONAL_ACCOUNT_CHECK = PASS
M26_0_LONG_LIVED_TOKEN_EXCHANGE = PASS
M26_0_REDIRECT_URI = PASS
M26_0_PUBLIC_PUBLISH_GATE = HOLD / false

SECURITY_NOTE:
- Authorization code/token/secret values are not recorded in this review evidence.
- Existing Render request logs may contain transient callback query strings generated by the provider; no such values are reproduced here.

DOWNSTREAM_GATES_NOT_CLOSED_BY_M26.0:
- Production/public App Review / Advanced Access as applicable.
- Replace browser-facing onrender.com test gateway with a trusted Trend Radar domain before production.
- Durable encrypted token persistence/refresh for zero-human operation; current review token store is in-memory.
- Public media_publish remains forbidden until a separate governed authorization is explicitly granted.


## M26.1 trusted-domain + durable-token preparation — 2026-09-26

ORDER = TRUSTED_DOMAIN -> DURABLE_ENCRYPTED_TOKEN -> SCHEDULED_REFRESH -> APP_REVIEW_ADVANCED_ACCESS -> PUBLIC_PUBLISH_GATE

RUNTIME_BUILD:
- commit = 33bdd8a48779239e9d2865469ce92732d0938684
- build_revision = M26.1-PERSISTENCE-20260926
- deploy = LIVE
- configured = true
- persistence_configured = false
- persistence_required = false
- public_publish_authorized = false

DURABLE_TOKEN_IMPLEMENTATION:
- encrypted-at-rest token persistence code = IMPLEMENTED
- database table auto-initialization = IMPLEMENTED
- exact-account binding after reload/refresh = IMPLEMENTED
- long-lived Instagram token refresh endpoint = IMPLEMENTED
- refresh re-verifies username, professional user_id, and account type = IMPLEMENTED
- refresh endpoint returns no token = IMPLEMENTED
- encryption key derives server-side from existing stable SESSION_SECRET unless an explicit key is supplied
- no encryption key/token/secret stored in GitHub evidence

ISOLATION:
- Existing Render Postgres resources belong to TCC/TTCL and MUST NOT be reused.
- Free Key Value was rejected because Render free Key Value has no persistence.
- A new free Trend Radar Postgres could not be provisioned because the workspace already has the single allowed active free database.
- No cross-project database was touched.

PRODUCTION_PERSISTENCE_GATE:
- A Trend Radar-only persistent datastore is still required.
- Do not set INSTAGRAM_PERSISTENCE_REQUIRED=true until that datastore is connected and verified.
- Re-run owner OAuth after persistence is connected because prior in-memory token state is not durable across deploys.

TRUSTED_DOMAIN_DISCOVERY:
- authoritative DNS provider = Cloudflare
- nameservers = ganz.ns.cloudflare.com / surina.ns.cloudflare.com
- auth.trendradar.com.co currently = NXDOMAIN / not created
- intended target = trendradar-connect.onrender.com
- intended production callback = https://auth.trendradar.com.co/oauth/browser/callback
- Cloudflare record should initially be DNS-only until Render certificate verification succeeds.
- Existing public site / www records must remain unchanged.

PUBLIC_PUBLISHING = HOLD

# Instagram Production / App Review Readiness — 2026-09-24

Project: TrendHunter / Trend Radar
Branch: instagram-production-review-20260924
Governance: ALI-PROGRAMMER-GOVERNANCE-GENERAL-1.5.0 + ALI_PRO
Strict platform isolation: ACTIVE
Public Instagram publication authority: FALSE

## Preserved baseline

Prior governed artifact:
- TrendHunter-M26-Instagram-Login-Provider-Reconciled-20260921.zip
- SHA-256: 833fa71fb0ce41c34d9b83c6eb6db1d390324e14fe70e73c540bf411fc9e26ed

Prior provider adapter capability:
- Reel container creation
- processing status check
- media_publish step
- external provider/OAuth activation remained gated

This branch adds only the isolated web activation/review surface and does not overwrite the preserved M26 artifact.

## Fresh provider reconciliation — 2026-09-24

Chosen model:
**Instagram API with Instagram Login**

Reason:
- supports Instagram Professional Business and Creator accounts;
- does not require a Facebook Page to be linked;
- current publishing permission names are Instagram-business scoped.

Minimal requested scopes:
- instagram_business_basic
- instagram_business_content_publish

Legacy/deprecated pre-2025 business_* scope names are not used.

Graph target:
- graph.instagram.com
- API version default: v26.0

Reels path:
1. OAuth authorization
2. server-side token exchange
3. professional-account identity verification
4. POST /{ig-user-id}/media with media_type=REELS and public HTTPS video_url
5. poll container status until FINISHED
6. POST /{ig-user-id}/media_publish only when the governed public-publish gate is explicitly authorized

## New isolated review service

Directory:
instagram_oauth_service/

Safety default:
INSTAGRAM_PUBLIC_PUBLISH_AUTHORIZED=false

Implemented review routes:
- /
- /health
- /auth/instagram/start
- /auth/instagram/callback
- /share
- /privacy
- /terms
- /deauthorize
- /data-deletion

Security / governance:
- OAuth state validation
- app secret kept server-side
- access token kept server-side
- no token plaintext intentionally returned to browser
- explicit user consent required for a Reel operation
- public publishing fail-closed by default
- temporary media expires from the review service
- Meta signed-request verification for deauthorization/data deletion

## External gates still required

G1 — Exact Instagram Professional account identity
No authoritative Trend Radar Instagram handle/account identity has yet been provider-verified.

G2 — Meta Developer App
Required values:
- Instagram App ID
- Instagram App Secret
- valid OAuth redirect URI

G3 — Instagram tester / role authorization while the Meta app is in development
The exact target Professional account must be authorized for testing.

G4 — Provider OAuth
The owner must complete the real Instagram login/consent flow.

G5 — Provider evidence
After OAuth, verify:
- exact Instagram account ID
- exact username
- account type = BUSINESS or MEDIA_CREATOR / provider-equivalent professional type
- granted scopes include the two requested scopes

G6 — App Review / Advanced Access
Production/public use of the publishing permission remains subject to Meta's applicable review/access requirements.

## Publication gate

Until a separate public-publish authorization exists:
- media container preparation/test may be used where non-public and provider-supported;
- media_publish is forbidden by service default;
- do not claim a successful Instagram public post;
- do not set INSTAGRAM_PUBLIC_PUBLISH_AUTHORIZED=true merely to test connectivity.

## Current decision

INTERNAL_REVIEW_SERVICE = READY
META_APP_CONFIGURATION = REQUIRED
INSTAGRAM_PROVIDER_OAUTH = REQUIRED
PUBLIC_INSTAGRAM_PUBLISHING = HOLD
NEXT_HUMAN_GATE = Meta Developer login/app configuration and exact Instagram Professional account authorization


## Live Meta app creation — 2026-09-24

META_APP_NAME = Trend Radar
META_APP_ID = 1584158563162593
META_APP_CREATED = PASS
META_DEVELOPER_ACCOUNT = trendradarar@gmail.com
USE_CASES = NOT_YET_ADDED
INSTAGRAM_PRODUCT_CONFIGURATION = NEXT


## Meta dashboard progress — 2026-09-24

INSTAGRAM_MANAGE_MESSAGING_CONTENT_USE_CASE = ADDED_IN_META_UI
META_DASHBOARD_ONBOARDING_MODAL = PRESENT
NEXT_PORTAL_ACTION = Close onboarding modal, then inspect required actions for the Instagram use case
PUBLIC_INSTAGRAM_PUBLISHING = HOLD

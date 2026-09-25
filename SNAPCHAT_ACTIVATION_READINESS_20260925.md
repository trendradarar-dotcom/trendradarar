# SNAPCHAT ACTIVATION READINESS — 2026-09-25

PROJECT: Trend Radar / TrendHunter
PLATFORM: Snapchat only
MODE: Fresh / isolated / exact-target-bound / fail-closed

## Fresh live baseline

- Repository: `trendradarar-dotcom/trendradarar`
- Source base: `main`
- Base commit: `2655e2a221540e63a35d49f6ba76bd479cbbb800`
- Snapchat branch: `snapchat-production-review-20260925`
- Cross-platform source branch reuse: NONE
- Public publication side effect: NONE

## Current official Snapchat facts verified 2026-09-25

1. Public Profile API is allowlist-only.
2. OAuth App must be created through Snap Business Manager / Business Dashboard → Business Details; the Snap Kit Developer Portal client ID is not valid for Public Profile API.
3. OAuth scope: `snapchat-profile-api`.
4. OAuth token endpoint: `https://accounts.snapchat.com/login/oauth2/access_token`.
5. Access token lifetime documented as 3600 seconds; refresh-token flow is supported.
6. Public Profile assets can be used to post Spotlight content through the Profile Asset Management API.
7. Spotlight posting flow: create encrypted media container → multipart encrypted upload → POST Spotlight.
8. Spotlight video constraints: MP4, 6–60 seconds, minimum 540×960, description maximum 160 characters.
9. New Spotlight status begins as `SUBMITTED` and is subject to Snapchat approval before `LIVE`; rejected content may become `REJECTED`.

Official evidence:
- https://developers.snap.com/marketing-api/Public-Profile-API/GetStarted
- https://developers.snap.com/marketing-api/Public-Profile-API/ProfileAssetManagement
- https://developers.snap.com/marketing-api/Ads-API/authentication

## Gate state

- Business Account / Organization: NOT YET VERIFIED
- Snapchat account exact binding: NOT YET VERIFIED
- OAuth App client ID: NOT YET CREATED / VERIFIED
- Client secret: NOT PRESENT IN REPOSITORY
- Redirect URI: NOT YET BOUND
- Public Profile API allowlist: NOT YET APPROVED
- Exact Public Profile ID: NOT YET BOUND
- OAuth token exchange: NOT YET EXECUTED
- Read-only profile verification: NOT YET EXECUTED
- Spotlight publication: BLOCKED

## Fail-closed rule

No Spotlight publication is permitted while any external Snapchat gate above is unresolved. The service code must keep `SNAPCHAT_PUBLICATION_ENABLED=false` until allowlist, OAuth, exact profile binding, and owner/publication authorization are all evidenced.

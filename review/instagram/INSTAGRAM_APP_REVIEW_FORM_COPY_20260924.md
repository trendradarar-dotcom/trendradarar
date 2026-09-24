# Meta / Instagram App Review — Prepared Copy — 2026-09-24

## App / service name
Trend Radar

## Use case
Trend Radar is a creator-authorized service that prepares and publishes original short-form videos to an Instagram Professional account. The authorized creator connects the Instagram account through Instagram Login, confirms the connected account, selects an original MP4, reviews the caption, and explicitly requests the Reel operation.

## Instagram API model
Instagram API with Instagram Login.

## Permission: instagram_business_basic
Used to identify the connected Instagram Professional account so the authorized user can confirm the exact account before any content operation.

## Permission: instagram_business_content_publish
Used for the user-initiated Reels publishing workflow:
1. create a Reel media container from the authorized original video;
2. poll the provider container until processing is FINISHED;
3. publish the finished container only after the user-requested publishing action and the service's governed publication gate permit it.

## Data handling
- Instagram App Secret remains server-side.
- Access tokens are handled server-side.
- Token plaintext is not intentionally exposed in browser responses.
- Instagram account data is used only for authorized identity verification and content operations.
- Trend Radar does not sell Instagram user data.
- Deauthorization and data-deletion endpoints are provided.

## Review website endpoints
Website: https://trendradar-instagram-oauth.onrender.com
OAuth redirect: https://trendradar-instagram-oauth.onrender.com/auth/instagram/callback
Privacy: https://trendradar-instagram-oauth.onrender.com/privacy
Terms: https://trendradar-instagram-oauth.onrender.com/terms
Data deletion: https://trendradar-instagram-oauth.onrender.com/data-deletion
Deauthorize callback: https://trendradar-instagram-oauth.onrender.com/deauthorize

## Review evidence still required
- real Meta Developer app configuration;
- real Instagram Professional test account authorization;
- OAuth consent/return recording;
- exact connected account identity;
- successful non-public-safe provider execution evidence;
- any provider-mandated successful publishing call required for Advanced Access/App Review must be separately authorized before a public side effect is performed.

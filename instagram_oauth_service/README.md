# Trend Radar — Instagram OAuth / Reels Review Service

Isolated review/activation service for the TrendHunter / Trend Radar Instagram Reels path.

## API model

Uses **Instagram API with Instagram Login** for Instagram Professional accounts (Business or Creator).

Requested scopes:
- `instagram_business_basic`
- `instagram_business_content_publish`

The older pre-2025 `business_*` scope names are intentionally not used.

## Safety default

`INSTAGRAM_PUBLIC_PUBLISH_AUTHORIZED=false`

With the default safety gate, the service can:
1. authorize the Instagram Professional account;
2. verify the returned account identity;
3. accept an original MP4 from the authorized user;
4. expose it temporarily to Instagram through a public HTTPS URL;
5. create a Reel media container;
6. poll until `FINISHED`;

but it **does not call `media_publish`**.

A real public post requires a separately governed authorization decision.

## Required environment variables

- `INSTAGRAM_APP_ID`
- `INSTAGRAM_APP_SECRET`
- `INSTAGRAM_REDIRECT_URI`

Recommended:
- `PUBLIC_BASE_URL`
- `SESSION_SECRET`
- `INSTAGRAM_API_VERSION=v26.0`

## Review endpoints

- `/`
- `/health`
- `/auth/instagram/start`
- `/auth/instagram/callback`
- `/share`
- `/privacy`
- `/terms`
- `/deauthorize`
- `/data-deletion`

## Isolation

This branch/service does not change the YouTube or TikTok review configurations and does not reuse their credentials.

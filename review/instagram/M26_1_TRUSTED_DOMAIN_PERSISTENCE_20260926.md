# M26.1 — Trusted Domain + Durable Token Persistence

Date: 2026-09-26
Project: Trend Radar / TrendHunter — Instagram only
Isolation: STRICT; no TCC/YouTube/TikTok/Snapchat resources reused

## Trusted OAuth domain

- Custom domain: `auth.trendradar.com.co`
- Render gateway service: `trendradar-connect`
- DNS: CNAME `auth` -> `trendradar-connect.onrender.com`
- Cloudflare mode during verification: DNS only
- Render domain status: VERIFIED
- Render certificate status: CERTIFICATE ISSUED
- Health: `https://auth.trendradar.com.co/health` => configured=true
- OAuth start generates callback:
  `https://auth.trendradar.com.co/oauth/browser/callback`
- Requested scopes remain:
  - instagram_business_basic
  - instagram_business_content_publish
- Public publishing remains fail-closed / false.

## Dedicated durable datastore

- Render Postgres name: `trendradar-instagram-postgres`
- Render resource id: `dpg-das2sqbbc2fs7393j0pg-a`
- Database: `trendradar_instagram_postgres`
- Region: Frankfurt
- PostgreSQL: 18
- Plan: basic_256mb
- Status: AVAILABLE
- External IP allowlist: EMPTY
- External MCP query attempt was correctly blocked by the empty allowlist.
- No TCC database or credentials are reused.

## Token persistence implementation

Existing M26.1 service code supports:
- dedicated `INSTAGRAM_DATABASE_URL`
- Fernet encryption using `INSTAGRAM_TOKEN_ENCRYPTION_KEY`
- `instagram_oauth_tokens` table with ciphertext only
- persistent token reload after process restart
- fail-closed `INSTAGRAM_PERSISTENCE_REQUIRED`
- protected refresh endpoint `/internal/refresh-instagram-token`
- post-refresh identity verification:
  - expected username
  - professional user id
  - BUSINESS or MEDIA_CREATOR account type
- refreshed token persisted only after verification

## Runtime preparation completed

- Dedicated token-encryption key configured server-side.
- Dedicated refresh secret configured server-side.
- No secret values are recorded in this evidence file.
- `INSTAGRAM_PERSISTENCE_REQUIRED` intentionally remains false until the private internal database URL is connected and tested.

## Remaining M26.1 gates

1. Bind the Render Postgres INTERNAL DATABASE URL to `INSTAGRAM_DATABASE_URL`.
2. Confirm `/health`: persistence_configured=true.
3. Re-authorize @trendradarar once so the current long-lived token is persisted.
4. Switch `INSTAGRAM_PERSISTENCE_REQUIRED=true`.
5. Restart service and prove token reload from encrypted Postgres.
6. Execute protected refresh and re-verify exact identity.
7. Close M26.1 only after all above PASS.

PUBLIC_PUBLISH_AUTHORIZED = false
M26.1 = IN PROGRESS

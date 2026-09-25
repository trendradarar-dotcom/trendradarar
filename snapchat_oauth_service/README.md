# Trend Radar — Snapchat Public Profile API Bridge

Isolated Snapchat integration for Trend Radar / TrendHunter.

## Isolation contract

- Branch: `snapchat-production-review-20260925`
- Base: `main` at `2655e2a221540e63a35d49f6ba76bd479cbbb800`
- No TikTok, Instagram, or YouTube credentials, tokens, evidence, callback URLs, or runtime state are reused.
- Public publishing is **closed by default**. `SNAPCHAT_PUBLICATION_ENABLED` must remain `false` until external Snapchat gates and exact profile binding are complete.

## Official integration path

This service targets Snapchat **Public Profile API**, not Creative Kit.

1. Create a Snapchat Business Account / Organization.
2. Create the OAuth App from **Business Dashboard → Business Details**. Do not create the OAuth App in the Snap Kit Developer Portal for this API.
3. Configure the exact redirect URI served by this service.
4. Request Public Profile API allowlisting for the OAuth client ID. Never send the client secret in the allowlist request.
5. Complete OAuth with scope `snapchat-profile-api`.
6. Bind the exact `SNAPCHAT_PUBLIC_PROFILE_ID`.
7. Run read-only verification.
8. Only after approval and owner/publication gates are satisfied may `SNAPCHAT_PUBLICATION_ENABLED=true` be set.

Official docs:
- https://developers.snap.com/marketing-api/Public-Profile-API/GetStarted
- https://developers.snap.com/marketing-api/Public-Profile-API/ProfileAssetManagement
- https://developers.snap.com/marketing-api/Ads-API/authentication

## Environment variables

Required for OAuth:
- `SNAPCHAT_CLIENT_ID`
- `SNAPCHAT_CLIENT_SECRET`
- `SNAPCHAT_REDIRECT_URI`
- `SNAPCHAT_STATE_SECRET`

Required for protected owner endpoints:
- `SNAPCHAT_OWNER_KEY`

Set after exact account/profile binding:
- `SNAPCHAT_PUBLIC_PROFILE_ID`

Optional token bootstrap:
- `SNAPCHAT_REFRESH_TOKEN`
- `SNAPCHAT_ACCESS_TOKEN` (short-lived; not recommended for durable operation)

Publication gate:
- `SNAPCHAT_PUBLICATION_ENABLED=false` (default and required during setup/review)

## Endpoints

- `GET /health` — non-secret configuration health.
- `GET /auth/start` — starts OAuth.
- `GET /auth/callback` — exchanges code; tokens are never returned to the browser.
- `GET /admin/token-status` — protected token metadata/fingerprints only.
- `GET /profiles/<profile_id>` — protected read-only profile check.
- `POST /spotlight/validate` — validates basic request fields without publishing.
- `GET /spotlight/status/<spotlight_id>` — protected read-only status check.
- `POST /spotlight/publish` — protected and additionally blocked unless the publication gate is explicitly opened.

## Spotlight constraints implemented from current official docs

- MP4 video.
- 6–60 seconds.
- Minimum 540×960.
- Description up to 160 characters.
- Media encrypted with AES-256-CBC before upload.
- Multipart upload chunks up to 32 MB.
- Provider upload supports up to 1 GB.

The service validates file type, request size, locale shape, and description length. Duration/resolution probing remains a separate pre-publication media pipeline responsibility.

## Run

```bash
pip install -r snapchat_oauth_service/requirements.txt
gunicorn --chdir snapchat_oauth_service app:app
```

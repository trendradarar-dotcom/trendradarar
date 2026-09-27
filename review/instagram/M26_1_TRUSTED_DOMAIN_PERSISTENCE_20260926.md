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


## Runtime closure evidence — 2026-09-27

- Dedicated internal Postgres URL bound to `INSTAGRAM_DATABASE_URL`.
- `/health` after binding:
  - configured=true
  - persistence_configured=true
  - persistence_required initially false
  - public_publish_authorized=false
- Fresh trusted-domain OAuth completed for @trendradarar through:
  `https://auth.trendradar.com.co/oauth/browser/callback`
- Backend callback returned HTTP 200 only after encrypted persistence succeeded.
- Verified provider identity:
  - username: trendradarar
  - account_type: BUSINESS
  - professional_user_id: 17841428134382903
  - granted permissions: instagram_business_basic, instagram_business_content_publish
- `INSTAGRAM_PERSISTENCE_REQUIRED=true` enabled and service restarted.
- After restart, a fresh browser request to `/share` reconstructed the same account and permissions from durable storage.
- Therefore encrypted durable token reload across process restart = PASS.
- Public publishing remained false throughout.

## Persistence deletion hardening

Commit:
`4bd4531ebc838173004792ac894b81afd60af409`

Verified Meta-signed deauthorization/data-deletion requests now remove the matching encrypted persisted token from PostgreSQL as well as in-memory records, and fail closed with HTTP 503 if durable deletion cannot be completed.

## Refresh verification timing gate

Meta long-lived Instagram tokens cannot be refreshed until they are at least 24 hours old and still unexpired.
The fresh long-lived token was issued during the successful callback at approximately:
`2026-09-26T22:08:55Z`.

Immediate provider refresh is therefore intentionally NOT attempted.

A safe server-side refresh self-test gate was added in commit:
`32d2a171bda31cfeb710149f9fea2013c724bc6d`

It:
- loads only the encrypted persisted token,
- refuses locally when token age < 86400 seconds,
- emits no access token or secret,
- on eligible execution requires provider refresh + exact identity verification + encrypted re-persistence before reporting REFRESHED_VERIFIED.

Current M26.1 status:
- TRUSTED_DOMAIN = PASS
- ENCRYPTED_PERSISTENCE = PASS
- FAIL_CLOSED_PERSISTENCE_REQUIRED = PASS
- RESTART_RELOAD = PASS
- VERIFIED_DELETION_PERSISTENCE = PASS
- REFRESH_FUNCTIONAL_VERIFICATION = PENDING PROVIDER 24H AGE WINDOW
- PUBLIC_PUBLISH = HOLD / false


## Refresh functional verification — PASS — 2026-09-28

Eligible refresh execution was performed after the provider 24-hour age window.

Render deploy:
`dep-daspkfrbc2fs738ap4kg`

Exact safe startup evidence:
```json
{"account_type":"BUSINESS","event":"INSTAGRAM_REFRESH_SELF_TEST","expires_in":5184000,"ok":true,"professional_user_id":"17841428134382903","public_publish_authorized":false,"status":"REFRESHED_VERIFIED","token_age_seconds":88049,"username":"trendradarar"}
```

Therefore:
- long-lived token refresh at provider = PASS
- post-refresh profile verification = PASS
- exact username @trendradarar = PASS
- exact professional user ID 17841428134382903 = PASS
- account type BUSINESS = PASS
- encrypted re-persistence after refresh = PASS
- public publish remained false = PASS

The temporary self-test gate was then returned to:
`INSTAGRAM_REFRESH_SELF_TEST=false`

Final clean restart deploy:
`dep-daspl0m0tbcc738ftkmg`

Final runtime verification after the clean restart:
- configured=true
- persistence_configured=true
- persistence_required=true
- public_publish_authorized=false
- /share reconstructed @trendradarar
- account_type=BUSINESS
- professional_user_id=17841428134382903
- permissions=instagram_business_basic, instagram_business_content_publish

## M26.1 final verdict

- TRUSTED_DOMAIN = PASS
- ENCRYPTED_PERSISTENCE = PASS
- FAIL_CLOSED_PERSISTENCE_REQUIRED = PASS
- RESTART_RELOAD = PASS
- VERIFIED_DELETION_PERSISTENCE = PASS
- REFRESH_FUNCTIONAL_VERIFICATION = PASS
- FINAL_CLEAN_RESTART = PASS
- PUBLIC_PUBLISH = HOLD / false

**M26.1 = PASS**

Next external gate:
Meta Instagram App Review / Advanced Access preparation and submission. Public publishing remains blocked until that gate is separately completed and owner-authorized.

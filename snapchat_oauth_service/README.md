# Trend Radar — Snapchat Direct Public Profile API Bridge

STATUS: DORMANT FIRST-PARTY FALLBACK
SCOPE: Snapchat only

This bridge targets Snapchat Public Profile API directly.

It is NOT the current production publication route because the current official first-party access model requires a Snapchat Business Account / Organization, an OAuth App created in Snapchat Business, and Public Profile API allowlisting.

The owner has frozen these constraints:
- do not invent a legal business entity;
- do not use the unrelated furniture commercial registry;
- do not add a misleading business setup merely to bypass an API gate;
- do not fall back to routine manual posting.

Therefore this bridge is retained for future legitimate first-party access and is closed by default.

## Safe default controls

- SNAPCHAT_DIRECT_API_ENABLED=false
- SNAPCHAT_PUBLICATION_ENABLED=false
- SNAPCHAT_KILL_SWITCH=true
- SNAPCHAT_EMERGENCY_READ_ONLY=true

When SNAPCHAT_DIRECT_API_ENABLED=false:
- OAuth start/callback are blocked;
- token-status and validation routes are blocked;
- external Public Profile reads are blocked;
- Spotlight status reads are blocked;
- Spotlight publication is blocked.

Publication additionally requires:
- SNAPCHAT_PUBLICATION_ENABLED=true
- SNAPCHAT_KILL_SWITCH=false
- SNAPCHAT_EMERGENCY_READ_ONLY=false
- exact profile binding and credentials.

## Official route if legitimately activated later

1. Establish the legitimate Snapchat Business Account / Organization required by the provider.
2. Create the OAuth App from Snapchat Business, not Snap Kit Developer Portal.
3. Configure the exact redirect URI.
4. Obtain Public Profile API allowlisting for the OAuth client.
5. Complete OAuth with scope snapchat-profile-api.
6. Bind the exact owned profile.
7. Perform read-only verification.
8. Complete independent/security acceptance.
9. Open publication controls intentionally.

## Configuration names

Connection:
- SNAPCHAT_CLIENT_ID
- SNAPCHAT_CLIENT_SECRET
- SNAPCHAT_REDIRECT_URI
- SNAPCHAT_STATE_SECRET
- SNAPCHAT_PUBLIC_PROFILE_ID

Protected owner API:
- SNAPCHAT_OWNER_KEY

Optional token bootstrap:
- SNAPCHAT_REFRESH_TOKEN
- SNAPCHAT_ACCESS_TOKEN

Control:
- SNAPCHAT_DIRECT_API_ENABLED
- SNAPCHAT_PUBLICATION_ENABLED
- SNAPCHAT_KILL_SWITCH
- SNAPCHAT_EMERGENCY_READ_ONLY

Credential values must not be committed to the repository.

## Endpoints

Always available:
- GET /health
- GET /

Closed unless direct API is intentionally enabled:
- GET /auth/start
- GET /auth/callback
- GET /profiles/{profile_id}
- GET /spotlight/status/{spotlight_id}
- POST /spotlight/publish

Also closed while the direct API is disabled:
- GET /admin/token-status
- POST /spotlight/validate

## Media mechanics retained for future first-party activation

The bridge retains:
- MP4 request validation;
- description length validation;
- AES-256-CBC media encryption;
- multipart encrypted media upload;
- Spotlight create request;
- provider status query.

The active Trend Radar content-policy gates live in the provider-neutral publisher layer. This direct bridge must not be promoted to production by itself without those gates and a fresh exact-target review.

Official documentation:
- https://developers.snap.com/marketing-api/Public-Profile-API/GetStarted
- https://developers.snap.com/marketing-api/Public-Profile-API/ProfileAssetManagement
- https://developers.snap.com/marketing-api/Ads-API/authentication

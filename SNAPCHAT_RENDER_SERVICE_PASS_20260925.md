# SNAPCHAT RENDER SERVICE PASS — 2026-09-25

PROJECT: Trend Radar / TrendHunter
PLATFORM: Snapchat only
ISOLATION: STRICT
PUBLICATION SIDE EFFECT: NONE

## Exact source

- Repository: `trendradarar-dotcom/trendradarar`
- Branch: `snapchat-production-review-20260925`
- Source commit deployed: `a57f08305786bb7fb7aa419be6a21d63a67553b2`

## Render

- Workspace: `My Workspace` / `tea-dads5hou01pc73c3eksg`
- Service: `trendradar-snapchat-oauth`
- Service ID: `srv-daqvhinavr4c73f6r9sg`
- URL: `https://trendradar-snapchat-oauth.onrender.com`
- OAuth callback: `https://trendradar-snapchat-oauth.onrender.com/auth/callback`
- Runtime: Python
- Region: Frankfurt
- Latest protected-config deploy: `dep-daqvhnfd13js73ctmrvg`
- Deploy state: LIVE

## External health verification

`GET /health` returned `ok=true`.

Non-secret flags verified:
- `owner_key=true`
- `state_secret=true`
- `redirect_uri=true`
- `publication_enabled=false`
- `client_id=false`
- `client_secret=false`
- `profile_id=false`
- `refresh_token=false`

Interpretation:
- Internal bridge deployment = PASS.
- Public publication gate = CLOSED.
- Snapchat OAuth/provider onboarding = NOT YET COMPLETE.

## Snapchat Business external gate

A live browser navigation to `https://business.snapchat.com/` redirected to Snapchat authentication.
No authenticated Snapchat Business session was available.

Human-only gate now required:
- sign in to / create the intended Trend Radar Snapchat account in a persistent browser profile;
- then resume Business Details → OAuth Apps.

No prior project evidence establishes an existing Snapchat username/account/Public Profile.
The intended project brand is Trend Radar and the project email is `trendradarar@gmail.com`, but account creation/binding remains an external gate.

## Next exact provider steps after authentication

1. Business Dashboard → Business Details.
2. Create/verify OAuth App `Trend Radar Snapchat API`.
3. Redirect URI must exactly equal:
   `https://trendradar-snapchat-oauth.onrender.com/auth/callback`
4. Record Client ID and secret only in Render secrets; never commit them.
5. Request Public Profile API allowlisting for the Client ID.
6. Complete OAuth scope `snapchat-profile-api`.
7. Bind exact Public Profile ID.
8. Perform read-only profile verification.
9. Keep `SNAPCHAT_PUBLICATION_ENABLED=false` until all gates and publication authorization are satisfied.


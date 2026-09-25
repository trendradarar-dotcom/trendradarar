# SNAPCHAT ACTIVATION READINESS — 2026-09-25

PROJECT: Trend Radar / TrendHunter
ENGINE: صياد الترند / TrendHunter
PLATFORM: Snapchat only
MODE: Fresh / isolated / exact-target-bound / fail-closed
GOVERNANCE: SNAPCHAT_AUTOMATION_ARCHITECTURE_GOVERNANCE_20260925.md

## Frozen intent

Snapchat is a fully automated TrendHunter distribution channel.

Runtime:
Trend discovery -> country routing -> local/legal filter -> original content production -> Snapchat-native visual board -> automated Spotlight publication -> performance feedback.

Public framing:
- Trend Radar / رادار الترند
- «اكتشف ما يصعد الآن في بلدك والعالم»
- country lane: «هذا ما يصعد الآن في بلدك»
- separate selected-global-trend lane

Business objective:
- account growth;
- eventual lawful monetization;
- zero routine human publication actions.

## Repository / isolation

- Repository: `trendradarar-dotcom/trendradarar`
- Snapchat branch: `snapchat-production-review-20260925`
- Cross-project/platform source-state reuse: NONE
- YouTube / TikTok / Instagram integrations are not imported into this Snapchat implementation.

## Snapchat account state

- Intended username: `trendradarar`
- Public brand: `Trend Radar`
- Public Profile: CREATED
- Snapchat Business Account / unrelated commercial registry: NOT REQUIRED BY DEFAULT ARCHITECTURE
- Direct Snapchat Business OAuth path: DEFERRED FALLBACK ONLY

## Geographic routing

Arab-country lanes:
DZ, BH, KM, DJ, EG, IQ, JO, KW, LB, LY, MR, MA, OM, PS, QA, SA, SO, SD, SY, TN, AE, YE.

Separate lane:
- `GLOBAL_SELECTED`

Saudi Arabia:
- initial operating market;
- dedicated Saudi filter is mandatory before publication.

## Primary automated publisher

Selected provider: `AYRSHARE`

Reason:
- API-first publishing path;
- documented direct Snapchat Spotlight support;
- account authorization is delegated through provider linking;
- normal publication can be fully programmatic after one-time account connection.

The prior Sprout Social idea is NOT the selected API runtime because its public Publishing API documentation does not currently list Snapchat as a supported create-post profile type, even though the Sprout UI can schedule/publish Snapchat.

## Implemented code

New service:
- `snapchat_publisher_service/publisher.py`
- `snapchat_publisher_service/app.py`
- `snapchat_publisher_service/requirements.txt`
- `snapchat_publisher_service/test_publisher.py`

Implemented gates:
- explicit Arab-country or `GLOBAL_SELECTED` market;
- Arabic activation;
- Saudi filter required for SA;
- explicit global-selection flag for GLOBAL_SELECTED;
- originality PASS;
- rights PASS;
- HTTPS media URL;
- monetization-oriented internal duration target 30-60 seconds;
- minimum 540x960;
- 9:16 target;
- Spotlight description <=160 characters;
- publication environment gate default CLOSED;
- provider key absent => publication BLOCKED.

## Render deployment

Service:
- `trendradar-snapchat-publisher`
- Service ID: `srv-dar6s0vavr4c7380epmg`
- URL: `https://trendradar-snapchat-publisher.onrender.com`
- Region: Frankfurt
- Branch: `snapchat-production-review-20260925`
- Runtime: Python
- Start command: `gunicorn --chdir snapchat_publisher_service app:app`
- Deploy: `dep-dar6s3ekjc1c73b5uc90`
- Deploy state: LIVE

External health verification:
- `ok=true`
- version=`snapchat-publisher-service-20260925.1`
- provider=`ayrshare`
- `api_key_configured=false`
- `publication_enabled=false`
- `supported_runtime_human_actions=0`
- all 22 Arab-country market codes + `GLOBAL_SELECTED` exposed in readiness.

## Provider setup state

Ayrshare:
- existing account for `trendradarar@gmail.com`: NOT FOUND
- signup route: AVAILABLE
- no account was created automatically because account creation / provider terms / any trial or financial commitment are owner-only setup gates.
- no card or paid subscription was started.
- no API key exists yet.
- no Snapchat account has been linked to Ayrshare yet.

## Direct Snapchat Public Profile API fallback

Existing service remains:
- `snapchat_oauth_service`

It is now a contingency path only.
It remains fail-closed and MUST NOT force use of an unrelated legal business registry.

## Publication state

PUBLIC SPOTLIGHT PUBLICATION = BLOCKED.

Reason:
1. Ayrshare account not yet created/authorized.
2. Snapchat Public Profile not yet linked to provider.
3. Ayrshare API key not yet configured.
4. exact provider-side binding to `trendradarar` not yet verified.
5. production publication gate remains `false`.

No random or live test post has been sent.

## Next external-only gate

One-time provider onboarding is the only remaining external blocker:
- create/sign in to Ayrshare;
- connect Snapchat Public/Professional Profile;
- authorize access;
- obtain API key into Render secret configuration.

After that, TrendHunter publication is designed to run with 0 routine human actions.

No commercial registry, furniture-business identity, or Snapchat Business Account is part of the default path.

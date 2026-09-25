# SNAPCHAT AUTOMATION ARCHITECTURE GOVERNANCE — 2026-09-25

PROJECT: Trend Radar / TrendHunter
ENGINE: صياد الترند / TrendHunter
PLATFORM SCOPE: Snapchat only
STATUS: ACTIVE / AUTHORITATIVE FOR SNAPCHAT IMPLEMENTATION
ISOLATION: STRICT — no source-state import from YouTube, TikTok, Instagram, Tanoub Travel, TCC, or any other project
NORMAL-RUNTIME HUMAN ACTIONS: 0
PUBLICATION DEFAULT: FAIL-CLOSED

## 1. Product intent

Snapchat is a fully automated distribution channel for TrendHunter.

The runtime objective is:

Trend discovery -> country routing -> local/legal filter -> original content production -> Snapchat-specific visual packaging -> automated Spotlight publication -> performance feedback -> TrendHunter ranking feedback.

The public editorial framing is:
- Brand: Trend Radar / رادار الترند
- Master slogan: «اكتشف ما يصعد الآن في بلدك والعالم»
- Country framing: «هذا ما يصعد الآن في بلدك» / equivalent country-specific wording
- Global lane: selected global trend, clearly separated from local country lanes

The business objective is account growth and eventual lawful monetization. Automation must optimize for durable growth and platform eligibility, not volume-at-any-cost.

## 2. Geographic model

Arab-country lanes are first-class routing targets. The canonical country codes are:

DZ, BH, KM, DJ, EG, IQ, JO, KW, LB, LY, MR, MA, OM, PS, QA, SA, SO, SD, SY, TN, AE, YE.

A separate target exists:
- GLOBAL_SELECTED

Rules:
- A local item must be routed to an explicit country.
- GLOBAL_SELECTED is not a fallback for unclassified content; it requires an explicit global-selection decision.
- Saudi Arabia (SA) is the initial operating market and must pass the dedicated Saudi filter before publication.
- The visual board/layout remains country-aware and platform-specific. Snapchat output must not reuse another platform's UI layout blindly.

## 3. Human-action rule

Routine publishing must require no human action.

Permitted human-only gates are limited to one-time or exceptional provider actions that cannot legally/technically be automated, such as:
- sign-in / CAPTCHA / 2FA;
- explicit account authorization/consent to connect Snapchat to an approved publishing provider;
- paid-plan purchase or other financial commitment;
- acceptance of new legal terms when the provider requires the account owner personally.

These are setup/exception gates, not normal runtime steps.

## 4. Snapchat account binding

Current intended account:
- username: trendradarar
- public brand: Trend Radar
- account role: owned Trend Radar Snapchat channel

The account has a Public Profile. A provider may require conversion of that Public Profile to a Professional Profile through Snapchat account settings. This does NOT authorize inventing or misrepresenting a legal business entity.

## 5. Publishing architecture

### Primary path — provider-managed official Snapchat integration

The preferred runtime path is an API-first publishing provider that:
1. publishes through Snapchat's supported/official integration path;
2. can publish Spotlight programmatically;
3. exposes an API callable by TrendHunter;
4. does not require manual scheduling for each post;
5. keeps provider credentials outside the repository.

Current selected provider: AYRSHARE.

Reason:
- Ayrshare documents direct Snapchat Spotlight publishing through its REST Post API.
- Snapchat account authorization is delegated through the provider's linking flow.
- TrendHunter can then publish with API calls; no per-post UI action is required.

### Deferred fallback — direct Snapchat Public Profile API

The existing `snapchat_oauth_service` remains a dormant fallback/contingency path.

It MUST NOT force the project into a Business Account / legal-business setup merely to keep development moving.
It remains fail-closed and publication-disabled unless the owner later explicitly chooses that direct-provider path.

## 6. Provider abstraction

TrendHunter must not hard-code its business logic to Ayrshare.

Required internal interface:
- validate(envelope)
- publish_spotlight(envelope)
- schedule_spotlight(envelope, schedule_time)
- read provider result/status where available

Provider selection must be environment-controlled.

Canonical provider environment:
- `SNAPCHAT_PUBLISH_PROVIDER=ayrshare`
- `AYRSHARE_API_KEY` = secret only
- `SNAPCHAT_PUBLICATION_ENABLED=false` by default

No provider key, OAuth token, password, refresh token, or secret may be committed to Git.

## 7. Content envelope

Every Snapchat publication request must carry at minimum:
- `market`: one Arab-country code or `GLOBAL_SELECTED`
- `language`: Arabic for current activation
- `headline`
- `description`
- `media_url`
- `duration_seconds`
- `width`
- `height`
- `originality_passed`
- `rights_passed`
- `saudi_filter_passed` when market=SA
- `global_selected` when market=GLOBAL_SELECTED
- `trend_id` or equivalent internal provenance key

No unresolved envelope may be published.

## 8. Snapchat media policy gate

For the monetization-oriented Snapchat lane, use the stricter internal production target:
- format: MP4
- portrait: 9:16 target
- target resolution: 1080x1920
- minimum operational resolution: 540x960
- target duration: 30-60 seconds
- Spotlight text/description: <=160 characters

The 30-second minimum is an internal monetization-oriented production rule; it is intentionally stricter than the provider's technical acceptance range.

## 9. Saudi filter

For market=SA:
- publication is blocked unless `saudi_filter_passed=true`;
- legal/safety/cultural review logic is applied before the publisher adapter;
- provider integration must not bypass the Saudi gate;
- provider success does not imply content-policy approval.

## 10. Originality and rights

TrendHunter must not copy third-party content.

Publication requires:
- original production or lawfully usable source material;
- transformation sufficient for original editorial value;
- provenance recorded internally;
- rights gate PASS.

AI may assist discovery, scripting, editing, localization, packaging, and production, but the system must preserve platform eligibility and authenticity requirements. The objective is recommendation-eligible, advertiser-friendly content, not merely technically publishable media.

## 11. Visual-board preservation

The previously established visual concept is preserved:
- country-specific Arabic trend boards/identity;
- one coherent Snapchat-native visual package;
- selected global-trend lane;
- no cross-platform UI mixing;
- public viewers see the trend; internal commercial opportunity/scoring data remains private.

## 12. Publication gates

Public Spotlight publication remains BLOCKED until all are true:
1. Snapchat Public/Professional Profile is linked to the selected provider.
2. Provider API credential is stored only in secret configuration.
3. Read-only/provider account validation passes.
4. A no-side-effect validation request passes.
5. Exact account binding is confirmed as trendradarar / Trend Radar.
6. Owner publication authorization for production mode is present.
7. `SNAPCHAT_PUBLICATION_ENABLED=true` is intentionally set.

No random live test post is permitted.

## 13. Cost rule

No paid subscription, credit-card entry, recurring commitment, or plan upgrade may be executed automatically.

Engineering may proceed through code, deployment, validation, and no-card trial/readiness states. A financial commitment remains an owner-only action.

## 14. Current implementation direction

Immediate implementation sequence:
1. preserve direct OAuth bridge as dormant fallback;
2. add provider-neutral Snapchat publisher adapter;
3. implement Ayrshare Spotlight adapter;
4. enforce country/global/SA/originality/rights gates in code;
5. keep live publication disabled;
6. deploy/validate without external publication;
7. complete one-time Snapchat-provider account authorization when the provider presents it;
8. run exact-account read-only verification;
9. only then open the production publication gate.

This document supersedes any prior assumption that a Snapchat Business Account or unrelated commercial registry must be used as the default route for Trend Radar Snapchat automation.

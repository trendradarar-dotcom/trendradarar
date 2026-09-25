# SNAPCHAT AUTOMATION ARCHITECTURE GOVERNANCE — 2026-09-25

PROJECT: Trend Radar / TrendHunter
ENGINE: صياد الترند / TrendHunter
PLATFORM SCOPE: Snapchat only
STATUS: ACTIVE / AUTHORITATIVE FOR SNAPCHAT IMPLEMENTATION
REVISION: 1.1 — post independent assurance review
ISOLATION: STRICT — no source-state import from YouTube, TikTok, Instagram, Tanoub Travel, TCC, or any other project
NORMAL-RUNTIME HUMAN ACTIONS: 0
PUBLICATION DEFAULT: FAIL-CLOSED

## 1. Product intent

Snapchat is a fully automated distribution channel for TrendHunter.

Runtime objective:
Trend discovery -> country routing -> local/legal filter -> original/authentic content production -> Snapchat-specific visual packaging -> provider validation -> automated Spotlight publication -> provider/platform status reconciliation -> performance feedback -> TrendHunter ranking feedback.

Public editorial framing:
- Brand: Trend Radar / رادار الترند
- Master slogan: «اكتشف ما يصعد الآن في بلدك والعالم»
- Country framing: «هذا ما يصعد الآن في بلدك» / equivalent country-specific wording
- Global lane: selected global trend, clearly separated from local country lanes

Business objective:
- durable account growth;
- eventual lawful monetization;
- no routine human publication actions.

## 2. Geographic model

Canonical Arab-country lanes:
DZ, BH, KM, DJ, EG, IQ, JO, KW, LB, LY, MR, MA, OM, PS, QA, SA, SO, SD, SY, TN, AE, YE.

Separate lane:
- GLOBAL_SELECTED

Rules:
- A local item must be routed to an explicit country.
- GLOBAL_SELECTED requires an explicit global-selection decision.
- Saudi Arabia (SA) is the initial operating market and must pass the dedicated Saudi filter before publication.
- Snapchat uses a Snapchat-native visual package; another platform's UI is not copied blindly.

## 3. Human-action rule

Routine publishing must require zero human action.

Permitted human-only gates are limited to one-time or exceptional provider actions that cannot legally/technically be automated:
- sign-in / CAPTCHA / 2FA;
- explicit account authorization/consent;
- switching the existing Snapchat Public Profile to the Professional Profile mode required by the selected provider;
- paid-plan purchase or other financial commitment;
- acceptance of new legal terms where the provider requires the owner personally.

These are setup/exception gates, not normal runtime steps.

## 4. Snapchat account binding

Current intended account:
- username: trendradarar
- public brand: Trend Radar
- role: owned Trend Radar Snapchat channel
- Public Profile: created

For the selected Ayrshare route, the existing Public Profile MUST be switched to a Professional Profile before linking, according to Ayrshare's current Snapchat linking requirements.

Professional Profile conversion does NOT authorize:
- inventing a business identity;
- using the unrelated furniture commercial registry;
- creating a separate Snapchat Business Account unless independently required later and explicitly approved.

## 5. Publishing architecture

### Primary path — provider-managed official integration

The preferred runtime path is an API-first provider that:
1. publishes through a supported Snapchat integration;
2. publishes Spotlight programmatically;
3. exposes API access to TrendHunter;
4. requires no per-post human scheduling;
5. supports provider-side validation without publication;
6. provides status/history sufficient to reconcile the publication result;
7. keeps secrets outside Git.

Current selected provider: AYRSHARE.

Current evidence:
- Snapchat account linking is documented by Ayrshare.
- Spotlight publishing is documented through the POST /post API using snapchat + spotlight options.
- provider-side no-publication validation is available through POST /validate/post.
- published/scheduled post state can be read by provider post ID.

### Deferred fallback — direct Snapchat Public Profile API

The existing `snapchat_oauth_service` remains a dormant contingency path.

It MUST NOT force the project into a Snapchat Business Account or unrelated legal-business setup merely to keep development moving.
It remains fail-closed and publication-disabled unless the owner later explicitly selects that route.

## 6. Provider abstraction

TrendHunter business logic must not depend directly on Ayrshare.

Required internal interface:
- validate(envelope)
- publish_spotlight(envelope)
- schedule_spotlight(envelope, schedule_time)
- get_post_status(provider_post_id)
- reconcile_result(publication_id, provider_result)

Canonical provider environment:
- `SNAPCHAT_PUBLISH_PROVIDER=ayrshare`
- `AYRSHARE_API_KEY` = secret only
- `SNAPCHAT_PUBLICATION_ENABLED=false` by default

No provider key, OAuth token, password, refresh token, profile key, or secret may be committed to Git.

## 7. Content envelope

Every Snapchat publication request must carry at minimum:
- `publication_id`: stable unique publication identity reused across retries
- `market`: one Arab-country code or `GLOBAL_SELECTED`
- `language`: Arabic for current activation
- `headline`
- `description`
- `media_url`
- `duration_seconds`
- `width`
- `height`
- `visual_template_id`
- `originality_passed`
- `rights_passed`
- `human_origin_passed`
- `saudi_filter_passed` when market=SA
- `global_selected` when market=GLOBAL_SELECTED
- `trend_id`

Only native JSON boolean true may satisfy a PASS gate. Strings such as "true"/"false", numbers and null must not satisfy a gate.

No unresolved envelope may be published.

## 8. Snapchat media / recommendation gate

Internal production target:
- MP4
- portrait 9:16
- target resolution 1080x1920
- minimum operational resolution 540x960
- duration 30-60 seconds
- Spotlight description <=160 characters

The 30-second minimum is intentionally stricter than the technical minimum because Spotlight videos must currently be at least 30 seconds to be eligible for revenue in Snapchat's monetization program.

As of July 2026, wholly AI-generated videos are not eligible for Spotlight recommendation. Therefore:
- the growth/monetization lane requires `human_origin_passed=true`;
- AI may automate discovery, scripting, editing, localization, packaging, captions and production around original/human-origin or lawfully usable material;
- a wholly AI-generated video must be blocked from this lane.

## 9. Saudi filter

For market=SA:
- publication is blocked unless `saudi_filter_passed=true`;
- legal/safety/cultural review logic runs before the publisher adapter;
- provider integration cannot bypass the Saudi gate;
- provider/API success never substitutes for the Saudi content gate.

## 10. Originality and rights

TrendHunter must not copy third-party content.

Publication requires:
- original production or lawfully usable source material;
- original editorial value;
- internal provenance;
- rights PASS;
- human-origin/authenticity PASS for the Snapchat growth lane.

## 11. Visual-board preservation

The established visual concept remains authoritative:
- country-specific Arabic trend boards/identity;
- one coherent Snapchat-native visual package;
- selected global-trend lane;
- no cross-platform UI mixing;
- public viewers see the trend while internal commercial opportunity/scoring data remains private.

The content factory must emit a valid `visual_template_id`; the publisher rejects a missing template identity.

## 12. Duplicate / retry safety

Every publication has a stable `publication_id`.

The provider payload must use a deterministic Ayrshare `idempotencyKey` derived from that publication identity.

The adapter must also serialize simultaneous submissions of the same publication identity because provider documentation warns that concurrent duplicate requests may escape provider-side idempotency detection.

A retry must reuse the same publication identity and must first reconcile whether the prior request already published.

## 13. Provider validation and result reconciliation

Before production publish:
1. local TrendHunter envelope validation passes;
2. Ayrshare POST /validate/post passes with no external publication side effect;
3. exact Snapchat account binding is confirmed;
4. publication gate is enabled.

After publish/schedule:
- store provider post ID against `publication_id`;
- read provider status by post ID until final state as applicable;
- scheduled publishing should use provider status/webhook capability when available;
- provider acceptance is not assumed to equal final platform success.

## 14. Publication gates

Public Spotlight publication remains BLOCKED until all are true:
1. existing Snapchat Public Profile is switched to Professional Profile.
2. Professional Profile is linked to the selected provider.
3. exact account binding is confirmed as trendradarar / Trend Radar.
4. provider API credential is stored only in secret configuration.
5. read-only/provider account verification passes.
6. local envelope validation passes.
7. provider no-side-effect validation passes.
8. exact-target automated tests pass.
9. owner publication authorization for production mode is present.
10. `SNAPCHAT_PUBLICATION_ENABLED=true` is intentionally set.

No random live test post is permitted.

## 15. Monetization reality

Technical publishing does not itself create monetization eligibility.

Current Snapchat program conditions include additional audience/compliance conditions such as:
- original advertiser-friendly content;
- eligible-country residence;
- Snap Star status;
- at least 50,000 followers;
- 15,000 view-hours over the prior 28 days, including at least 3,000 hours from Spotlight.

Saudi Arabia is currently listed as payout-eligible.

These conditions are growth/operations metrics and must be monitored separately from publishing health.

## 16. Cost rule

No paid subscription, card entry, recurring commitment or plan upgrade may be executed automatically.

Current selected provider has a material recurring production cost under its current public pricing. Engineering and trial/readiness work may continue, but any paid commitment is owner-only.

Provider economics remain a valid future reason to switch to the dormant direct Snapchat API route; the provider adapter must remain replaceable.

## 17. Current implementation direction

Immediate implementation sequence:
1. preserve direct OAuth bridge as dormant fallback;
2. keep provider-neutral publisher adapter;
3. harden Ayrshare adapter with strict booleans, authenticity/template gates, idempotency, provider validation and status reads;
4. keep public publication disabled;
5. prove exact-target tests/runtime health;
6. later complete one-time Professional Profile/provider authorization;
7. run exact-account read-only verification;
8. run provider-side no-publication validation;
9. only then open the production publication gate.

This document supersedes any prior assumption that a Snapchat Business Account or unrelated commercial registry is the default route for Trend Radar Snapchat automation.

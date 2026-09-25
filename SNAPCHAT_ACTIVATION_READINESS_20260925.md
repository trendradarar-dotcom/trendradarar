# SNAPCHAT ACTIVATION READINESS — 2026-09-25

PROJECT: Trend Radar / TrendHunter
ENGINE: صياد الترند / TrendHunter
PLATFORM: Snapchat only
MODE: Fresh / isolated / exact-target-bound / fail-closed
GOVERNANCE: SNAPCHAT_AUTOMATION_ARCHITECTURE_GOVERNANCE_20260925.md revision 1.1
ASSURANCE: SNAPCHAT_ARCHITECTURE_ASSURANCE_REVIEW_20260925.md
PUBLICATION STATE: BLOCKED

## Frozen product intent

TrendHunter -> country routing -> local/legal filter -> original/authentic content production -> Snapchat-native country/global visual board -> provider validation -> automated Spotlight publication -> result reconciliation -> performance feedback.

Public framing:
- Trend Radar / رادار الترند
- «اكتشف ما يصعد الآن في بلدك والعالم»
- country lane: «هذا ما يصعد الآن في بلدك»
- separate GLOBAL_SELECTED lane

Business objective:
- grow the account;
- reach lawful monetization eligibility;
- zero routine human publication actions.

## Repository / isolation

- Repository: trendradarar-dotcom/trendradarar
- Branch: snapchat-production-review-20260925
- Cross-project/platform source-state reuse: NONE
- Direct Snapchat OAuth service retained only as dormant fallback.

## Snapchat account

- username: trendradarar
- public brand: Trend Radar
- Public Profile: CREATED
- Professional Profile: REQUIRED FOR AYRSHARE LINK / NOT YET VERIFIED
- unrelated furniture commercial registry: NOT PART OF DEFAULT ARCHITECTURE
- Snapchat Business Account: NOT PART OF DEFAULT ARCHITECTURE

## Geographic model

Arab-country lanes:
DZ, BH, KM, DJ, EG, IQ, JO, KW, LB, LY, MR, MA, OM, PS, QA, SA, SO, SD, SY, TN, AE, YE.

Separate lane:
- GLOBAL_SELECTED

Saudi lane:
- initial operating market
- dedicated Saudi gate required before publication

## Primary provider architecture

Selected provider for current implementation: AYRSHARE.

Verified current provider capabilities:
- Snapchat Public/Professional Profile linking
- direct Spotlight publication through POST /post
- no-side-effect provider validation through POST /validate/post
- post status read by provider post ID
- provider idempotencyKey support

Provider economics:
- current public Premium price: $149/month for one social profile
- current Launch trial: 28 days, no card required
- any paid commitment remains owner-only

## Independent assurance review

Review mode:
Fresh Independent + Discovery + Directed + Creative/Adversarial + Verification.

Review commit:
- 6cb3af96edb6d54933e0c53d196b3b8779e18298

Findings discovered:
- F1 Professional Profile requirement
- F2 missing provider-side validation
- F3 missing duplicate/idempotency controls
- F4 missing provider status feedback implementation
- F5 unsafe Python bool coercion
- F6 Snapchat 2026 human-origin/authenticity requirement not executable
- F7 tests committed but no execution evidence
- F8 provider cost is a material business dependency
- F9 visual-board contract not machine-verified
- F10 monetization has additional audience/compliance conditions

## Remediation implemented

Publisher hardening commit:
- 7cf202902b2651db180aad52f1d33c03c0127dde

Implemented:
- strict native-JSON boolean PASS semantics
- stable publication_id
- deterministic Ayrshare idempotencyKey
- process serialization for same publication_id
- explicit human_origin_passed gate
- explicit visual_template_id gate
- provider POST /validate/post support
- provider GET /post/{id} status support

API wiring commit:
- 8ccee27c0e5d678c66de21cb4f300c5b6b126fdf

Implemented:
- local + provider validation path
- read-only provider status endpoint
- publication remains fail-closed

Expanded tests commit:
- 3bc01f001cef31d6359d5bf89d8eb912cad9fedc

Governance reconciliation commit:
- f693486ed71fbf0151b7f65521bebbee072e8d50

## Render

Service:
- trendradar-snapchat-publisher
- ID: srv-dar6s0vavr4c7380epmg
- URL: https://trendradar-snapchat-publisher.onrender.com
- region: Frankfurt
- branch: snapchat-production-review-20260925

Latest hardened deploy requested:
- dep-dar7dih42hec73d99o8g
- target commit: f693486ed71fbf0151b7f65521bebbee072e8d50
- current observed state at this readiness update: UPDATE_IN_PROGRESS

Previous live service remains fail-closed:
- AYRSHARE_API_KEY not configured
- SNAPCHAT_PUBLICATION_ENABLED=false

## Remaining assurance gates

HOLD remains in force until:
1. hardened deploy reaches LIVE;
2. exact-target automated tests have executed with PASS evidence;
3. existing Snapchat Public Profile is switched to Professional Profile;
4. provider account is created/authorized without invented legal identity;
5. exact trendradarar account binding is verified;
6. API key is stored only as a Render secret;
7. provider /validate/post passes with no publication;
8. exact-account read-only verification passes;
9. production publication is explicitly authorized;
10. SNAPCHAT_PUBLICATION_ENABLED is intentionally changed to true.

No live/random Snapchat post has been sent.

## Growth / monetization constraints

Current Snapchat first-party rules include:
- wholly AI-generated videos are not eligible for Spotlight recommendation;
- revenue-eligible Spotlight videos must be at least 30 seconds;
- current program eligibility also includes original advertiser-friendly content, eligible-country residence, Snap Star status, 50,000 followers, and 15,000 view-hours in 28 days including 3,000 Spotlight hours;
- Saudi Arabia is currently payout-eligible.

Therefore the automation target is not merely technically publishable content. It is recommendation-oriented, authentic, rights-safe, country-aware content designed for sustainable growth.

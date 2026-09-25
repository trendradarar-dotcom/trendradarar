# SNAPCHAT AUTOMATION GOVERNANCE V2 — 2026-09-25

PROJECT = Trend Radar / TrendHunter
SCOPE = Snapchat only
STATUS = ACTIVE / SUPERSEDES PRIOR SNAPCHAT ROUTING ASSUMPTIONS
NORMAL_RUNTIME_HUMAN_ACTIONS_TARGET = 0
RARE_EXTERNAL_EXCEPTION_ACTIONS = allowed only when Snapchat or another external service requires the owner personally
PUBLICATION_DEFAULT = FAIL_CLOSED

## Frozen owner model

Accepted requirement:

"Build it, leave it running, and disturb the owner only for a rare external exception that the system cannot legally or technically resolve by itself."

Routine work must not require the owner to:
- select trends;
- create ordinary content;
- upload ordinary content;
- schedule posts;
- watch routine health.

Rare external exceptions may include login, 2FA/CAPTCHA, OAuth re-consent, new external legal terms, or an explicit financial commitment.

## Product flow

Trend discovery
-> Arab-country or GLOBAL_SELECTED routing
-> local and Saudi gates
-> authentic/original content production
-> Snapchat-native visual board
-> publication preflight
-> autonomous Spotlight publication when a compliant route exists
-> provider/platform reconciliation
-> performance feedback.

Public identity:
- Trend Radar / رادار الترند
- «اكتشف ما يصعد الآن في بلدك والعالم»
- local framing: «هذا ما يصعد الآن في بلدك»
- global framing: «ترند عالمي»

## Markets

Canonical Arab-country lanes:
DZ الجزائر; BH البحرين; KM جزر القمر; DJ جيبوتي; EG مصر; IQ العراق; JO الأردن; KW الكويت; LB لبنان; LY ليبيا; MR موريتانيا; MA المغرب; OM عُمان; PS فلسطين; QA قطر; SA السعودية; SO الصومال; SD السودان; SY سوريا; TN تونس; AE الإمارات; YE اليمن.

Separate lane:
GLOBAL_SELECTED = ترند عالمي.

Saudi Arabia requires its dedicated Saudi gate before publication.

## Account

Owned Snapchat target:
- username: trendradarar
- brand: Trend Radar
- Public Profile: created

Forbidden:
- inventing a legal entity;
- using the unrelated furniture commercial registry;
- creating a misleading business identity merely to bypass an API gate.

## Current publication-route decision

Direct Snapchat Public Profile API:
- technically preferred for independence;
- current first-party setup requires Snapchat Business Account/Organization, OAuth App, and Public Profile API allowlisting;
- under the frozen owner constraint, this path is externally blocked for the current account setup;
- the direct bridge remains a dormant fail-closed contingency.

Ayrshare:
- programmatic Spotlight integration exists;
- it adds a recurring paid production dependency;
- owner decision: no new paid publisher merely to solve Snapchat;
- status: evaluated, not selected, dormant adapter only.

Creative Kit and profile web uploader:
- require the user to complete the posting flow;
- status: rejected for normal runtime because routine human publication actions must be zero.

Therefore current production setting is:
SNAPCHAT_PUBLISH_PROVIDER = disabled

This is deliberate. Public automation remains closed until a route is both supported and compatible with the frozen constraints.

## Visual contract

Local Arab-country template:
snap-country-board-v1

Global template:
snap-global-board-v1

Every publication request must carry:
- publication_id
- trend_id
- market
- market_label
- language
- headline
- description
- media_url
- duration_seconds
- width
- height
- visual_template_id
- originality_passed
- rights_passed
- human_origin_passed
- content_origin_type
- saudi_filter_passed for SA
- global_selected for GLOBAL_SELECTED

Only native JSON true can satisfy a PASS gate.

Exact country labels and template identity are mandatory.

## Media / authenticity

Internal Snapchat production target:
- MP4
- 9:16 portrait
- 1080x1920 target
- 540x960 minimum operational resolution
- 30–60 seconds
- description <=160 characters

Allowed growth-lane origin:
- human_original
- human_source_ai_assisted

Blocked from growth/recommendation lane:
- wholly_ai_generated

AI may automate analysis, scripting, localization, editing, packaging and production assistance around legitimate human-origin/original material.

## Saudi gate

For market=SA:
- saudi_filter_passed must be native true;
- missing/uncertain evidence blocks publication;
- a publishing provider cannot bypass the Saudi gate.

## Retry / duplicate / unknown state

Every intended post has a stable publication_id.

Provider idempotency is used where supported.

In-process duplicate requests are serialized.

Production acceptance additionally requires durable reconciliation because process memory is not a durable publication ledger.

UNKNOWN != SUCCESS.

No blind automatic retry is allowed after an unknown external side effect without reconciliation.

## Control plane

Default state:
- provider = disabled
- publication_enabled = false
- kill_switch = true
- emergency_read_only = true

Current external publication blast radius under the frozen configuration:
0

The kill switch and emergency read-only controls are independent of trend-selection logic.

## Auditability

Publisher service must emit structured UTC audit events with correlation IDs and without credential values.

External alert delivery, retention, and incident escalation are separate acceptance items and cannot be inferred merely from having logs.

## Recovery and maintainability

The Snapchat subsystem must remain recoverable without the original chat or original AI model.

Required recovery assets:
- repository, branch and exact commit;
- build/start instructions;
- dependency inventory;
- configuration-variable names without values;
- service inventory;
- external-account ownership inventory;
- recovery runbook;
- credential rotation/revocation procedure;
- known-good candidate baseline;
- independent evidence before declaring a GOLDEN RELEASE.

## Verification rule

AI-generated or AI-modified code is untrusted until verified.

Producer-written tests and producer-written reviews are useful engineering evidence, but they are not independent verification.

Therefore:
- internal CI can prove an implementation regression check;
- it cannot by itself establish independent code review, penetration test, ASVS L3, recovery proof, or cold-engineer handover.

Those remain NOT VERIFIED until actually performed independently.

## Financial scope

The Snapchat publisher performs no user financial transaction.

Financial transaction logic = NOT APPLICABLE.

Automatic subscription purchase, paid promotion, or provider upgrade is outside runtime authority.

## Production opening gate

Autonomous public Spotlight may open only after:
1. a supported zero-routine-human publication route exists;
2. exact target account is verified as trendradarar / Trend Radar;
3. no misleading business identity is used;
4. credentials are secret-managed;
5. local validation passes;
6. external preflight passes where available;
7. durable duplicate/reconciliation control is operational;
8. kill switch and emergency read-only are tested;
9. alerts for blocked/failed/unknown publication are operational;
10. exact-target tests pass;
11. applicable security/supply-chain findings are closed;
12. required independent verification is completed;
13. any owner-only legal/financial gate is explicitly satisfied;
14. production controls are intentionally opened.

No random live Spotlight post is authorized merely to prove connectivity.

## Current decision

SNAPCHAT_SUBSYSTEM_BUILD = CONTINUE
PUBLIC_AUTONOMOUS_SPOTLIGHT = HOLD_EXTERNAL_ACCESS_MODEL
PAID_PUBLISHER = NO
UNRELATED_COMMERCIAL_REGISTRY = NO
ROUTINE_HUMAN_POSTING = NO
PUBLIC_SIDE_EFFECT_AUTHORITY = ZERO

# SNAPCHAT ASSURANCE REVIEW — CURRENT SCOPED RESULT — 2026-09-25

PROJECT: Trend Radar / TrendHunter
PLATFORM: Snapchat only
TARGET BRANCH: snapchat-production-review-20260925
REVIEW TYPE: PRODUCER-ASSISTED INTERNAL ASSURANCE
INDEPENDENT VERIFICATION: NOT VERIFIED
PUBLICATION SIDE EFFECT: NONE
GOVERNANCE: SNAPCHAT_AUTOMATION_GOVERNANCE_V2_20260925.md

## Important verification boundary

This review and the implementation changes were produced with the same AI-assisted development process.

Therefore this document MUST NOT be represented as:
- independent code review;
- independent penetration test;
- independent ASVS L3 verification;
- independent recovery verification;
- cold-engineer handover evidence.

Producer self-review is useful for discovery/remediation but is not independent assurance.

## Fresh Snapchat-only findings

### S1 — No current publication route satisfies all frozen owner constraints
Status: OPEN / EXTERNAL BLOCKER

Frozen constraints:
- zero routine human posting;
- no unrelated/misleading business identity;
- no new paid publisher merely to solve Snapchat.

Verified route analysis:
- Direct Snapchat Public Profile API requires the first-party Business Account/Organization + OAuth App + allowlisting path.
- Ayrshare provides autonomous Spotlight API publication but is a paid production dependency and is not selected.
- Creative Kit and web upload require the user to complete posting.

Result:
AUTONOMOUS_PUBLIC_SPOTLIGHT = HOLD_EXTERNAL_ACCESS_MODEL.

This is not remediable by pretending a provider exists. The correct behavior is fail-closed.

### S2 — Paid provider was incorrectly treated as primary
Status: CLOSED

Remediation:
- default provider changed from ayrshare to disabled;
- Ayrshare retained only as dormant optional adapter;
- no subscription/trial/payment is required for current runtime.

### S3 — Missing independent kill/read-only controls
Status: IMPLEMENTED / INDEPENDENT RETEST NOT VERIFIED

Remediation:
- SNAPCHAT_KILL_SWITCH defaults true;
- SNAPCHAT_EMERGENCY_READ_ONLY defaults true;
- SNAPCHAT_PUBLICATION_ENABLED defaults false;
- publication requires all controls intentionally opened.

### S4 — Unsafe boolean coercion
Status: CLOSED BY IMPLEMENTATION / INTERNAL CI PASS

Remediation:
- only native JSON true satisfies PASS gates;
- strings/numbers/null do not satisfy gates.

### S5 — Visual board identity was too weak
Status: CLOSED BY IMPLEMENTATION / INTERNAL CI PASS

Remediation:
- exact local template ID required;
- exact global template ID required;
- exact Arabic country labels required;
- global lane requires exact «ترند عالمي» label.

### S6 — Wholly AI-generated Spotlight risk
Status: CLOSED BY GATE / SOURCE-MATERIAL OPERATIONS STILL REQUIRED

Remediation:
- explicit human_origin_passed;
- explicit content_origin_type;
- growth lane allows human_original or human_source_ai_assisted;
- wholly_ai_generated is blocked.

### S7 — Duplicate/retry safety is not fully durable
Status: PARTIAL / PRODUCTION BLOCKER

Implemented:
- stable publication_id;
- deterministic provider idempotency key where supported;
- in-process serialization.

Missing:
- durable publication ledger;
- durable reconciliation before retry after unknown provider-side effect.

### S8 — Provider acceptance was not enough
Status: PARTIAL

Implemented:
- provider validation method where supported;
- provider post-status read where supported;
- unknown provider exception is reported as UNKNOWN_REQUIRES_RECONCILIATION.

Missing:
- durable status persistence;
- automated final-state reconciliation loop for the eventual selected production route.

### S9 — Auditability was incomplete
Status: PARTIAL

Implemented:
- structured UTC audit log;
- correlation IDs;
- secret-safe field allowlist;
- explicit events for validation, block, request, status and unknown side effect.

Missing:
- verified external alert delivery;
- verified retention policy;
- independent incident drill.

### S10 — Exact tests existed without execution evidence
Status: CLOSED FOR INTERNAL REGRESSION ONLY

Implemented:
- GitHub Actions Snapchat-only CI;
- compile check;
- pip check;
- exact unittest discovery;
- obvious committed-secret-pattern scan.

Evidence:
- workflow: Snapchat Publisher CI
- run id: 36145796277
- head SHA: 6a20da8efe11afd33d8cf1353b3f47b0695ad53b
- conclusion: success

Boundary:
This is producer-side CI evidence, not independent verification.

### S11 — Dependency versions were loose in publisher runtime
Status: CLOSED FOR DIRECT PUBLISHER DEPENDENCIES

Publisher runtime pins:
- Flask 3.1.3
- gunicorn 26.2.0
- requests 2.34.2

Still required:
- vulnerability audit evidence;
- transitive dependency inventory/SBOM;
- direct OAuth fallback dependency reconciliation.

### S12 — Recovery ownership insufficiently documented
Status: REMEDIATION IN PROGRESS

Required:
- owner recovery package;
- recovery runbook;
- service/config inventory;
- credential rotation/revocation map;
- golden candidate;
- cold-engineer handover test.

### S13 — Direct OAuth fallback exposes unnecessary dormant attack surface
Status: OPEN / NON-PRODUCTION FALLBACK

Current direct service remains publication-disabled and externally unconfigured.

Required:
- keep dormant;
- close publication and owner controls;
- avoid treating it as production until first-party external access requirements are legitimately met.

## Security / reliability acceptance matrix

| Requirement | Current status |
|---|---|
| Exact Snapchat isolation | PASS |
| Normal runtime human target = 0 | PASS as architecture target |
| Current public publication authority | PASS = ZERO |
| Fail-closed default | PASS / internal evidence |
| Kill switch implemented | PASS implementation / independent retest NOT VERIFIED |
| Emergency read-only implemented | PASS implementation / independent retest NOT VERIFIED |
| Local content/business gates | PASS internal CI |
| Saudi gate | PASS internal CI |
| Country/global visual binding | PASS internal CI |
| AI authenticity gate | PASS internal CI |
| Duplicate prevention | PARTIAL |
| Durable reconciliation | NOT VERIFIED |
| Monitoring/logging | PARTIAL |
| Alerting | NOT VERIFIED |
| Secrets committed to Snapchat code | no obvious pattern found by CI; independent audit NOT VERIFIED |
| Supply-chain vulnerability scan | NOT VERIFIED |
| Full SBOM | NOT VERIFIED |
| Penetration test | NOT VERIFIED |
| ASVS L3 independent verification | NOT VERIFIED |
| Independent code review | NOT VERIFIED |
| Independent architecture review | NOT VERIFIED |
| Disaster recovery test | NOT VERIFIED |
| Backup/restore test | N/A for current stateless publication service data, but configuration/recovery test NOT VERIFIED |
| Golden release | NOT YET — candidate only |
| Owner recovery package | REQUIRED |
| Recovery runbook | REQUIRED |
| Human takeover | documented target / practical test NOT VERIFIED |
| Cold engineer handover | NOT VERIFIED |
| Financial transaction logic | NOT APPLICABLE |
| Auto subscription/payment authority | NONE |

## Current decision

ENGINEERING_DIRECTION = VIABLE
SNAPCHAT_INTERNAL_AUTOMATION_SUBSYSTEM = CONTINUE
PUBLIC_SPOTLIGHT_AUTOMATION = HOLD
REASON = no currently accepted official route satisfies every frozen owner constraint
ROUTINE_MANUAL_POSTING = REJECTED
PAID_AYRSHARE = REJECTED
UNRELATED_COMMERCIAL_REGISTRY = REJECTED
PUBLIC_SIDE_EFFECT_AUTHORITY = ZERO

The subsystem must stay useful while blocked: it may validate, package, audit and prepare Snapchat-ready output, but must not silently degrade to manual routine posting or an unapproved paid/legal workaround.

## Additional route finding — browser automation is not an acceptable workaround

Status: CLOSED / REJECTED ROUTE

Snapchat's current Terms of Service prohibit using robots, scripts, software, or other automated or semi-automated means to access the Services except where expressly permitted.

Therefore:
- automating profile.snapchat.com with a browser bot is NOT adopted as the production publication path;
- the fact that the web uploader exists does not make scripted UI posting an approved automation API;
- the project must wait for a supported first-party/API route compatible with the frozen constraints rather than silently bypass the access model.

This finding strengthens the current HOLD_EXTERNAL_ACCESS_MODEL decision.

### S14 — Oversized request error semantics were wrong
Status: CLOSED BY REMEDIATION / INTERNAL RETEST PASS AT 77520f0a231648b57c79d6e2712657a7a7f227d6

Discovery:
- an adversarial API test sent a JSON request above the publisher's 64 KiB limit;
- Flask/Werkzeug correctly raised RequestEntityTooLarge;
- the broad application exception handler incorrectly converted that fail-closed 413 into a 502 provider-validation error.

Risk:
- incorrect incident classification;
- misleading monitoring/alerting;
- possible confusion between local rejection and external-provider failure.

Remediation:
- explicitly catch RequestEntityTooLarge in validation and publication routes;
- return HTTP 413 / request_too_large;
- record external_publication_side_effect=NONE;
- retain correlation/audit evidence.

Retest:
- exact CI run 36148628478 on commit 77520f0a231648b57c79d6e2712657a7a7f227d6 = SUCCESS.

This finding demonstrates why negative/adversarial tests are required even when the service is already fail-closed.


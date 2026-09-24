# TikTok App Review Demo Evidence — Final Shot/Evidence Map

Project: TrendHunter / Trend Radar
Branch: tiktok-production-review-20260922
Governance: ALI-PROGRAMMER-GOVERNANCE-GENERAL-1.5.0 + ALI_PRO

The required review evidence is split truthfully across two real creator-facing recordings. Do not re-record successful evidence and do not represent either clip as showing steps it does not contain.

## Demo 1 — Login Kit + Upload-as-Draft

Filename: TrendRadar_TikTok_Review_Demo_Login_Draft.mp4
Duration: 37.233333 seconds
SHA-256: 4467cda68dee4ba76641f0a096e883b10db286e34a61c5d111e99789ee645c3a

Verified purpose:
- final review domain / creator-facing flow
- real TikTok Login Kit authorization and return
- connected creator identity / user.info.basic use
- local original MP4 selection
- explicit creator action/consent
- separate Upload-as-Draft workflow / video.upload
- TikTok processing response

Matching Render evidence:
- GET /auth/tiktok/start -> 302
- OAuth callback authorized scopes user.info.basic, video.publish, video.upload
- GET /share -> 200
- Draft init -> HTTP 200 / code=ok
- Draft binary upload -> HTTP 201
- POST /api/upload-draft -> HTTP 201

This clip MUST NOT be described as demonstrating Direct Post.

## Demo 2 — Direct Post

Filename: TrendRadar_TikTok_Review_Demo_DirectPost_20260923.mp4
Duration: 21.5 seconds
Size: 513874 bytes
SHA-256: 7e7c495919396061891536ec013ab94a513a3044a63ec766b15ea8206a123180

Verified visible sequence:
1. SELF_ONLY is shown for the unaudited/private-safe operation.
2. User invokes the real Direct Post action to TikTok.
3. TikTok status reaches PUBLISH_COMPLETE.
4. Provider error.code is ok.

Matching live Render evidence for the same Direct Post operation:
- POST /api/post -> HTTP 201
- Direct Post init -> HTTP 200 / provider code=ok
- Binary upload -> HTTP 201
- Final status -> PUBLISH_COMPLETE
- Privacy -> SELF_ONLY

Editing provenance:
- truthful trim/compression of the raw Direct Post recording
- no simulated TikTok UI
- no fabricated provider result
- no synthetic replacement of the creator-facing interface

## Scope-to-evidence binding

| Product/scope | Evidence | Status |
|---|---|---|
| Login Kit | Demo 1 + OAuth/Render trace | PASS |
| user.info.basic | Demo 1 connected creator identity | PASS |
| video.upload | Demo 1 Upload-as-Draft + 200/201 Render trace | PASS |
| video.publish | Demo 2 Direct Post + 201/200/201/PUBLISH_COMPLETE trace | PASS |

## Submission safety constraints

- TIKTOK_AUDIT_APPROVED must remain false/unset until documented TikTok approval.
- No public posting is authorized.
- SELF_ONLY evidence is intentional while unaudited.
- Do not add mock/simulated provider responses.
- Do not repeat successful posting/upload tests merely to create redundant evidence.
- Final external TikTok App Review submission is a human/external portal gate if the portal requires owner interaction.

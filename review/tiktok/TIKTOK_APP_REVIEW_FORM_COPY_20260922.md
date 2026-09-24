# TikTok App Review — Form Copy

Use only for the isolated Trend Radar TikTok review configuration.

## App name
Trend Radar AR

## App description
Trend Radar is a creator-facing web service for discovering rising trends and preparing original short-form content. Authorized creators can connect their TikTok account, confirm the connected creator identity, select an original video from their device, and intentionally either publish it through Direct Post or upload it to TikTok as a draft. Posting/upload is always user-initiated and consent-gated.

## Website URL
https://share.trendradar.com.co/

## Login Kit
Trend Radar uses TikTok Login Kit for secure account authorization. OAuth state is validated and authorization-code exchange occurs server-side. Tokens remain server-side and are not exposed in browser responses.

## user.info.basic
Used to display the connected TikTok creator identity so the user can confirm the destination account. Demo 1 demonstrates this after OAuth return.

## Content Posting API — Direct Post / video.publish
The creator selects an original MP4, reviews creator-derived privacy and interaction options, chooses settings, and explicitly consents before sending. Trend Radar queries Creator Info, initializes Direct Post, uploads the binary, and polls TikTok publishing status. Demo 2 shows SELF_ONLY and ends with PUBLISH_COMPLETE / error.code=ok.

## Content Posting API — Upload to TikTok / video.upload
Trend Radar also offers a separate creator-facing Upload-as-Draft action. The user explicitly selects the file and initiates the draft upload; it is not a background upload. Demo 1 demonstrates this capability end-to-end.

## Requested scopes
- user.info.basic — connected creator identity.
- video.publish — user-initiated Direct Post.
- video.upload — user-initiated Upload-as-Draft workflow.

All three scopes correspond to implemented and demonstrated creator-facing functionality.

## Review evidence

### Demo 1 — Login + Draft
Filename: TrendRadar_TikTok_Review_Demo_Login_Draft.mp4
Duration: 37.233333 seconds
SHA-256: 4467cda68dee4ba76641f0a096e883b10db286e34a61c5d111e99789ee645c3a

Demonstrates Login Kit, OAuth consent/return, user.info.basic creator identity, original MP4 selection, explicit consent, Upload-as-Draft action, and TikTok processing response.

Matching Render evidence:
- GET /auth/tiktok/start -> 302
- OAuth callback authorized user.info.basic, video.publish, video.upload
- GET /share -> 200
- Draft init -> HTTP 200 / code=ok
- Binary upload -> HTTP 201
- POST /api/upload-draft -> HTTP 201

### Demo 2 — Direct Post
Filename: TrendRadar_TikTok_Review_Demo_DirectPost_20260923.mp4
Duration: 21.5 seconds
Size: 513874 bytes
SHA-256: 7e7c495919396061891536ec013ab94a513a3044a63ec766b15ea8206a123180

Visual verification: the real creator-facing evidence shows SELF_ONLY, the Direct Post action, then TikTok status=PUBLISH_COMPLETE and error.code=ok. It is a truthful trim/compression of the raw recording; no simulated UI or fabricated provider result was added.

Matching live Render transaction evidence:
- POST /api/post -> HTTP 201
- Direct Post init -> HTTP 200 / provider code=ok
- Binary upload -> HTTP 201
- Final TikTok status -> PUBLISH_COMPLETE
- Privacy -> SELF_ONLY

## Reviewer test flow
1. Open https://share.trendradar.com.co/.
2. Connect a TikTok account through Login Kit and approve the requested scopes.
3. Confirm the connected creator identity after return.
4. Select an original MP4.
5. For Direct Post, review creator-derived posting options, use SELF_ONLY while unaudited, give explicit consent, and click the Direct Post action once; observe status through PUBLISH_COMPLETE.
6. For Upload-to-TikTok draft, select the file, give explicit consent, and invoke the separate Upload-as-Draft action.

## Data handling / safety summary
- Client secret and access/refresh tokens are server-side only.
- OAuth state/CSRF validation is used.
- Publishing/upload is user-initiated and consent-gated.
- No watermark, logo, promotional link, forced caption, simulated TikTok UI, or fabricated provider result is added.
- Sandbox/unaudited Direct Post evidence uses SELF_ONLY.
- TIKTOK_AUDIT_APPROVED remains false/unset until documented TikTok approval.
- No public posting is authorized before that approval.

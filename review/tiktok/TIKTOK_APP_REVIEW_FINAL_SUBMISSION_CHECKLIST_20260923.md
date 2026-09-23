# TikTok App Review — Final Submission Checklist — 2026-09-23

Project: TrendHunter / Trend Radar
Repository: trendradarar-dotcom/trendradarar
Working review branch: tiktok-production-review-20260922
Governance: ALI-PROGRAMMER-GOVERNANCE-GENERAL-1.5.0 + ALI_PRO
Public TikTok publishing authority: NOT GRANTED
TIKTOK_AUDIT_APPROVED: false/unset

## Fresh official-guideline reconciliation

Official TikTok App Review guidance checked on 2026-09-23:
- App Review Guidelines: https://developers.tiktok.com/docs/en/app-review-guidelines
- Register Your App / URL verification: https://developers.tiktok.com/docs/en/getting-started-create-an-app
- Login Kit Web: https://developers.tiktok.com/docs/en/login-kit-web
- Content Posting API — Direct Post: https://developers.tiktok.com/docs/en/content-posting-api-reference-direct-post
- Content Posting API — Upload: https://developers.tiktok.com/docs/en/content-posting-api-get-started-upload-content

Relevant current requirements verified against the Trend Radar review package:
- First-time review demo uses the Sandbox integration.
- Demo shows the real web integration and user interactions.
- The website domain shown in the demo matches the supplied review website domain.
- Selected products/scopes are all demonstrated.
- TikTok allows up to 5 demo videos, with each video up to 50 MB.
- Content Posting API URL ownership / URL property verification is required.
- Web Login Kit uses a static HTTPS redirect URI registered in the app configuration.
- Direct Post requires creator info, explicit user metadata/consent, video.publish, upload, and status handling.
- Unaudited Direct Post remains restricted to private viewing.

## Final review domain and URLs

Website:
https://share.trendradar.com.co/

Login Kit redirect URI:
https://share.trendradar.com.co/auth/tiktok/callback

Privacy:
https://share.trendradar.com.co/privacy

Terms:
https://share.trendradar.com.co/terms

The review domain and relevant URL property were previously verified. Do not change these values before submission.

## Products and scopes intentionally included

Login Kit:
- user.info.basic

Content Posting API:
- video.publish — creator-facing Direct Post
- video.upload — creator-facing Upload-to-Inbox Draft

All three scopes are intentionally retained because both creator-facing posting paths are implemented and demonstrated.

## Demo videos

### Demo 1 — Login Kit + Upload-to-Inbox Draft
Filename:
TrendRadar_TikTok_Review_Demo_Login_Draft.mp4

Verified metadata:
- Duration: 37.233333 seconds
- Size: 913,533 bytes
- SHA-256: 4467cda68dee4ba76641f0a096e883b10db286e34a61c5d111e99789ee645c3a
- Under 50 MB: PASS

Demonstrates:
- real review domain
- Login Kit consent/redirect
- connected creator identity
- user.info.basic
- original MP4 selection
- explicit consent
- Upload-to-Inbox Draft
- video.upload

Bound Render evidence:
- 2026-09-22T14:15:14Z — draft init HTTP 200 / code=ok
- 2026-09-22T14:15:16Z — binary upload HTTP 201
- 2026-09-22T14:15:16Z — POST /api/upload-draft HTTP 201

### Demo 2 — Direct Post
Filename:
TrendRadar_TikTok_Review_Demo_DirectPost_20260923.mp4

Verified metadata:
- Duration: 21.500000 seconds
- Size: 513,874 bytes
- SHA-256: 7e7c495919396061891536ec013ab94a513a3044a63ec766b15ea8206a123180
- Under 50 MB: PASS

Demonstrates:
- real review domain
- SELF_ONLY
- explicit user-controlled Direct Post action
- final PUBLISH_COMPLETE
- provider error.code=ok
- video.publish

Bound Render evidence:
- 2026-09-22T16:05:06Z — POST_STAGE received /api/post
- Creator Info HTTP 200
- Direct Post init HTTP 200 / code=ok
- Binary upload HTTP 201
- POST /api/post HTTP 201
- status polling HTTP 200
- final user-visible provider result PUBLISH_COMPLETE / error.code=ok

## Form copy

Use the maintained reviewer text in:
review/tiktok/TIKTOK_APP_REVIEW_FORM_COPY_20260922.md

The current app description is creator-facing and does not describe the production use as owner-only/internal-only.

## Gate result

R1 — Domain alignment: CLOSED
R2 — Scope configuration: CLOSED / intentional three-scope configuration
R3 — TikTok-specific Privacy and Terms: CLOSED
R4 — Creator-facing intended use: CLOSED
R5 — Demo evidence: CLOSED

Login Kit: PASS
user.info.basic: PASS
video.upload: PASS
video.publish: PASS

APP REVIEW PACKAGE: READY FOR EXTERNAL SUBMIT

## Submission safety

Before documented TikTok approval:
- TIKTOK_AUDIT_APPROVED must remain false/unset.
- Public TikTok publishing is forbidden.
- Do not repeat successful Direct Post or draft tests merely for review preparation.
- Do not alter the two demo videos other than copying/uploading the exact verified bytes.
- Do not expose client secret, access token, refresh token, or environment-variable values.

The only remaining step is the authenticated external TikTok Developer Portal submission using this prepared package.

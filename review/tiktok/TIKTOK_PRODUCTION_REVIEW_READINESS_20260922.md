# TikTok Production Review Readiness — 2026-09-22

Project: TrendHunter / Trend Radar
Review branch: tiktok-production-review-20260922
Exact base: af65448ebbceeda377981e6a0d19a8aa8ca8a308
Governance: ALI-PROGRAMMER-GOVERNANCE-GENERAL-1.5.0 + ALI_PRO
Mutation scope: review preparation only; main/public site unchanged.

## Verified PASS already achieved

- TikTok Sandbox OAuth: PASS
- Scopes authorized during Sandbox test: user.info.basic, video.publish, video.upload
- Creator Info query: PASS
- Direct Post init: HTTP 200 / provider code ok
- Binary upload: HTTP 201
- Final TikTok status: PUBLISH_COMPLETE
- Test privacy: SELF_ONLY
- Public publication authority: NOT GRANTED
- Evidence file: TIKTOK_SANDBOX_DIRECT_POST_PASS_20260922.md

## Current Production Review Decision

STATUS = HOLD_BEFORE_SUBMIT

Do not click Submit for review yet.

## Blocking items before submission

### R1 — Domain alignment for the web integration
TikTok review requires the demo video to show the website where the integration will actually run, and for the domain shown in the demo to match the Website URL supplied for review.

Current state:
- Public brand site: https://trendradar.com.co/
- Working TikTok integration: https://trendradar-tiktok-oauth.onrender.com/

Preferred remediation:
- Use a dedicated custom domain such as https://share.trendradar.com.co/ for the TikTok integration.
- Point that subdomain to the isolated Render TikTok service.
- Use that exact site as the Web/Website URL for TikTok review.
- Register the exact static HTTPS redirect URI:
  https://share.trendradar.com.co/auth/tiktok/callback
- Verify the required TikTok URL property/properties for that subdomain.

Reason for preferred remediation:
It keeps TikTok review isolated from the currently reviewed YouTube/Google public site and avoids materially changing the public Trend Radar privacy/terms during YouTube API review.

### R2 — Scope minimization
The creator-facing review flow currently uses:
- user.info.basic
- video.publish

The review flow does not need video.upload unless a separate Upload-to-TikTok draft UX is also demonstrated.

Required Production configuration:
- Keep user.info.basic.
- Keep video.publish.
- Remove video.upload before submission unless a real draft-upload feature is intentionally included and demonstrated end-to-end.

### R3 — TikTok-specific Privacy Policy and Terms
Current public privacy/terms are Google/YouTube-specific.

Required for the TikTok review site:
- TikTok OAuth data categories.
- Access/refresh token handling.
- Creator identity/profile data usage.
- Publishing metadata and status usage.
- No sale of TikTok user data.
- Retention/deletion and revocation.
- User control and explicit publishing consent.
- Contact channel.
- Content/IP responsibility and platform compliance.

Preferred location:
- https://share.trendradar.com.co/privacy
- https://share.trendradar.com.co/terms

Do not alter the current public Google/YouTube privacy pages while the YouTube API application is under review unless separately approved.

### R4 — Public-facing intended use
TikTok review does not approve private/personal/internal-only upload utilities.

The Production review description must present Trend Radar as a creator-facing web service where authorized creators can connect their TikTok account and intentionally share their original videos using a user-controlled posting screen.

Do not describe the production use as owner-only, internal-only, test-only, or a tool solely for accounts managed by the developer.

### R5 — Demo video
At least one real end-to-end demo video is required.

The recording must show the current integration and user interaction:
1. Open the actual review website/domain.
2. Start TikTok connection/login.
3. TikTok consent screen.
4. Return to the creator-facing posting page.
5. Display connected creator nickname/account.
6. Select an original MP4 from the user's device.
7. Show video preview.
8. Show latest creator-derived privacy options.
9. Leave title editable.
10. Demonstrate comment/Duet/Stitch controls respecting creator settings.
11. Show explicit user consent.
12. Submit once.
13. Show processing/status result.
14. In Sandbox/unaudited mode, demonstrate SELF_ONLY.
15. End with PUBLISH_COMPLETE if practical.

The demo must not use a simulated UI or fabricated provider result.

## Existing UX compliance strengths

The current creator-facing flow already:
- Queries current Creator Info.
- Displays creator nickname/username.
- Fetches privacy options from TikTok.
- Does not preselect privacy.
- Leaves title/description editable.
- Does not enable interactions by default.
- Respects creator-disabled comment/Duet/Stitch controls.
- Requires explicit publishing consent.
- Checks video duration server-side against latest creator max.
- Polls publishing status.
- Keeps access/refresh tokens server-side and out of browser responses.
- Enforces SELF_ONLY and private-account guards before audit.
- Does not add watermarks, logos, promotional text, or forced captions to user media.

## Submission gate

SUBMIT_FOR_REVIEW = FORBIDDEN until R1-R5 are all closed with fresh evidence.

TIKTOK_AUDIT_APPROVED must remain false/unset until documented TikTok approval is received.


## Progress update — 2026-09-22 after creator-facing hardening

### Closed in runtime/code
- R2 runtime OAuth request scopes minimized to: user.info.basic,video.publish.
- TIKTOK_SCOPES on Render updated to: user.info.basic,video.publish.
- TikTok-specific Privacy page implemented at /privacy in the isolated TikTok service.
- TikTok-specific Terms page implemented at /terms in the isolated TikTok service.
- Creator-facing landing copy now states the service is for authorized creators and that posting is user-initiated.
- Browser upload readiness bug fixed so metadata preview failure no longer permanently blocks the send button.
- Render deploy for commit cc7b25841b3300117217a266f89559c8ba8e2ef7 reached LIVE.

### Still open — external configuration / evidence gates
- R1: Add and verify custom domain share.trendradar.com.co on the isolated Render TikTok service.
- R1: Create the required DNS record at the domain/DNS provider.
- R1: After custom domain is live, change TikTok Web redirect URI to:
  https://share.trendradar.com.co/auth/tiktok/callback
- R1: Verify the relevant TikTok URL property for the review domain if TikTok requests it.
- R2 portal-side: Remove video.upload from the TikTok Developer production configuration unless a draft-upload feature is intentionally added and demonstrated. Runtime already requests only user.info.basic,video.publish.
- R5: Record the real creator-facing end-to-end review demo on the final review domain.
- FINAL: Submit for review only after all above items have fresh evidence.

### Important
Do not change TIKTOK_REDIRECT_URI on Render before the matching redirect URI is accepted in TikTok Developer.
Do not set TIKTOK_AUDIT_APPROVED=true before documented TikTok approval.
Do not modify Trend Radar main public Google/YouTube privacy pages for this TikTok review path.


## Fresh reconciliation — 2026-09-22 17:15 Asia/Riyadh

This section supersedes stale earlier progress bullets where they conflict with fresh live evidence.

### R1 — CLOSED
- Review domain is live at https://share.trendradar.com.co/
- Render custom domain verified and certificate issued.
- TikTok URL property for share.trendradar.com.co verified.
- Production Login Kit redirect URI registered as https://share.trendradar.com.co/auth/tiktok/callback
- Sandbox runtime uses the previously registered onrender callback plus one-time handoff to the custom review domain; OAuth tokens are not placed in the handoff URL.

### R2 — CLOSED / INTENTIONAL THREE-SCOPE CONFIGURATION
Production review now intentionally includes:
- user.info.basic
- video.publish
- video.upload

Both creator-facing capabilities exist:
- Direct Post via /api/post
- Upload-to-Inbox draft via /api/upload-draft

Therefore the earlier recommendation to remove video.upload is superseded.

### R3 — CLOSED
TikTok-specific Privacy and Terms are live on the isolated review domain:
- https://share.trendradar.com.co/privacy
- https://share.trendradar.com.co/terms

### R4 — CLOSED
The review site is creator-facing and requires explicit user action/consent. No silent publishing is enabled.

### R5 — PARTIALLY CLOSED; DIRECT-POST DEMO STILL REQUIRED
Raw creator recording captured on 2026-09-22:
- SHA-256: fedc025bcc203fb3294b046bae1d376856393ffc6e6872550bcdd53103ce8034
- Duration: 102.435733 seconds
- Size: 169,318,219 bytes

Prepared review clip:
- Filename: TrendRadar_TikTok_Review_Demo_Login_Draft.mp4
- SHA-256: 4467cda68dee4ba76641f0a096e883b10db286e34a61c5d111e99789ee645c3a
- Duration: 37.233333 seconds
- Size: 913,533 bytes
- Video: H.264, 1600x856, 30fps
- Audio: AAC
- Editing scope: only removal of unrelated ChatGPT/tab-detour segments and compression; no simulated TikTok UI or fabricated provider result.

The prepared clip visibly demonstrates:
- share.trendradar.com.co
- Trend Radar Sandbox OAuth consent
- return to creator-facing /share UI
- connected creator identity
- local original MP4 selected
- explicit consent controls
- Upload-as-Draft user action
- TikTok processing/status response

Fresh Render evidence for the same recording session:
- 2026-09-22T14:14:17Z: GET /auth/tiktok/start -> 302
- 2026-09-22T14:14:35Z: callback authorized scopes user.info.basic,video.publish,video.upload
- 2026-09-22T14:14:36Z: GET /share -> 200
- 2026-09-22T14:15:14Z: DRAFT_STAGE init_http=200 code=ok
- 2026-09-22T14:15:16Z: DRAFT_STAGE upload_http=201
- 2026-09-22T14:15:16Z: POST /api/upload-draft -> 201

No /api/post request is present in the same recording-session logs. Therefore this clip MUST NOT be represented as demonstrating Direct Post.

### Current submission gate
- Login Kit demo evidence: PASS
- user.info.basic visible/use evidence: PASS
- video.upload creator-facing demo evidence: PASS
- video.publish creator-facing demo evidence: OPEN — short Direct Post recording still required
- Submit for review: HOLD
- TIKTOK_AUDIT_APPROVED: false/unset

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

Closed since initial draft:
- R2 scope minimization = CLOSED. Runtime OAuth scopes are now user.info.basic,video.publish only.
- TikTok-specific privacy and terms pages are implemented on the isolated TikTok service. Custom-domain publication of those pages remains pending under R1/R3.

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

### R2 — Scope minimization — CLOSED

Current runtime OAuth scopes:
- user.info.basic
- video.publish

video.upload has been removed from the Render runtime scope configuration and from the default application scope set.

### R3 — TikTok-specific Privacy Policy and Terms — PARTIALLY CLOSED
Current public privacy/terms are Google/YouTube-specific.

Implemented on the isolated TikTok service at /privacy and /terms. Still required before submission: publish these same pages under the final review custom domain.

Coverage includes:
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

# TikTok Production Review Compliance Plan

Status: PRE-SUBMISSION HOLD

Fresh TikTok review findings (2026-09-22):
- Sandbox OAuth succeeded for scopes: user.info.basic, video.upload, video.publish.
- Creator Info query succeeded.
- Private/draft video upload initialization and binary upload succeeded.
- No public publication authority has been granted or exercised.
- TikTok review guidance requires a real, up-to-date end-to-end demo showing the actual website/app integration.
- TikTok content sharing guidance rejects API clients limited to internal/private use or merely uploading to accounts managed by the owner/team.

Required remediation before Production submission:
1. Preserve the current successful Sandbox evidence.
2. Build a real creator-facing TikTok sharing surface for external users, not an owner-only upload utility.
3. Display current creator nickname from creator_info before posting.
4. Display privacy options returned by creator_info and require explicit user selection/consent.
5. Validate video duration against max_video_post_duration_sec.
6. Support original-content upload without branding/watermarks added by the integration.
7. Keep scopes minimal: user.info.basic, video.upload, video.publish.
8. Store client secret server-side only; tokens must not be exposed to the browser or logs.
9. Provide a stable production-grade session/token store before review.
10. Record a demo video showing the actual end-to-end user flow on the same website/domain submitted to TikTok.
11. Do not submit Production review until the above is implemented and freshly verified.

Isolation:
- This branch is isolated from main.
- Do not modify YouTube/OAuth review artifacts.
- Do not modify the public Trend Radar site until an exact-target reconciliation explicitly authorizes it.

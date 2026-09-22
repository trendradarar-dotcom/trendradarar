# TikTok App Review Demo Video — Recording Shot List

Purpose: record one truthful, continuous demonstration of the actual Sandbox integration for TikTok App Review.

## Before recording
- Use the final review domain, not the temporary onrender.com hostname, if the Production Website URL will be a Trend Radar custom domain.
- Keep TikTok test account private while the client is unaudited.
- Use a valid original MP4 meeting TikTok video requirements.
- Ensure no secrets, client secret, access token, refresh token, environment variables, browser password manager contents, or unrelated private tabs are visible.
- Do not use the server-side diagnostic private-test page as the primary review demo; show the creator-facing integration users will actually use.

## Recording sequence
1. Show the browser address bar with the exact Trend Radar review website domain.
2. Show the page title/brand and visible Privacy Policy and Terms links.
3. Click the TikTok connection button.
4. Show the official TikTok authorization screen.
5. Show the requested permissions and approve them.
6. Show the redirect back to Trend Radar.
7. Show the connected creator nickname/username.
8. Show the creator-reported maximum video duration and posting controls.
9. Choose an original MP4 from the device.
10. Show the in-page video preview.
11. Show that title/caption is editable and is not forced.
12. Open privacy options returned for the creator and choose SELF_ONLY for Sandbox.
13. Show comments, Duet and Stitch controls; do not enable options unavailable to the creator.
14. Leave commercial content unchecked for the current non-commercial review test.
15. Check the explicit consent statement only after reviewing the settings.
16. Click Send to TikTok once.
17. Show that the page reports upload accepted / processing.
18. Show final provider status PUBLISH_COMPLETE if available in the same recording; otherwise show the same publish transaction after a normal status refresh.
19. End without changing content visibility to public.

## What this video proves
- Real Login Kit flow.
- user.info.basic use.
- Real Creator Info use.
- Creator-facing posting UX.
- video.publish Direct Post.
- Explicit user control and consent.
- Sandbox SELF_ONLY enforcement.
- Real provider status handling.

## Do not include
- Fake/mock provider responses.
- Multiple unnecessary posting attempts.
- Owner-only/private-tool framing.
- A different domain than the Website URL supplied to TikTok review.
- video.upload/draft functionality unless that scope is intentionally kept and fully demonstrated.

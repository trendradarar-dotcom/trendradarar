# TikTok App Review — Form Copy

Use only after the Production configuration matches the statements below.

## App name
Trend Radar AR

## App description
Trend Radar is a creator-facing web service for discovering rising trends and preparing original short-form content. Authorized creators can connect their TikTok account, review the target account and current posting options, select an original video from their device, choose privacy and interaction settings, give explicit consent, and share the video to their TikTok profile through TikTok's Content Posting API.

## Product: Login Kit
Trend Radar uses TikTok Login Kit for secure account authorization. The user is redirected to TikTok to sign in and grant requested permissions. After authorization, Trend Radar validates the OAuth state, exchanges the authorization code server-side, and returns the user to the posting interface. Tokens are handled server-side and are not exposed in browser responses.

## Scope: user.info.basic
Trend Radar uses user.info.basic to identify the connected TikTok creator in the posting interface. The creator's current nickname and account identity are shown so the user can confirm which TikTok account will receive the content.

## Product: Content Posting API — Direct Post
Trend Radar uses the Direct Post flow to let creators intentionally share their own original videos to their TikTok account. Before sending a video, Trend Radar queries TikTok Creator Info, displays the current creator identity and allowed privacy options, checks creator restrictions and video duration, lets the user edit the caption, and requires explicit consent. No video is sent until the user chooses the settings and confirms the upload. Trend Radar then initializes Direct Post, uploads the selected MP4, and checks the publishing status so the user can see the result.

## Scope: video.publish
video.publish is required only for the user-initiated Direct Post operation described above. Trend Radar does not silently publish in the background. The user selects the video and posting settings and gives explicit consent before the upload begins.

## Scope to remove before review unless separately implemented
video.upload

Reason:
The Production review flow currently demonstrates Direct Post. If the app is not offering a separate creator-facing Upload-to-TikTok draft workflow, video.upload should be removed so the requested scopes match the demonstrated functionality.

## Review notes
The integration has been tested in TikTok Sandbox. The Sandbox Direct Post test completed successfully with SELF_ONLY visibility and final TikTok status PUBLISH_COMPLETE. The unaudited integration remains restricted to private testing. Public posting will not be enabled until TikTok approval/audit is documented.

## Reviewer test flow
1. Open the supplied Trend Radar review website.
2. Click the TikTok account connection button.
3. Authorize the requested TikTok permissions.
4. Confirm the creator nickname/account shown after redirect.
5. Choose an MP4 video from the device.
6. Preview the selected video.
7. Choose an allowed privacy option. In Sandbox/unaudited testing use SELF_ONLY.
8. Optionally enter/edit the caption.
9. Review comment/Duet/Stitch settings.
10. Confirm the explicit consent checkbox.
11. Click the single Share/Send to TikTok button.
12. Observe the status update until TikTok returns the final publishing result.

## Data handling summary for reviewers
- Client secret is server-side only.
- User access/refresh tokens are server-side only.
- Browser responses do not expose token plaintext.
- OAuth state/CSRF validation is used.
- Posting is user-initiated and consent-gated.
- Trend Radar does not add a watermark, logo, promotional link, or forced promotional text to the uploaded video.

# Trend Radar TikTok OAuth service

Isolated OAuth callback service for the Trend Radar / TrendHunter TikTok activation path.

- Branch: tiktok-oauth-service
- No public publication authority.
- Client secret and refresh token are server-side only.
- OAuth state is random, one-time, and expires after 10 minutes.
- Callback query strings are never logged.
- Token storage is intentionally ephemeral for admission/demo flow.
- Production persistence must be integrated with the governed TrendHunter secret store before production admission.

Required environment variables:
- TIKTOK_CLIENT_KEY
- TIKTOK_CLIENT_SECRET
- TIKTOK_REDIRECT_URI
- Optional: TIKTOK_SCOPES (default: user.info.basic,video.upload,video.publish)

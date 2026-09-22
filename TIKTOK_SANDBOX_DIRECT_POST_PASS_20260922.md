# TikTok Sandbox Direct Post — PASS Evidence

Date: 2026-09-22
Project: TrendHunter / Trend Radar
Branch: tiktok-oauth-service
Environment: Render service trendradar-tiktok-oauth
Mode: Sandbox / unaudited / SELF_ONLY only

## Result

FINAL STATUS: PASS

The server-side private diagnostic flow completed successfully against TikTok Content Posting API.

Observed sequence:
- OAuth authorization: PASS
- Creator Info query: PASS
- Direct Post init: HTTP 200, provider code=ok
- Binary upload: HTTP 201
- TikTok status: PUBLISH_COMPLETE
- TikTok error.code: ok
- Privacy constraint: SELF_ONLY
- Public publication authority: NOT GRANTED

## Media used

Verified diagnostic media:
- Container: MP4
- Codec: H.264
- Resolution: 720x1280
- Frame rate: 30 fps CFR
- Duration: 3 seconds
- Pixel format: yuv420p

Previous diagnostic media failed with frame_rate_check_failed and was replaced before this PASS.

## Governing limitations

This PASS proves the private Sandbox Direct Post path only.
It does NOT authorize public TikTok publication.
Do not enable TIKTOK_AUDIT_APPROVED until documented TikTok approval is received.
Do not treat this as production app review approval.

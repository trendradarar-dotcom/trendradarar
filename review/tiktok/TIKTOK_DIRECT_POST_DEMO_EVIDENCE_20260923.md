# TikTok Direct Post Demo Evidence — 2026-09-23

Project: TrendHunter / Trend Radar  
Review branch: tiktok-production-review-20260922  
Governance: ALI-PROGRAMMER-GOVERNANCE-GENERAL-1.5.0 + ALI_PRO  
Public TikTok publishing authority: NOT GRANTED  
TIKTOK_AUDIT_APPROVED: false/unset

## Source recording

- Filename: Share to TikTok - Google Chrome 1448-04-11 19-01-02.mp4
- Conversation file id: file_0000000073008211a095c290bc3b84f2
- Size: 391,816,595 bytes
- Duration: 378.511800 seconds
- Source SHA-256: 416f15efe0f5bfc01b7be4fad30d21a04b1d751d3edd18f44221e8480a435a92

## Review-ready Direct Post clip

- Filename: TrendRadar_TikTok_Review_Demo_DirectPost_20260923.mp4
- Source trim window: 243.0s through 264.5s
- Duration: 21.500000 seconds
- Size: 513,874 bytes
- Video: H.264, 1920x1026, 30 fps, yuv420p
- Audio: AAC
- SHA-256: 7e7c495919396061891536ec013ab94a513a3044a63ec766b15ea8206a123180
- Portal size gate: PASS (< 50 MB)

## Editing integrity

Only the truthful Direct Post section was trimmed from the owner-provided raw screen recording and transcoded for size/compatibility.
No simulated TikTok UI, fabricated provider result, synthetic overlay, fake status, or altered provider response was added.

## Visual verification

The review-ready clip visibly shows the real creator-facing review domain and the actual Direct Post flow evidence, including:
- share.trendradar.com.co
- privacy option SELF_ONLY
- explicit user-controlled Direct Post action
- TikTok status payload with status = PUBLISH_COMPLETE
- provider error.code = ok

## Bound live Render evidence

The clip is bound to the same already-recorded live Direct Post execution evidence:
- POST_STAGE received /api/post
- POST_STAGE reading_body length=6398
- Creator Info query: ok=True, HTTP 200
- Direct Post init: HTTP 200, provider code=ok
- Binary upload: HTTP 201
- POST /api/post with privacy=SELF_ONLY and explicit consent: HTTP 201
- Status polling endpoint: HTTP 200
- Final user-visible provider status: PUBLISH_COMPLETE
- Final provider error.code: ok

## Companion review demo

The separate Login + Upload-to-Inbox Draft demo remains:
- Filename: TrendRadar_TikTok_Review_Demo_Login_Draft.mp4
- Duration: 37.233333 seconds
- Size: 913,533 bytes
- SHA-256: 4467cda68dee4ba76641f0a096e883b10db286e34a61c5d111e99789ee645c3a

Together the two demos truthfully cover:
- Login Kit
- user.info.basic
- video.upload
- video.publish

## Gate result

- Demo 1 (Login + Draft): READY
- Demo 2 (Direct Post): READY
- Direct Post size reduction: PASS
- Direct Post visual verification: PASS
- R5 demo evidence: CLOSED
- External TikTok App Review submission: READY FOR OWNER/PORTAL SUBMIT
- Public posting before TikTok approval: FORBIDDEN

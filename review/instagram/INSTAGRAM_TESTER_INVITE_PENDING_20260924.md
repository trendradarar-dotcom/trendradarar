# Instagram Tester Invitation — Pending Acceptance — 2026-09-24

PROJECT = TrendHunter / Trend Radar
BRANCH = instagram-production-review-20260924
META_APP_NAME = Trend Radar
META_APP_ID = 1584158563162593
INSTAGRAM_ACCOUNT = @trendradarar
INSTAGRAM_ACCOUNT_TYPE = BUSINESS
INSTAGRAM_TESTER_ROLE = INVITED
INSTAGRAM_TESTER_STATUS = PENDING_ACCEPTANCE

Provider/UI evidence:
- Meta App Roles > Instagram Testers shows `trendradarar`.
- Status displayed by Meta: Pending.
- Meta UI indicates Instagram users manage invitations from Apps and Websites in their Instagram profile.

Runtime verification:
- Render service: trendradar-instagram-oauth
- Service ID: srv-daqed80u01pc73fs6rgg
- URL: https://trendradar-instagram-oauth.onrender.com
- Latest known deploy: a58e05d85c7e550dd829797631ebf8a165c113b5
- Deploy reached LIVE.
- Gunicorn started successfully and GET / returned HTTP 200.

GOVERNING NEXT GATE:
Owner must accept the Instagram Tester invitation while authenticated as @trendradarar.
Do not repeat app creation, Business conversion, tester invitation, or prior M26 work.

PUBLIC_INSTAGRAM_PUBLISHING = HOLD

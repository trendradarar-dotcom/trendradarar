# Instagram Standard Access Decision — 2026-09-28

Project: TrendHunter / Trend Radar
Platform scope: Instagram only
Target account: @trendradarar
Account type: BUSINESS
Ownership model: single owner-managed Trend Radar account only
Third-party account service: NOT AUTHORIZED
Public publishing gate: HOLD / false

## Current Meta provider rule

Official Meta documentation, updated Jun 30, 2026, states in the Instagram App Review development-scenarios table:

- App only for a business the developer owns or manages
- Login type: No login or Instagram Login
- Access level: Standard Access
- App Review: Not required

Official source:
https://developers.facebook.com/documentation/instagram-platform/app-review

Meta's current Content Publishing guide also lists Instagram API with Instagram Login as supporting both:
- Advanced Access
- Standard Access

For Instagram Login content publishing, the guide lists:
- instagram_business_basic
- instagram_business_content_publish
- graph.instagram.com
- Instagram User access token

Official source:
https://developers.facebook.com/documentation/instagram-platform/content-publishing

## Project reconciliation

Trend Radar currently satisfies the owner-only Standard Access scenario:

- exact authorized account: @trendradarar
- account type: BUSINESS
- provider OAuth identity verified
- exact professional user ID verified
- granted scopes verified:
  - instagram_business_basic
  - instagram_business_content_publish
- encrypted durable token persistence = PASS
- restart reload = PASS
- long-lived token refresh = PASS
- no third-party Instagram accounts are served
- no customer-account onboarding exists
- no Tech Provider / multi-business scope is authorized

Therefore:

**META_APP_REVIEW_REQUIRED_FOR_CURRENT_SCOPE = NO**

**ACCESS_MODEL = STANDARD_ACCESS / OWNER-MANAGED ACCOUNT**

## Important scope boundary

If Trend Radar later serves Instagram accounts belonging to other businesses, customers, creators, or third parties, this decision no longer applies.

That expansion would require a fresh provider reconciliation and may require:
- Advanced Access
- App Review
- new review evidence / screencasts
- potentially additional business verification requirements then applicable

No such expansion is authorized by this decision.

## Permission naming reconciliation

Meta's App Review page currently displays the Advanced Access permission name as:
`instagram_business_content_publishing`

Meta's Content Publishing guide and the live provider OAuth/runtime use:
`instagram_business_content_publish`

Trend Radar keeps the live runtime scope that was actually granted and verified:
`instagram_business_content_publish`

Do not rename a working live scope solely from the App Review table wording without a fresh provider requirement.

## Publication authority

This decision removes the unnecessary App Review gate only.

It does **not** authorize public posting.

Current runtime remains:
`INSTAGRAM_PUBLIC_PUBLISH_AUTHORIZED=false`

A separate governed owner authorization is still required before enabling public Instagram publication.

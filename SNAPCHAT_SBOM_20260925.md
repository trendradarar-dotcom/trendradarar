# SNAPCHAT SOFTWARE BILL OF MATERIALS — 2026-09-25

SCOPE: Snapchat branch components only
STATUS: DIRECT-DEPENDENCY SBOM / TRANSITIVE INVENTORY REQUIRES AUTOMATED EXPORT

## Publisher runtime

Source:
- snapchat_publisher_service/requirements.txt

Direct dependencies:
- Flask == 3.1.3
- gunicorn == 26.2.0
- requests == 2.34.2

Python standard-library modules include:
- dataclasses
- datetime
- hashlib
- hmac
- json
- logging
- os
- re
- threading
- typing
- urllib.parse
- uuid

## Direct first-party OAuth fallback

Source:
- snapchat_oauth_service/requirements.txt

Current role:
- dormant fallback, not production publication route

Direct dependency families currently declared:
- Flask
- requests
- cryptography
- gunicorn

The fallback dependency file must be reconciled and retested before the direct route can be promoted.

## External services

- Snapchat Public Profile / Spotlight
- Render
- GitHub Actions
- optional dormant Ayrshare adapter

## Integrity / supply-chain state

Implemented:
- exact pins for active publisher direct dependencies;
- pip dependency consistency check in CI;
- compile + tests in CI;
- basic committed-secret-pattern scan.

Required before production acceptance:
- automated vulnerability audit result;
- transitive package inventory export;
- license review where applicable;
- independent supply-chain review for production.

This document does not claim that direct version pinning alone proves supply-chain security.
